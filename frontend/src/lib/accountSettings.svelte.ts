// SPDX-License-Identifier: AGPL-3.0-or-later
// Personal settings of the signed-in account, loaded once and shared by the pages that use them.
import { getAccountSettings, setAccountSettings, type AccountSettings } from '#lib/api.js';

const DEFAULTS: AccountSettings = {
	gallery_tooltip: true,
	video_sound: false,
	groups_similarity: 0.4,
	groups_core_neighbors: 3,
	groups_mutual: true
};

class AccountSettingsState {
	values = $state<AccountSettings>({ ...DEFAULTS });
	#loading: Promise<void> | null = null;

	load(): Promise<void> {
		this.#loading ??= getAccountSettings()
			.then((values) => {
				this.values = values;
			})
			.catch(() => {
				this.#loading = null; // the defaults until it works
			});
		return this.#loading;
	}

	async set(change: Partial<AccountSettings>): Promise<void> {
		this.values = await setAccountSettings(change);
	}
}

export const accountSettings = new AccountSettingsState();
