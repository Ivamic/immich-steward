// SPDX-License-Identifier: AGPL-3.0-or-later
// Which way the camera looked (D-245), as words: "north-east, 48° ±30°, street-level image".
import type { Direction } from '#lib/api.js';
import { m } from '#lib/paraglide/messages.js';

const POINTS = [
	m.compass_n,
	m.compass_ne,
	m.compass_e,
	m.compass_se,
	m.compass_s,
	m.compass_sw,
	m.compass_w,
	m.compass_nw
];

/** The point of the compass a heading is nearest to. */
export const compassPoint = (heading: number): string =>
	POINTS[Math.round((((heading % 360) + 360) % 360) / 45) % 8]();

function sourceText(source: string): string {
	if (source === 'street') return m.direction_source_street();
	if (source === 'street_match') return m.direction_source_match();
	return source;
}

export const directionText = (direction: Pick<Direction, 'heading' | 'accuracy' | 'source'>) =>
	m.direction_text({
		point: compassPoint(direction.heading),
		heading: Math.round(direction.heading),
		accuracy: Math.round(direction.accuracy),
		source: sourceText(direction.source)
	});

/** One street-level image matched with the photo: the way the photo looks by it, how sure. */
export interface HeadingFrom {
	heading: number;
	/** Points that fit: the more, the more it counts. */
	weight: number;
	/** How far off it may be on its own. */
	accuracy: number;
	key: string;
}

// Images further than this from the others are left out of the common heading.
const APART = 45;
// Images this far apart on average: they disagree, and it is said.
const DISAGREE = 20;

const wrap = (degrees: number) => ((degrees % 360) + 360) % 360;
/** Degrees from one heading to the other, -180..180. */
const between = (from: number, to: number) => ((to - from + 540) % 360) - 180;

function meanHeading(from: HeadingFrom[]): number {
	let x = 0;
	let y = 0;
	for (const f of from) {
		x += f.weight * Math.cos((f.heading * Math.PI) / 180);
		y += f.weight * Math.sin((f.heading * Math.PI) / 180);
	}
	return wrap((Math.atan2(y, x) * 180) / Math.PI);
}

/** The way the photo looks by all the images matched with it (D-246): their weighted mean, the
 * ones far from the rest left out; give or take as much as they differ. Null: none. */
export function commonHeading(from: HeadingFrom[]): {
	heading: number;
	accuracy: number;
	used: number;
	left: number;
	disagree: boolean;
	key: string;
} | null {
	if (!from.length) return null;
	const first = meanHeading(from);
	let used = from.filter((f) => Math.abs(between(first, f.heading)) <= APART);
	if (!used.length) used = from;
	const heading = meanHeading(used);
	const total = used.reduce((sum, f) => sum + f.weight, 0);
	const apart =
		used.reduce((sum, f) => sum + f.weight * Math.abs(between(heading, f.heading)), 0) / total;
	const best = used.reduce((a, b) => (b.weight > a.weight ? b : a));
	// One image: as sure as it is on its own; more: as close as they agree, never surer than the
	// surest of them.
	const accuracy =
		used.length === 1
			? best.accuracy
			: Math.max(Math.min(...used.map((f) => f.accuracy)) / 2, apart * 1.5, 5);
	return {
		heading,
		accuracy: Math.round(Math.min(45, accuracy)),
		used: used.length,
		left: from.length - used.length,
		disagree: from.length > used.length || apart > DISAGREE,
		key: best.key
	};
}
