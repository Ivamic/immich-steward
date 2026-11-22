// SPDX-License-Identifier: AGPL-3.0-or-later
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
	addToAlbum,
	albumsContaining,
	createAlbum,
	getSelectionSuggestions,
	markPhotos,
	MAX_IDS,
	removeFromAlbum,
	rotateSelection,
	setSelectionLocation,
	setSelectionReview,
	spreadSample,
	undoSelectionLocation
} from './api';

const album = { id: 'album-1', name: 'Trip' };

/** A fake API: every batch is answered as if all its photos were changed. */
function fakeApi() {
	const calls: { method: string; path: string; body: Record<string, unknown> }[] = [];
	vi.stubGlobal(
		'fetch',
		vi.fn(async (path: string, init: RequestInit) => {
			const body = JSON.parse(String(init.body)) as Record<string, unknown>;
			const ids = (body.ids ?? []) as string[];
			calls.push({ method: String(init.method), path, body });
			const n = calls.length;
			const reply: unknown = path.endsWith('/contains')
				? { counts: { 'album-1': ids.length } }
				: path.endsWith('/assets/remove')
					? { album, removed: ids.length, removed_ids: ids, failed: 0 }
					: path.startsWith('/api/albums')
						? {
								album,
								added: ids,
								already: 1,
								skipped_locked: 0,
								failed: 0,
								created: init.method === 'POST'
							}
						: path === '/api/selection/location'
							? { batch_id: `b${n}`, written: ids.length - 1, skipped_located: 1 }
							: path === '/api/selection/location/undo'
								? { undone: 2, changed: 1, failed: 0 }
								: path === '/api/selection/review'
									? { changed: ids.length }
									: path === '/api/selection/rotate'
										? { id: `job${n}` }
										: path === '/api/selection/suggestions'
											? []
											: { total: n };
			return new Response(JSON.stringify(reply), { status: 200 });
		})
	);
	return calls;
}

const ids = (n: number) => Array.from({ length: n }, (_, i) => `id-${i}`);
const sizes = (calls: ReturnType<typeof fakeApi>) =>
	calls.map((c) => (c.body.ids as string[]).length);

afterEach(() => vi.unstubAllGlobals());

describe('albums in batches', () => {
	it('adds more photos than one request takes', async () => {
		const calls = fakeApi();
		const result = await addToAlbum('album-1', ids(2478));
		expect(sizes(calls)).toEqual([MAX_IDS, 478]);
		expect(result.added).toEqual(ids(2478));
		expect(result.already).toBe(2);
		expect(result.created).toBe(false);
	});

	it('creates the album with the first batch and adds the rest to it', async () => {
		const calls = fakeApi();
		const result = await createAlbum('Trip', ids(2478));
		expect(calls.map((c) => [c.method, c.path])).toEqual([
			['POST', '/api/albums'],
			['PUT', '/api/albums/album-1/assets']
		]);
		expect(result.added).toHaveLength(2478);
		expect(result.created).toBe(true);
	});

	it('takes out and counts in batches', async () => {
		fakeApi();
		const removed = await removeFromAlbum('album-1', ids(4001));
		expect(removed.removed).toBe(4001);
		expect(removed.removed_ids).toHaveLength(4001);
		expect((await albumsContaining(ids(2478))).counts).toEqual({ 'album-1': 2478 });
	});

	it('sends one request for a few photos', async () => {
		const calls = fakeApi();
		await addToAlbum('album-1', ids(3));
		expect(calls).toHaveLength(1);
	});
});

describe('other actions in batches', () => {
	it('writes a location per batch and undoes them all', async () => {
		const calls = fakeApi();
		const written = await setSelectionLocation(ids(2478), { lat: 1, lon: 2 }, false);
		expect(sizes(calls)).toEqual([MAX_IDS, 478]);
		expect(written).toEqual({ batch_ids: ['b1', 'b2'], written: 2476, skipped_located: 2 });

		const undone = await undoSelectionLocation(written.batch_ids);
		expect(calls.slice(2).map((c) => c.body.batch_id)).toEqual(['b1', 'b2']);
		expect(undone).toEqual({ undone: 4, changed: 2, failed: 0 });
	});

	it('marks and turns in batches', async () => {
		const calls = fakeApi();
		expect(await setSelectionReview(ids(2478), 'skipped')).toEqual({ changed: 2478 });
		const jobs = await rotateSelection(ids(2478), 90);
		expect(jobs.map((job) => job.id)).toEqual(['job3', 'job4']);
		expect(sizes(calls)).toEqual([MAX_IDS, 478, MAX_IDS, 478]);
	});

	it('takes the state after the last batch of a group change', async () => {
		const calls = fakeApi();
		const after = await markPhotos(ids(2478));
		expect(sizes(calls)).toEqual([MAX_IDS, 478]);
		expect(after).toEqual({ total: 2 });
	});

	it('asks for suggestions with an even sample', async () => {
		const calls = fakeApi();
		await getSelectionSuggestions(ids(2478));
		const sent = calls[0].body.ids as string[];
		expect(sent).toHaveLength(MAX_IDS);
		expect(sent[0]).toBe('id-0');
		expect(sent.at(-1)).toBe('id-2476');
		expect(new Set(sent).size).toBe(MAX_IDS);
		expect(spreadSample(ids(5))).toEqual(ids(5));
	});
});
