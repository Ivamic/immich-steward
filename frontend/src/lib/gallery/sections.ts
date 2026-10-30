// SPDX-License-Identifier: AGPL-3.0-or-later
// The photos of a group in sections: by month, to see when a subject moved from one spot to
// another. A spot is a place where photos with a location lie together (`GroupPoint.spot`).
import type { AssetItem } from '#lib/api.js';
import { monthTitle } from './month.js';

export interface Section {
	key: string;
	title: string;
	photos: AssetItem[];
	/** Spot number -> its photos here, the most common first. */
	spots: [number, number][];
}

/** Spots are told apart by letters: they have no names. */
export const spotLetter = (number: number) =>
	number < 26 ? String.fromCharCode(65 + number) : '…';

function section(
	key: string,
	title: string,
	photos: AssetItem[],
	spotOf: Map<string, number>
): Section {
	const counts = new Map<number, number>();
	for (const photo of photos) {
		const number = spotOf.get(photo.id);
		if (number !== undefined) counts.set(number, (counts.get(number) ?? 0) + 1);
	}
	return { key, title, photos, spots: [...counts].sort(([, a], [, b]) => b - a) };
}

/** Every spot with its photos, the largest first. */
export function photosBySpot(
	photos: AssetItem[],
	spotOf: Map<string, number>
): [number, AssetItem[]][] {
	const spots = new Map<number, AssetItem[]>();
	for (const photo of photos) {
		const number = spotOf.get(photo.id);
		if (number === undefined) continue;
		let of = spots.get(number);
		if (!of) spots.set(number, (of = []));
		of.push(photo);
	}
	return [...spots].sort(([a], [b]) => a - b);
}

/** The months with photos, oldest first. */
export function byMonth(photos: AssetItem[], spotOf: Map<string, number>): Section[] {
	const months = new Map<string, AssetItem[]>();
	for (const photo of photos) {
		const month = photo.local_taken_at.slice(0, 7);
		let of = months.get(month);
		if (!of) months.set(month, (of = []));
		of.push(photo);
	}
	return [...months]
		.sort(([a], [b]) => a.localeCompare(b))
		.map(([month, of]) => section(month, monthTitle(month), of, spotOf));
}

/** The sections up to `limit` photos, with what is left of the last one. */
export function firstPhotos(sections: Section[], limit: number): Section[] {
	const shown: Section[] = [];
	let left = limit;
	for (const part of sections) {
		if (left <= 0) break;
		shown.push({ ...part, photos: part.photos.slice(0, left) });
		left -= part.photos.length;
	}
	return shown;
}
