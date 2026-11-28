// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { SHOW_CATEGORIES } from '#lib/api.js';
import {
	activeFilters,
	defaultFilter,
	failedFilter,
	filterFromUrl,
	filterToUrl,
	timelineAt,
	viewFilter
} from './filter.js';

const parse = (query: string) => filterFromUrl(new URLSearchParams(query));

describe('gallery filter in the URL', () => {
	it('keeps the failed photos filter', () => {
		const filter = failedFilter('geoclip', 'image_unavailable');
		expect(parse(filterToUrl(filter))).toEqual(filter);
		expect(filterToUrl(filter)).toContain('failed_module=geoclip&failure=image_unavailable');
	});

	it('shows every group, archived photos included, for failed photos', () => {
		const filter = failedFilter('geoclip');
		expect(filter.show).toEqual(['todo', 'with', 'skipped', 'not_applicable']);
		expect(filter.archived).toBe('with');
		expect(filter.failure).toBeNull();
	});

	it('keeps the three states of the archive and the locked folder', () => {
		expect(parse('archived=true').archived).toBe('with');
		expect(parse('archived=only&locked_folder=true')).toMatchObject({
			archived: 'only',
			locked_folder: 'with'
		});
		const filter = { ...defaultFilter, archived: 'only' as const, locked_folder: 'with' as const };
		expect(filterToUrl(filter)).toContain('archived=only&locked_folder=true');
		expect(parse(filterToUrl(filter))).toEqual(filter);
		expect(parse('archived=maybe').archived).toBe('off');
	});

	it('ignores a reason without a module', () => {
		expect(parse('failure=image_unavailable')).toEqual(defaultFilter);
	});
});

describe('activeFilters', () => {
	it('counts what differs from the default filter, a period once', () => {
		expect(activeFilters(defaultFilter)).toBe(0);
		expect(
			activeFilters({
				...defaultFilter,
				show: ['todo', 'with'],
				type: 'video',
				date_from: '2024-01-01',
				date_to: '2024-02-01'
			})
		).toBe(3);
	});
});

describe('the modes of the app (D-254)', () => {
	it('shows the whole library by default while looking at it', () => {
		expect(filterFromUrl(new URLSearchParams(''), 'view').show).toEqual([...SHOW_CATEGORIES]);
		expect(filterFromUrl(new URLSearchParams(''), 'work').show).toEqual(['todo']);
	});

	it('drops the filters of the work from a URL of the mode "work"', () => {
		const work = filterToUrl({
			...defaultFilter,
			show: ['skipped'],
			similar_confident: true,
			failed_module: 'geoclip',
			camera: 'Canon|EOS'
		});
		const viewed = filterFromUrl(new URLSearchParams(work), 'view');
		expect(viewed).toEqual({ ...viewFilter, camera: 'Canon|EOS' });
		expect(activeFilters(viewed, 'view')).toBe(1);
		expect(activeFilters(viewFilter, 'view')).toBe(0);
	});

	it('opens the timeline at a photo with the whole library', () => {
		const at = timelineAt('p1');
		expect(at).toBe(`${filterToUrl(viewFilter)}&at=p1`);
		const archived = filterFromUrl(
			new URLSearchParams(timelineAt('p2', { archived: true, locked: true })),
			'view'
		);
		expect(archived.archived).toBe('with');
		expect(archived.locked_folder).toBe('with');
		expect(archived.show).toEqual([...SHOW_CATEGORIES]);
	});
});
