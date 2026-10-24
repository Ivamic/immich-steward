<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  Sign-in with the Immich email and password (the app then creates and keeps its own API key),
  or with an API key made by hand, e.g. for accounts that sign in to Immich through OAuth.
-->
<script lang="ts">
	import { login, loginWithPassword, type Me } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import Brand from '#lib/ui/Brand.svelte';
	import Icon from '#lib/ui/Icon.svelte';
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

<div class="login">
	<!-- A coordinate graticule fading out from the middle: the one cartographic ornament. -->
	<div class="graticule" aria-hidden="true"></div>
	<div class="card">
		<Brand large />
		<h1>{m.auth_heading()}</h1>
		<p class="intro">{m.auth_intro()}</p>

		{#if error}
			<div class="st-banner st-banner--danger" role="alert">
				<Icon name="circle-alert" />
				<span class="st-banner__body">{error}</span>
			</div>
		{/if}

		<form class="password" onsubmit={(e) => signIn(e, () => loginWithPassword(email, password))}>
			<label class="st-field">
				<span class="st-field__label">{m.auth_email()}</span>
				<input type="email" bind:value={email} autocomplete="username" required disabled={busy} />
			</label>
			<label class="st-field">
				<span class="st-field__label">{m.auth_password()}</span>
				<input
					type="password"
					bind:value={password}
					autocomplete="current-password"
					required
					disabled={busy}
				/>
			</label>
			<button
				type="submit"
				class="st-btn st-btn--primary st-btn--lg st-btn--block"
				aria-busy={busy}
				disabled={busy || !email.trim() || !password}
			>
				{#if busy}<span class="st-spin"><Icon name="loader-circle" /></span>{/if}
				{m.auth_sign_in()}
			</button>
		</form>
		<p class="note">{m.auth_password_note()}</p>

		<details>
			<summary>{m.auth_key_summary()}</summary>
			<div class="key-body">
				<p>{m.auth_key_intro()}</p>
				<form class="key" onsubmit={(e) => signIn(e, () => login(apiKey))}>
					<label class="st-field">
						<span class="st-field__label">{m.auth_api_key()}</span>
						<input
							class="mono"
							type="password"
							bind:value={apiKey}
							autocomplete="off"
							spellcheck="false"
							required
							disabled={busy}
						/>
					</label>
					<button type="submit" class="st-btn" disabled={busy || !apiKey.trim()}>
						{m.auth_sign_in()}
					</button>
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
			</div>
		</details>
	</div>
</div>

<style>
	.login {
		position: relative;
		display: grid;
		place-items: start center;
		min-height: calc(100dvh - var(--header-height) - var(--space-12));
		padding-top: var(--space-8);
	}
	.graticule {
		position: fixed;
		inset: var(--header-height) 0 0;
		background-image:
			linear-gradient(var(--color-border) 1px, transparent 1px),
			linear-gradient(90deg, var(--color-border) 1px, transparent 1px);
		background-size: 48px 48px;
		mask-image: radial-gradient(ellipse at center, #000 10%, transparent 70%);
		pointer-events: none;
	}
	.card {
		position: relative;
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		width: min(100%, 26rem);
		padding: var(--space-6);
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-surface);
		box-shadow: var(--shadow-sm);
	}
	h1 {
		margin: var(--space-2) 0 0;
	}
	.intro,
	.note {
		margin: 0;
		font-size: var(--text-sm);
		color: var(--color-text-muted);
		text-wrap: pretty;
	}
	.note {
		font-size: var(--text-xs);
	}
	form {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}
	input {
		min-height: var(--control-md);
	}
	.mono {
		font-family: var(--font-mono);
	}
	details {
		font-size: var(--text-sm);
	}
	summary {
		color: var(--color-text-muted);
	}
	summary:hover {
		color: var(--color-text);
	}
	.key-body {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		margin-top: var(--space-3);
	}
	.key-body p {
		margin: 0;
	}
	.key-body ul {
		margin: 0;
		padding-inline-start: var(--space-5);
	}
	.st-spin {
		display: inline-flex;
	}
</style>
