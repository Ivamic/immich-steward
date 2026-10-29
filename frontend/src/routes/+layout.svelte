<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
	import favicon from '#lib/assets/favicon.svg';
	import { ApiError, getMe, logout } from '#lib/api.js';
	import HeaderMenu from '#lib/HeaderMenu.svelte';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import { session } from '#lib/session.svelte.js';
	import LanguageSwitcher from '#lib/LanguageSwitcher.svelte';
	import SaveNotices from '#lib/SaveNotices.svelte';
	import ThemeSwitcher from '#lib/ThemeSwitcher.svelte';
	import UpdateBadge from '#lib/UpdateBadge.svelte';
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

	const pages = $derived([
		{ href: resolve('/'), label: m.nav_gallery(), current: page.route.id === '/' },
		{
			href: resolve('/processing'),
			label: m.nav_processing(),
			current: page.route.id === '/processing'
		},
		{ href: resolve('/settings'), label: m.nav_settings(), current: page.route.id === '/settings' }
	]);

	async function signOut() {
		await logout().catch(() => {});
		session.user = null;
	}
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<title>{m.app_title()}</title>
</svelte:head>

<header class="st-header" class:st-header--menu={session.user}>
	<Brand href={session.user ? resolve('/') : undefined} />
	{#if session.user}
		<nav class="st-header__nav">
			{#each pages as item (item.href)}
				<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- resolved above -->
				<a href={item.href} aria-current={item.current ? 'page' : undefined}>{item.label}</a>
			{/each}
		</nav>
	{:else}
		<span class="tagline">{m.app_tagline()}</span>
	{/if}
	<div class="st-header__end">
		{#if session.user}
			<UpdateBadge />
			<span class="st-header__user st-header__wide">{session.user.name}</span>
			<button
				type="button"
				class="st-btn st-btn--ghost st-btn--sm st-header__wide"
				onclick={signOut}
			>
				<Icon name="log-out" size={14} />
				{m.auth_sign_out()}
			</button>
		{/if}
		<div class="st-header__wide">
			<LanguageSwitcher />
		</div>
		<div class="st-header__wide">
			<ThemeSwitcher />
		</div>
		{#if session.user}
			<HeaderMenu {pages} user={session.user.name} onsignout={signOut} />
		{/if}
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
