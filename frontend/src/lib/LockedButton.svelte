<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- The Immich locked folder in the header, once connected in Settings: a closed lock asks for
     the PIN code (`onunlock`), an open one closes the folder. -->
<script lang="ts">
	import { locked } from '#lib/locked.svelte.js';
	import { m } from '#lib/paraglide/messages.js';
	import Icon from '#lib/ui/Icon.svelte';
	import Tooltip from '#lib/ui/Tooltip.svelte';

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

{#if locked.connected}
	{#if locked.open}
		<Tooltip text={m.locked_close()} below>
			<button
				type="button"
				class="st-iconbtn lock open"
				aria-label={m.locked_close()}
				disabled={busy}
				onclick={lock}
			>
				<Icon name="lock-open" size={16} />
			</button>
		</Tooltip>
	{:else}
		<Tooltip text={m.locked_open()} below>
			<button type="button" class="st-iconbtn lock" aria-label={m.locked_open()} onclick={onunlock}>
				<Icon name="lock" size={16} />
			</button>
		</Tooltip>
	{/if}
{/if}

<style>
	.lock.open {
		color: var(--color-warning-text);
	}
</style>
