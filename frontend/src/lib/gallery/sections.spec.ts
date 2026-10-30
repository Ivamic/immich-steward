// SPDX-License-Identifier: AGPL-3.0-or-later
import type { AssetItem } from '#lib/api.js';
import { describe, expect, it } from 'vitest';
import { byMonth, byPart, firstPhotos, photosBySpot, spotLetter } from './sections.js';

const photo = (id: string, month: string) =>
	({ id, local_taken_at: `${month}-10T12:00:00` }) as AssetItem;

describe('byMonth', () => {
	const photos = [photo('b', '2024-05'), photo('a', '2021-11'), photo('c', '2024-05')];

	it('goes from the oldest month, keeping the order inside one', () => {
		const sections = byMonth(photos, new Map());
		expect(sections.map((s) => s.key)).toEqual(['2021-11', '2024-05']);
		expect(sections[1].photos.map((p) => p.id)).toEqual(['b', 'c']);
	});

	it('counts the spots of a month, the most common first', () => {
		const spots = new Map([
			['b', 1],
			['c', 1],
			['a', 0]
		]);
		expect(byMonth(photos, spots)[1].spots).toEqual([[1, 2]]);
		const mixed = new Map([
			['b', 0],
			['c', 1]
		]);
		expect(byMonth([...photos, photo('d', '2024-05')], mixed.set('d', 1))[1].spots).toEqual([
			[1, 2],
			[0, 1]
		]);
	});
});

describe('photosBySpot', () => {
	it('leaves out the photos without a location', () => {
		const photos = [photo('a', '2024-05'), photo('b', '2024-05'), photo('c', '2024-05')];
		const spots = photosBySpot(
			photos,
			new Map([
				['c', 1],
				['a', 0]
			])
		);
		expect(spots.map(([number, of]) => [number, of.map((p) => p.id)])).toEqual([
			[0, ['a']],
			[1, ['c']]
		]);
	});
});

describe('firstPhotos', () => {
	const sections = byMonth(
		[photo('a', '2021-01'), photo('b', '2021-01'), photo('c', '2022-01'), photo('d', '2023-01')],
		new Map()
	);

	it('cuts inside a section and stops there', () => {
		const shown = firstPhotos(sections, 3);
		expect(shown.map((s) => s.photos.length)).toEqual([2, 1]);
		expect(firstPhotos(sections, 1).map((s) => s.photos.length)).toEqual([1]);
	});
});

describe('spotLetter', () => {
	it('runs out at the end of the alphabet', () => {
		expect([spotLetter(0), spotLetter(25), spotLetter(26)]).toEqual(['A', 'Z', '…']);
	});
});

describe('byPart', () => {
	const photos = ['a', 'b', 'c', 'd'].map((id) => photo(id, '2024-05'));

	it('keeps the order of the scenes and puts the others last', () => {
		const sections = byPart(photos, [['c', 'd'], ['a']], new Map(), (n) => `Scene ${n}`, 'Rest');
		expect(sections.map((s) => [s.title, s.photos.map((p) => p.id)])).toEqual([
			['Scene 1', ['c', 'd']],
			['Scene 2', ['a']],
			['Rest', ['b']]
		]);
	});

	it('leaves out a scene the filter emptied, and a rest with nothing in it', () => {
		const sections = byPart(photos.slice(0, 2), [['c'], ['a', 'b']], new Map(), String, 'Rest');
		expect(sections.map((s) => s.key)).toEqual(['part-1']);
	});
});
