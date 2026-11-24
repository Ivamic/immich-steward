// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';

import { compassPoint } from './direction.js';

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
