// SPDX-License-Identifier: AGPL-3.0-or-later
// Copies text also where the app is opened over plain HTTP at a LAN address, the usual case at
// home: browsers give `navigator.clipboard` only to secure pages (HTTPS or localhost), so there
// the old `execCommand('copy')` on a hidden text field is used, which still works on a click.

/** Copies the text; false when the browser refused both ways (then let the user press Ctrl+C). */
export async function copyText(text: string): Promise<boolean> {
	if (globalThis.isSecureContext && navigator.clipboard) {
		try {
			await navigator.clipboard.writeText(text);
			return true;
		} catch {
			// Denied (e.g. the page is not focused): try the old way.
		}
	}
	return copyWithCommand(text);
}

function copyWithCommand(text: string): boolean {
	const field = document.createElement('textarea');
	field.value = text;
	field.setAttribute('readonly', '');
	// Off screen, but not display:none, which cannot be selected.
	field.style.position = 'fixed';
	field.style.top = '-1000px';
	field.style.opacity = '0';
	document.body.append(field);
	const focused = document.activeElement as HTMLElement | null;
	field.select();
	let copied: boolean;
	try {
		copied = document.execCommand('copy');
	} catch {
		copied = false;
	}
	field.remove();
	focused?.focus?.();
	return copied;
}
