// SPDX-License-Identifier: AGPL-3.0-or-later
// Labels for module suggestions. Modules return a kind and evidence; the text is made here so
// that it follows the interface language.
import type { Candidate, ModuleSuggestions, NeighborEvidence } from '#lib/api.js';
import { m } from '#lib/paraglide/messages.js';

/** "45 s", "12 min", "2 h 5 min" (sign is not shown). */
export function formatDuration(seconds: number): string {
	const s = Math.round(Math.abs(seconds));
	if (s < 60) return m.duration_s({ n: String(s) });
	const minutes = Math.round(s / 60);
	if (minutes < 60) return m.duration_min({ n: String(minutes) });
	const hours = String(Math.floor(minutes / 60));
	return minutes % 60
		? m.duration_h_min({ h: hours, m: String(minutes % 60) })
		: m.duration_h({ n: hours });
}

/** "−12 min" / "+5 min": time of a neighbor relative to the photo. */
export function formatDelta(seconds: number): string {
	return `${seconds < 0 ? '−' : '+'}${formatDuration(seconds)}`;
}

export function formatDistance(meters: number): string {
	if (meters < 1000) return m.distance_m({ n: String(Math.round(meters / 10) * 10) });
	const km = meters / 1000;
	return m.distance_km({ n: km < 10 ? km.toFixed(1) : String(Math.round(km)) });
}

export function moduleName(id: string): string {
	return id === 'time_neighbors' ? m.module_time_neighbors() : id;
}

export function moduleNote(note: string): string {
	switch (note) {
		case 'no_neighbors':
			return m.module_note_no_neighbors();
		case 'scanner':
			return m.module_note_scanner();
		default:
			return note;
	}
}

const neighborRef = (n: NeighborEvidence) =>
	m.neighbor_ref({ file: n.file_name, delta: formatDelta(n.delta_s) });

export function candidateLabel(candidate: Candidate): string {
	const neighbors = candidate.evidence.neighbors ?? [];
	if (candidate.kind === 'between' && neighbors.length === 2) {
		return m.candidate_between({
			before: neighborRef(neighbors[0]),
			after: neighborRef(neighbors[1])
		});
	}
	if ((candidate.kind === 'before' || candidate.kind === 'after') && neighbors.length === 1) {
		return m.candidate_same_place({ photo: neighborRef(neighbors[0]) });
	}
	return candidate.kind;
}

/** Remarks that lower trust in a candidate. */
export function candidateRemarks(candidate: Candidate): string[] {
	const neighbors = candidate.evidence.neighbors ?? [];
	const remarks: string[] = [];
	if (neighbors.some((n) => !n.same_camera)) remarks.push(m.candidate_other_camera());
	if (neighbors.some((n) => n.estimated)) remarks.push(m.candidate_estimated());
	return remarks;
}

export interface Numbered {
	module: ModuleSuggestions;
	candidate: Candidate;
	/** 1..9 for the first nine candidates in list order (keyboard shortcut), otherwise null. */
	key: number | null;
}

export function numberCandidates(modules: ModuleSuggestions[]): Numbered[] {
	return modules
		.flatMap((module) => module.candidates.map((candidate) => ({ module, candidate })))
		.map((item, index) => ({ ...item, key: index < 9 ? index + 1 : null }));
}
