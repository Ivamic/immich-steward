// SPDX-License-Identifier: AGPL-3.0-or-later
import { getLocale } from '#lib/paraglide/runtime.js';

/** "August 2019", "Август 2019 г.": only the first letter is raised (not "2019 Г."). */
export function monthTitle(month: string): string {
	const text = new Intl.DateTimeFormat(getLocale(), { month: 'long', year: 'numeric' }).format(
		new Date(`${month}-01T00:00:00`)
	);
	return text.charAt(0).toLocaleUpperCase(getLocale()) + text.slice(1);
}

/** When a photo was taken, by the camera clock: "Sun, 12 May 2024, 14:37". The time has no zone
 * (D-045), so it is read and shown as local time, unchanged. */
export function takenTitle(localTakenAt: string): string {
	return new Intl.DateTimeFormat(getLocale(), {
		weekday: 'short',
		day: 'numeric',
		month: 'long',
		year: 'numeric',
		hour: '2-digit',
		minute: '2-digit'
	}).format(new Date(localTakenAt.replace(/Z|[+-]\d\d:\d\d$/, '')));
}
