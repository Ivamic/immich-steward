// SPDX-License-Identifier: AGPL-3.0-or-later
// The Immich locked folder of the account (D-216), shared by the header, its menu and Settings.
// While it is open, a click or key press in the app keeps it open (told to the core at most once
// a minute); background requests do not. The core closes it after the idle time, so an open
// tab looks once a minute whether it is still open.
import {
	closeLocked,
	disconnectLocked,
	getLocked,
	lockedActivity,
	openLocked,
	type LockedState
} from '#lib/api.js';

const ACTIVITY_EVERY_MS = 60_000;
const CHECK_EVERY_MS = 60_000;

class Locked {
	state = $state<LockedState | null>(null);
	/** Changes whenever the folder opens or closes: pages that show locked photos reload. */
	version = $state(0);
	/** The PIN window is open (from the header, its menu or a page). */
	asking = $state(false);
	#lastActivity = 0;

	get connected(): boolean {
		return !!this.state?.connected;
	}

	get open(): boolean {
		return !!this.state?.open;
	}

	#set(state: LockedState) {
		if (this.state && this.state.open !== state.open) this.version++;
		this.state = state;
	}

	load() {
		getLocked()
			.then((state) => this.#set(state))
			.catch(() => {});
	}

	/** Throws an ApiError (wrong PIN, paused, ...) for the caller to show. */
	async unlock(pinCode: string) {
		this.#set(await openLocked(pinCode));
		this.#lastActivity = Date.now();
	}

	async lock() {
		this.#set(await closeLocked());
	}

	/** Settings after connecting or disconnecting. */
	replace(state: LockedState) {
		this.#set(state);
	}

	async disconnect() {
		this.#set(await disconnectLocked());
	}

	/** A click or key press of the user anywhere in the app. */
	activity() {
		if (!this.open || Date.now() - this.#lastActivity < ACTIVITY_EVERY_MS) return;
		this.#lastActivity = Date.now();
		lockedActivity()
			.then((state) => this.#set(state))
			.catch(() => {});
	}

	/** Watches the state while signed in: returns the cleanup. */
	watch(): () => void {
		this.load();
		const onAction = () => this.activity();
		window.addEventListener('pointerdown', onAction, { capture: true, passive: true });
		window.addEventListener('keydown', onAction, { capture: true, passive: true });
		const timer = setInterval(() => {
			if (this.open) this.load();
		}, CHECK_EVERY_MS);
		return () => {
			window.removeEventListener('pointerdown', onAction, { capture: true });
			window.removeEventListener('keydown', onAction, { capture: true });
			clearInterval(timer);
		};
	}
}

export const locked = new Locked();
