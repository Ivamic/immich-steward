// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { older } from './versions';

describe('older', () => {
	it('compares the numbers as numbers', () => {
		expect(older('0.5.1', '0.6.0')).toBe(true);
		expect(older('0.9.9', '0.10.0')).toBe(true);
		expect(older('0.6.0', '0.6.0')).toBe(false);
		expect(older('0.6', '0.6.0')).toBe(false);
		expect(older('v1.0.0', '0.6.3')).toBe(false);
	});

	it('puts a pre-release before its release', () => {
		expect(older('0.6.0rc2', '0.6.0')).toBe(true);
		expect(older('0.6.0-rc.1', '0.6.0rc2')).toBe(true);
		expect(older('0.6.0', '0.6.0rc2')).toBe(false);
		expect(older('0.5.9', '0.6.0rc1')).toBe(true);
	});
});
