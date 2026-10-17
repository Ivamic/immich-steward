<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  Photo card: preview, details, map with the location picker, saving the location to Immich,
  its history with undo, review actions and keyboard navigation.
-->
<script lang="ts">
	import {
		getAsset,
		getMapConfig,
		setReview,
		thumbnailUrl,
		undoLocation,
		type AssetDetail,
		type GalleryFilter,
		type MapConfig,
		type ReviewStatus
	} from '#lib/api.js';
	import { formatCoordinates, parseCoordinates, type LatLon } from '#lib/coords.js';
	import { errorMessage } from '#lib/errors.js';
	import { filterFromUrl, filterToUrl } from '#lib/gallery/filter.js';
	import GeocoderSearch from '#lib/map/GeocoderSearch.svelte';
	import MapView from '#lib/map/MapView.svelte';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import { saves } from '#lib/saves.svelte.js';
	import { untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';

	const id = $derived(page.params.id ?? '');
	const filter = $derived(filterFromUrl(page.url.searchParams));
	const query = $derived(filterToUrl(filter));

	let asset = $state<AssetDetail | null>(null);
	let mapConfig = $state<MapConfig | null>(null);
	let error = $state<string | null>(null);
	let busy = $state(false);
	let picked = $state<LatLon | null>(null);
	let coordinatesText = $state('');
	let coordinatesInvalid = $state(false);
	let mapView = $state<ReturnType<typeof MapView>>();

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

	function load(assetId: string, currentFilter: GalleryFilter) {
		error = null;
		picked = null;
		coordinatesText = '';
		coordinatesInvalid = false;
		getAsset(assetId, currentFilter)
			.then((result) => {
				asset = result;
				// Without a location the map stays where it was: neighbors are usually close.
				if (result.latitude != null && result.longitude != null) {
					mapView?.flyTo({ lat: result.latitude, lon: result.longitude });
				}
			})
			.catch((e) => (error = errorMessage(e)));
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
		if (event.ctrlKey || event.metaKey || event.altKey) return;
		if ((event.target as HTMLElement).closest('input, textarea, select')) return;
		const actions: Record<string, () => void> = {
			enter: save,
			arrowleft: () => open(asset?.previous_id),
			arrowright: () => open(asset?.next_id),
			escape: () => goto(resolve(`/${query}`)),
			n: () => review('not_applicable'),
			s: () => review('skipped'),
			u: () => review('new')
		};
		const key = event.key.toLowerCase();
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

<nav class="toolbar">
	<a href={resolve(`/${query}`)}>← {m.photo_back()}</a>
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

<div class="card">
	<figure class="preview">
		<img src={thumbnailUrl(id, 'preview')} alt={asset?.file_name ?? ''} />
		{#if asset?.type === 'VIDEO'}
			<figcaption class="muted">{m.photo_video_note()}</figcaption>
		{/if}
	</figure>

	<aside class="side">
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
				<dd class="file">{asset.file_name}</dd>
				{#if asset.albums.length}
					<dt>{m.photo_albums()}</dt>
					<dd>{asset.albums.join(', ')}</dd>
				{/if}
				<dt>{m.photo_location()}</dt>
				<dd>
					{#if current}
						{place || formatCoordinates(current)}
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
		{/if}

		<div class="map">
			{#if mapConfig}
				<MapView
					bind:this={mapView}
					styleUrl={mapConfig.style_url}
					{current}
					{picked}
					onpick={pick}
				/>
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
		{#if coordinatesInvalid}
			<p class="error">{m.photo_coordinates_invalid()}</p>
		{/if}
		{#if picked}
			<p class="picked">
				{m.photo_picked({ coordinates: formatCoordinates(picked) })}
				<button type="button" onclick={clearPicked}>{m.photo_clear()}</button>
			</p>
			<div class="actions">
				<button type="button" class="primary" onclick={save}>
					{m.photo_save()} <kbd>Enter</kbd>
				</button>
			</div>
			<p class="muted hint">{m.photo_save_note()}</p>
		{/if}
		{#if pending}
			<p class="pending">
				{m.photo_pending()}
				<button type="button" onclick={() => saves.cancel(pending.key)}>{m.save_cancel()}</button>
			</p>
		{/if}

		{#if asset}
			<div class="actions">
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
			<p class="muted hint">{m.photo_keys_hint()}</p>

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
	.card {
		display: grid;
		grid-template-columns: minmax(0, 3fr) minmax(20rem, 2fr);
		gap: 1.5rem;
		align-items: start;
	}
	@media (max-width: 60rem) {
		.card {
			grid-template-columns: 1fr;
		}
	}
	.preview {
		margin: 0;
		position: sticky;
		top: 1rem;
	}
	.preview img {
		display: block;
		max-width: 100%;
		max-height: calc(100vh - 8rem);
		margin: 0 auto;
	}
	.side {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
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
	.map {
		height: 24rem;
	}
	.coordinates {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}
	.coordinates input[aria-invalid='true'] {
		outline: 2px solid #cf222e;
	}
	.actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
	}
	.muted {
		opacity: 0.65;
	}
	.primary {
		font-weight: 600;
	}
	.pending {
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
	.hint {
		font-size: 0.85rem;
	}
	.error {
		color: #cf222e;
	}
	kbd {
		font-size: 0.75em;
		opacity: 0.7;
	}
</style>
