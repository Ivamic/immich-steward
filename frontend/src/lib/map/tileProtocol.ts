// SPDX-License-Identifier: AGPL-3.0-or-later
// Satellite tiles are loaded by us rather than by MapLibre (`addProtocol`): so they are counted
// (the own count, D-146) and the answers that mean a key problem are seen. MapTiler says 403 for a
// refused key (also when its limit is reached); Esri answers HTTP 200 with a JSON error instead of
// the image. The counts go to the core in batches; nothing goes anywhere else.

import { addProtocol, type AddProtocolAction } from 'maplibre-gl';
import { reportMapTiles, type MapKeyProblem } from '#lib/api.js';
import { parseProtocolUrl, TILE_PROTOCOL } from './sources.js';

const REPORT_EVERY_MS = 30_000;

/** What an answer to a tile request says about the key; null: nothing (a tile, or a hiccup). */
export function keyProblem(status: number, body: unknown): MapKeyProblem | null {
	if (status === 401 || status === 403) return 'invalid';
	if (status === 429) return 'exhausted';
	const error = (body as { error?: { code?: unknown } } | null)?.error;
	if (status !== 200 || !error) return null;
	// ArcGIS: 498 invalid token, 499 token required; 403 is a removed privilege (the free tier
	// used up), 429 too many requests.
	if (error.code === 403 || error.code === 429) return 'exhausted';
	return 'invalid';
}

/** Tiles loaded and problems seen since the last report. */
export class TileTally {
	tiles: Record<string, number> = {};
	problems: Record<string, MapKeyProblem> = {};

	tile(sourceId: string) {
		this.tiles[sourceId] = (this.tiles[sourceId] ?? 0) + 1;
	}

	problem(sourceId: string, problem: MapKeyProblem) {
		this.problems[sourceId] = problem;
	}

	get empty() {
		return !Object.keys(this.tiles).length && !Object.keys(this.problems).length;
	}

	/** Takes the collected numbers out, leaving the tally empty. */
	take(): { tiles: Record<string, number>; problems: Record<string, MapKeyProblem> } {
		const taken = { tiles: this.tiles, problems: this.problems };
		this.tiles = {};
		this.problems = {};
		return taken;
	}
}

const tally = new TileTally();
const listeners = new Set<(sourceId: string, problem: MapKeyProblem) => void>();
let registered = false;

/** Called when a tile tells that the key of a source has a problem. */
export function onKeyProblem(listener: (sourceId: string, problem: MapKeyProblem) => void) {
	listeners.add(listener);
	return () => listeners.delete(listener);
}

function flush(keepalive = false) {
	if (tally.empty) return;
	const { tiles, problems } = tally.take();
	// Lost counts are no harm: the own count is approximate anyway.
	reportMapTiles(tiles, problems, keepalive).catch(() => {});
}

const loadTile: AddProtocolAction = async (params, abortController) => {
	const parsed = parseProtocolUrl(params.url);
	if (!parsed) throw new Error(`not a ${TILE_PROTOCOL} address`);
	const response = await fetch(parsed.url, { signal: abortController.signal });
	const type = response.headers.get('content-type') ?? '';
	if (response.ok && type.startsWith('image/')) {
		tally.tile(parsed.sourceId);
		return { data: await response.arrayBuffer() };
	}
	const body = type.includes('json') || type.startsWith('text/') ? await readJson(response) : null;
	const problem = keyProblem(response.status, body);
	if (problem) {
		tally.problem(parsed.sourceId, problem);
		for (const listener of listeners) listener(parsed.sourceId, problem);
	}
	throw new Error(`tile not loaded: HTTP ${response.status}`);
};

async function readJson(response: Response): Promise<unknown> {
	try {
		return JSON.parse(await response.text());
	} catch {
		return null;
	}
}

/** Registers the protocol once per page and starts the reports. */
export function registerTileProtocol() {
	if (registered) return;
	registered = true;
	addProtocol(TILE_PROTOCOL, loadTile);
	setInterval(() => flush(), REPORT_EVERY_MS);
	// The last counts leave with the page.
	addEventListener('pagehide', () => flush(true));
}
