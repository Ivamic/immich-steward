<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
	import { getMonths, type GalleryFilter, type MonthBucket } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import FilterBar from '#lib/gallery/FilterBar.svelte';
	import MonthSection from '#lib/gallery/MonthSection.svelte';
	import Scrubber from '#lib/gallery/Scrubber.svelte';
	import { filterFromUrl, filterToUrl } from '#lib/gallery/filter.js';
	import { m } from '#lib/paraglide/messages.js';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';

	let months = $state<MonthBucket[] | null>(null);
	let error = $state<string | null>(null);
	let width = $state(0);
	let timeline = $state<HTMLElement>();

	const filter = $derived(filterFromUrl(page.url.searchParams));
	const query = $derived(filterToUrl(filter));
	const total = $derived(months?.reduce((sum, b) => sum + b.count, 0) ?? 0);

	$effect(() => {
		const current = filter;
		months = null;
		error = null;
		getMonths(current)
			.then((result) => (months = result))
			.catch((e) => (error = errorMessage(e)));
	});

	function changeFilter(next: GalleryFilter) {
		goto(resolve(`/${filterToUrl(next)}`), { replace: true, reset: false });
	}
</script>

<FilterBar {filter} onchange={changeFilter} />

{#if error}
	<p class="error" role="alert">{error}</p>
{:else if months === null}
	<p>{m.status_loading()}</p>
{:else if months.length === 0}
	<p>{m.gallery_empty()}</p>
{:else}
	<p class="total">{m.gallery_total({ count: new Intl.NumberFormat().format(total) })}</p>
	<div id="timeline" class="timeline" bind:this={timeline} bind:clientWidth={width}>
		<!-- Re-created when the filter changes, so that no month keeps stale items. -->
		{#key query}
			{#each months as bucket (bucket.month)}
				<MonthSection {bucket} {filter} {width} {query} />
			{/each}
		{/key}
	</div>
	{#if timeline}
		<Scrubber {timeline} />
	{/if}
{/if}

<style>
	.timeline {
		/* room for the scrubber on the right */
		padding-right: 3.5rem;
	}
	.total {
		opacity: 0.7;
	}
	.error {
		color: #cf222e;
	}
</style>
