// SPDX-License-Identifier: AGPL-3.0-or-later
// Where the timeline scrubber puts its year labels and month dots.

export interface Segment {
	month: string; // YYYY-MM
	top: number; // px from the top of the timeline
	height: number;
}

// px on the bar, the values of Immich's scrubber
const MIN_LABEL_GAP = 16; // between year labels
const MIN_DOT_GAP = 8; // between month dots
const MIN_DOT_HEIGHT = 5; // months shorter than this get no dot

export interface Marks {
	years: { year: string; y: number }[];
	dots: number[];
}

/**
 * Going from the oldest month on (up from the bottom when the newest are on top, down from the
 * top when the oldest are), a year is labeled at the edge where its earliest month (January,
 * usually) begins, and months get a dot at that edge; labels and dots that would crowd the
 * previous ones are left out. Unlike Immich, a crowded year label is left out rather than moved
 * to a later month of the year: a label always marks where its year begins. `toY` turns
 * timeline px into bar px.
 */
export function scrubberMarks(segments: Segment[], toY: (px: number) => number): Marks {
	const years: Marks['years'] = [];
	const dots: number[] = [];
	let labeledYear = '';
	let sinceLabel = Infinity;
	let sinceDot = Infinity;
	const oldestFirst =
		segments.length > 1 && segments[0].month < segments[segments.length - 1].month;
	for (const segment of oldestFirst ? segments : segments.toReversed()) {
		const year = segment.month.slice(0, 4);
		const start = toY(oldestFirst ? segment.top : segment.top + segment.height);
		const height = toY(segment.height);
		if (year !== labeledYear) {
			if (sinceLabel > MIN_LABEL_GAP) {
				years.push({ year, y: start });
				sinceLabel = 0;
			}
			labeledYear = year;
		}
		if (dots.length === 0 || (height > MIN_DOT_HEIGHT && sinceDot > MIN_DOT_GAP)) {
			dots.push(start);
			sinceDot = 0;
		}
		sinceLabel += height;
		sinceDot += height;
	}
	return { years, dots };
}
