// SPDX-License-Identifier: AGPL-3.0-or-later
// Notices about actions on several photos chosen in the gallery (D-149): turning them in Immich
// (a background job of the core, followed here until it is over), marking them, putting them into
// an album (with an undo, D-233). Shown with the
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
// One that can be undone stays longer, to leave time for the undo.
const UNDO_NOTICE_MS = 20_000;
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
	/** Reverts the action and tells what it did; shown as "Undo" while the notice is done. */
	undo?: () => Promise<string>;
}

interface Progress {
	total?: number;
	done?: number;
	videos?: number;
	failed?: number;
	/** Chosen, but in another rotate job already: left out, so that turns do not add up. */
	busy?: number;
	/** From the list of turned photos, which no longer offered them. */
	skipped?: number;
}

export class BulkNotices {
	items = $state<BulkNotice[]>([]);
	/** Photos being turned now: marked in the gallery. */
	busy = new SvelteSet<string>();
	#nextKey = 1;

	/** Follows the rotation jobs (one per batch of photos) until they are all over, as one
	 * notice; `ids` are the photos they turn (not the videos). */
	followRotation(jobs: Job[], ids: string[], total: number) {
		const notice = this.#add('running', m.rotate_running({ done: 0, total }));
		notice.progress = { done: 0, total };
		for (const id of ids) this.busy.add(id);
		const finish = (phase: BulkNotice['phase'], text: string, details: string[]) => {
			for (const id of ids) this.busy.delete(id);
			this.#finish(notice.key, phase, text, details);
		};
		const poll = async () => {
			let current: Job[];
			try {
				current = await Promise.all(jobs.map((job) => getSelectionJob(job.id)));
			} catch (error) {
				finish('failed', m.rotate_failed({ error: errorMessage(error) }), []);
				return;
			}
			const failed = current.find((job) => job.status === 'failed');
			if (failed) {
				galleryChanged();
				const error = new ApiError(0, failed.error ?? '', { permissions: EDIT_PERMISSIONS });
				finish('failed', m.rotate_failed({ error: errorMessage(error) }), []);
				return;
			}
			const progress = current.map((job) => job.progress as Progress);
			const sum = (count: (p: Progress) => number | undefined) =>
				progress.reduce((all, p) => all + (count(p) ?? 0), 0);
			if (current.every((job) => job.status === 'done')) {
				galleryChanged();
				const videos = sum((p) => p.videos);
				const failedSome = sum((p) => p.failed);
				const busy = sum((p) => p.busy);
				const skipped = sum((p) => p.skipped);
				finish('done', m.rotate_done({ count: sum((p) => p.done) }), [
					...(videos ? [m.rotate_videos({ count: videos })] : []),
					...(busy ? [m.rotate_busy({ count: busy })] : []),
					...(skipped ? [m.rotate_skipped({ count: skipped })] : []),
					...(failedSome ? [m.rotate_failed_some({ count: failedSome })] : [])
				]);
				return;
			}
			const item = this.#get(notice.key);
			// The jobs' own total once each has counted its photos; until then the one asked.
			if (item) {
				const done = sum((p) => p.done);
				const all = progress.every((p) => p.total !== undefined) ? sum((p) => p.total) : total;
				item.text = m.rotate_running({ done, total: all });
				item.progress = { done, total: all };
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

	/** A finished action that can be undone. */
	undoable(text: string, details: string[], undo: () => Promise<string>) {
		const notice = this.#add('done', text);
		notice.details = details;
		notice.undo = undo;
		this.#dismissLater(notice.key, UNDO_NOTICE_MS);
	}

	async runUndo(key: number) {
		const item = this.#get(key);
		const undo = item?.undo;
		if (!item || !undo) return;
		Object.assign(item, { phase: 'running', undo: undefined });
		try {
			this.#finish(key, 'done', await undo(), []);
		} catch (error) {
			this.#finish(key, 'failed', m.undo_failed({ error: errorMessage(error) }), []);
		}
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
		this.#dismissLater(key, NOTICE_MS);
	}

	/** Dismisses the notice later, unless it is busy again by then (an undo running). */
	#dismissLater(key: number, ms: number) {
		setTimeout(() => {
			if (this.#get(key)?.phase !== 'running') this.dismiss(key);
		}, ms);
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
