// SPDX-License-Identifier: AGPL-3.0-or-later
// Matching typed text against names in a list: any part of the name, whatever the case and the
// accents ("zab" finds "Žabljak", "ежик" finds "Ёжик").

/** Lower case without accents: what the typed text and the names are compared as. */
export function foldText(text: string): string {
	return text.toLocaleLowerCase().normalize('NFD').replace(/\p{M}/gu, '');
}

/** Whether the name contains every word typed, in any order. */
export function matches(name: string, query: string): boolean {
	const folded = foldText(name);
	return foldText(query)
		.split(/\s+/)
		.filter(Boolean)
		.every((word) => folded.includes(word));
}
