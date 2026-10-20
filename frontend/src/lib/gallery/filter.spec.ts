// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { defaultFilter, failedFilter, filterFromUrl, filterToUrl } from './filter.js';

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
		expect(filter.archived).toBe(true);
		expect(filter.failure).toBeNull();
	});

	it('ignores a reason without a module', () => {
		expect(parse('failure=image_unavailable')).toEqual(defaultFilter);
	});
});
