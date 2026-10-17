// SPDX-License-Identifier: AGPL-3.0-or-later
// Parsing and formatting of coordinates typed or pasted by the user.

export interface LatLon {
	lat: number;
	lon: number;
}

const valid = ({ lat, lon }: LatLon) =>
	Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;

// 42°25'29.7"N 18°46'16.8"E, also with ′ ″ and spaces; minutes and seconds are optional.
const DMS =
	/(\d+(?:[.,]\d+)?)\s*°\s*(?:(\d+(?:[.,]\d+)?)\s*['′]\s*)?(?:(\d+(?:[.,]\d+)?)\s*(?:"|″|'')\s*)?([NSEWСЮВЗ])/giu;

const num = (s: string | undefined) => (s ? Number(s.replace(',', '.')) : 0);

function parseDms(text: string): LatLon | null {
	const parts = [...text.matchAll(DMS)];
	if (parts.length !== 2) return null;
	let lat: number | null = null;
	let lon: number | null = null;
	for (const [, deg, min, sec, hemi] of parts) {
		const value = num(deg) + num(min) / 60 + num(sec) / 3600;
		const h = hemi.toUpperCase();
		if (h === 'N' || h === 'С') lat = value;
		else if (h === 'S' || h === 'Ю') lat = -value;
		else if (h === 'E' || h === 'В') lon = value;
		else lon = -value;
	}
	return lat === null || lon === null ? null : { lat, lon };
}

/** "42.4249, 18.7713", "42.4249 18.7713", "42,4249; 18,7713" or degrees-minutes-seconds. */
export function parseCoordinates(text: string): LatLon | null {
	const trimmed = text.trim();
	if (!trimmed) return null;
	if (/[°NSEWСЮВЗ]/iu.test(trimmed)) {
		const dms = parseDms(trimmed);
		return dms && valid(dms) ? dms : null;
	}
	// Two decimal numbers; a comma inside a number is a decimal separator only if the
	// numbers themselves are separated by a semicolon or whitespace.
	const separatedBySemicolon = trimmed.includes(';');
	const numbers = separatedBySemicolon
		? trimmed.split(';').map((s) => s.trim().replace(',', '.'))
		: trimmed.split(/[\s,]+/).filter(Boolean);
	if (numbers.length !== 2) return null;
	const [lat, lon] = numbers.map(Number);
	const point = { lat, lon };
	return valid(point) ? point : null;
}

export const formatCoordinates = ({ lat, lon }: LatLon) => `${lat.toFixed(6)}, ${lon.toFixed(6)}`;
