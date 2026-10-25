// SPDX-License-Identifier: AGPL-3.0-or-later
// Which satellite source the map shows (D-143): the one picked by hand, or, with "Auto", the far
// or the near source of the settings by zoom. A source that cannot be used (off, no key, refused
// or exhausted) is skipped for the next one that can; at the end the plain map.

import type { MapAuto, MapSourceConfig } from '#lib/api.js';

/** The plain map (the vector style), no imagery. */
export const SCHEME = 'scheme';

/** How the likely areas of the suggestions are drawn: filled, outlined only or not at all. */
export const AREA_MODES = ['fill', 'line', 'none'] as const;
export type AreaMode = (typeof AREA_MODES)[number];

export function areaMode(value: string): AreaMode {
	return (AREA_MODES as readonly string[]).includes(value) ? (value as AreaMode) : 'fill';
}

/** The id of the switching by zoom in the settings, linked from the bar above the map. */
export const AUTO_ANCHOR = 'map-auto';

// Close up the sharper sources first; EOX (10 m) is the last resort before the plain map.
const NEAR_ORDER = ['esri', 'maptiler', 'eox'];
const FAR_ORDER = ['eox'];

/** Sources the map can show now; `down` are those that failed in this page. */
export function usable(source: MapSourceConfig, down: ReadonlySet<string>): boolean {
	return source.enabled && source.status === 'ok' && !down.has(source.id);
}

function firstUsable(
	ids: (string | null)[],
	sources: MapSourceConfig[],
	down: ReadonlySet<string>
): string {
	for (const id of ids) {
		if (id === null || id === SCHEME) return SCHEME;
		const source = sources.find((s) => s.id === id);
		if (source && usable(source, down)) return id;
	}
	return SCHEME;
}

/** The source to show: `choice` (a source id or SCHEME), or with `auto` the one for `zoom`. */
export function effectiveSource(
	sources: MapSourceConfig[],
	choice: string,
	auto: MapAuto | null,
	zoom: number,
	down: ReadonlySet<string> = new Set()
): string {
	if (auto) {
		const near = zoom >= auto.switch_zoom;
		const wanted = near ? auto.near : auto.far;
		if (wanted === null) return SCHEME;
		return firstUsable([wanted, ...(near ? NEAR_ORDER : FAR_ORDER)], sources, down);
	}
	if (choice === SCHEME) return SCHEME;
	return firstUsable([choice, ...NEAR_ORDER], sources, down);
}

const ESCAPES: Record<string, string> = {
	'&': '&amp;',
	'<': '&lt;',
	'>': '&gt;',
	'"': '&quot;',
	"'": '&#39;'
};

/** The attribution HTML of a variant with the provider's copyright text (plain text) in it. */
export function attributionHtml(template: string, copyright: string | null): string {
	const text = (copyright ?? '').replace(/[&<>"']/g, (c) => ESCAPES[c]);
	return template.replace('{copyright}', text);
}

/** Tile addresses go through our protocol, so that the tiles are counted and errors seen. */
export const TILE_PROTOCOL = 'steward-tile';

export function protocolUrl(sourceId: string, tiles: string): string {
	return `${TILE_PROTOCOL}://${sourceId}/${tiles}`;
}

/** The source id and the real address of a tile requested through our protocol. */
export function parseProtocolUrl(url: string): { sourceId: string; url: string } | null {
	const prefix = `${TILE_PROTOCOL}://`;
	if (!url.startsWith(prefix)) return null;
	const rest = url.slice(prefix.length);
	const slash = rest.indexOf('/');
	if (slash <= 0) return null;
	return { sourceId: rest.slice(0, slash), url: rest.slice(slash + 1) };
}

/** The attribution that stays visible with the full one folded under (i). */
export function shortAttribution(active: string): string {
	switch (active) {
		case 'esri':
			return '© OpenStreetMap · Powered by Esri';
		case 'maptiler':
			return '© MapTiler © OpenStreetMap';
		case 'eox':
			return '© OpenStreetMap · Sentinel-2 cloudless by EOX';
		default:
			return '© OpenStreetMap';
	}
}
