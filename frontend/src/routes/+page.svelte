<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
	import {
		getAsset,
		getMonths,
		type AssetItem,
		type GalleryFilter,
		type MonthBucket
	} from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import FilterBar from '#lib/gallery/FilterBar.svelte';
	import PauseBar from '#lib/PauseBar.svelte';
	import MonthSection from '#lib/gallery/MonthSection.svelte';
	import Scrubber from '#lib/gallery/Scrubber.svelte';
	import SelectionBar from '#lib/gallery/SelectionBar.svelte';
	import SelectionLocation from '#lib/gallery/SelectionLocation.svelte';
	import { defaultFilter, filterFromUrl, filterToUrl } from '#lib/gallery/filter.js';
	import { galleryChanges, Selection } from '#lib/gallery/selection.svelte.js';
	import { m } from '#lib/paraglide/messages.js';
	import EmptyState from '#lib/ui/EmptyState.svelte';
	import Skeleton from '#lib/ui/Skeleton.svelte';
	import { afterNavigate, goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { tick, untrack } from 'svelte';
	import { SvelteMap } from 'svelte/reactivity';

	// How long to wait for the photo to return to, and where to put it on the screen.
	const AT_TIMEOUT_MS = 5000;
	const AT_SCREEN_SHARE = 1 / 3;

	let months = $state<MonthBucket[] | null>(null);
	let error = $state<string | null>(null);
	let width = $state(0);
	let timeline = $state<HTMLElement>();
	// `?at=<photo>` of the last navigation, until the timeline is scrolled to it.
	let pendingAt = $state<string | null>(null);
	// Photos chosen for an action on all of them (D-149), and the photos of the loaded months, in
	// the order of the gallery, for choosing a range with Shift.
	const selection = new Selection();
	const loaded = new SvelteMap<string, AssetItem[]>();
	let locationOpen = $state(false);

	const filter = $derived(filterFromUrl(page.url.searchParams));
	const query = $derived(filterToUrl(filter));
	const total = $derived(months?.reduce((sum, b) => sum + b.count, 0) ?? null);
	// Nothing left to do, rather than nothing matching a narrowed filter.
	const allDone = $derived(query === filterToUrl(defaultFilter));

	// Only a change of the filter reloads the months, not `at` added to the URL.
	$effect(() => {
		void query;
		const current = untrack(() => filter);
		months = null;
		error = null;
		selection.clear();
		loaded.clear();
		getMonths(current)
			.then((result) => (months = result))
			.catch((e) => (error = errorMessage(e)));
	});

	// Photos changed (a location saved, photos marked or turned): the month counts too.
	let seenChanges = galleryChanges.count;
	$effect(() => {
		const count = galleryChanges.count;
		if (count === seenChanges) return;
		seenChanges = count;
		getMonths(untrack(() => filter))
			.then((result) => (months = result))
			.catch((e) => (error = errorMessage(e)));
	});

	function pick(item: AssetItem, range: boolean) {
		if (!range || !selection.anchor) {
			selection.toggle(item);
			return;
		}
		const ordered = (months ?? []).flatMap((bucket) => loaded.get(bucket.month) ?? []);
		selection.extend(item, ordered);
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'Escape' && selection.size && !locationOpen) {
			event.preventDefault();
			selection.clear();
		}
	}

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

<svelte:window {onkeydown} />

<FilterBar {filter} {total} onchange={changeFilter} />
<!-- Beside the timeline of years on the right, as the photos are. -->
<div class="beside-scrubber"><PauseBar /></div>

{#if error}
	<p class="error" role="alert">{error}</p>
{:else if months === null}
	<div class="loading" aria-busy="true" aria-label={m.status_loading()}>
		<Skeleton width="8rem" height="1rem" />
		<div class="skeleton-grid">
			{#each { length: 18 }, i (i)}
				<Skeleton width="160px" height="160px" radius="2px" />
			{/each}
		</div>
	</div>
{:else if months.length === 0}
	{#if allDone}
		<EmptyState
			icon="map-pin-check"
			title={m.gallery_all_done()}
			text={m.gallery_all_done_text()}
		/>
	{:else}
		<EmptyState icon="filter" title={m.gallery_empty()} text={m.gallery_empty_text()}>
			<button type="button" class="st-btn st-btn--sm" onclick={() => changeFilter(defaultFilter)}>
				{m.filter_reset()}
			</button>
		</EmptyState>
	{/if}
{:else}
	<div id="timeline" class="timeline" bind:this={timeline}>
		<div bind:clientWidth={width}>
			<!-- Re-created when the filter changes, so that no month keeps stale items. -->
			{#key query}
				{#each months as bucket (bucket.month)}
					<MonthSection
						{bucket}
						{filter}
						{width}
						{query}
						{selection}
						onitems={(month, items) => loaded.set(month, items)}
						onpick={pick}
					/>
				{/each}
			{/key}
		</div>
	</div>
	{#if timeline}
		<Scrubber {timeline} />
	{/if}
{/if}

{#if selection.size}
	<SelectionBar {selection} onlocation={() => (locationOpen = true)} />
{/if}
{#if locationOpen}
	<SelectionLocation
		items={[...selection.items.values()]}
		onsaved={() => {
			locationOpen = false;
			selection.clear();
		}}
		onclose={() => (locationOpen = false)}
	/>
{/if}

<style>
	.beside-scrubber,
	.timeline {
		/* room for the scrubber on the right */
		padding-right: 3.5rem;
	}
	.timeline {
		/* room for the bar of actions below the last photos */
		padding-bottom: 5rem;
	}
	.loading {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding-top: var(--space-2);
	}
	.skeleton-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, 160px);
		gap: 4px;
	}
	.error {
		color: var(--color-danger-text);
	}
</style>
