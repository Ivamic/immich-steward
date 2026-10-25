// SPDX-License-Identifier: AGPL-3.0-or-later
// Module colors come from the theme palette (`--module-1…8`, tuned for light and dark), so that
// markers, rows and legend match in both themes. A module the app does not know yet keeps the
// color the core sends.
const SLOTS: Record<string, number> = {
	time_neighbors: 1,
	geoclip: 2,
	similar: 3,
	// The chosen photos' own locations (several photos at once, D-149).
	selection: 4
};

/** Palette slot of a module (1–8), or null for a module without one. */
export const moduleSlot = (module: string): number | null => SLOTS[module] ?? null;

/** CSS color of the module: a theme token, or the core's color as a fallback. */
export function moduleColor(module: string, fallback: string): string {
	const slot = moduleSlot(module);
	return slot ? `var(--module-${slot})` : fallback;
}

/** CSS color of text on the module color (the number on a marker). */
export function moduleOnColor(module: string): string {
	const slot = moduleSlot(module);
	return slot ? `var(--module-${slot}-on)` : 'var(--gray-0)';
}

/**
 * The color as `rgb()`, for MapLibre layers: they take neither CSS variables nor OKLCH. Read
 * from a pixel drawn with the computed color, so it follows the current theme.
 */
export function resolvedColor(css: string): string {
	if (!css.startsWith('var(')) return css;
	const name = css.slice(4, -1);
	const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
	const context = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
	if (!value || !context) return '#888888';
	context.fillStyle = value;
	context.fillRect(0, 0, 1, 1);
	const [r, g, b] = context.getImageData(0, 0, 1, 1).data;
	return `rgb(${r}, ${g}, ${b})`;
}
