<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Asks for the PIN code of the Immich locked folder, from the header or its menu. -->
<script lang="ts">
	import { errorMessage } from '#lib/errors.js';
	import { locked } from '#lib/locked.svelte.js';
	import { m } from '#lib/paraglide/messages.js';
	import Dialog from '#lib/ui/Dialog.svelte';
	import Icon from '#lib/ui/Icon.svelte';

	let { onclose }: { onclose: () => void } = $props();

	let pin = $state('');
	let busy = $state(false);
	let error = $state('');
	let input: HTMLInputElement | undefined = $state();

	async function unlock(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		error = '';
		try {
			await locked.unlock(pin);
			onclose();
		} catch (e) {
			error = errorMessage(e);
			pin = '';
		} finally {
			busy = false;
		}
		// Enabled again only now: ready for the next try.
		if (error) setTimeout(() => input?.focus());
	}
</script>

<Dialog title={m.locked_open()} icon="lock" {onclose}>
	<form id="locked-pin" onsubmit={unlock}>
		<label class="st-field">
			<span class="st-field__label">{m.locked_pin()}</span>
			<!-- svelte-ignore a11y_autofocus -->
			<input
				type="password"
				inputmode="numeric"
				autocomplete="off"
				bind:this={input}
				bind:value={pin}
				required
				disabled={busy}
				autofocus
			/>
		</label>
		{#if error}
			<p class="error" role="alert">{error}</p>
		{/if}
		<p class="hint">{m.locked_pin_note()}</p>
	</form>
	{#snippet footer()}
		<button type="button" class="st-btn" onclick={onclose}>{m.save_cancel()}</button>
		<button
			type="submit"
			form="locked-pin"
			class="st-btn st-btn--primary"
			aria-busy={busy}
			disabled={busy || !pin}
		>
			{#if busy}<span class="st-spin"><Icon name="loader-circle" size={14} /></span>{/if}
			{m.locked_open_button()}
		</button>
	{/snippet}
</Dialog>

<style>
	form {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}
	p {
		margin: 0;
	}
	.hint {
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	.error {
		color: var(--color-danger-text);
	}
</style>
