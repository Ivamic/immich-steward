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

	it('takes Shift + slash as "?" in any layout', () => {
		expect(shortcutKey({ key: '?', code: 'Slash', shiftKey: true })).toBe('?');
		expect(shortcutKey({ key: ',', code: 'Slash', shiftKey: true })).toBe('?');
		expect(shortcutKey({ key: '.', code: 'Slash' })).toBe('.');
	});

	it('takes "?", "[" and "]" as typed wherever their key is', () => {
		// German keyboard: AltGr + 8 and 9; French: Shift + the key at the place of M.
		expect(shortcutKey({ key: '[', code: 'Digit8' })).toBe('[');
		expect(shortcutKey({ key: ']', code: 'Digit9' })).toBe(']');
		expect(shortcutKey({ key: '?', code: 'KeyM', shiftKey: true })).toBe('?');
		// Russian keyboard: Shift + 7.
		expect(shortcutKey({ key: '?', code: 'Digit7', shiftKey: true })).toBe('?');
	});

	it('keeps named keys', () => {
		expect(shortcutKey({ key: 'Enter', code: 'Enter' })).toBe('enter');
		expect(shortcutKey({ key: 'ArrowLeft', code: 'ArrowLeft' })).toBe('arrowleft');
	});
});
