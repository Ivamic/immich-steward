// SPDX-License-Identifier: AGPL-3.0-or-later
// The gallery filter lives in the page URL, so that a filtered view can be bookmarked and
// survives going to a photo and back.
import type { GalleryFilter } from '#lib/api.js';

export const defaultFilter: GalleryFilter = {
	view: 'todo',
	type: 'all',
	camera: null,
	album: null,
	date_from: null,
	date_to: null,
	archived: false
};

const oneOf = <T extends string>(value: string | null, allowed: readonly T[], fallback: T): T =>
	allowed.includes(value as T) ? (value as T) : fallback;

export function filterFromUrl(params: Pick<URLSearchParams, 'get'>): GalleryFilter {
	return {
		view: oneOf(
			params.get('view'),
			['todo', 'with', 'skipped', 'not_applicable', 'all'] as const,
			defaultFilter.view
		),
		type: oneOf(params.get('type'), ['all', 'image', 'video'] as const, defaultFilter.type),
		camera: params.get('camera'),
		album: params.get('album'),
		date_from: params.get('date_from'),
		date_to: params.get('date_to'),
		archived: params.get('archived') === 'true'
	};
}

export type FilterQuery = `?${string}`;

/** URL query for the page: like the API query, but `view` is always explicit. */
export function filterToUrl(filter: GalleryFilter): FilterQuery {
	const params = new URLSearchParams();
	params.set('view', filter.view);
	if (filter.type !== 'all') params.set('type', filter.type);
	if (filter.camera !== null) params.set('camera', filter.camera);
	if (filter.album) params.set('album', filter.album);
	if (filter.date_from) params.set('date_from', filter.date_from);
	if (filter.date_to) params.set('date_to', filter.date_to);
	if (filter.archived) params.set('archived', 'true');
	return `?${params}`;
}
