// SPDX-License-Identifier: AGPL-3.0-or-later
// Colors of the time-neighbor route: hue tells "before" from "after" the photo, brightness tells
// how close in time (bright = close, faded = long ago).
import type { ExpressionSpecification } from 'maplibre-gl';

type Rgb = readonly [number, number, number];

export const BEFORE_RGB: Rgb = [130, 80, 223]; // purple
export const AFTER_RGB: Rgb = [212, 99, 29]; // orange

// Same time scale as the score of the time-neighbors module (an hour away ~ 0.37).
const TIME_SCALE_S = 3600;
const MIN_ALPHA = 0.12;
const EPSILON = 1e-6;

/** 1 at the moment of the photo, fading towards MIN_ALPHA for photos long before or after. */
export function closeness(deltaS: number): number {
	return MIN_ALPHA + (1 - MIN_ALPHA) * Math.exp(-Math.abs(deltaS) / TIME_SCALE_S);
}

export function rgba([r, g, b]: Rgb, alpha: number): string {
	return `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(3)})`;
}

export function trackColor(deltaS: number): string {
	return rgba(deltaS <= 0 ? BEFORE_RGB : AFTER_RGB, closeness(deltaS));
}

interface RoutePoint {
	latitude: number;
	longitude: number;
	delta_s: number;
}

/**
 * `line-gradient` for the route through `points` (sorted by time). MapLibre places gradient
 * stops by the share of the line length, so each photo's color is put at its share; where the
 * line passes the moment of the photo, the color switches from "before" to "after" at full
 * brightness. Null when the line has no length.
 */
export function trackGradient(points: RoutePoint[]): ExpressionSpecification | null {
	const lengths = [0];
	for (let i = 1; i < points.length; i++) {
		lengths.push(lengths[i - 1] + planarDistance(points[i - 1], points[i]));
	}
	const total = lengths[lengths.length - 1];
	if (points.length < 2 || total <= 0) return null;

	const stops: [number, string][] = [];
	const add = (share: number, color: string) => {
		const last = stops[stops.length - 1];
		// Stops must strictly increase; photos at the same spot keep the first color.
		if (!last || share > last[0] + EPSILON) stops.push([Math.min(share, 1), color]);
	};
	points.forEach((p, i) => {
		const next = points[i + 1];
		add(lengths[i] / total, trackColor(p.delta_s));
		if (next && p.delta_s <= 0 && next.delta_s > 0) {
			// The photo itself lies between these two, at the share of the time gap.
			const at = p.delta_s / (p.delta_s - next.delta_s);
			const share = (lengths[i] + (lengths[i + 1] - lengths[i]) * at) / total;
			add(share - EPSILON * 2, rgba(BEFORE_RGB, 1));
			add(share, rgba(AFTER_RGB, 1));
		}
	});
	if (stops.length < 2) return null;
	return ['interpolate', ['linear'], ['line-progress'], ...stops.flat()] as ExpressionSpecification;
}

/** Relative distance, enough to place gradient stops along a short route. */
function planarDistance(a: RoutePoint, b: RoutePoint): number {
	const k = Math.cos((((a.latitude + b.latitude) / 2) * Math.PI) / 180);
	return Math.hypot((b.longitude - a.longitude) * k, b.latitude - a.latitude);
}
