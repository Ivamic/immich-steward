// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { dayOrder, serverNow, serverTime, weekdayNames } from './schedule';

const berlinWinter = { zone: 'Europe/Berlin', utc_offset_min: 60 };
// Monday 2026-11-23, 22:30 UTC.
const mondayNight = Date.UTC(2026, 10, 23, 22, 30);

describe('worker schedule', () => {
	it('starts the week as the language does', () => {
		expect(dayOrder('ru')).toEqual([0, 1, 2, 3, 4, 5, 6]);
		expect(dayOrder('de')).toEqual([0, 1, 2, 3, 4, 5, 6]);
		expect(dayOrder('en')).toEqual([6, 0, 1, 2, 3, 4, 5]);
	});

	it('names the days from Monday', () => {
		const names = weekdayNames('en');
		expect(names[0]).toBe('Mon');
		expect(names[6]).toBe('Sun');
	});

	it('reads the hour on the server clock', () => {
		expect(serverNow(berlinWinter, mondayNight)).toMatchObject({ day: 0, hour: 23 });
		// An hour later it is Tuesday in Berlin, still Monday in UTC.
		const later = serverNow(berlinWinter, mondayNight + 3_600_000);
		expect([later.day, later.hour]).toEqual([1, 0]);
		expect(serverNow({ zone: null, utc_offset_min: 0 }, mondayNight).hour).toBe(22);
	});

	it('shows the time of a change, with the day when it is not today', () => {
		const sevenTuesday = new Date(Date.UTC(2026, 10, 24, 6)).toISOString();
		expect(serverTime(sevenTuesday, berlinWinter, 'en', mondayNight - 3_600_000)).toBe(
			'Tue 07:00 AM'
		);
		const elevenMonday = new Date(Date.UTC(2026, 10, 23, 22)).toISOString();
		expect(serverTime(elevenMonday, berlinWinter, 'ru', mondayNight - 3_600_000)).toBe('23:00');
	});
});
