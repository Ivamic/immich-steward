// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { shortcutKey } from './keys.js';

describe('shortcut keys', () => {
	it('takes Latin letters and digits as typed', () => {
		expect(shortcutKey({ key: 'R', code: 'KeyR' })).toBe('r');
		// French keyboard: the key at the place of W types Z.
		expect(shortcutKey({ key: 'z', code: 'KeyW' })).toBe('z');
		expect(shortcutKey({ key: '3', code: 'Digit3' })).toBe('3');
	});

	it('maps other layouts to the English one', () => {
		expect(shortcutKey({ key: 'к', code: 'KeyR' })).toBe('r');
		expect(shortcutKey({ key: 'Ы', code: 'KeyS' })).toBe('s');
		// French keyboard without Shift: "&" on the key of 1.
		expect(shortcutKey({ key: '&', code: 'Digit1' })).toBe('1');
		expect(shortcutKey({ key: 'х', code: 'BracketLeft' })).toBe('[');
		expect(shortcutKey({ key: 'ъ', code: 'BracketRight' })).toBe(']');
		expect(shortcutKey({ key: ']', code: 'BracketRight' })).toBe(']');
	});

	it('keeps named keys', () => {
		expect(shortcutKey({ key: 'Enter', code: 'Enter' })).toBe('enter');
		expect(shortcutKey({ key: 'ArrowLeft', code: 'ArrowLeft' })).toBe('arrowleft');
	});
});
