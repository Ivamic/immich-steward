// SPDX-License-Identifier: AGPL-3.0-or-later
// The tooltip of a tile (`TileTooltip`): asked for when a mouse rests on it.
import type { AssetItem } from '#lib/api.js';
import type { Action } from 'svelte/action';

// The tooltip waits a moment, so that moving across the grid does not flash it.
const DELAY_MS = 400;

export type Tip = { item: AssetItem; anchor: DOMRect } | null;

interface HoverTip {
	item: AssetItem;
	/** Off (a personal setting): the tile shows the file name by itself. */
	enabled: boolean;
	ontip: (tip: Tip) => void;
}

export const hoverTip: Action<HTMLElement, HoverTip> = (node, params) => {
	let current = params;
	let timer: ReturnType<typeof setTimeout> | undefined;
	let shown = false;

	function enter(event: PointerEvent) {
		if (!current.enabled || event.pointerType !== 'mouse') return;
		clearTimeout(timer);
		timer = setTimeout(() => {
			shown = true;
			current.ontip({ item: current.item, anchor: node.getBoundingClientRect() });
		}, DELAY_MS);
	}

	function leave() {
		clearTimeout(timer);
		shown = false;
		current.ontip(null);
	}

	node.addEventListener('pointerenter', enter);
	node.addEventListener('pointerleave', leave);
	node.addEventListener('pointerdown', leave);
	return {
		update(next) {
			current = next;
		},
		destroy() {
			clearTimeout(timer);
			if (shown) current.ontip(null);
		}
	};
};
