// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { googleSatelliteUrl, googleStreetViewUrl } from './externalMaps';

describe('Google Maps links', () => {
	it('opens the satellite view at the point', () => {
		expect(googleSatelliteUrl({ lat: 41.9028, lon: 12.4964 })).toBe(
			'https://www.google.com/maps/@?api=1&map_action=map&center=41.902800,12.496400&zoom=18&basemap=satellite'
		);
	});

	it('opens the nearest Street View panorama', () => {
		expect(googleStreetViewUrl({ lat: -33.8568, lon: 151.2153 })).toBe(
			'https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=-33.856800,151.215300'
		);
	});

	it('keeps no more than six decimals (about 10 cm)', () => {
		expect(googleSatelliteUrl({ lat: 1.123456789, lon: -2.987654321 })).toContain(
			'center=1.123457,-2.987654'
		);
	});
});
