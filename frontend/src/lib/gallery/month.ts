// SPDX-License-Identifier: AGPL-3.0-or-later
import { getLocale } from '#lib/paraglide/runtime.js';

/** "August 2019", "Август 2019 г.": only the first letter is raised (not "2019 Г."). */
export function monthTitle(month: string): string {
	const text = new Intl.DateTimeFormat(getLocale(), { month: 'long', year: 'numeric' }).format(
		new Date(`${month}-01T00:00:00`)
	);
	return text.charAt(0).toLocaleUpperCase(getLocale()) + text.slice(1);
}
