<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  Sign-in with the Immich email and password (the app then creates and keeps its own API key),
  or with an API key made by hand, e.g. for accounts that sign in to Immich through OAuth.
-->
<script lang="ts">
	import { login, loginWithPassword, type Me } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { session } from '#lib/session.svelte.js';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';

	// Keep in sync with REQUIRED_PERMISSIONS and OPTIONAL_PERMISSIONS in
	// core/src/steward/immich/compat.py.
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
	const optionalPermissions: [string, () => string][] = [
		['asset.download', m.auth_help_optional_download],
		['asset.edit.get', m.auth_help_optional_edit],
		['asset.edit.create', m.auth_help_optional_edit],
		['asset.edit.delete', m.auth_help_optional_edit]
	];

	let email = $state('');
	let password = $state('');
	let apiKey = $state('');
	let busy = $state(false);
	let error = $state<string | null>(null);

	async function signIn(event: SubmitEvent, request: () => Promise<Me>) {
		event.preventDefault();
		busy = true;
		error = null;
		try {
			session.user = await request();
			password = '';
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

<form class="password" onsubmit={(e) => signIn(e, () => loginWithPassword(email, password))}>
	<label>
		{m.auth_email()}
		<input type="email" bind:value={email} autocomplete="username" required disabled={busy} />
	</label>
	<label>
		{m.auth_password()}
		<input
			type="password"
			bind:value={password}
			autocomplete="current-password"
			required
			disabled={busy}
		/>
	</label>
	<button type="submit" disabled={busy || !email.trim() || !password}>{m.auth_sign_in()}</button>
</form>
<p class="muted">{m.auth_password_note()}</p>

{#if error}
	<p class="error" role="alert">{error}</p>
{/if}

<details>
	<summary>{m.auth_key_summary()}</summary>
	<p>{m.auth_key_intro()}</p>
	<form class="key" onsubmit={(e) => signIn(e, () => login(apiKey))}>
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
	<p>{m.auth_help_steps()}</p>
	<p>{m.auth_help_permissions()}</p>
	<ul>
		{#each permissions as permission (permission)}
			<li><code>{permission}</code></li>
		{/each}
		{#each optionalPermissions as [permission, purpose] (permission)}
			<li><code>{permission}</code> — {purpose()}</li>
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
		min-width: 14rem;
	}
	.muted {
		opacity: 0.7;
		font-size: 0.9rem;
	}
	.error {
		color: #cf222e;
	}
	details {
		margin-top: 2rem;
	}
</style>
