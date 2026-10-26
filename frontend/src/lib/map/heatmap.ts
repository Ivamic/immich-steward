// SPDX-License-Identifier: AGPL-3.0-or-later
// The heat map of the photos with a location (D-155): where the library already has many photos
// helps to find one's way on the map. Loaded once per page when first turned on; the browser
// asks again with the ETag, so a reload sends nothing when no location changed.
import type { ExpressionSpecification, HeatmapLayerSpecification } from 'maplibre-gl';
import { getHeatmap } from '#lib/api.js';

export const HEATMAP = 'steward-heatmap';

let cells: Promise<number[]> | null = null;

/** Latitude, longitude and number of photos, cell after cell; shared by every map of the page. */
export function loadHeatmap(): Promise<number[]> {
	cells ??= getHeatmap().catch((error) => {
		cells = null; // try again next time
		throw error;
	});
	return cells;
}

/** The cells as GeoJSON points with their number of photos (`n`). */
export function heatmapFeatures(flat: number[]) {
	const features = [];
	for (let i = 0; i + 2 < flat.length; i += 3) {
		features.push({
			type: 'Feature' as const,
			properties: { n: flat[i + 2] },
			geometry: { type: 'Point' as const, coordinates: [flat[i + 1], flat[i]] }
		});
	}
	return { type: 'FeatureCollection' as const, features };
}

const byZoom = (...stops: number[]): ExpressionSpecification =>
	['interpolate', ['linear'], ['zoom'], ...stops] as ExpressionSpecification;

// Violet: a hue no module uses (their colors are blue, orange, magenta, teal, yellow), seen on the
// plain map and on imagery alike.
export const heatmapPaint: HeatmapLayerSpecification['paint'] = {
	// A cell weighs by the square root of its photos: home with 2,000 photos does not drown out
	// a place with 20.
	'heatmap-weight': ['interpolate', ['linear'], ['sqrt', ['get', 'n']], 1, 0.15, 4, 0.5, 12, 1],
	'heatmap-intensity': byZoom(0, 0.6, 9, 1.2, 15, 2.5),
	'heatmap-radius': byZoom(0, 3, 5, 8, 10, 14, 14, 24, 18, 40),
	'heatmap-opacity': byZoom(0, 0.75, 16, 0.6, 19, 0.45),
	'heatmap-color': [
		'interpolate',
		['linear'],
		['heatmap-density'],
		0,
		'rgba(124, 58, 237, 0)',
		0.12,
		'rgba(124, 58, 237, 0.35)',
		0.4,
		'rgba(124, 58, 237, 0.75)',
		0.7,
		'rgb(167, 139, 250)',
		1,
		'rgb(237, 233, 254)'
	]
};
