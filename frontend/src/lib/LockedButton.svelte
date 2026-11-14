<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- The Immich locked folder in the header: not connected, a faint lock that leads to its place in
     Settings and says what to do; connected, a closed lock asks for the PIN code (`onunlock`), and
     an open one, on a colored background, closes the folder. -->
<script lang="ts">
	import { locked } from '#lib/locked.svelte.js';
	import { m } from '#lib/paraglide/messages.js';
	import Icon from '#lib/ui/Icon.svelte';
	import Tooltip from '#lib/ui/Tooltip.svelte';
	import { resolve } from '$app/paths';

	let { onunlock }: { onunlock: () => void } = $props();

	let busy = $state(false);

	async function lock() {
		busy = true;
		try {
			await locked.lock();
		} catch {
			// Closed by the core anyway; the state comes with the next check.
		} finally {
			busy = false;
		}
	}
</script>

{#if locked.state && !locked.connected}
	<Tooltip text={m.locked_setup_hint()} below>
		<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- resolved, with the section -->
		<a
			class="st-iconbtn lock off"
			href="{resolve('/settings')}#locked"
			aria-label={m.locked_setup_hint()}
		>
			<Icon name="lock" size={16} />
		</a>
	</Tooltip>
{:else if locked.open}
	<Tooltip text={m.locked_is_open()} below>
		<button
			type="button"
			class="st-iconbtn lock open"
			aria-label={m.locked_is_open()}
			disabled={busy}
			onclick={lock}
		>
			<Icon name="lock-open" size={16} />
		</button>
	</Tooltip>
{:else if locked.connected}
	<Tooltip text={m.locked_is_closed()} below>
		<button
			type="button"
			class="st-iconbtn lock"
			aria-label={m.locked_is_closed()}
			onclick={onunlock}
		>
			<Icon name="lock" size={16} />
		</button>
	</Tooltip>
{/if}

<style>
	/* Not connected: there, but not asking for attention. */
	.lock.off {
		opacity: 0.45;
	}
	.lock.off:hover {
		opacity: 1;
	}
	/* Open: the locked photos are visible, so it stands out until closed. */
	.lock.open {
		background: var(--color-warning-subtle);
		color: var(--color-warning-text);
		box-shadow: inset 0 0 0 1px var(--color-warning);
	}
</style>
