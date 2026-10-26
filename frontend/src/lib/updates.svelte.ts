// SPDX-License-Identifier: AGPL-3.0-or-later
// Whether a newer release of the app is out, shared by the badge in the header and the section in
// Settings. The badge can be closed: it stays closed for that version, in this browser.
import { getUpdates, type Updates } from '#lib/api.js';

const DISMISSED_KEY = 'steward-update-dismissed';

function readDismissed(): string | null {
	try {
		return localStorage.getItem(DISMISSED_KEY);
	} catch {
		return null;
	}
}

class UpdateState {
	info = $state<Updates | null>(null);
	dismissed = $state<string | null>(readDismissed());

	/** The version to offer in the header, if any. */
	get offered(): string | null {
		const info = this.info;
		if (!info?.enabled || !info.newer || !info.latest) return null;
		return info.latest === this.dismissed ? null : info.latest;
	}

	load() {
		getUpdates()
			.then((info) => (this.info = info))
			.catch(() => {});
	}

	dismiss(version: string) {
		this.dismissed = version;
		try {
			localStorage.setItem(DISMISSED_KEY, version);
		} catch {
			// Blocked storage: closed until the page is reloaded.
		}
	}
}

export const updates = new UpdateState();
