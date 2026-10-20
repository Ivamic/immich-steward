<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
	import { getAsset, getMonths, type GalleryFilter, type MonthBucket } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import FilterBar from '#lib/gallery/FilterBar.svelte';
	import MonthSection from '#lib/gallery/MonthSection.svelte';
	import Scrubber from '#lib/gallery/Scrubber.svelte';
	import { filterFromUrl, filterToUrl } from '#lib/gallery/filter.js';
	import { m } from '#lib/paraglide/messages.js';
	import { afterNavigate, goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { tick, untrack } from 'svelte';

	// How long to wait for the photo to return to, and where to put it on the screen.
	const AT_TIMEOUT_MS = 5000;
	const AT_SCREEN_SHARE = 1 / 3;

	let months = $state<MonthBucket[] | null>(null);
	let error = $state<string | null>(null);
	let width = $state(0);
	let timeline = $state<HTMLElement>();
	// `?at=<photo>` of the last navigation, until the timeline is scrolled to it.
	let pendingAt = $state<string | null>(null);

	const filter = $derived(filterFromUrl(page.url.searchParams));
	const query = $derived(filterToUrl(filter));
	const total = $derived(months?.reduce((sum, b) => sum + b.count, 0) ?? 0);

	// Only a change of the filter reloads the months, not `at` added to the URL.
	$effect(() => {
		void query;
		const current = untrack(() => filter);
		months = null;
		error = null;
		getMonths(current)
			.then((result) => (months = result))
			.catch((e) => (error = errorMessage(e)));
	});

	afterNavigate(({ to }) => {
		pendingAt = to?.url.searchParams.get('at') ?? null;
	});

	$effect(() => {
		const id = pendingAt;
		if (!id || !months || !timeline) return;
		pendingAt = null;
		void scrollToPhoto(id);
	});

	/** Scrolls to the month of the photo, then, once its photos are there, to the photo. */
	async function scrollToPhoto(id: string) {
		let month: string;
		try {
			month = (await getAsset(id, filter)).local_taken_at.slice(0, 7);
		} catch {
			return; // e.g. the photo was deleted: the timeline stays at the top
		}
		await tick();
		const place = (el: Element) =>
			window.scrollBy({
				top: el.getBoundingClientRect().top - window.innerHeight * AT_SCREEN_SHARE
			});
		const section = timeline?.querySelector(`[data-month="${month}"]`);
		if (!section) return;
		place(section);
		const deadline = Date.now() + AT_TIMEOUT_MS;
		while (Date.now() < deadline) {
			const tile = timeline?.querySelector(`[data-asset="${CSS.escape(id)}"]`);
			if (tile) {
				place(tile);
				return;
			}
			await new Promise((done) => setTimeout(done, 50));
		}
	}

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
	<div id="timeline" class="timeline" bind:this={timeline}>
		<div bind:clientWidth={width}>
			<!-- Re-created when the filter changes, so that no month keeps stale items. -->
			{#key query}
				{#each months as bucket (bucket.month)}
					<MonthSection {bucket} {filter} {width} {query} />
				{/each}
			{/key}
		</div>
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
