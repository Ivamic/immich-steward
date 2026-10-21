// SPDX-License-Identifier: AGPL-3.0-or-later
// Keyboard shortcuts that work whatever the keyboard layout.

/**
 * The shortcut a key press stands for: the typed letter or digit when it is a Latin one
 * (so that Z on a French keyboard is still Z), otherwise the key at that place on an English
 * keyboard (so that "к" on a Russian one is R). Named keys come as is: "enter", "arrowleft"...
 */
export function shortcutKey(event: Pick<KeyboardEvent, 'key' | 'code'>): string {
	const key = event.key.toLowerCase();
	if (key.length > 1 || /^[a-z0-9]$/.test(key)) return key;
	if (/^Key[A-Z]$/.test(event.code)) return event.code.slice(3).toLowerCase();
	if (/^(Digit|Numpad)[0-9]$/.test(event.code)) return event.code.slice(-1);
	// Square brackets: "х" and "ъ" on a Russian keyboard.
	if (event.code === 'BracketLeft') return '[';
	if (event.code === 'BracketRight') return ']';
	return key;
}
