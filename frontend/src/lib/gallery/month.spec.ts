// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { byDay, columnsFor, DAY_GAP, DAY_HEAD, GAP, monthHeight, TILE, tileFor } from './month';

describe('byDay', () => {
	it('groups the photos by the day of the camera clock, in order', () => {
		const items = [
			{ id: 'a', local_taken_at: '2024-05-31T23:59:59' },
			{ id: 'b', local_taken_at: '2024-05-31T08:00:00' },
			{ id: 'c', local_taken_at: '2024-05-03T12:00:00' }
		];
		expect(byDay(items).map((d) => [d.day, d.items.map((i) => i.id)])).toEqual([
			['2024-05-31', ['a', 'b']],
			['2024-05-03', ['c']]
		]);
	});
});

describe('monthHeight', () => {
	// Five columns of tiles.
	const width = 5 * TILE + 4 * GAP;

	it('starts each day on a new row under its heading', () => {
		const row = TILE + GAP;
		// 7 photos: two rows; 3 photos: one row.
		expect(monthHeight([7, 3], width)).toBe(
			DAY_HEAD + 2 * row - GAP + DAY_GAP + DAY_HEAD + row - GAP
		);
	});

	it('is one heading and its rows for a single day', () => {
		expect(monthHeight([5], width)).toBe(DAY_HEAD + TILE);
	});
});

describe('tiles on a phone', () => {
	it('shrink so that three fit in a row', () => {
		expect(columnsFor(342)).toBe(3);
		expect(tileFor(342)).toBe(111);
		expect(monthHeight([4], 342)).toBe(DAY_HEAD + 2 * 111 + GAP);
	});

	it('keep their size on a wide screen', () => {
		expect(tileFor(1200)).toBe(TILE);
	});
});
