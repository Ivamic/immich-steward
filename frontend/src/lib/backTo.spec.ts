// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';

import { backPath, fromQuery } from './backTo.js';

describe('the way back from a photo', () => {
	it('leads to the page and the filter it was opened from', () => {
		expect(backPath('turned')).toBe('/groups/turned');
		expect(backPath('turned:3')).toBe('/groups/turned?turn=3');
		expect(backPath('turned:kept')).toBe('/groups/turned?view=kept');
		expect(backPath('trash')).toBe('/groups?view=trash');
		expect(backPath('candidates:scattered')).toBe('/groups/candidates?tab=scattered');
	});

	it('knows no other place', () => {
		for (const from of [null, '', 'https://example.org', '//example.org', '/groups', 'toString']) {
			expect(backPath(from)).toBeNull();
		}
	});

	it('goes along with the photo', () => {
		expect(fromQuery('turned:1')).toBe('?from=turned%3A1');
	});
});
