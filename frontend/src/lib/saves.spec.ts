// SPDX-License-Identifier: AGPL-3.0-or-later
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, type AssetDetail } from '#lib/api.js';
import { GRACE_MS, NOTICE_MS, Saves } from '#lib/saves.svelte.js';

const point = { lat: 42.42, lon: 18.77 };

function fakeApi(canUndo = true) {
	return {
		save: vi.fn(async () => ({ can_undo: canUndo }) as AssetDetail),
		undo: vi.fn(async () => ({ can_undo: false }) as AssetDetail),
		saveBatch: vi.fn(async () => ({ batch_id: 'b1', written: 2, skipped_located: 1 })),
		undoBatch: vi.fn(async () => ({ undone: 1, changed: 1, failed: 0 }))
	};
}

describe('Saves', () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => vi.useRealTimers());

	it('sends a save only after the grace period', async () => {
		const api = fakeApi();
		const saves = new Saves(api);
		saves.schedule('a', 'IMG_1.JPG', point);
		expect(saves.pendingFor('a')).toBeDefined();

		await vi.advanceTimersByTimeAsync(GRACE_MS - 1);
		expect(api.save).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(1);
		expect(api.save).toHaveBeenCalledWith('a', point, false);
		expect(saves.items[0].phase).toBe('saved');
		expect(saves.changed?.assetId).toBe('a');

		await vi.advanceTimersByTimeAsync(NOTICE_MS);
		expect(saves.items).toEqual([]);
	});

	it('never sends a cancelled save', async () => {
		const api = fakeApi();
		const saves = new Saves(api);
		saves.schedule('a', 'IMG_1.JPG', point);
		saves.cancel(saves.items[0].key);
		await vi.advanceTimersByTimeAsync(GRACE_MS * 2);
		expect(api.save).not.toHaveBeenCalled();
		expect(saves.items).toEqual([]);
	});

	it('replaces a pending save of the same photo', async () => {
		const api = fakeApi();
		const saves = new Saves(api);
		saves.schedule('a', 'IMG_1.JPG', point);
		saves.schedule('a', 'IMG_1.JPG', { lat: 1, lon: 2 });
		await vi.advanceTimersByTimeAsync(GRACE_MS);
		expect(api.save).toHaveBeenCalledTimes(1);
		expect(api.save).toHaveBeenCalledWith('a', { lat: 1, lon: 2 }, false);
	});

	it('flushes pending saves with keepalive when the page closes', async () => {
		const api = fakeApi();
		const saves = new Saves(api);
		saves.schedule('a', 'IMG_1.JPG', point);
		saves.schedule('b', 'IMG_2.JPG', point);
		saves.flush();
		expect(api.save).toHaveBeenCalledTimes(2);
		expect(api.save).toHaveBeenLastCalledWith('b', point, true);
		await vi.advanceTimersByTimeAsync(GRACE_MS);
		expect(api.save).toHaveBeenCalledTimes(2);
	});

	it('keeps a failed save for retry, then undoes it', async () => {
		const api = fakeApi();
		api.save.mockRejectedValueOnce(new ApiError(502, 'immich_unreachable'));
		const saves = new Saves(api);
		saves.schedule('a', 'IMG_1.JPG', point);
		await vi.advanceTimersByTimeAsync(GRACE_MS + NOTICE_MS);
		const [save] = saves.items;
		expect(save.phase).toBe('failed');
		expect(save.error).not.toBeNull();

		await saves.send(save.key);
		expect(saves.items[0].phase).toBe('saved');
		await saves.undo(save.key);
		expect(api.undo).toHaveBeenCalledWith('a');
		expect(saves.items[0].phase).toBe('undone');
	});

	it('does not offer undo when the photo had no coordinates', async () => {
		const api = fakeApi(false);
		const saves = new Saves(api);
		saves.schedule('a', 'IMG_1.JPG', point);
		await vi.advanceTimersByTimeAsync(GRACE_MS);
		expect(saves.items[0].canUndo).toBe(false);
		await saves.undo(saves.items[0].key);
		expect(api.undo).not.toHaveBeenCalled();
	});

	it('saves one location for several photos and undoes them together', async () => {
		const api = fakeApi();
		const saves = new Saves(api);
		const batch = { ids: ['a', 'b', 'c'], overwrite: false };
		saves.scheduleBatch(batch, '3 photos', point);
		await vi.advanceTimersByTimeAsync(GRACE_MS);
		expect(api.saveBatch).toHaveBeenCalledWith(batch, point, false);
		const [save] = saves.items;
		expect([save.phase, save.batchId, save.skipped, save.canUndo]).toEqual([
			'saved',
			'b1',
			1,
			true
		]);

		await saves.undo(save.key);
		expect(api.undoBatch).toHaveBeenCalledWith('b1');
		expect([save.phase, save.kept]).toEqual(['undone', 1]);
		expect(api.undo).not.toHaveBeenCalled();
	});
});
