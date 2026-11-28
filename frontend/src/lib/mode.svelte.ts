// SPDX-License-Identifier: AGPL-3.0-or-later
// How the app is used (D-253, D-254): "work" — finding and checking places, everything shown;
// "view" — looking at the library, the tools of the work out of the way. A personal setting of
// the account; the browser keeps the last one too, so that a page opens in it before the
// settings arrive.
import { accountSettings } from '#lib/accountSettings.svelte.js';
import type { UiMode } from '#lib/api.js';

const KEY = 'steward.mode';

function remembered(): UiMode | null {
	try {
		const value = globalThis.localStorage?.getItem(KEY);
		return value === 'view' || value === 'work' ? value : null;
	} catch {
		return null;
	}
}

function remember(value: UiMode) {
	try {
		globalThis.localStorage?.setItem(KEY, value);
	} catch {
		// private mode: the setting of the account is enough
	}
}

class ModeState {
	#loaded = $state(false);
	#early = remembered();

	/** The mode now: the account's, or until it is known the one this browser last had. */
	get current(): UiMode {
		return this.#loaded ? accountSettings.values.ui_mode : (this.#early ?? 'work');
	}

	get viewing(): boolean {
		return this.current === 'view';
	}

	load(): Promise<void> {
		return accountSettings.load().then(() => {
			this.#loaded = true;
			remember(accountSettings.values.ui_mode);
		});
	}

	/** Switches at once; the account keeps it (back to the old one if that fails). */
	async set(value: UiMode): Promise<void> {
		const before = accountSettings.values;
		accountSettings.values = { ...before, ui_mode: value };
		this.#loaded = true;
		remember(value);
		try {
			await accountSettings.set({ ui_mode: value });
		} catch (e) {
			accountSettings.values = before;
			remember(before.ui_mode);
			throw e;
		}
	}
}

export const mode = new ModeState();
