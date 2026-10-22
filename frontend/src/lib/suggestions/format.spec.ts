// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import type { Candidate, ModuleSuggestions, NeighborEvidence } from '#lib/api.js';
import {
	candidateLabel,
	candidateRemarks,
	formatDelta,
	formatDistance,
	formatDuration,
	neighborMeta,
	numberCandidates,
	visibleSuggestions
} from './format.js';

const candidate = (rank: number): Candidate => ({
	rank,
	latitude: 0,
	longitude: 0,
	score: 1,
	radius_m: null,
	kind: 'before',
	evidence: {},
	tier: 'normal'
});

const module = (id: string, count: number): ModuleSuggestions => ({
	module: id,
	version: '1',
	color: '#000',
	shape: 'circle',
	candidates: Array.from({ length: count }, (_, i) => candidate(i + 1)),
	track: [],
	cameras: [],
	status: 'ready',
	runnable: false,
	worker_available: true,
	paused: false,
	worker_loading: false,
	error: null,
	error_code: null,
	key: id,
	region: null,
	turn: 0,
	finished_at: null,
	queue_position: null,
	note: null
});

describe('suggestion formatting', () => {
	it('formats durations and deltas', () => {
		expect(formatDuration(45)).toBe('45 s');
		expect(formatDuration(-720)).toBe('12 min');
		expect(formatDuration(7500)).toBe('2 h 5 min');
		expect(formatDuration(-10_800)).toBe('3 h');
		expect(formatDelta(-240)).toBe('−4 min');
		expect(formatDelta(420)).toBe('+7 min');
	});

	it('formats distances', () => {
		expect(formatDistance(654)).toBe('650 m');
		expect(formatDistance(2345)).toBe('2.3 km');
		expect(formatDistance(20_000)).toBe('20 km');
	});

	it('gives keys 1–9 to the first nine candidates across modules', () => {
		const numbered = numberCandidates([module('a', 5), module('b', 6)]);
		expect(numbered.map((item) => item.key)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, null, null]);
		expect(numbered[5].module.module).toBe('b');
		expect(numbered[5].candidate.rank).toBe(1);
	});

	it('folds weak candidates unless their module is unfolded', () => {
		const geoclip = module('geoclip', 3);
		geoclip.candidates[2] = { ...geoclip.candidates[2], tier: 'weak' };
		const folded = visibleSuggestions([geoclip], []);
		expect(folded[0].candidates.map((c) => c.rank)).toEqual([1, 2]);
		expect(numberCandidates(folded).map((item) => item.key)).toEqual([1, 2]);
		expect(visibleSuggestions([geoclip], ['geoclip'])[0].candidates).toHaveLength(3);
	});

	it('labels similar photos by the most similar one', () => {
		const photo = (file_name: string, estimated = false): NeighborEvidence => ({
			asset_id: file_name,
			file_name,
			delta_s: -3600,
			estimated,
			similarity: 0.42,
			local_taken_at: '2019-07-14T12:00:00'
		});
		const similar = (neighbors: NeighborEvidence[]): Candidate => ({
			...candidate(1),
			kind: 'similar',
			evidence: { neighbors }
		});
		expect(candidateLabel(similar([photo('a.jpg')]))).toBe('Like a.jpg');
		expect(candidateLabel(similar([photo('a.jpg'), photo('b.jpg'), photo('c.jpg')]))).toBe(
			'Like a.jpg and 2 more'
		);
		// No camera to compare with: never "another camera".
		expect(candidateRemarks(similar([photo('a.jpg')]))).toEqual([]);
		expect(neighborMeta(photo('a.jpg'), '')).toBe('42% alike · 2019-07-14');
		expect(neighborMeta(photo('a.jpg', true), '')).toContain('set by hand');
	});

	it('describes a time neighbor by its time and camera', () => {
		const neighbor: NeighborEvidence = {
			asset_id: 'x',
			file_name: 'x.jpg',
			delta_s: -720,
			same_camera: true,
			estimated: false
		};
		expect(neighborMeta(neighbor, 'Canon EOS')).toBe(`${formatDelta(-720)} · Canon EOS`);
	});
});
