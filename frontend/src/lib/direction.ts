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
