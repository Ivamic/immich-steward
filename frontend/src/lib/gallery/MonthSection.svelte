<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  One month of the timeline. Its photos are fetched and rendered only while the section is
  near the viewport; otherwise it is an empty block of the estimated height. This keeps the
  page light for libraries with tens of thousands of photos.
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
	import { getLocale } from '#lib/paraglide/runtime.js';
	import { resolve } from '$app/paths';
	import type { FilterQuery } from './filter.js';

	const TILE = 160; // px, keep in sync with the grid CSS below
	const GAP = 4;
	const NEAR_VIEWPORT = '1500px';

	let {
		bucket,
		filter,
		width,
		query
	}: { bucket: MonthBucket; filter: GalleryFilter; width: number; query: FilterQuery } = $props();

	let section: HTMLElement;
	let near = $state(false);
	let items = $state<AssetItem[] | null>(null);
	let failed = $state(false);

	const columns = $derived(Math.max(1, Math.floor((width + GAP) / (TILE + GAP))));
	const estimatedHeight = $derived(Math.ceil(bucket.count / columns) * (TILE + GAP));
	const title = $derived(
		new Intl.DateTimeFormat(getLocale(), { month: 'long', year: 'numeric' }).format(
			new Date(`${bucket.month}-01T00:00:00`)
		)
	);

	$effect(() => {
		const observer = new IntersectionObserver(([entry]) => (near = entry.isIntersecting), {
			rootMargin: `${NEAR_VIEWPORT} 0px`
		});
		observer.observe(section);
		return () => observer.disconnect();
	});

	$effect(() => {
		if (!near || items !== null || failed) return;
		getMonthAssets(bucket.month, filter)
			.then((result) => (items = result))
			.catch(() => (failed = true));
	});
</script>

<section bind:this={section} data-month={bucket.month}>
	<h2>{title} <span class="count">{bucket.count}</span></h2>
	{#if near && items}
		<div class="grid">
			{#each items as item (item.id)}
				<a
					class="tile"
					href={resolve(`/photo/[id]${query}`, { id: item.id })}
					title={item.file_name}
				>
					<img src={thumbnailUrl(item.id)} alt={item.file_name} loading="lazy" decoding="async" />
					{#if item.type === 'VIDEO'}
						<span class="badge video" aria-label={m.asset_video()}>▶</span>
					{/if}
					{#if item.has_location}
						<span class="badge location" aria-label={m.asset_has_location()}>●</span>
					{/if}
				</a>
			{/each}
		</div>
	{:else}
		<div class="placeholder" style:height="{estimatedHeight}px"></div>
	{/if}
</section>

<style>
	section {
		margin-bottom: 1.5rem;
	}
	h2 {
		font-size: 1.05rem;
		font-weight: 600;
		margin: 0 0 0.5rem;
		text-transform: capitalize;
	}
	.count {
		font-weight: 400;
		opacity: 0.6;
		margin-left: 0.4rem;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, 160px);
		gap: 4px;
	}
	.tile {
		position: relative;
		display: block;
		width: 160px;
		height: 160px;
		background: color-mix(in srgb, currentColor 8%, transparent);
	}
	.tile:focus-visible {
		outline: 3px solid #0969da;
		outline-offset: 1px;
	}
	img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.badge {
		position: absolute;
		font-size: 0.75rem;
		line-height: 1;
		color: white;
		text-shadow: 0 0 3px black;
	}
	.video {
		top: 6px;
		right: 6px;
	}
	.location {
		bottom: 6px;
		right: 6px;
		color: #3fb950;
	}
	.placeholder {
		background: color-mix(in srgb, currentColor 4%, transparent);
	}
</style>
