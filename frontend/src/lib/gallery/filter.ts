// SPDX-License-Identifier: AGPL-3.0-or-later
// The gallery filter lives in the page URL, so that a filtered view can be bookmarked and
// survives going to a photo and back.
import {
	inclusionOf,
	inclusionParam,
	SHOW_CATEGORIES,
	type GalleryFilter,
	type UiMode
} from '#lib/api.js';

export const defaultFilter: GalleryFilter = {
	show: ['todo'],
	type: 'all',
	camera: null,
	album: null,
	date_from: null,
	date_to: null,
	archived: 'off',
	locked_folder: 'off',
	geoclip_confident: false,
	similar_confident: false,
	details_confirmed: false,
	nearby: false,
	little_background: false,
	failed_module: null,
	failure: null,
	order: 'newest'
};

/** The gallery of the mode "view" (D-254): the whole library, without the filters of the work. */
export const viewFilter: GalleryFilter = { ...defaultFilter, show: [...SHOW_CATEGORIES] };

export const defaultFilterOf = (mode: UiMode): GalleryFilter =>
	mode === 'view' ? viewFilter : defaultFilter;

/** The filter as the mode shows it: in "view", what only the work filters by (what to show, the
 * hints, the failed runs) is off, also when the URL came from the mode "work". */
export function forMode(filter: GalleryFilter, mode: UiMode): GalleryFilter {
	if (mode === 'work') return filter;
	return {
		...filter,
		show: [...SHOW_CATEGORIES],
		geoclip_confident: false,
		similar_confident: false,
		details_confirmed: false,
		nearby: false,
		little_background: false,
		failed_module: null,
		failure: null
	};
}

const oneOf = <T extends string>(value: string | null, allowed: readonly T[], fallback: T): T =>
	allowed.includes(value as T) ? (value as T) : fallback;

export function filterFromUrl(
	params: Pick<URLSearchParams, 'get' | 'getAll'>,
	mode: UiMode = 'work'
): GalleryFilter {
	// Kept in a fixed order, so that equal filters give equal URLs.
	const show = SHOW_CATEGORIES.filter((category) => params.getAll('show').includes(category));
	return forMode(fromUrl(params, show.length ? show : defaultFilterOf(mode).show), mode);
}

function fromUrl(
	params: Pick<URLSearchParams, 'get' | 'getAll'>,
	show: GalleryFilter['show']
): GalleryFilter {
	return {
		show,
		type: oneOf(params.get('type'), ['all', 'image', 'video'] as const, defaultFilter.type),
		camera: params.get('camera'),
		album: params.get('album'),
		date_from: params.get('date_from'),
		date_to: params.get('date_to'),
		archived: inclusionOf(params.get('archived')),
		locked_folder: inclusionOf(params.get('locked_folder')),
		geoclip_confident: params.get('geoclip_confident') === 'true',
		similar_confident: params.get('similar_confident') === 'true',
		details_confirmed: params.get('details_confirmed') === 'true',
		nearby: params.get('nearby') === 'true',
		little_background: params.get('little_background') === 'true',
		failed_module: params.get('failed_module'),
		failure: params.get('failed_module') ? params.get('failure') : null,
		order: oneOf(params.get('order'), ['newest', 'oldest'] as const, defaultFilter.order)
	};
}

/** Every photo, whatever its review status, whose latest run of the module failed so. */
export const failedFilter = (module: string, failure: string | null = null): GalleryFilter => ({
	...defaultFilter,
	show: [...SHOW_CATEGORIES],
	archived: 'with',
	failed_module: module,
	failure
});

export type FilterQuery = `?${string}`;

/** Gallery URL query that opens the timeline at this photo, like Immich's `?at=`. */
export const atPhoto = (query: FilterQuery, id: string): FilterQuery =>
	`${query}${query.length > 1 ? '&' : ''}at=${encodeURIComponent(id)}`;

/** URL query for the page: like the API query, but `show` is always explicit. */
export function filterToUrl(filter: GalleryFilter): FilterQuery {
	const params = new URLSearchParams();
	for (const category of filter.show) params.append('show', category);
	if (filter.type !== 'all') params.set('type', filter.type);
	if (filter.camera !== null) params.set('camera', filter.camera);
	if (filter.album) params.set('album', filter.album);
	if (filter.date_from) params.set('date_from', filter.date_from);
	if (filter.date_to) params.set('date_to', filter.date_to);
	for (const key of ['archived', 'locked_folder'] as const) {
		const value = inclusionParam(filter[key]);
		if (value) params.set(key, value);
	}
	if (filter.geoclip_confident) params.set('geoclip_confident', 'true');
	if (filter.similar_confident) params.set('similar_confident', 'true');
	if (filter.details_confirmed) params.set('details_confirmed', 'true');
	if (filter.nearby) params.set('nearby', 'true');
	if (filter.little_background) params.set('little_background', 'true');
	if (filter.failed_module) {
		params.set('failed_module', filter.failed_module);
		if (filter.failure) params.set('failure', filter.failure);
	}
	if (filter.order === 'oldest') params.set('order', 'oldest');
	return `?${params}`;
}

/** The gallery at a photo with the whole library shown ("Show in the timeline", like Immich): the
 * archive and the locked folder taken in when the photo is there. */
export function timelineAt(
	id: string,
	place: { archived?: boolean; locked?: boolean } = {}
): FilterQuery {
	const filter: GalleryFilter = {
		...viewFilter,
		archived: place.archived ? 'with' : 'off',
		locked_folder: place.locked ? 'with' : 'off'
	};
	return atPhoto(filterToUrl(filter), id);
}

/** How many filters differ from the default ones: the count on the filter button of a phone. */
export function activeFilters(filter: GalleryFilter, mode: UiMode = 'work'): number {
	const defaults = defaultFilterOf(mode);
	const fields: (keyof GalleryFilter)[] = [
		'type',
		'camera',
		'album',
		'archived',
		'locked_folder',
		'geoclip_confident',
		'similar_confident',
		'details_confirmed',
		'nearby',
		'little_background',
		'failed_module'
	];
	const changed = fields.filter((field) => filter[field] !== defaults[field]).length;
	const shown = filter.show.join() !== defaults.show.join() ? 1 : 0;
	const period = filter.date_from || filter.date_to ? 1 : 0;
	return changed + shown + period;
}
