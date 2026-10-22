// SPDX-License-Identifier: AGPL-3.0-or-later
// Paused background runs of worker modules, shared by the workers panel and the pause bars.
import { getPause, resumeAll, setPause, type Pause } from '#lib/api.js';
import { getLocale } from '#lib/paraglide/runtime.js';

class PauseState {
	all = $state(false);
	modules = $state<string[]>([]);
	/** When the pause of all modules ends by itself; null: until resumed. */
	allUntil = $state<string | null>(null);
	/** Module -> when its pause ends by itself (absent: until resumed). */
	until = $state<Record<string, string>>({});

	get any(): boolean {
		return this.all || this.modules.length > 0;
	}

	isPaused(module: string): boolean {
		return this.all || this.modules.includes(module);
	}

	/** When the pause of the module ends: of all modules, if they are all paused. */
	untilOf(module: string): string | null {
		return this.all ? this.allUntil : (this.until[module] ?? null);
	}

	update(pause: Pause) {
		this.all = pause.all;
		this.modules = pause.modules;
		this.allUntil = pause.all_until;
		this.until = pause.until;
	}

	async load() {
		this.update(await getPause());
	}

	/** `minutes`: a pause that ends by itself; null: until resumed. */
	async set(module: string | null, paused: boolean, minutes: number | null = null) {
		this.update(await setPause(module, paused, minutes));
	}

	async resume() {
		this.update(await resumeAll());
	}
}

export const pause = new PauseState();

/** The lengths of a pause offered, in minutes; null: until resumed. */
export const PAUSE_LENGTHS: (number | null)[] = [null, 30, 60, 12 * 60, 24 * 60];

const time = new Intl.DateTimeFormat(getLocale(), { timeStyle: 'short' });
const dayAndTime = new Intl.DateTimeFormat(getLocale(), {
	weekday: 'short',
	hour: '2-digit',
	minute: '2-digit'
});

/** The end of a pause: the time today, with the day of the week later. */
export function formatUntil(iso: string): string {
	const date = new Date(iso);
	return date.toDateString() === new Date().toDateString()
		? time.format(date)
		: dayAndTime.format(date);
}
