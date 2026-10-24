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
		rotateInImmich,
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
	import PauseBar from '#lib/PauseBar.svelte';
	import { atPhoto, filterFromUrl, filterToUrl } from '#lib/gallery/filter.js';
	import KeysDialog from '#lib/KeysDialog.svelte';
	import GeocoderSearch from '#lib/map/GeocoderSearch.svelte';
	import MapView from '#lib/map/MapView.svelte';
	import PhotoViewer from '#lib/PhotoViewer.svelte';
	import { shortcutKey } from '#lib/keys.js';
	import RegionPicker from '#lib/RegionPicker.svelte';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import { saves } from '#lib/saves.svelte.js';
	import { cameraFilter } from '#lib/suggestions/cameraFilter.svelte.js';
	import {
		displayedModules,
		hiddenModules,
		cameraName,
		numberCandidates,
		PART_KEY_MODULE,
		visibleSuggestions
	} from '#lib/suggestions/format.js';
	import SuggestionList from '#lib/suggestions/SuggestionList.svelte';
	import Icon from '#lib/ui/Icon.svelte';
	import Kbd from '#lib/ui/Kbd.svelte';
	import Tooltip from '#lib/ui/Tooltip.svelte';
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
	let keysOpen = $state(false);
	// The module to choose a part of the photo for, and the part to start from (FR-35).
	let partPicker = $state<{ module: string; region: Region | null } | null>(null);
	// The part outlined on the photo while its suggestions are hovered.
	let shownPart = $state<Region | null>(null);
	// How the user turned the photo here (not in Immich); back to 0 on another photo.
	let turn = $state<Turn>(0);
	// Outcome of the last rotation saved to Immich.
	let rotationNotice = $state<string | null>(null);
	const version = $derived(asset?.version ?? null);
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
		cameraName(asset?.camera_make ?? null, asset?.camera_model ?? null) || m.photo_no_camera()
	);
	// Modules whose weak suggestions the user unfolded; kept while moving between photos.
	let unfolded = $state<string[]>([]);
	// Hidden modules (Settings page) shown in the card anyway; kept while moving between photos.
	let revealed = $state<string[]>([]);
	// The suggestion under the pointer, in the list or on the map.
	let highlight = $state<Highlight | null>(null);
	// Medium screens: which of the two side panels is shown.
	let tab = $state<'place' | 'info'>('place');
	const listed = $derived(displayedModules(suggestions, revealed));
	const shown = $derived(visibleSuggestions(listed, unfolded));
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
		const block = suggestions.find((s) => s.module === PART_KEY_MODULE && s.region);
		// One part at a time: wait until the run on the last one is over.
		if (block && isPending(block)) return;
		startPart(PART_KEY_MODULE, block?.region ?? null);
	}

	/** The last part is a start only when it was chosen on the photo turned as it is now. */
	function startPart(module: string, region: Region | null) {
		const block = suggestions.find((s) => s.module === module && s.region);
		partPicker = { module, region: block?.turn === turn ? region : null };
	}

	/** Saves the rotation to Immich; the photo then comes from Immich rotated. */
	async function saveRotation() {
		if (!asset || busy || !turn) return;
		busy = true;
		rotationNotice = null;
		const before = asset.version;
		try {
			asset = await rotateInImmich(asset.id, turn, filter);
			turn = 0;
			shownPart = null;
			rotationNotice =
				asset.version !== before ? m.photo_rotation_saved() : m.photo_rotation_saved_later();
			fetchSuggestions(asset.id);
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	function resetRotation() {
		turn = 0;
		shownPart = null;
	}

	function rotate(by: 90 | -90) {
		rotationNotice = null;
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
		rotationNotice = null;
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
		return visibleSuggestions(displayedModules(modules, revealed), unfolded).flatMap((module) => [
			...module.candidates.map((c) => ({
				lat: c.latitude,
				lon: c.longitude,
				radius_m: c.radius_m
			})),
			...module.track.filter((p) => p.role).map((p) => ({ lat: p.latitude, lon: p.longitude }))
		]);
	}

	function locate(module: string, candidate: Candidate) {
		mapView?.fitTo([
			{ lat: candidate.latitude, lon: candidate.longitude, radius_m: candidate.radius_m }
		]);
		highlight = { module, rank: candidate.rank, from: 'map' };
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

	// The control last pressed with the mouse: it keeps the focus, but Enter should still save.
	let pointerControl: Element | null = null;

	function onpointerdown(event: PointerEvent) {
		pointerControl = (event.target as HTMLElement).closest('button, a');
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'Tab') pointerControl = null;
		// The viewer and the windows handle their own keys (Esc closes them).
		if (viewerOpen || partPicker || keysOpen) return;
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
			']': () => rotate(90),
			'?': () => (keysOpen = true)
		};
		const key = shortcutKey(event);
		const suggestion = numbered.find((item) => String(item.key) === key);
		if (suggestion) {
			event.preventDefault();
			// Shift + number: show the suggestion on the map (and its row in the list), without
			// picking it, as a click on its row does.
			if (event.shiftKey) locate(suggestion.module.key, suggestion.candidate);
			else choose(suggestion.candidate);
			return;
		}
		// Enter on a button or link reached with the keyboard belongs to that control.
		const control = (event.target as HTMLElement).closest('button, a');
		if (key === 'enter' && control && control !== pointerControl) return;
		const action = actions[key];
		if (action) {
			event.preventDefault();
			action();
		}
	}
</script>

<svelte:window {onkeydown} {onpointerdown} />
<svelte:document {onvisibilitychange} />

<nav class="toolbar">
	<Tooltip text={m.photo_back()} keys="Esc" below>
		<a class="st-iconbtn" href={backUrl} aria-label={m.photo_back()}>
			<Icon name="arrow-left" size={18} />
		</a>
	</Tooltip>
	{#if asset}
		<div class="title">
			<strong>{asset.file_name}</strong>
			<span
				>{takenAt}{#if asset.time_zone}&nbsp;({asset.time_zone}){/if}</span
			>
		</div>
	{/if}
	<span class="spacer"></span>
	<Tooltip text={m.photo_previous()} keys="←" below>
		<button
			type="button"
			class="st-btn st-btn--sm"
			disabled={!asset?.previous_id}
			onclick={() => open(asset?.previous_id)}
		>
			<Icon name="chevron-left" />
			{m.photo_previous()}
		</button>
	</Tooltip>
	<Tooltip text={m.photo_next()} keys="→" below>
		<button
			type="button"
			class="st-btn st-btn--sm"
			disabled={!asset?.next_id}
			onclick={() => open(asset?.next_id)}
		>
			{m.photo_next()}
			<Icon name="chevron-right" />
		</button>
	</Tooltip>
	<Tooltip text={m.photo_keys()} keys="?" below>
		<button
			type="button"
			class="st-iconbtn"
			aria-label={m.photo_keys()}
			onclick={() => (keysOpen = true)}
		>
			<Icon name="keyboard" size={18} />
		</button>
	</Tooltip>
	{#if asset?.immich_url}
		<Tooltip text={m.photo_open_in_immich()} below>
			<!-- eslint-disable svelte/no-navigation-without-resolve -- external link -->
			<a
				class="st-iconbtn"
				href={asset.immich_url}
				target="_blank"
				rel="noopener"
				aria-label={m.photo_open_in_immich()}
			>
				<Icon name="external-link" size={18} />
			</a>
			<!-- eslint-enable svelte/no-navigation-without-resolve -->
		</Tooltip>
	{/if}
</nav>

<PauseBar />

{#if error}
	<p class="error" role="alert">{error}</p>
{/if}

<div class="card" class:show-info={tab === 'info'}>
	<div class="map">
		{#if mapConfig}
			<MapView
				bind:this={mapView}
				styleUrl={mapConfig.style_url}
				styleUrlDark={mapConfig.style_url_dark}
				sources={mapConfig.sources}
				auto={mapConfig.auto}
				{current}
				{picked}
				suggestions={shown}
				onpick={pick}
				{highlight}
				onhighlight={(h) => (highlight = h)}
			/>
		{/if}
	</div>

	<div class="tabs st-tabs" role="tablist">
		<button type="button" role="tab" aria-selected={tab === 'place'} onclick={() => (tab = 'place')}
			>{m.photo_tab_place()}</button
		>
		<button type="button" role="tab" aria-selected={tab === 'info'} onclick={() => (tab = 'info')}
			>{m.photo_tab_info()}</button
		>
	</div>

	<section class="panel">
		<!-- Stays in view: only the search and the suggestions below scroll. -->
		<div class="pinned">
			{#if asset}
				<label
					class="point st-input st-input--mono"
					class:picked
					data-invalid={coordinatesInvalid}
					title={m.photo_coordinates()}
				>
					<Icon name="locate-fixed" />
					<input
						type="text"
						bind:value={coordinatesText}
						placeholder={m.photo_coordinates()}
						aria-label={m.photo_coordinates()}
						aria-invalid={coordinatesInvalid}
						onchange={applyCoordinatesText}
						onkeydown={(e) => e.key === 'Enter' && applyCoordinatesText()}
					/>
					{#if picked}
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
				<!-- Re-created for every new point, so that it catches the eye each time. -->
				{#key picked}
					<button
						type="button"
						class="save st-btn st-btn--primary st-btn--lg st-btn--block"
						class:ready={picked}
						disabled={!picked}
						onclick={save}
					>
						<Icon name="map-pin-check" />
						{m.photo_save()}
						<Kbd>Enter</Kbd>
					</button>
				{/key}
				<div class="actions">
					{#if asset.review_status === 'new'}
						<button
							type="button"
							class="st-btn st-btn--block"
							disabled={busy}
							onclick={() => review('skipped')}
						>
							<Icon name="skip-forward" />
							{m.photo_skip()}
							<Kbd>S</Kbd>
						</button>
						<button
							type="button"
							class="st-btn st-btn--block"
							disabled={busy}
							onclick={() => review('not_applicable')}
						>
							<Icon name="ban" />
							{m.photo_not_applicable()}
							<Kbd>N</Kbd>
						</button>
					{:else}
						<button
							type="button"
							class="st-btn st-btn--block"
							disabled={busy}
							onclick={() => review('new')}
						>
							<Icon name="undo-2" />
							{m.photo_back_to_todo()}
							<Kbd>U</Kbd>
						</button>
					{/if}
				</div>
				{#if pending}
					<div class="st-banner st-banner--warning" role="status">
						<Icon name="clock" />
						<span class="st-banner__body">{m.photo_pending()}</span>
						<span class="st-banner__actions">
							<button
								type="button"
								class="st-btn st-btn--sm"
								onclick={() => saves.cancel(pending.key)}>{m.save_cancel()}</button
							>
						</span>
					</div>
				{/if}
			{/if}
		</div>

		{#if mapConfig?.geocoder_enabled}
			<GeocoderSearch
				near={picked ?? current}
				onselect={(point) => {
					pick(point);
					mapView?.flyTo(point);
				}}
			/>
		{/if}

		<SuggestionList
			modules={listed}
			hidden={hiddenModules(suggestions, revealed)}
			onreveal={(module) => (revealed = [...revealed, module])}
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
				aria-label={m.photo_zoom()}
				onclick={() => (viewerOpen = true)}
			>
				<span class="framed">
					<!-- Re-created for each photo and turn, so that the new one fades in. -->
					{#key `${id}:${turn}`}
						<img src={thumbnailUrl(id, 'preview', turn, version)} alt={asset?.file_name ?? ''} />
					{/key}
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
			</button>
			<div class="tools">
				<div class="st-glass group">
					<Tooltip text={m.photo_turn_left()} keys="[">
						<button
							type="button"
							class="st-iconbtn st-iconbtn--sm"
							aria-label={m.photo_turn_left()}
							onclick={() => rotate(-90)}
						>
							<Icon name="rotate-ccw" />
						</button>
					</Tooltip>
					<Tooltip text={m.photo_turn_right()} keys="]">
						<button
							type="button"
							class="st-iconbtn st-iconbtn--sm"
							aria-label={m.photo_turn_right()}
							onclick={() => rotate(90)}
						>
							<Icon name="rotate-cw" />
						</button>
					</Tooltip>
				</div>
				<div class="st-glass group">
					<Tooltip text={m.photo_zoom()} keys="Z">
						<button
							type="button"
							class="st-iconbtn st-iconbtn--sm"
							aria-label={m.photo_zoom()}
							onclick={() => (viewerOpen = true)}
						>
							<Icon name="maximize-2" />
						</button>
					</Tooltip>
				</div>
			</div>
		</figure>
		{#if turn}
			<div class="st-banner st-banner--info rotation" role="status">
				<Icon name="rotate-cw" />
				<div class="st-banner__body">
					{asset?.type === 'IMAGE' ? m.photo_turned_note() : m.photo_rotation_video()}
					<div class="rotation-actions">
						{#if asset?.type === 'IMAGE'}
							<button
								type="button"
								class="st-btn st-btn--primary st-btn--sm"
								disabled={busy}
								onclick={saveRotation}
							>
								<Icon name="check" size={14} />
								{m.photo_rotation_save()}
							</button>
						{/if}
						<button type="button" class="st-btn st-btn--ghost st-btn--sm" onclick={resetRotation}>
							{m.photo_rotation_reset()}
						</button>
					</div>
				</div>
			</div>
		{/if}
		{#if rotationNotice}
			<p class="turned" role="status">{rotationNotice}</p>
		{/if}
		{#if asset?.type === 'VIDEO'}
			<p class="turned">{m.photo_video_note()}</p>
		{/if}

		{#if asset}
			<dl class="details">
				<dt>{m.photo_camera()}</dt>
				<dd>{camera}</dd>
				{#if asset.albums.length}
					<dt>{m.photo_albums()}</dt>
					<dd>{asset.albums.join(', ')}</dd>
				{/if}
				<dt>{m.photo_location()}</dt>
				<dd>
					{#if current}
						{#if place}{place}<br />{/if}
						<span class="st-coords">{formatCoordinates(current)}</span>
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
								<span class="st-coords coords">
									{formatCoordinates({ lat: change.latitude, lon: change.longitude })}
								</span>
								<span class="muted">
									{changedAt.format(new Date(change.created_at))}
									·
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
						<button type="button" class="st-btn st-btn--sm" disabled={busy} onclick={undo}>
							<Icon name="undo-2" />
							{m.photo_undo()}
						</button>
					{/if}
				</section>
			{/if}
		{/if}
	</aside>
</div>

{#if partPicker}
	<RegionPicker
		src={thumbnailUrl(id, asset?.type === 'VIDEO' ? 'preview' : 'fullsize', turn, version)}
		alt={asset?.file_name ?? ''}
		initial={partPicker.region}
		onrun={(region) => {
			const module = partPicker?.module ?? PART_KEY_MODULE;
			partPicker = null;
			run(module, region);
		}}
		onclose={() => (partPicker = null)}
	/>
{/if}

{#if keysOpen}
	<KeysDialog onclose={() => (keysOpen = false)} />
{/if}

{#if viewerOpen}
	<PhotoViewer
		src={thumbnailUrl(id, asset?.type === 'VIDEO' ? 'preview' : 'fullsize', turn, version)}
		alt={asset?.file_name ?? ''}
		onclose={() => (viewerOpen = false)}
	/>
{/if}

<style>
	.toolbar {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		margin: calc(var(--space-3) * -1) 0 var(--space-3);
	}
	.title {
		display: flex;
		flex-direction: column;
		min-width: 0;
		margin-inline-start: var(--space-1);
		line-height: var(--leading-snug);
	}
	.title strong {
		overflow: hidden;
		font-weight: var(--weight-semibold);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.title span {
		font-size: var(--text-xs);
		color: var(--color-text-muted);
	}
	.spacer {
		flex: 1;
	}
	a.st-iconbtn {
		text-decoration: none;
	}
	/* The page fits the window: only the panels scroll, the map stays in view. */
	.card {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 24rem 19rem;
		grid-template-areas: 'map panel info';
		gap: var(--space-4);
		height: calc(100dvh - 8.5rem);
		min-height: 30rem;
	}
	.map {
		grid-area: map;
		min-height: 0;
		overflow: hidden;
		border-radius: var(--radius-lg);
		background: var(--color-stage);
	}
	.tabs {
		grid-area: tabs;
		display: none;
	}
	.panel {
		grid-area: panel;
	}
	.info {
		grid-area: info;
	}
	/* Each column is a surface of its own, so that it stands out from the page in both themes. */
	.panel,
	.info {
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
	.pinned {
		position: sticky;
		top: calc(var(--space-3) * -1);
		margin-top: calc(var(--space-3) * -1);
		padding-top: var(--space-3);
		z-index: 2;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding-bottom: var(--space-3);
		border-bottom: var(--border-width) solid var(--color-border);
		background: var(--color-surface);
	}
	.point.picked {
		border-color: var(--color-accent);
		background: var(--color-surface-selected);
	}
	.point .st-iconbtn {
		margin-inline-end: calc(var(--space-1) * -1);
	}
	/* Long labels (other languages) wrap the buttons onto two lines rather than overflow. */
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}
	.actions .st-btn {
		flex: 1 1 auto;
		width: auto;
	}
	/* A point is picked: saving is the next step, do not forget it. */
	.save.ready {
		animation: attention 1.2s var(--ease-out) 1;
	}
	@keyframes attention {
		0% {
			box-shadow: 0 0 0 0 color-mix(in oklab, var(--color-accent), transparent 40%);
		}
		100% {
			box-shadow: 0 0 0 12px color-mix(in oklab, var(--color-accent), transparent 100%);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.save.ready {
			animation: none;
		}
	}
	.preview {
		position: relative;
		margin: 0;
		overflow: hidden;
		border-radius: var(--radius-lg);
		background: var(--color-stage);
	}
	.zoom {
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
		max-height: 17rem;
		/* Only opacity: cheap, and the next key can interrupt it. */
		animation: st-fade var(--motion-photo-swap) var(--ease-out);
	}
	.part {
		position: absolute;
		outline: 2px dashed var(--gray-0);
		box-shadow: 0 0 0 100vmax oklch(0 0 0 / 0.45);
		pointer-events: none;
	}
	.tools {
		position: absolute;
		inset-inline: var(--space-2);
		bottom: var(--space-2);
		display: flex;
		justify-content: space-between;
		pointer-events: none;
	}
	.tools .group {
		display: flex;
		gap: 2px;
		padding: 2px;
		pointer-events: auto;
	}
	.tools .st-iconbtn {
		color: var(--color-text);
	}
	.rotation-actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		margin-top: var(--space-2);
	}
	.turned {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2);
		margin: 0;
		font-size: var(--text-xs);
		color: var(--color-text-muted);
	}
	.details {
		display: grid;
		grid-template-columns: max-content minmax(0, 1fr);
		gap: var(--space-1-5) var(--space-4);
		margin: 0;
		font-size: var(--text-sm);
	}
	dt {
		color: var(--color-text-muted);
	}
	dd {
		margin: 0;
		overflow-wrap: anywhere;
	}
	.muted {
		color: var(--color-text-muted);
	}
	.error {
		color: var(--color-danger-text);
	}
	.history {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--space-2);
		font-size: var(--text-sm);
	}
	.history h2 {
		margin: var(--space-2) 0 0;
		font-size: var(--text-base);
	}
	.history ol {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.history li {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.history .muted {
		font-size: var(--text-xs);
	}
	.history li.undone .coords {
		text-decoration: line-through;
	}
</style>
