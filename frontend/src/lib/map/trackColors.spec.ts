// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { closeness, trackColor, trackGradient } from './trackColors.js';

const at = (longitude: number, delta_s: number) => ({ latitude: 0, longitude, delta_s });

describe('track colors', () => {
	it('fades with the time gap and tells before from after', () => {
		expect(closeness(0)).toBe(1);
		expect(closeness(-3600)).toBeCloseTo(0.12 + 0.88 / Math.E);
		expect(closeness(10 * 3600)).toBeCloseTo(0.12, 3);
		expect(trackColor(-60)).toMatch(/^rgba\(130, 80, 223,/);
		expect(trackColor(60)).toMatch(/^rgba\(212, 99, 29,/);
	});

	it('switches from before to after where the photo lies on the route', () => {
		// Before at 0, after at 3 (degrees of longitude); the photo is a third of the way in time.
		const gradient = trackGradient([at(0, -600), at(3, 1200)]);
		expect(gradient?.slice(0, 3)).toEqual(['interpolate', ['linear'], ['line-progress']]);
		const stops = gradient!.slice(3) as (number | string)[];
		const shares = stops.filter((_, i) => i % 2 === 0) as number[];
		expect(shares[0]).toBe(0);
		expect(shares[shares.length - 1]).toBe(1);
		expect(shares[2]).toBeCloseTo(1 / 3);
		expect(stops[5]).toBe('rgba(212, 99, 29, 1.000)');
		expect(shares).toEqual([...shares].sort((a, b) => a - b));
	});

	it('has no gradient for a route without length', () => {
		expect(trackGradient([at(1, -60), at(1, 60)])).toBeNull();
		expect(trackGradient([at(1, -60)])).toBeNull();
	});
});
