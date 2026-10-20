// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { scrubberMarks, type Segment } from './scrubber.js';

/** Months newest first, as in the timeline, each 30 px high. */
function months(...names: string[]): Segment[] {
	return names.map((month, i) => ({ month, top: i * 30, height: 30 }));
}

describe('scrubber marks', () => {
	it('labels a year at the bottom of its earliest month, like Immich', () => {
		const marks = scrubberMarks(months('2017-02', '2017-01', '2016-12', '2016-11'), (px) => px);
		// 2016: bottom of November (the last segment); 2017: bottom of January.
		expect(marks.years).toEqual([
			{ year: '2016', y: 120 },
			{ year: '2017', y: 60 }
		]);
	});

	it('leaves out labels that would crowd the previous one', () => {
		// The bar is 10 times shorter than the timeline: 3 px per month.
		const marks = scrubberMarks(months('2018-01', '2017-01', '2016-01'), (px) => px / 10);
		expect(marks.years.map((label) => label.year)).toEqual(['2016']);
		expect(marks.dots).toHaveLength(1);
	});
});

describe('atPhoto', () => {
	it('adds the photo to the gallery query', async () => {
		const { atPhoto } = await import('./filter.js');
		expect(atPhoto('?show=todo', 'abc')).toBe('?show=todo&at=abc');
		expect(atPhoto('?', 'abc')).toBe('?at=abc');
	});
});
