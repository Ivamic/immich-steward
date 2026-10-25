<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  One month of the timeline. Its photos are fetched and rendered only while the section is
  near the viewport; otherwise it is an empty block of the estimated height. This keeps the
  page light for libraries with tens of thousands of photos.

  Photos are chosen with the check in their corner; once one is chosen, a click on a photo
  chooses it too (Shift: everything from the photo clicked before), instead of opening it.
-->
<script lang="ts">
	import {
		getMonthAssets,
		thumbnailUrl,
		type AssetItem,
		type GalleryFilter,
		type MonthBucket
	} from '#lib/api.js';
	import { m } from '#lib/paraglide/messages.js';
	import Icon from '#lib/ui/Icon.svelte';
	import { replaceState } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { untrack } from 'svelte';
	import { atPhoto, type FilterQuery } from './filter.js';
	import { monthTitle } from './month.js';
	import { photoWork } from './bulk.svelte.js';
	import { galleryChanges, type Selection } from './selection.svelte.js';

	const TILE = 160; // px, keep in sync with the grid CSS below
	const GAP = 4;
	const NEAR_VIEWPORT = '1500px';

	let {
		bucket,
		filter,
		width,
		query,
		selection,
		onitems,
		onpick
	}: {
		bucket: MonthBucket;
		filter: GalleryFilter;
		width: number;
		query: FilterQuery;
		selection: Selection;
		/** The photos of the month, once fetched: for choosing a range across months. */
		onitems: (month: string, items: AssetItem[]) => void;
		/** Choose or unchoose the photo; `range`: everything from the photo clicked before. */
		onpick: (item: AssetItem, range: boolean) => void;
	} = $props();

	let section: HTMLElement;
	let near = $state(false);
	let items = $state<AssetItem[] | null>(null);
	let failed = $state(false);

	const columns = $derived(Math.max(1, Math.floor((width + GAP) / (TILE + GAP))));
	const estimatedHeight = $derived(Math.ceil(bucket.count / columns) * (TILE + GAP) - GAP);
	const title = $derived(monthTitle(bucket.month));

	/** Shows the thumbnail once loaded; it may already be loaded (cache) when this runs. */
	function fadeIn(img: HTMLImageElement) {
		const show = () => img.classList.add('loaded');
		if (img.complete) show();
		else img.addEventListener('load', show, { once: true });
	}

	$effect(() => {
		const observer = new IntersectionObserver(([entry]) => (near = entry.isIntersecting), {
			rootMargin: `${NEAR_VIEWPORT} 0px`
		});
		observer.observe(section);
		return () => observer.disconnect();
	});

	$effect(() => {
		if (!near || items !== null || failed) return;
		fetchItems();
	});

	// Photos changed (e.g. a location saved for the chosen ones): fetch the loaded month again.
	let seenChanges = galleryChanges.count;
	$effect(() => {
		const count = galleryChanges.count;
		if (count === seenChanges) return;
		seenChanges = count;
		if (untrack(() => items) !== null) untrack(fetchItems);
	});

	function fetchItems() {
		getMonthAssets(bucket.month, filter)
			.then((result) => {
				items = result;
				onitems(bucket.month, result);
			})
			.catch(() => (failed = true));
	}

	/** While photos are being chosen, a click chooses rather than opens. */
	function onclick(event: MouseEvent, item: AssetItem) {
		if (selection.size || event.shiftKey) {
			event.preventDefault();
			onpick(item, event.shiftKey);
			return;
		}
		replaceState(resolve(`/${atPhoto(query, item.id)}`), {});
	}
</script>

