// SPDX-License-Identifier: AGPL-3.0-or-later
// The way back from a photo opened on a page of the groups that is no group of its own (turned
// photos, the trash, the candidates): the photo page takes it in `from`, so that "Back" and Esc
// lead there and not to the gallery. Only these pages are known: a link cannot send the user
// anywhere else.

/** The page a photo was opened from, as the `from` parameter of its address. */
export type BackTo =
	| 'turned'
	| 'turned:1'
	| 'turned:2'
	| 'turned:3'
	| 'turned:kept'
	| 'trash'
	| 'candidates'
	| 'candidates:scattered';

const PAGES = {
	turned: '/groups/turned',
	'turned:1': '/groups/turned?turn=1',
	'turned:2': '/groups/turned?turn=2',
	'turned:3': '/groups/turned?turn=3',
	'turned:kept': '/groups/turned?view=kept',
	trash: '/groups?view=trash',
	candidates: '/groups/candidates',
	'candidates:scattered': '/groups/candidates?tab=scattered'
} as const satisfies Record<BackTo, string>;

/** The path to go back to (for `resolve`), or null when `from` names no known page. */
export function backPath(from: string | null): (typeof PAGES)[BackTo] | null {
	return from !== null && Object.hasOwn(PAGES, from) ? PAGES[from as BackTo] : null;
}

/** The query of a photo opened from `from`. */
export const fromQuery = (from: BackTo): `?from=${string}` => `?from=${encodeURIComponent(from)}`;
