<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
	import { login } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { session } from '#lib/session.svelte.js';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';

	// Keep in sync with REQUIRED_PERMISSIONS in core/src/steward/immich/compat.py.
	const permissions = [
		'user.read',
		'asset.read',
		'asset.view',
		'asset.update',
		'album.read',
		'tag.read',
		'tag.create',
		'tag.asset'
	];

	let apiKey = $state('');
	let busy = $state(false);
	let error = $state<string | null>(null);

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		error = null;
		try {
			session.user = await login(apiKey);
			apiKey = '';
			await goto(resolve('/'));
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}
</script>

<h1>{m.auth_heading()}</h1>
<p>{m.auth_intro()}</p>

<form onsubmit={submit}>
	<label>
		{m.auth_api_key()}
		<input
			type="password"
			bind:value={apiKey}
			autocomplete="off"
			spellcheck="false"
			required
			disabled={busy}
		/>
	</label>
	<button type="submit" disabled={busy || !apiKey.trim()}>{m.auth_sign_in()}</button>
</form>

{#if error}
	<p class="error" role="alert">{error}</p>
{/if}

<details>
	<summary>{m.auth_help_summary()}</summary>
	<p>{m.auth_help_steps()}</p>
	<p>{m.auth_help_permissions()}</p>
	<ul>
		{#each permissions as permission (permission)}
			<li><code>{permission}</code></li>
		{/each}
	</ul>
	<p>{m.auth_help_storage()}</p>
</details>

<style>
	form {
		display: flex;
		gap: 0.75rem;
		align-items: end;
		flex-wrap: wrap;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		flex: 1;
		min-width: 16rem;
	}
	.error {
		color: #cf222e;
	}
	details {
		margin-top: 2rem;
	}
</style>
