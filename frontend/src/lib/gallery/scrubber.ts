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
 * Going from the oldest month up, a year is labeled at the bottom of its earliest month
 * (January, usually), and months get a dot at their bottom; labels and dots that would crowd the
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
	for (const segment of segments.toReversed()) {
		const year = segment.month.slice(0, 4);
		const bottom = toY(segment.top + segment.height);
		const height = toY(segment.height);
		if (year !== labeledYear) {
			if (sinceLabel > MIN_LABEL_GAP) {
				years.push({ year, y: bottom });
				sinceLabel = 0;
			}
			labeledYear = year;
		}
		if (dots.length === 0 || (height > MIN_DOT_HEIGHT && sinceDot > MIN_DOT_GAP)) {
			dots.push(bottom);
			sinceDot = 0;
		}
		sinceLabel += height;
		sinceDot += height;
	}
	return { years, dots };
}
