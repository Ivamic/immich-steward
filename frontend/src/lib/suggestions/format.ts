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

/** Why a module run failed; the core sends one of these codes (newer ones are shown as is). */
export const FAILURE_CODES = [
	'image_unavailable',
	'immich_auth',
	'image_invalid',
	'module_error',
	'worker_error',
	'lease_expired'
] as const;

/** Whose trouble a failure is: the photo (or Immich), the worker or the module itself. */
export const FAILURE_GROUPS = [
	{ group: 'photo', codes: ['image_unavailable', 'immich_auth', 'image_invalid'] },
	{ group: 'worker', codes: ['worker_error', 'lease_expired'] },
	{ group: 'module', codes: ['module_error'] }
] as const satisfies readonly { group: string; codes: readonly (typeof FAILURE_CODES)[number][] }[];

export type FailureGroup = (typeof FAILURE_GROUPS)[number]['group'];

export function failureGroup(code: string | null): FailureGroup {
	return (
		FAILURE_GROUPS.find((g) => (g.codes as readonly string[]).includes(code ?? ''))?.group ??
		'module'
	);
}

export function failureGroupName(group: FailureGroup): string {
	switch (group) {
		case 'photo':
			return m.failure_group_photo();
		case 'worker':
			return m.failure_group_worker();
		default:
			return m.failure_group_module();
	}
}

export function failureReason(code: string | null): string {
	switch (code) {
		case 'image_unavailable':
			return m.failure_image_unavailable();
		case 'immich_auth':
			return m.failure_immich_auth();
		case 'image_invalid':
			return m.failure_image_invalid();
		case 'module_error':
		case null:
			return m.failure_module_error();
		case 'worker_error':
			return m.failure_worker_error();
		case 'lease_expired':
			return m.failure_lease_expired();
		default:
			return code;
	}
}

export function moduleName(id: string): string {
	switch (id) {
		case 'time_neighbors':
			return m.module_time_neighbors();
		case 'geoclip':
			return m.module_geoclip();
		case 'similar':
			return m.module_similar();
		case 'selection':
			return m.module_selection();
		default:
			return id;
	}
}

/** Shown when a finished run of the module has nothing to suggest. */
export function noCandidates(id: string): string {
	return id === 'similar' ? m.module_similar_none() : m.module_no_candidates();
}

/** Second line under a neighbor's thumbnail: how it relates to the photo. */
export function neighborMeta(neighbor: NeighborEvidence, camera: string): string {
	const parts =
		neighbor.similarity === undefined
			? [formatDelta(neighbor.delta_s), camera || m.device_unknown()]
			: [
					m.neighbor_similarity({ percent: String(Math.round(neighbor.similarity * 100)) }),
					neighbor.local_taken_at?.slice(0, 10) ?? ''
				];
	if (neighbor.estimated) parts.push(m.candidate_estimated());
	return parts.filter(Boolean).join(' · ');
}

export function moduleNote(note: string): string {
	switch (note) {
		case 'no_neighbors':
			return m.module_note_no_neighbors();
		case 'scanner':
			return m.module_note_scanner();
		case 'none_located':
			return m.module_note_none_located();
		default:
			return note;
	}
}

const neighborRef = (n: NeighborEvidence) =>
	m.neighbor_ref({ file: n.file_name, delta: formatDelta(n.delta_s) });

export function candidateLabel(candidate: Candidate): string {
	const label = singleLabel(candidate);
	// Several chosen photos with the same suggestion (D-149).
	const photos = candidate.evidence.photos;
	return candidate.kind !== 'selected' && typeof photos === 'number' && photos > 1
		? m.candidate_photos({ label, count: photos })
		: label;
}

function singleLabel(candidate: Candidate): string {
	const neighbors = candidate.evidence.neighbors ?? [];
	if (candidate.kind === 'selected') {
		const photos = typeof candidate.evidence.photos === 'number' ? candidate.evidence.photos : 1;
		return photos === 1 && neighbors.length
			? m.candidate_selected_one({ file: neighbors[0].file_name })
			: m.candidate_selected({ count: photos });
	}
	if (candidate.kind === 'between' && neighbors.length === 2) {
		return m.candidate_between({
			before: neighborRef(neighbors[0]),
			after: neighborRef(neighbors[1])
		});
	}
	if ((candidate.kind === 'before' || candidate.kind === 'after') && neighbors.length === 1) {
		return m.candidate_same_place({ photo: neighborRef(neighbors[0]) });
	}
	if (candidate.kind === 'area') return m.candidate_area();
	if (candidate.kind === 'similar' && neighbors.length) {
		const file = neighbors[0].file_name;
		return neighbors.length > 1
			? m.candidate_similar_more({ file, count: String(neighbors.length - 1) })
			: m.candidate_similar({ file });
	}
	return candidate.kind;
}

/** Longer explanation shown on hover, if the candidate has one. */
export function candidateDetails(candidate: Candidate): string | undefined {
	if (candidate.kind === 'area' && typeof candidate.evidence.points === 'number') {
		return m.candidate_area_details({ points: String(candidate.evidence.points) });
	}
	if (candidate.kind === 'similar') {
		const count = String(candidate.evidence.neighbors?.length ?? 0);
		return m.candidate_similar_details({ count });
	}
	return undefined;
}

/** Remarks that lower trust in a candidate. */
export function candidateRemarks(candidate: Candidate): string[] {
	const neighbors = candidate.evidence.neighbors ?? [];
	const remarks: string[] = [];
	if (neighbors.some((n) => n.same_camera === false)) remarks.push(m.candidate_other_camera());
	if (neighbors.some((n) => n.estimated)) remarks.push(m.candidate_estimated());
	return remarks;
}

/** The modules shown in the card: hidden ones only once revealed there. */
export function displayedModules(
	modules: ModuleSuggestions[],
	revealed: string[]
): ModuleSuggestions[] {
	return modules.filter((module) => !module.hidden || revealed.includes(module.module));
}

/** Modules hidden in the card and not revealed, each once. */
export function hiddenModules(modules: ModuleSuggestions[], revealed: string[]): string[] {
	const ids = modules.filter((m) => m.hidden && !revealed.includes(m.module)).map((m) => m.module);
	return [...new Set(ids)];
}

/** Suggestions as shown: weak candidates only for the modules the user unfolded. */
export function visibleSuggestions(
	modules: ModuleSuggestions[],
	unfolded: string[]
): ModuleSuggestions[] {
	return modules.map((module) =>
		unfolded.includes(module.key)
			? module
			: { ...module, candidates: module.candidates.filter((c) => c.tier !== 'weak') }
	);
}

export interface Numbered {
	module: ModuleSuggestions;
	candidate: Candidate;
	/** 1, 2, 3… through all the modules in list order: shown in the list and on the map. */
	number: number;
	/** The same number for the first nine candidates (keyboard shortcut), otherwise null. */
	key: number | null;
}

export function numberCandidates(modules: ModuleSuggestions[]): Numbered[] {
	return modules
		.flatMap((module) => module.candidates.map((candidate) => ({ module, candidate })))
		.map((item, index) => ({ ...item, number: index + 1, key: index < 9 ? index + 1 : null }));
}

/** The module whose recognition on a part of the photo the R key starts. */
export const PART_KEY_MODULE = 'geoclip';

/** "Canon EOS 550D" rather than "Canon Canon EOS 550D": many models already name the make. */
export function cameraName(make: string | null, model: string | null): string {
	if (make && model?.toLowerCase().startsWith(make.toLowerCase())) return model;
	return [make, model].filter(Boolean).join(' ');
}
