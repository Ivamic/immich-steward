// SPDX-License-Identifier: AGPL-3.0-or-later
import { getLocale } from '#lib/paraglide/runtime.js';

/** "August 2019", "Август 2019 г.": only the first letter is raised (not "2019 Г."). */
export function monthTitle(month: string): string {
	const text = new Intl.DateTimeFormat(getLocale(), { month: 'long', year: 'numeric' }).format(
		new Date(`${month}-01T00:00:00`)
	);
	return text.charAt(0).toLocaleUpperCase(getLocale()) + text.slice(1);
}

/** When a photo was taken, by the camera clock: "Sun, 12 May 2024, 14:37". The time has no zone
 * (D-045), so it is read and shown as local time, unchanged. */
export function takenTitle(localTakenAt: string): string {
	return new Intl.DateTimeFormat(getLocale(), {
		weekday: 'short',
		day: 'numeric',
		month: 'long',
		year: 'numeric',
		hour: '2-digit',
		minute: '2-digit'
	}).format(new Date(localTakenAt.replace(/Z|[+-]\d\d:\d\d$/, '')));
}

/** "Sun, 12 May": the heading of a day inside its month. */
export function dayTitle(day: string): string {
	const text = new Intl.DateTimeFormat(getLocale(), {
		weekday: 'short',
		day: 'numeric',
		month: 'long'
	}).format(new Date(`${day}T00:00:00`));
	return text.charAt(0).toLocaleUpperCase(getLocale()) + text.slice(1);
}

/** The photos of a month by the day they were taken (camera clock), in the order given. */
export function byDay<T extends { local_taken_at: string }>(
	items: T[]
): { day: string; items: T[] }[] {
	const days: { day: string; items: T[] }[] = [];
	for (const item of items) {
		const day = item.local_taken_at.slice(0, 10);
		if (days.at(-1)?.day !== day) days.push({ day, items: [] });
		days.at(-1)!.items.push(item);
	}
	return days;
}

// The sizes the layout of a month is made of, px; keep in sync with the CSS of MonthSection.
export const TILE = 160;
export const GAP = 4;
/** The heading of a day with the space under it. */
export const DAY_HEAD = 32;
/** Between the days of a month. */
export const DAY_GAP = 12;

/** Below this width (a phone) the tiles shrink so that three fit in a row. */
export const NARROW = 600;
const NARROW_COLUMNS = 3;

/** Side of a tile in a gallery this wide. */
export const tileFor = (width: number) =>
	width > 0 && width < NARROW
		? Math.floor((width - GAP * (NARROW_COLUMNS - 1)) / NARROW_COLUMNS)
		: TILE;

export const columnsFor = (width: number) =>
	Math.max(1, Math.floor((width + GAP) / (tileFor(width) + GAP)));

/** Height of a month before its photos are loaded: each day starts a new row under its
 * heading. `days`: the photos of each of its days. */
export function monthHeight(days: number[], width: number): number {
	const columns = columnsFor(width);
	const tile = tileFor(width);
	const grids = days.map((count) => Math.ceil(count / columns) * (tile + GAP) - GAP);
	return grids.reduce((sum, grid) => sum + DAY_HEAD + grid, 0) + DAY_GAP * (days.length - 1);
}
