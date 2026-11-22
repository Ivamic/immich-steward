// SPDX-License-Identifier: AGPL-3.0-or-later
// Worker schedules (D-238): 7 numbers, Monday first, bit `h` for the hour h:00-h:59, by the
// clock of the server.
import type { ServerClock } from '#lib/api.js';

export const DAYS = 7;
export const HOURS = 24;
export const FULL_DAY = 2 ** HOURS - 1;

// Languages whose week starts on Sunday (of the ones the app speaks).
const SUNDAY_FIRST = new Set(['en']);

/** The days (0 = Monday) in the order the language shows a week. */
export function dayOrder(locale: string): number[] {
	const monday = [0, 1, 2, 3, 4, 5, 6];
	return SUNDAY_FIRST.has(locale.split('-')[0]) ? [6, ...monday.slice(0, 6)] : monday;
}

/** Short names of the days, 0 = Monday. */
export function weekdayNames(locale: string): string[] {
	const format = new Intl.DateTimeFormat(locale, { weekday: 'short', timeZone: 'UTC' });
	// 2026-11-23 is a Monday.
	return Array.from({ length: DAYS }, (_, i) => format.format(Date.UTC(2026, 10, 23 + i)));
}

/** The time on the server's clock now: a Date whose UTC fields show it, and its day and hour. */
export function serverNow(clock: ServerClock, now = Date.now()) {
	const date = new Date(now + clock.utc_offset_min * 60_000);
	return { date, day: (date.getUTCDay() + 6) % 7, hour: date.getUTCHours() };
}

/** A moment (ISO) as the server's clock shows it, e.g. "Tue 07:00" (the day only if not today). */
export function serverTime(iso: string, clock: ServerClock, locale: string, now = Date.now()) {
	const at = serverNow(clock, new Date(iso).getTime());
	const today = serverNow(clock, now);
	const time = new Intl.DateTimeFormat(locale, {
		hour: '2-digit',
		minute: '2-digit',
		timeZone: 'UTC'
	}).format(at.date);
	const sameDay = at.date.toISOString().slice(0, 10) === today.date.toISOString().slice(0, 10);
	return sameDay ? time : `${weekdayNames(locale)[at.day]} ${time}`;
}
