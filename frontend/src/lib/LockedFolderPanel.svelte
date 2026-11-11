<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Settings: connecting the Immich locked folder with the password once, or disconnecting it
     (D-216). Opening and closing the folder is in the header. -->
<script lang="ts">
	import { connectLocked, disconnectLocked, getLocked, type LockedState } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import Icon from '#lib/ui/Icon.svelte';

	let folder = $state<LockedState | null>(null);
	let password = $state('');
	let busy = $state(false);
	let error = $state('');
	// Known right after connecting only: Immich is not asked each time the page opens.
	let noPin = $state(false);

	const day = new Intl.DateTimeFormat(getLocale(), { dateStyle: 'long' });

	$effect(() => {
		getLocked()
			.then((result) => (folder = result))
			.catch((e) => (error = errorMessage(e)));
	});

	async function connect(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		error = '';
		try {
			const result = await connectLocked(password);
			folder = result;
			noPin = !result.has_pin;
			password = '';
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	async function disconnect() {
		busy = true;
		error = '';
		try {
			folder = await disconnectLocked();
			noPin = false;
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}
</script>

<section aria-busy={busy}>
	<h2>{m.locked_heading()}</h2>
	<p class="hint">{m.locked_hint()}</p>
	{#if folder?.connected}
		<p>
			{m.locked_connected({
				date: folder.connected_at ? day.format(new Date(folder.connected_at)) : ''
			})}
		</p>
		<p class="hint">{m.locked_idle({ minutes: String(folder.idle_minutes) })}</p>
		{#if noPin}
			<p class="warning" role="status">
				<Icon name="triangle-alert" size={14} />{m.locked_no_pin()}
			</p>
		{/if}
		<div>
			<button type="button" class="st-btn st-btn--sm" disabled={busy} onclick={disconnect}>
				{m.locked_disconnect()}
			</button>
		</div>
	{:else if folder}
		<form onsubmit={connect}>
			<label class="st-field">
				<span class="st-field__label">{m.locked_password()}</span>
				<input
					type="password"
					bind:value={password}
					autocomplete="current-password"
					required
					disabled={busy}
				/>
			</label>
			<button type="submit" class="st-btn st-btn--sm" aria-busy={busy} disabled={busy || !password}>
				{#if busy}<span class="st-spin"><Icon name="loader-circle" size={14} /></span>{/if}
				{m.locked_connect()}
			</button>
		</form>
		<p class="hint">{m.locked_password_note()}</p>
	{/if}
	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
</section>

<style>
	section {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		margin-bottom: var(--space-10);
	}
	h2,
	p {
		margin: 0;
	}
	.hint {
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	form {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-end;
		gap: var(--space-3);
	}
	form .st-field {
		flex: 1 1 14rem;
	}
	.warning {
		display: flex;
		gap: var(--space-2);
		align-items: baseline;
		color: var(--color-warning-text);
	}
	.error {
		color: var(--color-danger-text);
	}
</style>
