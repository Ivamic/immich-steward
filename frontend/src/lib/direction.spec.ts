// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';

import { commonHeading, compassPoint } from './direction.js';

describe('the point of the compass', () => {
	it('is the nearest of the eight', () => {
		expect(compassPoint(0)).toBe('north');
		expect(compassPoint(48)).toBe('north-east');
		expect(compassPoint(22)).toBe('north');
		expect(compassPoint(23)).toBe('north-east');
		expect(compassPoint(350)).toBe('north');
		expect(compassPoint(-90)).toBe('west');
		expect(compassPoint(540)).toBe('south');
	});
});

const at = (heading: number, weight = 100, accuracy = 15) => ({
	heading,
	weight,
	accuracy,
	key: `mapillary:${heading}`
});

describe('commonHeading', () => {
	it('is none without images', () => {
		expect(commonHeading([])).toBeNull();
	});

	it('is the one image alone', () => {
		expect(commonHeading([at(48)])).toMatchObject({ heading: 48, accuracy: 15, used: 1 });
	});

	it('weighs the images across north', () => {
		const found = commonHeading([at(350, 100), at(10, 300)])!;
		expect(found.heading).toBeCloseTo(5, 0);
		expect(found.key).toBe('mapillary:10');
		expect(found.disagree).toBe(false);
	});

	it('leaves out the one far from the rest and says so', () => {
		const found = commonHeading([at(40), at(50), at(45), at(200, 60)])!;
		expect(found.heading).toBeCloseTo(45, 0);
		expect(found.used).toBe(3);
		expect(found.left).toBe(1);
		expect(found.disagree).toBe(true);
	});

	it('agreeing images are surer than one', () => {
		expect(commonHeading([at(44), at(46), at(45)])!.accuracy).toBeLessThan(15);
	});
});
