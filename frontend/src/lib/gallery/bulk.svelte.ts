// SPDX-License-Identifier: AGPL-3.0-or-later
// Notices about actions on several photos chosen in the gallery (D-149): turning them in Immich
// (a background job of the core, followed here until it is over) and marking them. Shown with the
// save notices (SaveNotices.svelte). Locations for several photos are saves (saves.svelte.ts).
import { ApiError, getSelectionJob, type Job } from '#lib/api.js';
import { errorMessage } from '#lib/errors.js';
import { m } from '#lib/paraglide/messages.js';
import { saves } from '#lib/saves.svelte.js';
import { SvelteSet } from 'svelte/reactivity';
import { galleryChanged } from './selection.svelte.js';

// The first look comes soon, so that the progress shows at once.
const FIRST_POLL_MS = 500;
const POLL_MS = 1500;
// How long a notice about a finished action stays on screen.
const NOTICE_MS = 10_000;
// What turning needs from the Immich API key, for the message when it is missing.
const EDIT_PERMISSIONS = ['asset.edit.get', 'asset.edit.create', 'asset.edit.delete'];

export interface BulkNotice {
	key: number;
	phase: 'running' | 'done' | 'failed';
	text: string;
	/** Further lines: videos left as they are, photos that failed. */
	details: string[];
	/** While running: how far it got. */
	progress: { done: number; total: number } | null;
}

interface Progress {
	total?: number;
	done?: number;
	videos?: number;
	failed?: number;
}

export class BulkNotices {
	items = $state<BulkNotice[]>([]);
	/** Photos being turned now: marked in the gallery. */
	busy = new SvelteSet<string>();
	#nextKey = 1;

	/** Follows a rotation job until it is over; `ids` are the photos it turns (not the videos). */
	followRotation(job: Job, ids: string[], total: number) {
		const notice = this.#add('running', m.rotate_running({ done: 0, total }));
		notice.progress = { done: 0, total };
		for (const id of ids) this.busy.add(id);
		const finish = (phase: BulkNotice['phase'], text: string, details: string[]) => {
			for (const id of ids) this.busy.delete(id);
			this.#finish(notice.key, phase, text, details);
		};
		const poll = async () => {
			let current: Job;
			try {
				current = await getSelectionJob(job.id);
			} catch (error) {
				finish('failed', m.rotate_failed({ error: errorMessage(error) }), []);
				return;
			}
			const progress = current.progress as Progress;
			if (current.status === 'done') {
				galleryChanged();
				finish('done', m.rotate_done({ count: progress.done ?? 0 }), [
					...(progress.videos ? [m.rotate_videos({ count: progress.videos })] : []),
					...(progress.failed ? [m.rotate_failed_some({ count: progress.failed })] : [])
				]);
				return;
			}
			if (current.status === 'failed') {
				galleryChanged();
				const error = new ApiError(0, current.error ?? '', { permissions: EDIT_PERMISSIONS });
				finish('failed', m.rotate_failed({ error: errorMessage(error) }), []);
				return;
			}
			const item = this.#get(notice.key);
			if (item && progress.total !== undefined) {
				const done = progress.done ?? 0;
				item.text = m.rotate_running({ done, total: progress.total });
				item.progress = { done, total: progress.total };
			}
			setTimeout(poll, POLL_MS);
		};
		setTimeout(poll, FIRST_POLL_MS);
	}

	/** A finished action with nothing to follow. */
	done(text: string) {
		const notice = this.#add('done', text);
		setTimeout(() => this.dismiss(notice.key), NOTICE_MS);
	}

	dismiss(key: number) {
		this.items = this.items.filter((item) => item.key !== key);
	}

	#add(phase: BulkNotice['phase'], text: string): BulkNotice {
		this.items.push({ key: this.#nextKey++, phase, text, details: [], progress: null });
		// The proxy in the list, so that later changes show.
		return this.items[this.items.length - 1];
	}

	#get(key: number): BulkNotice | undefined {
		return this.items.find((item) => item.key === key);
	}

	#finish(key: number, phase: BulkNotice['phase'], text: string, details: string[]) {
		const item = this.#get(key);
		if (!item) return;
		Object.assign(item, { phase, text, details, progress: null });
		setTimeout(() => this.dismiss(key), NOTICE_MS);
	}
}

export const bulkNotices = new BulkNotices();

/** What is being done with a photo of the gallery now: its location waits to be saved with
 * others (and can still be cancelled), or it is being saved or turned. */
export function photoWork(id: string): 'waiting' | 'working' | null {
	if (bulkNotices.busy.has(id)) return 'working';
	const save = saves.items.find(
		(s) => s.batch?.ids.includes(id) && (s.phase === 'pending' || s.phase === 'saving')
	);
	if (!save) return null;
	return save.phase === 'pending' ? 'waiting' : 'working';
}
