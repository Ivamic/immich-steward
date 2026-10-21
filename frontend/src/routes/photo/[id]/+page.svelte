<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  Photo card in three columns that fill the window: the map (always in view), a panel to pick
  the location with the actions and the suggestions, and the reference column. Only the panels
  scroll. On medium screens the panel and the reference column share one column with tabs; on
  small ones everything is stacked. Narrow column: reference information as it is now (photo, details, current location, history).
-->
<script lang="ts">
	import {
		getAsset,
		getMapConfig,
		getSuggestions,
		isPending,
		runModule,
		setReview,
		thumbnailUrl,
		undoLocation,
		type AssetDetail,
		type Candidate,
		type GalleryFilter,
		type MapConfig,
		type ModuleSuggestions,
		type Region,
		type ReviewStatus,
		type Turn
	} from '#lib/api.js';
	import { formatCoordinates, parseCoordinates, type LatLon } from '#lib/coords.js';
	import { errorMessage } from '#lib/errors.js';
	import { atPhoto, filterFromUrl, filterToUrl } from '#lib/gallery/filter.js';
	import GeocoderSearch from '#lib/map/GeocoderSearch.svelte';
	import MapView from '#lib/map/MapView.svelte';
	import PhotoViewer from '#lib/PhotoViewer.svelte';
	import { shortcutKey } from '#lib/keys.js';
	import RegionPicker from '#lib/RegionPicker.svelte';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import { saves } from '#lib/saves.svelte.js';
	import { cameraFilter } from '#lib/suggestions/cameraFilter.svelte.js';
	import { numberCandidates, visibleSuggestions } from '#lib/suggestions/format.js';
	import SuggestionList from '#lib/suggestions/SuggestionList.svelte';
	import type { Highlight } from '#lib/suggestions/highlight.js';
	import { untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';

	const id = $derived(page.params.id ?? '');
	const filter = $derived(filterFromUrl(page.url.searchParams));
	const query = $derived(filterToUrl(filter));
	// Back to the gallery at the photo shown now (after stepping through others, too).
	const backUrl = $derived(resolve(`/${atPhoto(query, id)}`));

	let asset = $state<AssetDetail | null>(null);
	let mapConfig = $state<MapConfig | null>(null);
	let error = $state<string | null>(null);
	let busy = $state(false);
	let picked = $state<LatLon | null>(null);
	let coordinatesText = $state('');
	let coordinatesInvalid = $state(false);
	let mapView = $state<ReturnType<typeof MapView>>();
	let viewerOpen = $state(false);
	// The module to choose a part of the photo for, and the part to start from (FR-35).
	let partPicker = $state<{ module: string; region: Region | null } | null>(null);
	// The part outlined on the photo while its suggestions are hovered.
	let shownPart = $state<Region | null>(null);
	// How the user turned the photo here (not in Immich); back to 0 on another photo.
	let turn = $state<Turn>(0);
	let suggestions = $state<ModuleSuggestions[]>([]);
	let suggestionsLoading = $state(false);

	const current = $derived<LatLon | null>(
		asset?.latitude != null && asset.longitude != null
			? { lat: asset.latitude, lon: asset.longitude }
			: null
	);
	const takenAt = $derived(
		asset
			? new Intl.DateTimeFormat(getLocale(), {
					dateStyle: 'long',
					timeStyle: 'medium',
					// Local wall-clock time arrives without a zone: show it exactly as it is.
					timeZone: 'UTC'
				}).format(new Date(asset.local_taken_at + 'Z'))
			: ''
	);
	const camera = $derived(
		[asset?.camera_make, asset?.camera_model].filter(Boolean).join(' ') || m.photo_no_camera()
	);
	// Modules whose weak suggestions the user unfolded; kept while moving between photos.
	let unfolded = $state<string[]>([]);
	// The suggestion under the pointer, in the list or on the map.
	let highlight = $state<Highlight | null>(null);
	// Medium screens: which of the two side panels is shown.
	let tab = $state<'place' | 'info'>('place');
	const shown = $derived(visibleSuggestions(suggestions, unfolded));
	const numbered = $derived(numberCandidates(shown));
	const pending = $derived(asset ? saves.pendingFor(asset.id) : undefined);
	const changedAt = new Intl.DateTimeFormat(getLocale(), {
		dateStyle: 'medium',
		timeStyle: 'short'
	});
	const place = $derived([asset?.city, asset?.state, asset?.country].filter(Boolean).join(', '));

	$effect(() => {
		getMapConfig()
			.then((config) => (mapConfig = config))
			.catch((e) => (error = errorMessage(e)));
	});

	$effect(() => {
		load(id, filter);
	});

	// A save sent from the notices (after the card moved on) may concern the photo shown now.
	$effect(() => {
		const changed = saves.changed;
		if (changed && changed.assetId === untrack(() => asset?.id)) {
			untrack(() => load(id, filter));
		}
	});

	// Cameras excluded or included again: recompute the suggestions of this photo.
	$effect(() => {
		void cameraFilter.excluded;
		void cameraFilter.sameOnly;
		if (untrack(() => asset)) untrack(() => fetchSuggestions(id));
	});

	/** Back in this tab (e.g. after fixing a neighbor in another one): bring the data up to date. */
	function onvisibilitychange() {
		if (document.visibilityState !== 'visible' || !asset) return;
		getAsset(id, filter)
			.then((result) => (asset = result))
			.catch((e) => (error = errorMessage(e)));
		fetchSuggestions(id);
	}

	// While a worker module is queued or running, look for its result every few seconds.
	$effect(() => {
		if (!suggestions.some(isPending)) return;
		const assetId = id;
		const timer = setTimeout(() => fetchSuggestions(assetId), 2000);
		return () => clearTimeout(timer);
	});

	function setSuggestions(assetId: string, result: ModuleSuggestions[]) {
		// The user may have moved on to another photo meanwhile. Unchanged results are kept as they
		// are, so that polling does not redraw the map (and close an open preview).
		if (assetId === id && JSON.stringify(result) !== JSON.stringify(suggestions)) {
			suggestions = result;
		}
	}

	async function run(module: string, region: Region | null = null) {
		if (!asset) return;
		const assetId = asset.id;
		try {
			setSuggestions(
				assetId,
				await runModule(assetId, module, cameraFilter.excluded, region, cameraFilter.sameOnly, turn)
			);
		} catch (e) {
			error = errorMessage(e);
		}
	}

	// R: a part of the photo (of the preview frame of a video) for GeoCLIP, starting from the part
	// chosen last time.
	function pickPart() {
		if (!asset) return;
		const block = suggestions.find((s) => s.module === 'geoclip' && s.region);
		// One part at a time: wait until the run on the last one is over.
		if (block && isPending(block)) return;
		startPart('geoclip', block?.region ?? null);
	}

	/** The last part is a start only when it was chosen on the photo turned as it is now. */
	function startPart(module: string, region: Region | null) {
		const block = suggestions.find((s) => s.module === module && s.region);
		partPicker = { module, region: block?.turn === turn ? region : null };
	}

	function rotate(by: 90 | -90) {
		turn = ((((turn + by) % 360) + 360) % 360) as Turn;
		shownPart = null;
	}

	function fetchSuggestions(assetId: string): Promise<ModuleSuggestions[]> {
		suggestionsLoading = true;
		const found = getSuggestions(assetId, cameraFilter.excluded, cameraFilter.sameOnly).then(
			(result) => {
				setSuggestions(assetId, result);
				return result;
			}
		);
		found.catch((e) => (error = errorMessage(e))).finally(() => (suggestionsLoading = false));
		return found;
	}

	function load(assetId: string, currentFilter: GalleryFilter) {
		error = null;
		picked = null;
		turn = 0;
		coordinatesText = '';
		coordinatesInvalid = false;
		suggestions = [];
		const located = getAsset(assetId, currentFilter).then((result) => {
			asset = result;
			return result.latitude != null && result.longitude != null
				? { lat: result.latitude, lon: result.longitude }
				: null;
		});
		const suggested = fetchSuggestions(assetId);
		located
			.then(async (point) => {
				if (point) {
					mapView?.flyTo(point);
					return;
				}
				// No location yet: show the suggestions and the photos around them; without any,
				// the map stays where it was (neighbors are usually close).
				const found = await suggested;
				if (assetId === id) mapView?.fitTo(suggestionPoints(found));
			})
			.catch((e) => (error = errorMessage(e)));
	}

	/** What to fit the map to: the suggestions as shown (with their circles) and the neighbors. */
	function suggestionPoints(modules: ModuleSuggestions[]) {
		return visibleSuggestions(modules, unfolded).flatMap((module) => [
			...module.candidates.map((c) => ({
				lat: c.latitude,
				lon: c.longitude,
				radius_m: c.radius_m
			})),
			...module.track.filter((p) => p.role).map((p) => ({ lat: p.latitude, lon: p.longitude }))
		]);
	}

	function choose(candidate: Candidate) {
		pick({ lat: candidate.latitude, lon: candidate.longitude });
	}

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

	function open(targetId: string | null | undefined) {
		if (targetId) goto(resolve(`/photo/[id]${query}`, { id: targetId }));
	}

	async function review(status: ReviewStatus) {
		if (!asset || busy || asset.review_status === status) return;
		busy = true;
		try {
			const updated = await setReview(asset.id, status, filter);
			// The photo may have left the filtered list: go on to the next one (FR-39).
			if (status !== 'new' && updated.next_id) open(updated.next_id);
			else asset = updated;
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	/** Queues the write (it can be cancelled for a few seconds) and moves on (FR-39). */
	function save() {
		if (!asset || !picked) return;
		if (picked.lat === 0 && picked.lon === 0) {
			error = m.error_location_null_island();
			return;
		}
		saves.schedule(asset.id, asset.file_name, picked);
		if (asset.next_id) open(asset.next_id);
		else clearPicked();
	}

	async function undo() {
		if (!asset || busy) return;
		busy = true;
		try {
			asset = await undoLocation(asset.id, filter);
			if (asset.latitude != null && asset.longitude != null) {
				mapView?.flyTo({ lat: asset.latitude, lon: asset.longitude });
			}
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	function onkeydown(event: KeyboardEvent) {
		// The viewer handles its own keys (Esc closes it).
		if (viewerOpen || partPicker) return;
		if (event.ctrlKey || event.metaKey || event.altKey) return;
		if ((event.target as HTMLElement).closest('input, textarea, select')) return;
		const actions: Record<string, () => void> = {
			enter: save,
			arrowleft: () => open(asset?.previous_id),
			arrowright: () => open(asset?.next_id),
			escape: () => goto(backUrl),
			n: () => review('not_applicable'),
			s: () => review('skipped'),
			u: () => review('new'),
			z: () => (viewerOpen = true),
			r: pickPart,
			'[': () => rotate(-90),
			']': () => rotate(90)
		};
		const key = shortcutKey(event);
		const suggestion = numbered.find((item) => String(item.key) === key);
		if (suggestion) {
			event.preventDefault();
			choose(suggestion.candidate);
			return;
		}
		// Enter on a focused button or link belongs to that control.
		if (key === 'enter' && (event.target as HTMLElement).closest('button, a')) return;
		const action = actions[key];
		if (action) {
			event.preventDefault();
			action();
		}
	}
</script>

<svelte:window {onkeydown} />
<svelte:document {onvisibilitychange} />

<nav class="toolbar">
	<a href={backUrl}>← {m.photo_back()}</a>
	<span class="spacer"></span>
	<button type="button" disabled={!asset?.previous_id} onclick={() => open(asset?.previous_id)}>
		← {m.photo_previous()}
	</button>
	<button type="button" disabled={!asset?.next_id} onclick={() => open(asset?.next_id)}>
		{m.photo_next()} →
	</button>
</nav>

{#if error}
	<p class="error" role="alert">{error}</p>
{/if}

<div class="card" class:show-info={tab === 'info'}>
	<div class="map">
		{#if mapConfig}
			<MapView
				bind:this={mapView}
				styleUrl={mapConfig.style_url}
				{current}
				{picked}
				suggestions={shown}
				onpick={pick}
				{highlight}
				onhighlight={(h) => (highlight = h)}
			/>
		{/if}
	</div>

	<div class="tabs" role="tablist">
		<button type="button" role="tab" aria-selected={tab === 'place'} onclick={() => (tab = 'place')}
			>{m.photo_tab_place()}</button
		>
		<button type="button" role="tab" aria-selected={tab === 'info'} onclick={() => (tab = 'info')}
			>{m.photo_tab_info()}</button
		>
	</div>

	<section class="panel">
		{#if asset}
			<div class="actions">
				<!-- Re-created for every new point, so that it catches the eye each time. -->
				{#key picked}
					<button type="button" class="save" class:ready={picked} disabled={!picked} onclick={save}>
						{m.photo_save()} <kbd>Enter</kbd>
					</button>
				{/key}
				{#if asset.review_status === 'new'}
					<button type="button" disabled={busy} onclick={() => review('skipped')}>
						{m.photo_skip()} <kbd>S</kbd>
					</button>
					<button type="button" disabled={busy} onclick={() => review('not_applicable')}>
						{m.photo_not_applicable()} <kbd>N</kbd>
					</button>
				{:else}
					<button type="button" disabled={busy} onclick={() => review('new')}>
						{m.photo_back_to_todo()} <kbd>U</kbd>
					</button>
				{/if}
			</div>
		{/if}
		{#if picked}
			<p class="picked">
				{m.photo_picked({ coordinates: formatCoordinates(picked) })}
				<button type="button" onclick={clearPicked}>{m.photo_clear()}</button>
			</p>
		{/if}
		{#if pending}
			<p class="pending">
				{m.photo_pending()}
				<button type="button" onclick={() => saves.cancel(pending.key)}>{m.save_cancel()}</button>
			</p>
		{/if}

		<div class="picker">
			{#if mapConfig?.geocoder_enabled}
				<GeocoderSearch
					near={picked ?? current}
					onselect={(point) => {
						pick(point);
						mapView?.flyTo(point);
					}}
				/>
			{/if}
			<label class="coordinates">
				{m.photo_coordinates()}
				<input
					type="text"
					bind:value={coordinatesText}
					placeholder="42.4249, 18.7713"
					aria-invalid={coordinatesInvalid}
					onchange={applyCoordinatesText}
					onkeydown={(e) => e.key === 'Enter' && applyCoordinatesText()}
				/>
			</label>
		</div>
		{#if coordinatesInvalid}
			<p class="error">{m.photo_coordinates_invalid()}</p>
		{/if}

		{#if asset}
			<details class="keys">
				<summary>{m.photo_keys()}</summary>
				<p class="muted hint">{m.photo_save_note()} {m.photo_keys_hint()}</p>
			</details>
		{/if}

		<SuggestionList
			modules={suggestions}
			loading={suggestionsLoading}
			onchoose={choose}
			onrun={run}
			{highlight}
			onhighlight={(h) => (highlight = h)}
			{unfolded}
			ontoggle={(module) =>
				(unfolded = unfolded.includes(module)
					? unfolded.filter((m) => m !== module)
					: [...unfolded, module])}
			onlocate={(c) =>
				mapView?.fitTo([{ lat: c.latitude, lon: c.longitude, radius_m: c.radius_m }])}
			onpart={startPart}
			onpartshow={(region, partTurn) => (shownPart = partTurn === turn ? region : null)}
		/>
	</section>

	<aside class="info">
		<figure class="preview">
			<button
				type="button"
				class="zoom"
				title={m.photo_zoom()}
				aria-label={m.photo_zoom()}
				onclick={() => (viewerOpen = true)}
			>
				<span class="framed">
					<img src={thumbnailUrl(id, 'preview', turn)} alt={asset?.file_name ?? ''} />
					{#if shownPart}
						<span
							class="part"
							style:left="{shownPart.x * 100}%"
							style:top="{shownPart.y * 100}%"
							style:width="{shownPart.w * 100}%"
							style:height="{shownPart.h * 100}%"
						></span>
					{/if}
				</span>
				<span class="zoom-label">⤢ {m.photo_zoom()} <kbd>Z</kbd></span>
			</button>
			<div class="turns">
				<button type="button" title="{m.photo_turn_left()} [" onclick={() => rotate(-90)}>
					⟲ <span class="sr-only">{m.photo_turn_left()}</span>
				</button>
				<button type="button" title="{m.photo_turn_right()} ]" onclick={() => rotate(90)}>
					⟳ <span class="sr-only">{m.photo_turn_right()}</span>
				</button>
				{#if turn}
					<span class="muted turned">{m.photo_turned_note()}</span>
				{/if}
			</div>
			{#if asset?.type === 'VIDEO'}
				<figcaption class="muted">{m.photo_video_note()}</figcaption>
			{/if}
		</figure>

		{#if asset}
			<dl class="details">
				<dt>{m.photo_taken_at()}</dt>
				<dd>
					{takenAt}
					{#if asset.time_zone}<span class="muted">({asset.time_zone})</span>{/if}
				</dd>
				<dt>{m.photo_camera()}</dt>
				<dd>{camera}</dd>
				<dt>{m.photo_file()}</dt>
				<dd class="file">
					{asset.file_name}
					{#if asset.immich_url}
						<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- external link -->
						<br /><a href={asset.immich_url} target="_blank" rel="noopener"
							>{m.photo_open_in_immich()} ↗</a
						>
					{/if}
				</dd>
				{#if asset.albums.length}
					<dt>{m.photo_albums()}</dt>
					<dd>{asset.albums.join(', ')}</dd>
				{/if}
				<dt>{m.photo_location()}</dt>
				<dd>
					{#if current}
						{#if place}{place}<br />{/if}
						<span class="coords">{formatCoordinates(current)}</span>
					{:else}
						<span class="muted">{m.photo_no_location()}</span>
					{/if}
				</dd>
				{#if asset.review_status !== 'new'}
					<dt>{m.photo_status()}</dt>
					<dd>
						{asset.review_status === 'skipped'
							? m.photo_status_skipped()
							: m.photo_status_not_applicable()}
					</dd>
				{/if}
			</dl>

			{#if asset.location_history.length}
				<section class="history">
					<h2>{m.photo_history()}</h2>
					<ol>
						{#each asset.location_history as change (change.id)}
							<li class:undone={change.status === 'undone'}>
								<span>{changedAt.format(new Date(change.created_at))}</span>
								<strong>
									{formatCoordinates({ lat: change.latitude, lon: change.longitude })}
								</strong>
								<span class="muted">
									{change.source === 'manual' ? m.photo_history_manual() : change.source}
									·
									{change.prev_latitude != null && change.prev_longitude != null
										? m.photo_history_was({
												coordinates: formatCoordinates({
													lat: change.prev_latitude,
													lon: change.prev_longitude
												})
											})
										: m.photo_history_was_empty()}
									{#if change.status === 'undone'}· {m.photo_history_undone()}{/if}
								</span>
							</li>
						{/each}
					</ol>
					{#if asset.can_undo}
						<button type="button" disabled={busy} onclick={undo}>{m.photo_undo()}</button>
					{/if}
				</section>
			{/if}
		{/if}
	</aside>
</div>

{#if partPicker}
	<RegionPicker
		src={thumbnailUrl(id, asset?.type === 'VIDEO' ? 'preview' : 'fullsize', turn)}
		alt={asset?.file_name ?? ''}
		initial={partPicker.region}
		onrun={(region) => {
			const module = partPicker?.module ?? 'geoclip';
			partPicker = null;
			run(module, region);
		}}
		onclose={() => (partPicker = null)}
	/>
{/if}

{#if viewerOpen}
	<PhotoViewer
		src={thumbnailUrl(id, asset?.type === 'VIDEO' ? 'preview' : 'fullsize', turn)}
		alt={asset?.file_name ?? ''}
		onclose={() => (viewerOpen = false)}
	/>
{/if}

<style>
	.toolbar {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 1rem;
	}
	.spacer {
		flex: 1;
	}
	/* The page fits the window: only the panels scroll, the map stays in view. */
	.card {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 23rem 19rem;
		grid-template-areas: 'map panel info';
		gap: 1rem;
		height: calc(100dvh - 9rem);
		min-height: 30rem;
	}
	.map {
		grid-area: map;
		min-height: 0;
	}
	.tabs {
		grid-area: tabs;
		display: none;
		gap: 0.25rem;
	}
	.tabs button[aria-selected='true'] {
		font-weight: 600;
		border-bottom: 2px solid #0969da;
	}
	.panel {
		grid-area: panel;
	}
	.info {
		grid-area: info;
	}
	.panel,
	.info {
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
		min-width: 0;
		min-height: 0;
		overflow-y: auto;
		padding-right: 0.25rem;
	}
	/* Medium screens: one side column, with tabs. */
	@media (max-width: 80rem) {
		.card {
			grid-template-columns: minmax(0, 1fr) 24rem;
			grid-template-rows: auto minmax(0, 1fr);
			grid-template-areas: 'map tabs' 'map side';
		}
		.tabs {
			display: flex;
		}
		.panel,
		.info {
			grid-area: side;
		}
		.card:not(.show-info) .info,
		.card.show-info .panel {
			display: none;
		}
	}
	/* Small screens: everything stacked, the page scrolls. */
	@media (max-width: 50rem) {
		.card {
			display: flex;
			flex-direction: column;
			height: auto;
		}
		.map {
			height: 55vh;
		}
		.tabs {
			display: none;
		}
		.card:not(.show-info) .info,
		.card.show-info .panel {
			display: flex;
		}
		.panel,
		.info {
			overflow: visible;
		}
	}
	.picker {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	.keys summary {
		cursor: pointer;
		font-size: 0.85rem;
		opacity: 0.75;
	}
	.preview {
		margin: 0;
	}
	.zoom {
		position: relative;
		display: block;
		width: 100%;
		padding: 0;
		border: none;
		background: none;
		cursor: zoom-in;
	}
	/* Fits the photo exactly, so that a part can be outlined on it. */
	.framed {
		position: relative;
		display: block;
		width: fit-content;
		margin: 0 auto;
		overflow: hidden;
	}
	.zoom img {
		display: block;
		max-width: 100%;
		max-height: 16rem;
	}
	.part {
		position: absolute;
		outline: 2px dashed #fff;
		box-shadow: 0 0 0 100vmax rgb(0 0 0 / 0.45);
		pointer-events: none;
	}
	.turns {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem;
		margin-top: 0.4rem;
	}
	.turns .turned {
		font-size: 0.8rem;
	}
	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
		white-space: nowrap;
	}
	.zoom-label {
		position: absolute;
		right: 0.4rem;
		bottom: 0.4rem;
		padding: 0.15rem 0.45rem;
		border-radius: 0.3rem;
		background: rgb(0 0 0 / 0.6);
		color: #fff;
		font-size: 0.8rem;
	}
	.details {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 0.3rem 1rem;
		margin: 0;
	}
	dt {
		font-weight: 600;
	}
	dd {
		margin: 0;
	}
	.file {
		word-break: break-all;
	}
	.coords {
		font-variant-numeric: tabular-nums;
	}
	.coordinates {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}
	.coordinates input[aria-invalid='true'] {
		outline: 2px solid #cf222e;
	}
	.picked {
		margin: 0;
	}
	.actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
	}
	.muted {
		opacity: 0.65;
	}
	.hint {
		font-size: 0.85rem;
		margin: 0;
	}
	.error {
		color: #cf222e;
	}
	kbd {
		font-size: 0.75em;
		opacity: 0.7;
	}
	/* The main actions, at the top of the panel and bigger than other buttons. */
	.actions button {
		padding: 0.45rem 0.8rem;
		font-size: 0.95rem;
	}
	.save {
		font-weight: 600;
	}
	/* A point is picked: saving is the next step, do not forget it. */
	.save.ready {
		border-color: #1a7f37;
		background: #1f883d;
		color: #fff;
		animation: attention 1.2s ease-out 1;
	}
	.save.ready kbd {
		opacity: 0.85;
	}
	@keyframes attention {
		0% {
			box-shadow: 0 0 0 0 rgb(31 136 61 / 0.6);
		}
		100% {
			box-shadow: 0 0 0 12px rgb(31 136 61 / 0);
		}
	}
	.pending {
		margin: 0;
		padding: 0.5rem 0.75rem;
		border-left: 3px solid #bf8700;
		background: rgb(191 135 0 / 0.1);
	}
	.history h2 {
		font-size: 1rem;
		margin: 0.5rem 0;
	}
	.history ol {
		list-style: none;
		padding: 0;
		margin: 0 0 0.5rem;
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}
	.history li {
		display: flex;
		flex-direction: column;
	}
	.history li.undone strong {
		text-decoration: line-through;
	}
</style>
