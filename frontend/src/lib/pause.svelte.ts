// SPDX-License-Identifier: AGPL-3.0-or-later
// Paused background runs of worker modules, shared by the workers panel and the pause bars.
import { getPause, resumeAll, setPause, type Pause } from '#lib/api.js';

class PauseState {
	all = $state(false);
	modules = $state<string[]>([]);

	get any(): boolean {
		return this.all || this.modules.length > 0;
	}

	isPaused(module: string): boolean {
		return this.all || this.modules.includes(module);
	}

	update(pause: Pause) {
		this.all = pause.all;
		this.modules = pause.modules;
	}

	async load() {
		this.update(await getPause());
	}

	async set(module: string | null, paused: boolean) {
		this.update(await setPause(module, paused));
	}

	async resume() {
		this.update(await resumeAll());
	}
}

export const pause = new PauseState();
