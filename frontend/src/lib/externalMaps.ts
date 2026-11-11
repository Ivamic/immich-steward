// SPDX-License-Identifier: AGPL-3.0-or-later
// Links that open a point in Google Maps (Maps URLs: no key, allowed by Google's terms). Only the
// coordinates leave Steward, and only on a click: the links go without a referrer.

import type { LatLon } from './coords.js';

const point = ({ lat, lon }: LatLon) => `${lat.toFixed(6)},${lon.toFixed(6)}`;

/** The satellite view of the point, close enough to see a building. */
export function googleSatelliteUrl(at: LatLon): string {
	return `https://www.google.com/maps/@?api=1&map_action=map&center=${point(at)}&zoom=18&basemap=satellite`;
}

/** The Street View panorama nearest to the point, if Google has one there. */
export function googleStreetViewUrl(at: LatLon): string {
	return `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${point(at)}`;
}
