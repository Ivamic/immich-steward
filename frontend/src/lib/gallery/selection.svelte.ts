// SPDX-License-Identifier: AGPL-3.0-or-later
// Photos chosen in the gallery for an action on all of them (D-149). Kept while the gallery is
// open; a change of the filter starts over.
import type { AssetItem } from '#lib/api.js';
import { SvelteMap } from 'svelte/reactivity';

export class Selection {
	/** Chosen photos by id, in the order they were chosen. */
	items = new SvelteMap<string, AssetItem>();
	/** The photo clicked last: Shift + click chooses everything between it and the next one. */
	anchor = $state<string | null>(null);

	get size(): number {
		return this.items.size;
	}

	get ids(): string[] {
		return [...this.items.keys()];
	}

	/** Chosen photos that already have a location. */
	get located(): number {
		return [...this.items.values()].filter((item) => item.has_location).length;
	}

	get videos(): number {
		return [...this.items.values()].filter((item) => item.type === 'VIDEO').length;
	}

	has(id: string): boolean {
		return this.items.has(id);
	}

	toggle(item: AssetItem) {
		if (this.items.has(item.id)) this.items.delete(item.id);
		else this.items.set(item.id, item);
		this.anchor = item.id;
	}

	/** Chooses the photos from the anchor to `item` in `ordered` (the gallery as shown). */
	extend(item: AssetItem, ordered: AssetItem[]) {
		const from = ordered.findIndex((i) => i.id === this.anchor);
		const to = ordered.findIndex((i) => i.id === item.id);
		if (from < 0 || to < 0) {
			this.toggle(item);
			return;
		}
		for (const i of ordered.slice(Math.min(from, to), Math.max(from, to) + 1)) {
			this.items.set(i.id, i);
		}
		this.anchor = item.id;
	}

	/** Chooses all of the photos (a whole day), or unchooses them all. */
	setAll(items: AssetItem[], chosen: boolean) {
		for (const item of items) {
			if (chosen) this.items.set(item.id, item);
			else this.items.delete(item.id);
		}
		if (items.length) this.anchor = items.at(-1)!.id;
	}

	clear() {
		this.items.clear();
		this.anchor = null;
	}
}

/** Bumped when photos changed in a way the gallery shows (location, status, thumbnails): the
 * loaded months fetch their photos again. */
export const galleryChanges = $state({ count: 0 });

export function galleryChanged() {
	galleryChanges.count++;
}
