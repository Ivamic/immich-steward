<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  One location for several photos chosen in the gallery (D-149). The map and the controls are
  those of the photo card: a click on the map, the coordinates, the address search, the
  suggestions (keys 1–9, Enter saves). The suggestions come only from what is already known: the
  places of the chosen photos, their neighbors in time and the confident results of the modules.
  Photos that already have a location keep it unless the user ticks to overwrite it.
-->
<script lang="ts">
	import {
		getMapConfig,
		getSelectionSuggestions,
		thumbnailUrl,
		type AssetItem,
		type Candidate,
		type MapConfig,
		type ModuleSuggestions
	} from '#lib/api.js';
	import { formatCoordinates, parseCoordinates, type LatLon } from '#lib/coords.js';
	import { errorMessage } from '#lib/errors.js';
	import { shortcutKey } from '#lib/keys.js';
	import GeocoderSearch from '#lib/map/GeocoderSearch.svelte';
	import MapView from '#lib/map/MapView.svelte';
	import { m } from '#lib/paraglide/messages.js';
	import { saves } from '#lib/saves.svelte.js';
	import {
		displayedModules,
		hiddenModules,
		numberCandidates,
		visibleSuggestions
	} from '#lib/suggestions/format.js';
	import type { Highlight } from '#lib/suggestions/highlight.js';
	import SuggestionList from '#lib/suggestions/SuggestionList.svelte';
	import Icon from '#lib/ui/Icon.svelte';
	import Kbd from '#lib/ui/Kbd.svelte';
	import CopyButton from '#lib/ui/CopyButton.svelte';
	import HoverPreview from './HoverPreview.svelte';
	import { longpress } from './longpress.js';
	import PhotoPeek from './PhotoPeek.svelte';

	let {
		items,
		onsaved,
		onclose
	}: {
		/** The chosen photos. */
		items: AssetItem[];
		/** The save is queued (it can still be cancelled from its notice). */
		onsaved: () => void;
		onclose: () => void;
	} = $props();

	// Thumbnails shown at the top; the rest are counted.
	const STRIP = 12;

	let dialog: HTMLDialogElement;
	let mapConfig = $state<MapConfig | null>(null);
	let mapView = $state<ReturnType<typeof MapView>>();
	let suggestions = $state<ModuleSuggestions[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let picked = $state<LatLon | null>(null);
	let coordinatesText = $state('');
	let coordinatesInput = $state<HTMLInputElement>();
	let coordinatesInvalid = $state(false);
	let overwrite = $state(false);
	let highlight = $state<Highlight | null>(null);
	let unfolded = $state<string[]>([]);
	let revealed = $state<string[]>([]);

	// A larger look at a thumbnail of the strip: on hovering it with a mouse, or large on a long
	// press (touch screens), as in the gallery.
	let hovered = $state<{ item: AssetItem; anchor: DOMRect } | null>(null);
	let peeked = $state<AssetItem | null>(null);
	const located = $derived(items.filter((item) => item.has_location).length);
	const listed = $derived(displayedModules(suggestions, revealed));
	const shown = $derived(visibleSuggestions(listed, unfolded));
	const numbered = $derived(numberCandidates(shown));
	// Without overwriting, the photos with a location are left out: nothing to save without others.
	const writes = $derived(overwrite ? items.length : items.length - located);

	$effect(() => {
		dialog.showModal();
		return () => dialog.close();
	});

	$effect(() => {
		getMapConfig()
			.then((config) => (mapConfig = config))
			.catch((e) => (error = errorMessage(e)));
		getSelectionSuggestions(items.map((item) => item.id))
			.then((result) => (suggestions = result))
			.catch((e) => (error = errorMessage(e)))
			.finally(() => (loading = false));
	});

	// Once both the map and the suggestions are there: show the suggestions and their photos.
	let fitted = false;
	$effect(() => {
		if (fitted || loading || !mapView) return;
		fitted = true;
		const points = shown.flatMap((module) => [
			...module.candidates.map((c) => ({
				lat: c.latitude,
				lon: c.longitude,
				radius_m: c.radius_m
			})),
			...module.track.filter((p) => p.role).map((p) => ({ lat: p.latitude, lon: p.longitude }))
		]);
		mapView.fitTo(points);
	});

	function pick(point: LatLon) {
		picked = point;
		coordinatesText = formatCoordinates(point);
		coordinatesInvalid = false;
	}

	function clearPicked() {
		picked = null;
		coordinatesText = '';
	}

	function applyCoordinatesText() {
		const point = parseCoordinates(coordinatesText);
		coordinatesInvalid = point === null && coordinatesText.trim() !== '';
		if (point) {
			pick(point);
			mapView?.flyTo(point);
		}
	}

	function locate(module: string, candidate: Candidate) {
		mapView?.fitTo([
			{ lat: candidate.latitude, lon: candidate.longitude, radius_m: candidate.radius_m }
		]);
		highlight = { module, rank: candidate.rank, from: 'map' };
	}

	function save() {
		if (!picked || !writes) return;
		if (picked.lat === 0 && picked.lon === 0) {
			error = m.error_location_null_island();
			return;
		}
		saves.scheduleBatch(
			{
				ids: items.map((item) => item.id),
				overwrite,
				keep: items.filter((item) => item.has_location).map((item) => item.id)
			},
			m.selection_photos({ count: items.length }),
			picked
		);
		onsaved();
	}

	// The window opens with the focus on its first control: Enter there should still save. A
	// control reached with Tab gets its Enter.
	let tabbed = false;

	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'Tab') tabbed = true;
		if (event.ctrlKey || event.metaKey || event.altKey) return;
		if ((event.target as HTMLElement).closest('input, textarea, select')) return;
		const key = shortcutKey(event);
		const suggestion = numbered.find((item) => String(item.key) === key);
		if (suggestion) {
			event.preventDefault();
			if (event.shiftKey) locate(suggestion.module.key, suggestion.candidate);
			else pick({ lat: suggestion.candidate.latitude, lon: suggestion.candidate.longitude });
			return;
		}
		if (key === 'enter' && !(tabbed && (event.target as HTMLElement).closest('button, a'))) {
			event.preventDefault();
			save();
		}
	}
