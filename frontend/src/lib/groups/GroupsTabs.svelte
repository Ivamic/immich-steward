<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- The tabs of the Groups pages: the groups of photos of one view ("Environment"), and the photos
     that look turned (D-237), with how many there are. -->
<script lang="ts">
	import { getTurned } from '#lib/api.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import { resolve } from '$app/paths';

	let {
		current,
		turned = null
	}: {
		current: 'environment' | 'turned';
		/** How many photos look turned, when the page knows it already. */
		turned?: number | null;
	} = $props();

	let fetched = $state<number | null>(null);
	const count = $derived(turned ?? fetched);
	const number = new Intl.NumberFormat(getLocale());

	$effect(() => {
		if (turned !== null) return;
		getTurned(null, 0, 1)
			.then((answer) => (fetched = answer.groups.reduce((sum, g) => sum + g.total, 0)))
			.catch(() => (fetched = null));
	});
</script>

<nav class="tabs">
	<a href={resolve('/groups')} aria-current={current === 'environment' ? 'page' : undefined}>
		{m.groups_tab_environment()}
	</a>
	<a href={resolve('/groups/turned')} aria-current={current === 'turned' ? 'page' : undefined}>
		{m.turned_title()}
		{#if count !== null}<span class="count">{number.format(count)}</span>{/if}
	</a>
</nav>

<style>
	.tabs {
		display: flex;
		gap: var(--space-4);
		margin-bottom: var(--space-4);
		border-bottom: 1px solid var(--color-border);
	}
	.tabs a {
		padding: var(--space-2) var(--space-1);
		margin-bottom: -1px;
		border-bottom: 2px solid transparent;
		color: var(--color-text-muted);
		text-decoration: none;
	}
	.tabs a[aria-current='page'] {
		border-bottom-color: var(--color-accent);
		color: var(--color-text);
		font-weight: var(--weight-medium);
	}
	.count {
		margin-left: var(--space-1);
		color: var(--color-text-muted);
		font-size: var(--text-sm);
		font-weight: normal;
	}
</style>
