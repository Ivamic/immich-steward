// SPDX-License-Identifier: AGPL-3.0-or-later
// HTML markers over the map: module suggestions (shape × color × number) and pins (the picked
// point, the location in Immich). Styles: `.st-marker`, `.st-pin` (styles/components/map.css).

/** A photo shown as a point on the map; `chosen` marks it, `apart` tells it from the others. */
export interface MapDot {
	id: string;
	lat: number;
	lon: number;
	chosen: boolean;
	apart?: boolean;
}

// Shapes on a 28 × 28 grid. Shape tells modules apart without relying on color (FR-31).
const SHAPES: Record<string, string> = {
	circle: '<circle cx="14" cy="14" r="12"/>',
	ring: '<circle cx="14" cy="14" r="11"/>',
	square: '<rect x="2.5" y="2.5" width="23" height="23" rx="5"/>',
	diamond: '<path d="M14 0.8 27.2 14 14 27.2 0.8 14Z" stroke-linejoin="round"/>',
	triangle: '<path d="M14 1.5 27 25.5H1Z" stroke-linejoin="round"/>',
	hexagon: '<path d="M14 1 25.5 7.5v13L14 27 2.5 20.5v-13Z" stroke-linejoin="round"/>',
	pentagon: '<path d="M14 1.2 26.8 10.5 21.9 26H6.1L1.2 10.5Z" stroke-linejoin="round"/>',
	shield:
		'<path d="M3.5 2.5h21v11.5c0 6.5-5 10.5-10.5 12.5C8.5 24.5 3.5 20.5 3.5 14Z" stroke-linejoin="round"/>'
};

const shapeOf = (shape: string) => (shape in SHAPES ? shape : 'circle');

/** The marker drawing: halo (highlight), outline (selected) and the shape itself. */
export function shapeSvg(shape: string): string {
	const figure = SHAPES[shapeOf(shape)];
	const withClass = (cls: string, extra = '') =>
		figure.replace(/^<(\w+)/, `<$1 class="${cls}"${extra}`);
	return (
		'<svg viewBox="0 0 28 28" aria-hidden="true">' +
		withClass('st-marker__halo') +
		withClass('st-marker__sel', ' transform="translate(14 14) scale(1.28) translate(-14 -14)"') +
		withClass('st-marker__shape') +
		'</svg>'
	);
}

/**
 * A suggestion marker. The outer element is the one MapLibre positions (with a transform), so
 * the hover and highlight scaling is done on the inner one.
 */
export function markerElement(options: {
	shape: string;
	number: number;
	color: string;
	on: string;
	part: boolean;
	weak: boolean;
	label: string;
}): HTMLDivElement {
	const outer = document.createElement('div');
	outer.className = 'steward-candidate';
	const marker = document.createElement('span');
	marker.className = `st-marker st-marker--${shapeOf(options.shape)}`;
	if (options.part) marker.classList.add('st-marker--part');
	if (options.weak) {
		marker.dataset.weak = 'true';
		marker.dataset.state = 'weak';
	}
	marker.style.setProperty('--_c', options.color);
	marker.style.setProperty('--_on', options.on);
	marker.setAttribute('role', 'img');
	marker.setAttribute('aria-label', options.label);
	marker.innerHTML = shapeSvg(options.shape);
	const number = document.createElement('span');
	number.className = 'st-marker__num';
	number.textContent = String(options.number);
	marker.append(number);
	outer.append(marker);
	return outer;
}

/** The picked point (dark, green dot) or the location stored in Immich (grey). */
export function pinElement(variant: 'picked' | 'current', label: string): HTMLDivElement {
	const outer = document.createElement('div');
	const pin = document.createElement('span');
	pin.className = variant === 'current' ? 'st-pin st-pin--current' : 'st-pin';
	pin.setAttribute('role', 'img');
	pin.setAttribute('aria-label', label);
	pin.innerHTML =
		'<svg viewBox="0 0 28 36" aria-hidden="true">' +
		'<path class="st-pin__body" d="M14 1.5C7.1 1.5 1.5 6.9 1.5 13.6 1.5 22.5 14 34.5 14 34.5S26.5 22.5 26.5 13.6C26.5 6.9 20.9 1.5 14 1.5Z"/>' +
		'<circle class="st-pin__dot" cx="14" cy="13.5" r="4.5"/>' +
		'</svg>';
	outer.append(pin);
	return outer;
}
