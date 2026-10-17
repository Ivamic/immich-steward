// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { formatCoordinates, parseCoordinates } from './coords';

describe('parseCoordinates', () => {
	it.each([
		['42.4249205, 18.7713332', 42.4249205, 18.7713332],
		['42.4249 18.7713', 42.4249, 18.7713],
		['  -33.8568,151.2153 ', -33.8568, 151.2153],
		['42,4249; 18,7713', 42.4249, 18.7713]
	])('decimal %s', (text, lat, lon) => {
		expect(parseCoordinates(text)).toEqual({ lat, lon });
	});

	it('degrees, minutes, seconds', () => {
		const point = parseCoordinates(`42°25'29.7"N 18°46'16.8"E`);
		expect(point?.lat).toBeCloseTo(42.42492, 4);
		expect(point?.lon).toBeCloseTo(18.77133, 4);
	});

	it('southern and western hemispheres, Russian letters', () => {
		expect(parseCoordinates(`33°51′ S 151°12′ E`)?.lat).toBeCloseTo(-33.85, 2);
		expect(parseCoordinates(`55°45′ С 37°37′ В`)?.lon).toBeCloseTo(37.6167, 3);
		expect(parseCoordinates(`40°42′N 74°0′W`)?.lon).toBeCloseTo(-74, 3);
	});

	it.each(['', 'Kotor', '91, 10', '10, 181', '1 2 3', '42°N'])('rejects %j', (text) => {
		expect(parseCoordinates(text)).toBeNull();
	});
});

it('formats with six decimals', () => {
	expect(formatCoordinates({ lat: 42.42492, lon: -18.7713332 })).toBe('42.424920, -18.771333');
});
