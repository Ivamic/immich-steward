// SPDX-License-Identifier: AGPL-3.0-or-later
// Locations the user saved, on their way to Immich.
//
// A save waits a few seconds before it is sent: until then it can be cancelled without touching
// Immich at all. After that it can still be undone through the history. Saves outlive the photo card (the card moves on to the
// next photo right away) and are shown as notices by SaveNotices.svelte.
import { setLocation, undoLocation, type AssetDetail } from '#lib/api.js';
import type { LatLon } from '#lib/coords.js';
import { errorMessage } from '#lib/errors.js';

export const GRACE_MS = 5000;
// How long a notice about a finished save stays on screen.
export const NOTICE_MS = 8000;

export type SavePhase = 'pending' | 'saving' | 'saved' | 'undone' | 'failed';

export interface Save {
	key: number;
	assetId: string;
	fileName: string;
	point: LatLon;
	phase: SavePhase;
	/** When a pending save is sent (ms since epoch). */
	sendAt: number;
	/** After saving: the core reports the write can be undone. */
	canUndo: boolean;
	error: string | null;
}

interface Api {
	save: (id: string, point: LatLon, keepalive: boolean) => Promise<AssetDetail>;
	undo: (id: string) => Promise<AssetDetail>;
}

const realApi: Api = {
	save: (id, point, keepalive) => setLocation(id, point, null, keepalive),
	undo: (id) => undoLocation(id)
};

export class Saves {
	items = $state<Save[]>([]);
	/** The asset whose location changed in Immich last, with a counter so repeats are seen. */
	changed = $state<{ assetId: string; count: number } | null>(null);

	// Not reactive on purpose: timers never drive the UI.
	// eslint-disable-next-line svelte/prefer-svelte-reactivity
	#timers = new Map<number, ReturnType<typeof setTimeout>>();
	#nextKey = 1;
	#count = 0;

	constructor(private readonly api: Api = realApi) {}

	/** Queues a save; a pending save of the same photo is replaced. */
	schedule(assetId: string, fileName: string, point: LatLon) {
		for (const item of this.items) {
			if (item.assetId === assetId && item.phase === 'pending') this.cancel(item.key);
		}
		const save: Save = {
			key: this.#nextKey++,
			assetId,
			fileName,
			point,
			phase: 'pending',
			sendAt: Date.now() + GRACE_MS,
			canUndo: false,
			error: null
		};
		this.items.push(save);
		this.#later(save.key, GRACE_MS, () => this.send(save.key));
	}

	pendingFor(assetId: string): Save | undefined {
		return this.items.find((item) => item.assetId === assetId && item.phase === 'pending');
	}

	cancel(key: number) {
		if (this.#get(key)?.phase !== 'pending') return;
		this.dismiss(key);
	}

	dismiss(key: number) {
		this.#clearTimer(key);
		this.items = this.items.filter((item) => item.key !== key);
	}

	/** Sends a pending (or failed) save now. */
	async send(key: number, keepalive = false) {
		const save = this.#get(key);
		if (!save || (save.phase !== 'pending' && save.phase !== 'failed')) return;
		this.#clearTimer(key);
		save.phase = 'saving';
		save.error = null;
		try {
			const detail = await this.api.save(save.assetId, save.point, keepalive);
			save.phase = 'saved';
			save.canUndo = detail.can_undo;
			this.#markChanged(save.assetId);
			this.#later(key, NOTICE_MS, () => this.dismiss(key));
		} catch (error) {
			save.phase = 'failed';
			save.error = errorMessage(error);
		}
	}

	async undo(key: number) {
		const save = this.#get(key);
		if (!save || save.phase !== 'saved' || !save.canUndo) return;
		this.#clearTimer(key);
		try {
			await this.api.undo(save.assetId);
			save.phase = 'undone';
			this.#markChanged(save.assetId);
		} catch (error) {
			save.error = errorMessage(error);
		}
		this.#later(key, NOTICE_MS, () => this.dismiss(key));
	}

	/** Sends every pending save right away; called when the page is being closed. */
	flush() {
		for (const item of this.items) {
			if (item.phase === 'pending') void this.send(item.key, true);
		}
	}

	#get(key: number): Save | undefined {
		return this.items.find((item) => item.key === key);
	}

	#markChanged(assetId: string) {
		this.changed = { assetId, count: ++this.#count };
	}

	#later(key: number, ms: number, action: () => void) {
		this.#clearTimer(key);
		this.#timers.set(key, setTimeout(action, ms));
	}

	#clearTimer(key: number) {
		clearTimeout(this.#timers.get(key));
		this.#timers.delete(key);
	}
}

export const saves = new Saves();
