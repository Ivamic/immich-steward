// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import type { MapAuto, MapSourceConfig } from '#lib/api.js';
import {
	areaMode,
	attributionHtml,
	effectiveSource,
	parseProtocolUrl,
	protocolUrl,
	SCHEME
} from './sources.js';
import { keyProblem, TileTally } from './tileProtocol.js';

function source(id: string, extra: Partial<MapSourceConfig> = {}): MapSourceConfig {
	return {
		id,
		name: id,
		enabled: true,
		status: 'ok',
		variants: [{ id: 'default', tiles: `https://${id}.test/{z}/{x}/{y}`, attribution: id }],
		tile_size: 256,
		max_zoom: 19,
		logo_url: null,
		copyright: null,
		copyright_url: null,
		...extra
	};
}

const ALL = [source('eox'), source('esri'), source('maptiler')];
const AUTO: MapAuto = { far: 'eox', near: 'esri', switch_zoom: 14 };

describe('effectiveSource', () => {
	it('shows the source picked by hand', () => {
		expect(effectiveSource(ALL, 'maptiler', null, 5)).toBe('maptiler');
		expect(effectiveSource(ALL, SCHEME, null, 18)).toBe(SCHEME);
	});

	it('switches by zoom with auto', () => {
		expect(effectiveSource(ALL, SCHEME, AUTO, 13.9)).toBe('eox');
		expect(effectiveSource(ALL, SCHEME, AUTO, 14)).toBe('esri');
	});

	it('takes the next usable source when one is not', () => {
		const exhausted = [source('eox'), source('esri', { status: 'exhausted' }), source('maptiler')];
		expect(effectiveSource(exhausted, SCHEME, AUTO, 16)).toBe('maptiler');
		// Failed in this page: skipped at once, before the core knows.
		expect(effectiveSource(ALL, SCHEME, AUTO, 16, new Set(['esri']))).toBe('maptiler');
		expect(effectiveSource(ALL, 'esri', null, 16, new Set(['esri']))).toBe('maptiler');
	});

	it('ends with EOX and then the plain map', () => {
		const off = [
			source('eox'),
			source('esri', { enabled: false }),
			source('maptiler', { status: 'no_key' })
		];
		expect(effectiveSource(off, SCHEME, AUTO, 16)).toBe('eox');
		expect(effectiveSource(off, SCHEME, AUTO, 16, new Set(['eox']))).toBe(SCHEME);
		expect(effectiveSource([], SCHEME, AUTO, 3)).toBe(SCHEME);
	});

	it('keeps the plain map where the settings say so', () => {
		expect(effectiveSource(ALL, 'esri', { ...AUTO, far: null }, 3)).toBe(SCHEME);
		expect(effectiveSource(ALL, SCHEME, { ...AUTO, near: null }, 17)).toBe(SCHEME);
	});
});

describe('tile protocol', () => {
	it('carries the source and the real address', () => {
		const tiles = 'https://ibasemaps-api.arcgis.com/tile/{z}/{y}/{x}?token=k';
		const url = protocolUrl('esri', tiles).replace('{z}/{y}/{x}', '5/11/17');
		expect(parseProtocolUrl(url)).toEqual({
			sourceId: 'esri',
			url: 'https://ibasemaps-api.arcgis.com/tile/5/11/17?token=k'
		});
		expect(parseProtocolUrl('https://example.test/1/2/3')).toBeNull();
	});

	it('tells key problems from the answers', () => {
		expect(keyProblem(200, null)).toBeNull();
		expect(keyProblem(500, null)).toBeNull();
		expect(keyProblem(403, null)).toBe('invalid'); // MapTiler, also when its limit is reached
		expect(keyProblem(429, null)).toBe('exhausted');
		// Esri: HTTP 200 with a JSON error.
		expect(keyProblem(200, { error: { code: 499, message: 'Token Required.' } })).toBe('invalid');
		expect(keyProblem(200, { error: { code: 498 } })).toBe('invalid');
		expect(keyProblem(200, { error: { code: 403 } })).toBe('exhausted');
	});

	it('counts in batches', () => {
		const tally = new TileTally();
		expect(tally.empty).toBe(true);
		tally.tile('eox');
		tally.tile('eox');
		tally.problem('esri', 'invalid');
		expect(tally.take()).toEqual({ tiles: { eox: 2 }, problems: { esri: 'invalid' } });
		expect(tally.empty).toBe(true);
	});
});

describe('attributionHtml', () => {
	it('puts the copyright text in as text', () => {
		expect(attributionHtml('Powered by Esri | {copyright}', 'Esri, Vantor & <b>x</b>')).toBe(
			'Powered by Esri | Esri, Vantor &amp; &lt;b&gt;x&lt;/b&gt;'
		);
		expect(attributionHtml('© EOX', null)).toBe('© EOX');
	});
});

describe('areaMode', () => {
	it('keeps a known mode and falls back to the fill', () => {
		expect(areaMode('line')).toBe('line');
		expect(areaMode('none')).toBe('none');
		expect(areaMode('outline')).toBe('fill');
	});
});
