// SPDX-License-Identifier: AGPL-3.0-or-later
// Notices about actions on several photos chosen in the gallery (D-149): turning them in Immich
// (a background job of the core, followed here until it is over) and marking them. Shown with the
// save notices (SaveNotices.svelte). Locations for several photos are saves (saves.svelte.ts).
import { ApiError, getSelectionJob, type Job } from '#lib/api.js';
import { errorMessage } from '#lib/errors.js';
import { m } from '#lib/paraglide/messages.js';
import { galleryChanged } from './selection.svelte.js';

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
}

interface Progress {
	total?: number;
	done?: number;
	videos?: number;
	failed?: number;
}

export class BulkNotices {
	items = $state<BulkNotice[]>([]);
	#nextKey = 1;

	/** Follows a rotation job until it is over. */
	followRotation(job: Job) {
		const notice = this.#add('running', m.rotate_queued());
		const poll = async () => {
			let current: Job;
			try {
				current = await getSelectionJob(job.id);
			} catch (error) {
				this.#finish(notice.key, 'failed', m.rotate_failed({ error: errorMessage(error) }), []);
				return;
			}
			const progress = current.progress as Progress;
			if (current.status === 'done') {
				galleryChanged();
				this.#finish(notice.key, 'done', m.rotate_done({ count: progress.done ?? 0 }), [
					...(progress.videos ? [m.rotate_videos({ count: progress.videos })] : []),
					...(progress.failed ? [m.rotate_failed_some({ count: progress.failed })] : [])
				]);
				return;
			}
			if (current.status === 'failed') {
				galleryChanged();
				const error = new ApiError(0, current.error ?? '', { permissions: EDIT_PERMISSIONS });
				this.#finish(notice.key, 'failed', m.rotate_failed({ error: errorMessage(error) }), []);
				return;
			}
			const item = this.#get(notice.key);
			if (item && progress.total !== undefined) {
				item.text = m.rotate_running({ done: progress.done ?? 0, total: progress.total });
			}
			setTimeout(poll, POLL_MS);
		};
		setTimeout(poll, POLL_MS);
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
		const notice: BulkNotice = { key: this.#nextKey++, phase, text, details: [] };
		this.items.push(notice);
		return notice;
	}

	#get(key: number): BulkNotice | undefined {
		return this.items.find((item) => item.key === key);
	}

	#finish(key: number, phase: BulkNotice['phase'], text: string, details: string[]) {
		const item = this.#get(key);
		if (!item) return;
		Object.assign(item, { phase, text, details });
		setTimeout(() => this.dismiss(key), NOTICE_MS);
	}
}

export const bulkNotices = new BulkNotices();