<section bind:this={section} data-month={bucket.month}>
	<h2>{title} <span class="count">{bucket.count}</span></h2>
	{#if near && items}
		<div class="grid">
			{#each items as item (item.id)}
				{@const chosen = selection.has(item.id)}
				{@const work = photoWork(item.id)}
				<div class="cell" class:chosen class:choosing={selection.size > 0}>
					<a
						class="tile"
						href={resolve(`/photo/[id]${query}`, { id: item.id })}
						title={item.file_name}
						data-asset={item.id}
						onclick={(e) => onclick(e, item)}
					>
						<img
							src={thumbnailUrl(item.id, 'thumbnail', 0, item.version)}
							alt={item.file_name}
							loading="lazy"
							decoding="async"
							use:fadeIn
						/>
						{#if item.type === 'VIDEO'}
							<span class="video" role="img" aria-label={m.asset_video()}>
								<Icon name="play" size={11} strokeWidth={2.25} />
							</span>
						{/if}
						{#if item.has_location}
							<span
								class="marker location"
								role="img"
								aria-label={m.asset_has_location()}
								title={m.asset_has_location()}
							>
								<Icon name="map-pin" size={13} strokeWidth={2.25} />
							</span>
						{:else if item.geoclip_confident}
							<!-- Crosshair: a guess to check, in GeoCLIP's color as on the map. -->
							<span
								class="marker geoclip"
								role="img"
								aria-label={m.asset_geoclip_confident()}
								title={m.asset_geoclip_confident()}
							>
								<Icon name="crosshair" size={13} strokeWidth={2.25} />
							</span>
						{/if}
					</a>
					{#if work}
						<!-- Saved with others or being turned: shown on the photo itself. -->
						<span
							class="work"
							role="img"
							aria-label={work === 'waiting' ? m.photo_work_waiting() : m.photo_work_working()}
							title={work === 'waiting' ? m.photo_work_waiting() : m.photo_work_working()}
						>
							{#if work === 'waiting'}
								<Icon name="clock" size={22} />
							{:else}
								<span class="st-spin"><Icon name="loader-circle" size={22} /></span>
							{/if}
						</span>
					{/if}
					<button
						type="button"
						class="check"
						aria-pressed={chosen}
						aria-label={m.select_photo({ file: item.file_name })}
						title={m.select_photo_hint()}
						onclick={(e) => onpick(item, e.shiftKey)}
					>
						<Icon name="check" size={14} strokeWidth={3} />
					</button>
				</div>
			{/each}
		</div>
	{:else}
		<div class="placeholder" style:height="{estimatedHeight}px"></div>
	{/if}
</section>

<style>
	section {
		margin-bottom: var(--space-6);
	}
	h2 {
		display: flex;
		align-items: baseline;
		gap: var(--space-2);
		margin: 0 0 var(--space-2);
		font-size: var(--text-md);
		font-weight: var(--weight-semibold);
	}
	.count {
		font-size: var(--text-sm);
		font-weight: var(--weight-regular);
		color: var(--color-text-muted);
		font-variant-numeric: tabular-nums;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, 160px);
		gap: 4px;
	}
	.cell {
		position: relative;
	}
	.work {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
		border-radius: 2px;
		background: oklch(0 0 0 / 0.45);
		color: var(--gray-0);
		pointer-events: none;
	}
	.work .st-spin {
		display: inline-flex;
	}
	/* The check: on hover, and on every photo while some are chosen. */
	.check {
		position: absolute;
		top: 6px;
		left: 6px;
		display: grid;
		place-items: center;
		width: 22px;
		height: 22px;
		padding: 0;
		border: 2px solid var(--gray-0);
		border-radius: 50%;
		background: oklch(0 0 0 / 0.3);
		color: transparent;
		box-shadow: var(--shadow-badge);
		cursor: pointer;
		opacity: 0;
		transition: opacity var(--motion-fast) var(--ease-out);
	}
	.cell:hover .check,
	.cell.choosing .check,
	.check:focus-visible {
		opacity: 1;
	}
	.check:hover {
		background: oklch(0 0 0 / 0.5);
		color: var(--gray-0);
	}
	.chosen .check {
		border-color: var(--color-accent);
		background: var(--color-accent);
		color: var(--color-on-accent);
	}
	/* A chosen photo shrinks into a frame of the accent color. */
	.chosen .tile {
		box-shadow: inset 0 0 0 3px var(--color-accent);
	}
	.chosen img {
		transform: scale(0.88);
		border-radius: 4px;
	}
	.chosen .tile:hover img {
		transform: scale(0.88);
	}
	.tile {
		position: relative;
		display: block;
		width: 160px;
		height: 160px;
		overflow: hidden;
		border-radius: 2px;
		background: var(--color-skeleton);
		outline: none;
	}
	.tile::after {
		content: '';
		position: absolute;
		inset: 0;
		pointer-events: none;
		border-radius: inherit;
	}
	.tile:focus-visible::after {
		box-shadow:
			inset 0 0 0 3px var(--color-focus),
			inset 0 0 0 5px var(--color-bg);
	}
	img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
		opacity: 0;
		transition:
			opacity var(--motion-base) var(--ease-out),
			transform var(--motion-fast) var(--ease-out);
	}
	img:global(.loaded) {
		opacity: 1;
	}
	.tile:hover img {
		transform: scale(1.02);
	}
	.video {
		position: absolute;
		top: 6px;
		right: 6px;
		display: grid;
		place-items: center;
		width: 20px;
		height: 20px;
		border-radius: var(--radius-full);
		background: oklch(0 0 0 / 0.55);
		color: var(--gray-0);
	}
	/* White disc with a shadow: visible on snow and sky as well as on dark photos. */
	.marker {
		position: absolute;
		bottom: 6px;
		right: 6px;
		display: grid;
		place-items: center;
		width: 22px;
		height: 22px;
		border-radius: 50%;
		background: var(--gray-0);
		box-shadow: var(--shadow-badge);
	}
	.location {
		color: var(--moss-600);
	}
	.geoclip {
		background: var(--module-2);
		color: var(--gray-0);
	}
	.placeholder {
		border-radius: 2px;
		background: var(--color-skeleton);
		opacity: 0.5;
	}
</style>
