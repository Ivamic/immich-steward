<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
	import favicon from '#lib/assets/favicon.svg';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import LanguageSwitcher from '#lib/LanguageSwitcher.svelte';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	$effect(() => {
		document.documentElement.lang = getLocale();
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<title>{m.app_title()}</title>
</svelte:head>

<header>
	<div>
		<strong>{m.app_title()}</strong>
		<span class="tagline">{m.app_tagline()}</span>
	</div>
	<LanguageSwitcher />
</header>

<main>
	{@render children()}
</main>

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
	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.75rem 1.5rem;
		border-bottom: 1px solid color-mix(in srgb, currentColor 15%, transparent);
	}
	.tagline {
		margin-left: 0.75rem;
		opacity: 0.7;
	}
	main {
		max-width: 48rem;
		margin: 0 auto;
		padding: 1.5rem;
	}
</style>
