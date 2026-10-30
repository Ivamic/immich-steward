// SPDX-License-Identifier: AGPL-3.0-or-later
// Endless lists: an element at the end of the list asks for more when it comes near the screen.
import type { Action } from 'svelte/action';

interface NearScreen {
	/** What is shown so far: when it changes and the element is still near, it asks again. */
	at: number;
	onnear: () => void;
}

export const nearScreen: Action<HTMLElement, NearScreen> = (node, params) => {
	let onnear = params.onnear;
	const observer = new IntersectionObserver(
		(entries) => {
			if (entries.some((entry) => entry.isIntersecting)) onnear();
		},
		{ rootMargin: '800px' }
	);
	observer.observe(node);
	return {
		update(next) {
			onnear = next.onnear;
			observer.unobserve(node);
			observer.observe(node);
		},
		destroy() {
			observer.disconnect();
		}
	};
};
