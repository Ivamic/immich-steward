// SPDX-License-Identifier: AGPL-3.0-or-later
// The suggestion under the pointer, shared by the list and the map (FR-32).

export interface Highlight {
	/** Key of the block (`ModuleSuggestions.key`). */
	module: string;
	rank: number;
	/** Where the pointer is: the list scrolls only for markers hovered on the map. */
	from: 'list' | 'map';
}
