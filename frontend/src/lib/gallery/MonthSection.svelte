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
						<span
							class="marker location"
							role="img"
							aria-label={m.asset_has_location()}
							title={m.asset_has_location()}
						>
							<!-- Map pin -->
							<svg viewBox="0 0 24 24" aria-hidden="true">
								<path
									d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7Zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5Z"
								/>
							</svg>
						</span>
					{:else if item.geoclip_confident}
						<span
							class="marker geoclip"
							role="img"
							aria-label={m.asset_geoclip_confident()}
							title={m.asset_geoclip_confident()}
						>
							<!-- Crosshair: a guess to check -->
							<svg viewBox="0 0 24 24" aria-hidden="true">
								<circle cx="12" cy="12" r="6.5" fill="none" stroke-width="2.4" />
								<circle cx="12" cy="12" r="2.2" />
								<path d="M12 2v4.5M12 17.5V22M2 12h4.5M17.5 12H22" fill="none" stroke-width="2.4" />
							</svg>
						</span>
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
	/* White disc with a shadow: visible on snow and sky as well as on dark photos. */
	.marker {
		position: absolute;
		bottom: 6px;
		right: 6px;
		display: flex;
		align-items: center;
		justify-content: center;
		width: 22px;
		height: 22px;
		border-radius: 50%;
		background: #fff;
		box-shadow: 0 1px 3px rgb(0 0 0 / 0.55);
	}
	.marker svg {
		width: 16px;
		height: 16px;
	}
	.location svg {
		fill: #1a7f37;
	}
	/* GeoCLIP's color, as on the map. */
	.geoclip {
		background: #bc4c00;
	}
	.geoclip svg {
		fill: #fff;
		stroke: #fff;
	}
	.placeholder {
		background: color-mix(in srgb, currentColor 4%, transparent);
	}
</style>
