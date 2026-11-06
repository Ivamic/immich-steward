<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- The page "Map" (D-207): the photos with a location, gathered on the server into circles with
     their number as the zoom asks. A click zooms in; close up it shows the photos of the place,
     to open or to choose as in the gallery. The filters are those of the gallery that mean
     something here; where the map is lives in the address, so the way back from a photo leads to
     the same place. -->
<script lang="ts">
	import {
		getMapCells,
		getMapConfig,
		getMapPhotos,
		markPhotos,
		thumbnailUrl,
		type AssetItem,
		type GalleryFilter,
		type MapConfig
	} from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { bulkNotices } from '#lib/gallery/bulk.svelte.js';
	import FilterBar from '#lib/gallery/FilterBar.svelte';
	import { filterFromUrl, filterToUrl } from '#lib/gallery/filter.js';
	import { nearScreen } from '#lib/gallery/nearScreen.js';
	import SelectionBar from '#lib/gallery/SelectionBar.svelte';
	import SelectionLocation from '#lib/gallery/SelectionLocation.svelte';
	import { galleryChanged, galleryChanges, Selection } from '#lib/gallery/selection.svelte.js';
	import MapView from '#lib/map/MapView.svelte';
	import type { MapBounds, MapCell, MapViewState } from '#lib/map/markers.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import Icon from '#lib/ui/Icon.svelte';
	import { goto, replaceState } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { untrack } from 'svelte';

	// From this zoom a click on a circle shows its photos instead of zooming in.
	const PLACE_ZOOM = 15;
	// How far a click zooms in.
	const ZOOM_STEP = 3;
	const PART = 120;
	const SENT_MOST = 2000;
	// Requests for the cells wait for the map to stop.
	const VIEW_DELAY_MS = 200;

	const filter = $derived(filterFromUrl(page.url.searchParams));
	const numbers = new Intl.NumberFormat(getLocale());
	const count = (n: number) => numbers.format(n);

	/** "lat,lon,zoom" and, with a place open, ",south,west,north,east". */
	function readState(value: string | null): { at: MapViewState | null; place: MapBounds | null } {
		const parts = (value ?? '').split(',').map(Number);
		if (parts.length < 3 || parts.some((n) => Number.isNaN(n))) return { at: null, place: null };
		const [lat, lon, zoom, south, west, north, east] = parts;
		const at = { lat, lon, zoom, south: lat, west: lon, north: lat, east: lon };
		const place = parts.length >= 7 ? { south, west, north, east } : null;
		return { at, place };
	}

	const opened = readState(page.url.searchParams.get('map'));
	let view = $state<MapViewState | null>(null);
	let cells = $state.raw<MapCell[]>([]);
	let photosInView = $state<number | null>(null);
	let mapConfig = $state<MapConfig | null>(null);
	let error = $state<string | null>(null);
	let loaded = $state(false);
	let place = $state<MapBounds | null>(opened.place);
	let placePhotos = $state.raw<AssetItem[]>([]);
	let placeTotal = $state(0);
	let loadingPlace = false;
	let busy = $state(false);
	let locationOpen = $state(false);
	let filterHeight = $state(0);
	let mapView = $state<MapView>();
	const selection = new Selection();
	const chosenIds = $derived(new Set(selection.ids));
	let latest = 0;
	let fittedOnce = opened.at !== null;

	const round = (n: number, digits: number) => Number(n.toFixed(digits));
	const stateText = $derived.by(() => {
		if (!view) return page.url.searchParams.get('map') ?? '';
		const at = [round(view.lat, 5), round(view.lon, 5), round(view.zoom, 2)];
		const open = place
			? [place.south, place.west, place.north, place.east].map((n) => round(n, 6))
			: [];
		return [...at, ...open].join(',');
	});
	const photoQuery = $derived<`?${string}`>(
		`${filterToUrl(filter)}&map=${encodeURIComponent(stateText)}`
	);

	$effect(() => {
		getMapConfig()
			.then((config) => (mapConfig = config))
			.catch((e) => (error = errorMessage(e)));
	});

	// The address follows the map, without a new entry in the history.
	$effect(() => {
		const text = stateText;
		if (!text) return;
		untrack(() => {
			const others = page.url.search
				.slice(1)
				.split('&')
				.filter((part) => part && !part.startsWith('map='));
			const search = [...others, `map=${encodeURIComponent(text)}`].join('&');
			if (`?${search}` !== page.url.search) replaceState(resolve(`/map?${search}`), {});
		});
	});

	async function loadCells(at: MapViewState, current: GalleryFilter) {
		const mine = ++latest;
		try {
			const answer = await getMapCells(at, at.zoom, current);
			if (mine !== latest) return;
			cells = answer.cells.map((cell) => ({
				lat: cell.latitude,
				lon: cell.longitude,
				photos: cell.photos,
				bounds: cell.bounds,
				asset_id: cell.asset_id
			}));
			photosInView = answer.photos;
			loaded = true;
			error = null;
			// The first look without a place to go to: all the photos in view.
			if (!fittedOnce && cells.length) {
				fittedOnce = true;
				mapView?.fitTo(cells);
			}
		} catch (e) {
			if (mine === latest) error = errorMessage(e);
		}
	}

	// The cells of what the map shows now, once it stops; again with a new filter, and when photos
	// got a place elsewhere (the location dialog).
	$effect(() => {
		const at = view;
		const current = filter;
		void galleryChanges.count;
		if (!at) return;
		const timer = setTimeout(() => loadCells(at, current), VIEW_DELAY_MS);
		return () => clearTimeout(timer);
	});

	async function loadPlace(bounds: MapBounds, upTo = PART) {
		loadingPlace = true;
		try {
			const answer = await getMapPhotos(bounds, 0, upTo, filter);
			if (place !== bounds) return;
			placePhotos = answer.photos;
			placeTotal = answer.total;
		} catch (e) {
			error = errorMessage(e);
		} finally {
			loadingPlace = false;
		}
	}

	async function morePlace() {
		const bounds = place;
		if (!bounds || loadingPlace) return;
		loadingPlace = true;
		try {
			const answer = await getMapPhotos(bounds, placePhotos.length, PART, filter);
			if (place !== bounds) return;
			const known = new Set(placePhotos.map((photo) => photo.id));
			placePhotos = [...placePhotos, ...answer.photos.filter((photo) => !known.has(photo.id))];
			placeTotal = answer.total;
		} catch (e) {
			error = errorMessage(e);
		} finally {
			loadingPlace = false;
		}
	}

	// The place open in the address (back from a photo), or chosen, with the filter of now.
	$effect(() => {
		const bounds = place;
		void filter;
		void galleryChanges.count;
		if (bounds) untrack(() => loadPlace(bounds, Math.max(placePhotos.length, PART)));
	});

	function openCell(cell: MapCell) {
		if (cell.photos > 1 && view && view.zoom < PLACE_ZOOM) {
			mapView?.easeTo(cell, Math.min(view.zoom + ZOOM_STEP, 19));
			return;
		}
		selection.clear();
		placePhotos = [];
		placeTotal = cell.photos;
		place = cell.bounds;
	}

	function closePlace() {
		selection.clear();
		place = null;
		placePhotos = [];
	}

	function changeFilter(next: GalleryFilter) {
		selection.clear();
		goto(resolve(`/map${filterToUrl(next)}&map=${encodeURIComponent(stateText)}`), {
			replace: true,
			reset: false
		});
	}

	async function mark() {
		busy = true;
		try {
			const ids = selection.ids;
			for (let start = 0; start < ids.length; start += SENT_MOST) {
				await markPhotos(ids.slice(start, start + SENT_MOST));
			}
			selection.clear();
			galleryChanged();
			bulkNotices.done(m.candidates_marked({ count: ids.length }));
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	function clickTile(event: MouseEvent, photo: AssetItem) {
		if (event.shiftKey && selection.anchor) {
			event.preventDefault();
			selection.extend(photo, placePhotos);
		} else if (selection.size > 0 || event.ctrlKey || event.metaKey) {
			event.preventDefault();
			selection.toggle(photo);
		}
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key !== 'Escape' || locationOpen) return;
		if (selection.size) {
			event.preventDefault();
			selection.clear();
		} else if (place) {
			event.preventDefault();
			closePlace();
		}
	}
</script>

<svelte:window {onkeydown} />

<FilterBar
	{filter}
	total={photosInView}
	placesOnly
	bind:height={filterHeight}
	onchange={changeFilter}
/>

{#if error}
	<p class="bad" role="alert">{error}</p>
{/if}

<div class="layout" class:with-place={place !== null} style:--_filter="{filterHeight}px">
	<div class="map">
		{#if mapConfig}
			<MapView
				bind:this={mapView}
				styleUrl={mapConfig.style_url}
				styleUrlDark={mapConfig.style_url_dark}
				sources={mapConfig.sources}
				auto={mapConfig.auto}
				current={null}
				picked={null}
				onpick={() => {}}
				{cells}
				oncell={openCell}
				onview={(next) => (view = next)}
				startView={opened.at}
				scrollingPage
			/>
		{/if}
		{#if loaded && cells.length === 0}
			<p class="empty">{m.map_empty()}</p>
		{/if}
	</div>

	{#if place}
		<section class="place" aria-label={m.map_place_photos({ count: count(placeTotal) })}>
			<header>
				<h2>{m.map_place_photos({ count: count(placeTotal) })}</h2>
				{#if placePhotos.length > 1}
					<button
						type="button"
						class="st-btn st-btn--ghost st-btn--sm"
						onclick={() => selection.setAll(placePhotos, true)}
					>
						{m.candidates_choose_all()}
					</button>
				{/if}
				<button
					type="button"
					class="st-iconbtn st-iconbtn--sm"
					aria-label={m.map_close_place()}
					title={m.map_close_place()}
					onclick={closePlace}
				>
					<Icon name="x" />
				</button>
			</header>
			<div class="st-tile-grid">
				{#each placePhotos as photo (photo.id)}
					{@const chosen = chosenIds.has(photo.id)}
					<div class="st-tile-cell" class:chosen class:choosing={selection.size > 0}>
						<a
							class="st-tile"
							href={resolve(`/photo/[id]${photoQuery}`, { id: photo.id })}
							title={photo.file_name}
							onclick={(event) => clickTile(event, photo)}
						>
							<img
								src={thumbnailUrl(photo.id, 'thumbnail', 0, photo.version)}
								alt={photo.file_name}
								loading="lazy"
								decoding="async"
							/>
						</a>
						<button
							type="button"
							class="st-tile-check"
							aria-pressed={chosen}
							aria-label={m.groups_choose_photo()}
							title={m.groups_choose_photo()}
							onclick={() => selection.toggle(photo)}
						>
							<Icon name="check" size={12} strokeWidth={3} />
						</button>
					</div>
				{/each}
			</div>
			{#if placePhotos.length < placeTotal}
				<div class="more" use:nearScreen={{ at: placePhotos.length, onnear: morePlace }}></div>
			{/if}
		</section>
	{:else}
		<p class="hint">{m.map_hint()}</p>
	{/if}
</div>

{#if selection.size}
	<SelectionBar {selection} onlocation={() => (locationOpen = true)}>
		<button type="button" class="st-btn st-btn--ghost st-btn--sm" disabled={busy} onclick={mark}>
			<Icon name="eye-off" size={14} />
			{m.groups_photos_trash()}
		</button>
	</SelectionBar>
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
	.bad {
		color: var(--color-danger-text);
	}
	.layout {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: var(--space-3);
	}
	/* The map takes the window under the header and the filters. */
	.map {
		position: relative;
		height: calc(100dvh - var(--header-height) - var(--_filter) - var(--space-8));
		min-height: 20rem;
		overflow: hidden;
		border-radius: var(--radius-md);
	}
	.empty {
		position: absolute;
		top: var(--space-3);
		left: 50%;
		z-index: 1;
		margin: 0;
		padding: var(--space-1) var(--space-3);
		border-radius: var(--radius-full);
		background: var(--color-surface);
		box-shadow: var(--shadow-sm);
		font-size: var(--text-sm);
		transform: translateX(-50%);
	}
	.hint {
		margin: 0;
		color: var(--color-text-muted);
		font-size: var(--text-sm);
	}
	/* The photos of a place beside the map on a wide screen, under it on a narrow one. */
	@media (min-width: 60rem) {
		.layout.with-place {
			grid-template-columns: minmax(0, 1fr) 26rem;
		}
		.with-place .place {
			height: calc(100dvh - var(--header-height) - var(--_filter) - var(--space-8));
			overflow-y: auto;
		}
	}
	@media (max-width: 59.99rem) {
		.with-place .map {
			height: 50dvh;
		}
	}
	.place header {
		position: sticky;
		top: 0;
		z-index: 1;
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-1) 0 var(--space-2);
		background: var(--color-bg);
	}
	.place h2 {
		flex: 1;
		margin: 0;
		font-size: var(--text-base);
	}
	.place .st-tile-grid {
		grid-template-columns: repeat(auto-fill, minmax(6rem, 1fr));
		margin-bottom: var(--space-16);
	}
	.more {
		height: 1px;
	}
</style>
