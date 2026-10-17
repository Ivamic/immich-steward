<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  Photo card: preview, details, map with the location picker, review actions and keyboard
  navigation. Writing the picked location to Immich comes with the next step.
-->
<script lang="ts">
	import {
		getAsset,
		getMapConfig,
		setReview,
		thumbnailUrl,
		type AssetDetail,
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
	const place = $derived([asset?.city, asset?.state, asset?.country].filter(Boolean).join(', '));

	$effect(() => {
		getMapConfig()
			.then((config) => (mapConfig = config))
			.catch((e) => (error = errorMessage(e)));
	});

	$effect(() => {
		const assetId = id;
		const currentFilter = filter;
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

	function onkeydown(event: KeyboardEvent) {
		if (event.ctrlKey || event.metaKey || event.altKey) return;
		if ((event.target as HTMLElement).closest('input, textarea, select')) return;
		const actions: Record<string, () => void> = {
			arrowleft: () => open(asset?.previous_id),
			arrowright: () => open(asset?.next_id),
			escape: () => goto(resolve(`/${query}`)),
			n: () => review('not_applicable'),
			s: () => review('skipped'),
			u: () => review('new')
		};
		const action = actions[event.key.toLowerCase()];
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
			<p class="muted">{m.photo_save_next_step()}</p>
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
