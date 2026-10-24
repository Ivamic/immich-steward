<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
	import favicon from '#lib/assets/favicon.svg';
	import { ApiError, getMe, logout } from '#lib/api.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import { session } from '#lib/session.svelte.js';
	import LanguageSwitcher from '#lib/LanguageSwitcher.svelte';
	import SaveNotices from '#lib/SaveNotices.svelte';
	import ThemeSwitcher from '#lib/ThemeSwitcher.svelte';
	import Brand from '#lib/ui/Brand.svelte';
	import Icon from '#lib/ui/Icon.svelte';
	import '#lib/styles/index.css';
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

<header class="st-header">
	<Brand href={session.user ? resolve('/') : undefined} />
	{#if session.user}
		<nav class="st-header__nav">
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
	<div class="st-header__end">
		{#if session.user}
			<span class="st-header__user">{session.user.name}</span>
			<button type="button" class="st-btn st-btn--ghost st-btn--sm" onclick={signOut}>
				<Icon name="log-out" size={14} />
				{m.auth_sign_out()}
			</button>
		{/if}
		<LanguageSwitcher />
		<ThemeSwitcher />
	</div>
</header>

<main class:wide={page.route.id === '/' || page.route.id === '/photo/[id]'}>
	{#if session.checked}
		{@render children()}
	{/if}
</main>

<SaveNotices />

<style>
	.tagline {
		color: var(--color-text-muted);
		font-size: var(--text-sm);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	main {
		max-width: 48rem;
		margin: 0 auto;
		padding: var(--space-6);
	}
	main.wide {
		max-width: none;
	}
</style>
