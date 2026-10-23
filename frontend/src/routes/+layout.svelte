<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
	import favicon from '#lib/assets/favicon.svg';
	import { ApiError, getMe, logout } from '#lib/api.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import { session } from '#lib/session.svelte.js';
	import LanguageSwitcher from '#lib/LanguageSwitcher.svelte';
	import SaveNotices from '#lib/SaveNotices.svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	const loginPath = resolve('/login');

	$effect(() => {
		document.documentElement.lang = getLocale();
	});

	$effect(() => {
		getMe()
			.then((user) => (session.user = user))
			.catch((error) => {
				session.user = null;
				if (!(error instanceof ApiError && error.status === 401)) console.error(error);
			})
			.finally(() => (session.checked = true));
	});

	// Everything except the sign-in page requires a signed-in user.
	$effect(() => {
		if (session.checked && !session.user && page.url.pathname !== loginPath) {
			goto(loginPath);
		}
	});

	async function signOut() {
		await logout().catch(() => {});
		session.user = null;
	}
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<title>{m.app_title()}</title>
</svelte:head>

<header>
	<div class="brand">
		<strong>{m.app_title()}</strong>
		{#if session.user}
			<nav>
				<a href={resolve('/')} aria-current={page.route.id === '/' ? 'page' : undefined}>
					{m.nav_gallery()}
				</a>
				<a
					href={resolve('/processing')}
					aria-current={page.route.id === '/processing' ? 'page' : undefined}
				>
					{m.nav_processing()}
				</a>
				<a
					href={resolve('/settings')}
					aria-current={page.route.id === '/settings' ? 'page' : undefined}
				>
					{m.nav_settings()}
				</a>
			</nav>
		{:else}
			<span class="tagline">{m.app_tagline()}</span>
		{/if}
	</div>
	<div class="actions">
		{#if session.user}
			<span>{session.user.name}</span>
			<button type="button" onclick={signOut}>{m.auth_sign_out()}</button>
		{/if}
		<LanguageSwitcher />
	</div>
</header>

<main class:wide={page.route.id === '/' || page.route.id === '/photo/[id]'}>
	{#if session.checked}
		{@render children()}
	{/if}
</main>

<SaveNotices />

<style>
	:global(body) {
		margin: 0;
		font-family: system-ui, sans-serif;
		color: #1f2328;
		background: #f6f8fa;
	}
	@media (prefers-color-scheme: dark) {
		:global(body) {
			color: #e6edf3;
			background: #0d1117;
		}
	}
	/* Stays in view: from far down the gallery the menu is one click away. */
	header {
		position: sticky;
		top: 0;
		z-index: 20;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.75rem 1.5rem;
		border-bottom: 1px solid color-mix(in srgb, currentColor 15%, transparent);
		background: #f6f8fa;
	}
	@media (prefers-color-scheme: dark) {
		header {
			background: #0d1117;
		}
	}
	.tagline {
		margin-left: 0.75rem;
		opacity: 0.7;
	}
	.actions {
		display: flex;
		align-items: center;
		gap: 1rem;
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 1.5rem;
	}
	nav {
		display: flex;
		gap: 1rem;
	}
	nav a {
		color: inherit;
		text-decoration: none;
		opacity: 0.75;
	}
	nav a[aria-current='page'] {
		opacity: 1;
		font-weight: 600;
		text-decoration: underline;
	}
	main {
		max-width: 48rem;
		margin: 0 auto;
		padding: 1.5rem;
	}
	main.wide {
		max-width: none;
	}
</style>
