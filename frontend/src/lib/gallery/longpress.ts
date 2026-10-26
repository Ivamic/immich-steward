// SPDX-License-Identifier: AGPL-3.0-or-later
// A long press on a gallery tile (mouse or touch) shows a large preview; a short one opens the
// photo card as before. Moving the pointer first is scrolling or dragging, not a press.
import type { Action } from 'svelte/action';

export const LONG_PRESS_MS = 400;
// More movement than this (px) before the press fires cancels it.
const MOVE_TOLERANCE = 8;

export const longpress: Action<HTMLElement, () => void> = (node, onlong) => {
	let fire = onlong;
	let timer: ReturnType<typeof setTimeout> | undefined;
	let start: { x: number; y: number } | null = null;
	// The press fired: the click and the context menu that follow it belong to it.
	let fired = false;

	function cancel() {
		clearTimeout(timer);
		start = null;
	}

	function down(event: PointerEvent) {
		if (event.button !== 0 || event.shiftKey || event.ctrlKey || event.metaKey) return;
		fired = false;
		start = { x: event.clientX, y: event.clientY };
		clearTimeout(timer);
		timer = setTimeout(() => {
			start = null;
			fired = true;
			fire?.();
		}, LONG_PRESS_MS);
	}

	function move(event: PointerEvent) {
		if (start && Math.hypot(event.clientX - start.x, event.clientY - start.y) > MOVE_TOLERANCE)
			cancel();
	}

	function swallow(event: Event) {
		if (!fired) return;
		event.preventDefault();
		event.stopPropagation();
	}

	function click(event: MouseEvent) {
		swallow(event);
		fired = false;
	}

	node.addEventListener('pointerdown', down);
	node.addEventListener('pointermove', move);
	node.addEventListener('pointerup', cancel);
	node.addEventListener('pointercancel', cancel);
	node.addEventListener('pointerleave', cancel);
	// Capture: before the tile's own click handler opens the card.
	node.addEventListener('click', click, true);
	node.addEventListener('contextmenu', swallow);
	node.addEventListener('dragstart', swallow);

	return {
		update(next) {
			fire = next;
		},
		destroy() {
			cancel();
			node.removeEventListener('pointerdown', down);
			node.removeEventListener('pointermove', move);
			node.removeEventListener('pointerup', cancel);
			node.removeEventListener('pointercancel', cancel);
			node.removeEventListener('pointerleave', cancel);
			node.removeEventListener('click', click, true);
			node.removeEventListener('contextmenu', swallow);
			node.removeEventListener('dragstart', swallow);
		}
	};
};