</script>

<dialog
	bind:this={dialog}
	class="window"
	aria-label={m.selection_location_title({ count: items.length })}
	oncancel={(e) => {
		e.preventDefault();
		onclose();
	}}
	{onkeydown}
>
	<div class="map">
		{#if mapConfig}
			<MapView
				bind:this={mapView}
				styleUrl={mapConfig.style_url}
				styleUrlDark={mapConfig.style_url_dark}
				sources={mapConfig.sources}
				auto={mapConfig.auto}
				current={null}
				{picked}
				suggestions={shown}
				onpick={pick}
				{highlight}
				onhighlight={(h) => (highlight = h)}
			/>
		{/if}
	</div>

	<section class="panel">
		<div class="pinned">
			<header>
				<h2>{m.selection_location_title({ count: items.length })}</h2>
				<button
					type="button"
					class="st-iconbtn st-iconbtn--sm"
					aria-label={m.save_dismiss()}
					title={m.save_dismiss()}
					onclick={onclose}
				>
					<Icon name="x" />
				</button>
			</header>
			<ul class="strip">
				{#each items.slice(0, STRIP) as item (item.id)}
					<li
						onpointerenter={(e) => {
							if (e.pointerType === 'mouse')
								hovered = { item, anchor: e.currentTarget.getBoundingClientRect() };
						}}
						onpointerleave={() => (hovered = null)}
						use:longpress={() => {
							hovered = null;
							peeked = item;
						}}
					>
						<img src={thumbnailUrl(item.id, 'thumbnail', 0, item.version)} alt={item.file_name} />
						{#if item.has_location}
							<span class="pin" title={m.asset_has_location()}
								><Icon name="map-pin" size={10} /></span
							>
						{/if}
					</li>
				{/each}
				{#if items.length > STRIP}<li class="more">+{items.length - STRIP}</li>{/if}
			</ul>

			<label
				class="point st-input st-input--mono"
				class:picked
				data-invalid={coordinatesInvalid}
				title={m.photo_coordinates()}
			>
				<Icon name="locate-fixed" />
				<input
					type="text"
					bind:this={coordinatesInput}
					bind:value={coordinatesText}
					placeholder={m.photo_coordinates()}
					aria-label={m.photo_coordinates()}
					aria-invalid={coordinatesInvalid}
					onchange={applyCoordinatesText}
					onkeydown={(e) => e.key === 'Enter' && applyCoordinatesText()}
				/>
				{#if picked}
					<CopyButton
						text={formatCoordinates(picked)}
						label={m.copy_coordinates()}
						onfailed={() => coordinatesInput?.select()}
					/>
					<button
						type="button"
						class="st-iconbtn st-iconbtn--sm"
						aria-label={m.photo_clear()}
						title={m.photo_clear()}
						onclick={clearPicked}
					>
						<Icon name="x" />
					</button>
				{/if}
			</label>
			{#if coordinatesInvalid}
				<p class="st-field__error">{m.photo_coordinates_invalid()}</p>
			{/if}
			<button
				type="button"
				class="st-btn st-btn--primary st-btn--lg st-btn--block"
				disabled={!picked || !writes}
				onclick={save}
			>
				<Icon name="map-pin-check" />
				{m.selection_save({ count: writes })}
				<Kbd>Enter</Kbd>
			</button>
			{#if located}
				<!-- Below the button and framed, so that it is not missed; warm while on. -->
				<label class="st-check st-check--sm overwrite" class:on={overwrite}>
					<input type="checkbox" bind:checked={overwrite} />
					{m.selection_overwrite({ count: located, total: items.length })}
				</label>
			{/if}
			{#if error}<p class="error" role="alert">{error}</p>{/if}
		</div>

		{#if mapConfig?.geocoder_enabled}
			<GeocoderSearch
				near={picked}
				onselect={(point) => {
					pick(point);
					mapView?.flyTo(point);
				}}
			/>
		{/if}

		<p class="note">{m.selection_suggestions_note()}</p>
		<SuggestionList
			modules={listed}
			hidden={hiddenModules(suggestions, revealed)}
			onreveal={(module) => (revealed = [...revealed, module])}
			{loading}
			onchoose={(c) => pick({ lat: c.latitude, lon: c.longitude })}
			onrun={() => {}}
			{highlight}
			onhighlight={(h) => (highlight = h)}
			{unfolded}
			ontoggle={(module) =>
				(unfolded = unfolded.includes(module)
					? unfolded.filter((x) => x !== module)
					: [...unfolded, module])}
			onlocate={(c) =>
				mapView?.fitTo([{ lat: c.latitude, lon: c.longitude, radius_m: c.radius_m }])}
			onpart={() => {}}
			onpartshow={() => {}}
		/>
	</section>

	<!-- Inside the dialog: only what is in it shows over it. -->
	{#if hovered}
		<HoverPreview item={hovered.item} anchor={hovered.anchor} />
	{/if}
	{#if peeked}
		<PhotoPeek item={peeked} onclose={() => (peeked = null)} />
	{/if}
</dialog>

<style>
	/* Fills the window: the map on the left, the controls on the right, as in the photo card. */
	.window {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 26rem;
		gap: var(--space-3);
		width: calc(100vw - 2rem);
		max-width: none;
		height: calc(100dvh - 2rem);
		max-height: none;
		padding: var(--space-3);
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-bg);
		color: var(--color-text);
	}
	.window::backdrop {
		background: var(--color-scrim);
	}
	.map {
		min-height: 0;
		overflow: hidden;
		border-radius: var(--radius-lg);
		background: var(--color-stage);
	}
	.panel {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		min-width: 0;
		min-height: 0;
		overflow-y: auto;
		padding: var(--space-3);
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-surface);
	}
	.pinned {
		position: sticky;
		top: calc(var(--space-3) * -1);
		margin-top: calc(var(--space-3) * -1);
		padding-block: var(--space-3);
		z-index: 2;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		border-bottom: var(--border-width) solid var(--color-border);
		background: var(--color-surface);
	}
	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-2);
	}
	h2 {
		margin: 0;
		font-size: var(--text-md);
	}
	.strip {
		display: flex;
		flex-wrap: wrap;
		gap: 4px;
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.strip li {
		position: relative;
		/* A long press shows the photo large: no system menu or text selection on touch screens. */
		user-select: none;
		-webkit-touch-callout: none;
		width: 44px;
		height: 44px;
		overflow: hidden;
		border-radius: 2px;
		background: var(--color-skeleton);
	}
	.strip img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.strip .pin {
		position: absolute;
		right: 2px;
		bottom: 2px;
		display: grid;
		place-items: center;
		width: 14px;
		height: 14px;
		border-radius: 50%;
		background: var(--gray-0);
		color: var(--moss-600);
	}
	.strip .more {
		display: grid;
		place-items: center;
		font-size: var(--text-xs);
		color: var(--color-text-muted);
	}
	.point.picked {
		border-color: var(--color-accent);
		background: var(--color-surface-selected);
	}
	.point .st-iconbtn {
		margin-inline-end: calc(var(--space-1) * -1);
	}
	.overwrite {
		align-items: flex-start;
		padding: var(--space-2) var(--space-3);
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface-sunken);
	}
	.overwrite.on {
		border-color: var(--color-warning);
		background: var(--color-warning-subtle);
		color: var(--color-warning-text);
	}
	.note {
		margin: 0;
		font-size: var(--text-xs);
		color: var(--color-text-muted);
	}
	.error {
		margin: 0;
		color: var(--color-danger-text);
	}
	@media (max-width: 60rem) {
		.window {
			grid-template-columns: 1fr;
			grid-template-rows: 45vh minmax(0, 1fr);
		}
	}
</style>
