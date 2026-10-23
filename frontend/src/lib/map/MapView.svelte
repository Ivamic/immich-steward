<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  Map of the photo card. Grey marker: the location currently stored in Immich. Red marker:
  the point the user picked (click on the map or drag the marker). Module suggestions: numbered
  markers in the module color with an error circle; time neighbors also draw the route of the
  located photos around the photo, with the "before" and "after" photos labelled and the segment
  between them dashed. A click close to that segment snaps onto it. Hovering a photo of the route
  shows its preview; a click pins the preview, which links to the photo (opens a new tab).
-->
<script lang="ts">
	import {
		LngLatBounds,
		Map as MapLibreMap,
		Marker,
		NavigationControl,
		Popup,
		setWorkerUrl,
		type MapGeoJSONFeature,
		type ExpressionSpecification,
		type GeoJSONSource,
		type MapMouseEvent
	} from 'maplibre-gl';
	// MapLibre looks for its worker next to its own module, but the bundler moves that module
	// into a chunk; without an explicit URL vector tiles are never parsed (blank map on zoom).
	import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
	import { untrack } from 'svelte';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import {
		thumbnailUrl,
		type Candidate,
		type ModuleSuggestions,
		type TrackPoint
	} from '#lib/api.js';
	import type { LatLon } from '#lib/coords.js';
	import { m } from '#lib/paraglide/messages.js';
	import { formatDelta, neighborMeta, numberCandidates } from '#lib/suggestions/format.js';
	import type { Highlight } from '#lib/suggestions/highlight.js';
	import { resolve } from '$app/paths';
	import {
		AFTER_RGB,
		BEFORE_RGB,
		closeness,
		rgba,
		trackColor,
		trackGradient
	} from './trackColors.js';

	let {
		styleUrl,
		current,
		picked,
		suggestions = [],
		onpick,
		highlight = null,
		onhighlight = () => {}
	}: {
		styleUrl: string;
		current: LatLon | null;
		picked: LatLon | null;
		suggestions?: ModuleSuggestions[];
		onpick: (point: LatLon) => void;
		/** The suggestion hovered in the list or on the map (FR-32). */
		highlight?: Highlight | null;
		onhighlight?: (highlight: Highlight | null) => void;
	} = $props();

	setWorkerUrl(workerUrl);

	// GeoJSON types as MapLibre takes them (the geojson typings are its dependency, not ours).
	type FeatureCollection = Extract<
		Parameters<GeoJSONSource['setData']>[0],
		{ type: 'FeatureCollection' }
	>;
	type Feature = FeatureCollection['features'][number];

	const WORLD: [number, number] = [15, 45];
	const CLOSE_ZOOM = 14;
	// A click this close (px) to the before–after segment lands on it.
	const SNAP_PX = 10;
	const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] };

	let container: HTMLDivElement;
	let map = $state.raw<MapLibreMap>();
	let ready = $state(false);
	let currentMarker: Marker | undefined;
	let pickedMarker: Marker | undefined;
	let overlayMarkers: Marker[] = [];
	// Bumped when the markers are recreated, so that the highlight is applied to the new ones.
	let overlayVersion = $state(0);
	// Preview of a photo of the route: follows the pointer, or stays after a click (pinned).
	let popup: Popup | undefined;
	let popupPinned = false;

	const route = $derived(suggestions.find((s) => s.track.length) ?? null);
	// Legend: faded long before → bright at the photo → faded long after.
	const legendRamp = `linear-gradient(to right, ${rgba(BEFORE_RGB, 0.12)}, ${rgba(BEFORE_RGB, 1)} 50%, ${rgba(AFTER_RGB, 1)} 50%, ${rgba(AFTER_RGB, 0.12)})`;
	const segment = $derived.by(() => {
		const before = route?.track.find((p) => p.role === 'before');
		const after = route?.track.find((p) => p.role === 'after');
		return before && after ? { before, after } : null;
	});

	/** Moves the view to a point, e.g. a geocoder result. */
	export function flyTo(point: LatLon, zoom = CLOSE_ZOOM) {
		map?.flyTo({ center: [point.lon, point.lat], zoom });
	}

	/** Shows all the points, e.g. the suggestions of a photo without a location. */
	export function fitTo(points: (LatLon & { radius_m?: number | null })[]) {
		if (!map || !points.length) return;
		const bounds = new LngLatBounds();
		for (const p of points) {
			// Areas with an error radius are shown whole, not just their center.
			const dLat = (p.radius_m ?? 0) / 111_320;
			const dLon = dLat / Math.max(Math.cos((p.lat * Math.PI) / 180), 0.01);
			bounds.extend([p.lon - dLon, p.lat - dLat]);
			bounds.extend([p.lon + dLon, p.lat + dLat]);
		}
		map.fitBounds(bounds, { padding: 60, maxZoom: 16, duration: 600 });
	}

	$effect(() => {
		// Only the initial view depends on the points; later changes just move the markers.
		const start = untrack(() => picked ?? current);
		const instance = new MapLibreMap({
			container,
			style: styleUrl,
			center: start ? [start.lon, start.lat] : WORLD,
			zoom: start ? CLOSE_ZOOM : 3,
			attributionControl: { compact: true }
		});
		instance.addControl(new NavigationControl({ showCompass: false }), 'top-right');
		instance.on('click', (event: MapMouseEvent) => onclick(instance, event));
		instance.on('mousemove', 'steward-track-points', (event) => {
			instance.getCanvas().style.cursor = 'pointer';
			if (!popupPinned && event.features?.length)
				showFeaturePreview(instance, event.features[0], false);
		});
		instance.on('mouseleave', 'steward-track-points', () => {
			instance.getCanvas().style.cursor = '';
			if (!popupPinned) closePreview();
		});
		instance.on('load', () => {
			addLayers(instance);
			ready = true;
		});
		currentMarker = pickedMarker = undefined;
		map = instance;
		return () => {
			ready = false;
			instance.remove();
			map = undefined;
		};
	});

	function addLayers(instance: MapLibreMap) {
		for (const id of ['steward-radius', 'steward-track', 'steward-segment']) {
			// Line metrics let the route be colored along its length (line-gradient).
			instance.addSource(id, {
				type: 'geojson',
				data: EMPTY,
				lineMetrics: id === 'steward-track'
			});
		}
		instance.addLayer({
			id: 'steward-radius-fill',
			type: 'fill',
			source: 'steward-radius',
			paint: { 'fill-color': ['get', 'color'], 'fill-opacity': radiusOpacity(null) }
		});
		instance.addLayer({
			id: 'steward-radius-line',
			type: 'line',
			source: 'steward-radius',
			paint: { 'line-color': ['get', 'color'], 'line-opacity': 0.85, 'line-width': 2 }
		});
		instance.addLayer({
			id: 'steward-track-line',
			type: 'line',
			source: 'steward-track',
			filter: ['==', ['geometry-type'], 'LineString'],
			layout: { 'line-cap': 'round', 'line-join': 'round' },
			paint: { 'line-color': '#57606a', 'line-width': 6 }
		});
		instance.addLayer({
			id: 'steward-track-points',
			type: 'circle',
			source: 'steward-track',
			filter: ['==', ['geometry-type'], 'Point'],
			paint: {
				// Photos of another camera are smaller: their clocks are less reliable.
				'circle-radius': ['case', ['get', 'same_camera'], 5, 3.5],
				'circle-color': ['get', 'color'],
				'circle-stroke-color': '#fff',
				'circle-stroke-width': 1,
				'circle-stroke-opacity': ['get', 'alpha']
			}
		});
		instance.addLayer({
			id: 'steward-segment-line',
			type: 'line',
			source: 'steward-segment',
			// Thin white dashes over the colored route: marks the segment, keeps its colors visible.
			paint: { 'line-color': '#ffffff', 'line-width': 2, 'line-dasharray': [2, 2] }
		});
	}

	$effect(() => {
		if (!map) return;
		currentMarker?.remove();
		currentMarker = current
			? new Marker({ color: '#6e7781' }).setLngLat([current.lon, current.lat]).addTo(map)
			: undefined;
	});

	$effect(() => {
		if (!map) return;
		if (!picked) {
			pickedMarker?.remove();
			pickedMarker = undefined;
			return;
		}
		if (!pickedMarker) {
			pickedMarker = new Marker({ color: '#cf222e', draggable: true })
				.setLngLat([picked.lon, picked.lat])
				.addTo(map);
			pickedMarker.on('dragend', () => {
				const at = pickedMarker?.getLngLat();
				if (at) onpick({ lat: at.lat, lon: at.lng });
			});
		} else {
			pickedMarker.setLngLat([picked.lon, picked.lat]);
		}
	});

	// Suggestions, route and their HTML markers.
	$effect(() => {
		if (!map || !ready) return;
		const instance = map;
		for (const marker of overlayMarkers) marker.remove();
		overlayMarkers = [];
		closePreview();

		source(instance, 'steward-radius').setData({
			type: 'FeatureCollection',
			features: suggestions.flatMap((module) =>
				module.candidates
					.filter((c) => c.radius_m)
					.map((c) =>
						circle(
							c.latitude,
							c.longitude,
							c.radius_m ?? 0,
							module.color,
							`${module.key}:${c.rank}`
						)
					)
			)
		});
		const track = route?.track ?? [];
		source(instance, 'steward-track').setData({
			type: 'FeatureCollection',
			features: [
				...(track.length > 1 ? [line(track)] : []),
				...track.map((p) =>
					point(p.longitude, p.latitude, {
						asset_id: p.asset_id,
						file_name: p.file_name,
						delta_s: p.delta_s,
						camera: p.camera,
						estimated: p.estimated,
						same_camera: p.same_camera,
						version: p.version ?? null,
						color: trackColor(p.delta_s),
						alpha: closeness(p.delta_s)
					})
				)
			]
		});
		const gradient = trackGradient(track);
		if (gradient) instance.setPaintProperty('steward-track-line', 'line-gradient', gradient);
		source(instance, 'steward-segment').setData(
			segment && route
				? {
						type: 'FeatureCollection',
						features: [
							{ ...line([segment.before, segment.after]), properties: { color: route.color } }
						]
					}
				: EMPTY
		);

		for (const p of track.filter((p) => p.role)) {
			const tag = document.createElement('div');
			tag.className = 'steward-tag';
			tag.textContent = `${p.role === 'before' ? m.map_before() : m.map_after()} · ${formatDelta(p.delta_s)}`;
			tag.title = `${p.file_name} — ${m.photo_open_new_tab()}`;
			tag.addEventListener('click', () =>
				showPreview(instance, { lat: p.latitude, lon: p.longitude }, [p], true)
			);
			overlayMarkers.push(
				new Marker({ element: tag, anchor: 'top', offset: [0, 14] })
					.setLngLat([p.longitude, p.latitude])
					.addTo(instance)
			);
		}
		// The same numbers as in the list, through all the modules.
		const numbers = new Map(numberCandidates(suggestions).map((i) => [i.candidate, i.number]));
		for (const module of suggestions) {
			// Lowest rank on top.
			for (const c of [...module.candidates].reverse()) {
				const pin = document.createElement('div');
				// Shape tells modules apart without relying on color (FR-31).
				pin.className = `steward-candidate steward-shape-${module.shape}`;
				// A guess from a part of the photo: same module, dashed rim.
				if (module.region) pin.classList.add('steward-part');
				pin.style.background = module.color;
				pin.style.setProperty('--marker-color', module.color);
				pin.textContent = String(numbers.get(c) ?? c.rank);
				pin.dataset.lat = String(c.latitude);
				pin.dataset.lon = String(c.longitude);
				pin.dataset.candidate = `${module.key}:${c.rank}`;
				// Hover shows the photos the suggestion comes from; a click still picks it.
				const photos = candidatePhotos(c, module.track);
				pin.addEventListener('mouseenter', () => {
					onhighlight({ module: module.key, rank: c.rank, from: 'map' });
					if (!popupPinned && photos.length) {
						showPreview(instance, { lat: c.latitude, lon: c.longitude }, photos, false);
					}
				});
				pin.addEventListener('mouseleave', () => {
					onhighlight(null);
					if (!popupPinned) closePreview();
				});
				overlayMarkers.push(
					new Marker({ element: pin }).setLngLat([c.longitude, c.latitude]).addTo(instance)
				);
			}
		}
		untrack(() => overlayVersion++);
	});

	// Outline the highlighted marker; the markers themselves are not recreated.
	$effect(() => {
		void overlayVersion;
		const key = highlight ? `${highlight.module}:${highlight.rank}` : null;
		if (map && ready)
			map.setPaintProperty('steward-radius-fill', 'fill-opacity', radiusOpacity(key));
		for (const marker of overlayMarkers) {
			const element = marker.getElement();
			if (element.dataset.candidate) {
				element.classList.toggle('steward-highlight', element.dataset.candidate === key);
			}
		}
	});

	/**
	 * Fill of the error circles: clearly visible for areas up to a city, paler for very wide ones
	 * (which would tint the whole map), strong for the highlighted suggestion.
	 */
	function radiusOpacity(highlightKey: string | null): ExpressionSpecification {
		const byRadius: ExpressionSpecification = [
			'interpolate',
			['linear'],
			['get', 'radius'],
			1000,
			0.2,
			10_000,
			0.12,
			50_000,
			0.05
		];
		return highlightKey ? ['case', ['==', ['get', 'key'], highlightKey], 0.3, byRadius] : byRadius;
	}

	function source(instance: MapLibreMap, id: string): GeoJSONSource {
		return instance.getSource(id) as GeoJSONSource;
	}

	function onclick(instance: MapLibreMap, event: MapMouseEvent) {
		// A click on a "before"/"after" label pins its photo (handled by the label itself).
		if ((event.originalEvent.target as HTMLElement | null)?.closest?.('.steward-tag')) return;
		// The first click after a pinned preview only closes it.
		if (popupPinned) {
			closePreview();
			return;
		}
		const onCandidate = (event.originalEvent.target as HTMLElement | null)?.closest?.(
			'.steward-candidate'
		);
		const { x, y } = event.point;
		const photo = onCandidate
			? []
			: instance.queryRenderedFeatures(
					[
						[x - 6, y - 6],
						[x + 6, y + 6]
					],
					{ layers: ['steward-track-points'] }
				);
		if (photo.length) showFeaturePreview(instance, photo[0], true);
		else onpick(snap(instance, event));
	}

	interface PreviewPhoto {
		asset_id: string;
		file_name: string;
		delta_s: number;
		camera: string;
		estimated: boolean;
		similarity?: number;
		local_taken_at?: string;
		version?: string | null;
	}

	function showFeaturePreview(instance: MapLibreMap, feature: MapGeoJSONFeature, pinned: boolean) {
		const props = feature.properties as PreviewPhoto;
		const [lon, lat] = (feature.geometry as { coordinates: [number, number] }).coordinates;
		showPreview(instance, { lat, lon }, [props], pinned);
	}

	function showPreview(instance: MapLibreMap, at: LatLon, photos: PreviewPhoto[], pinned: boolean) {
		closePreview();
		popup = new Popup({
			closeButton: pinned,
			closeOnClick: false,
			focusAfterOpen: false,
			offset: 16,
			maxWidth: '15rem'
		})
			.setLngLat([at.lon, at.lat])
			.setDOMContent(previewContent(photos, pinned))
			.addTo(instance);
		popupPinned = pinned;
		popup.on('close', () => (popupPinned = false));
	}

	function closePreview() {
		popup?.remove();
		popup = undefined;
		popupPinned = false;
	}

	/** Photos a suggestion is based on, with their camera taken from the route. */
	function candidatePhotos(candidate: Candidate, track: TrackPoint[]): PreviewPhoto[] {
		return (candidate.evidence.neighbors ?? []).map((n) => ({
			...n,
			camera: track.find((p) => p.asset_id === n.asset_id)?.camera ?? ''
		}));
	}

	// Built with textContent: file names come from the library and must not be parsed as HTML.
	function previewContent(photos: PreviewPhoto[], pinned: boolean): HTMLElement {
		const box = document.createElement('div');
		box.className = 'steward-preview';
		for (const photo of photos) {
			const item = document.createElement('div');
			item.className = 'item';
			const image = document.createElement('img');
			image.src = thumbnailUrl(photo.asset_id, 'thumbnail', 0, photo.version ?? null);
			image.alt = photo.file_name;
			const name = document.createElement('div');
			name.className = 'name';
			name.textContent = photo.file_name;
			const meta = document.createElement('div');
			// Map features carry their properties as strings.
			meta.textContent = neighborMeta({ ...photo, delta_s: Number(photo.delta_s) }, photo.camera);
			item.append(image, name, meta);
			if (pinned) {
				const link = document.createElement('a');
				link.href = resolve('/photo/[id]', { id: photo.asset_id });
				link.target = '_blank';
				link.rel = 'noopener';
				link.textContent = m.photo_open_new_tab();
				item.append(link);
			}
			box.append(item);
		}
		return box;
	}

	/** The clicked point, moved onto the before–after segment when the click is close to it. */
	function snap(instance: MapLibreMap, event: MapMouseEvent): LatLon {
		// A click on a suggestion marker picks exactly that suggestion.
		const pin = (event.originalEvent.target as HTMLElement | null)?.closest?.('.steward-candidate');
		if (pin instanceof HTMLElement && pin.dataset.lat && pin.dataset.lon) {
			return { lat: Number(pin.dataset.lat), lon: Number(pin.dataset.lon) };
		}
		const clicked = { lat: event.lngLat.lat, lon: event.lngLat.lng };
		if (!segment) return clicked;
		const { x, y } = event.point;
		const hit = instance.queryRenderedFeatures(
			[
				[x - SNAP_PX, y - SNAP_PX],
				[x + SNAP_PX, y + SNAP_PX]
			],
			{ layers: ['steward-segment-line'] }
		);
		if (!hit.length) return clicked;
		const a = segment.before;
		const b = segment.after;
		// Planar projection is fine at the scale of a segment.
		const k = Math.cos((a.latitude * Math.PI) / 180);
		const dx = (b.longitude - a.longitude) * k;
		const dy = b.latitude - a.latitude;
		const length = dx * dx + dy * dy;
		if (!length) return clicked;
		const t = ((clicked.lon - a.longitude) * k * dx + (clicked.lat - a.latitude) * dy) / length;
		const share = Math.min(1, Math.max(0, t));
		return { lat: a.latitude + dy * share, lon: a.longitude + (b.longitude - a.longitude) * share };
	}

	function point(lon: number, lat: number, properties = {}): Feature {
		return { type: 'Feature', properties, geometry: { type: 'Point', coordinates: [lon, lat] } };
	}

	function line(points: Pick<TrackPoint, 'latitude' | 'longitude'>[]): Feature {
		return {
			type: 'Feature',
			properties: {},
			geometry: { type: 'LineString', coordinates: points.map((p) => [p.longitude, p.latitude]) }
		};
	}

	function circle(lat: number, lon: number, radius: number, color: string, key: string): Feature {
		const steps = 64;
		const dLat = radius / 111_320;
		const dLon = radius / (111_320 * Math.cos((lat * Math.PI) / 180));
		const ring = Array.from({ length: steps + 1 }, (_, i) => {
			const angle = (i / steps) * 2 * Math.PI;
			return [lon + dLon * Math.cos(angle), lat + dLat * Math.sin(angle)];
		});
		return {
			type: 'Feature',
			properties: { color, radius, key },
			geometry: { type: 'Polygon', coordinates: [ring] }
		};
	}
</script>

<div class="wrap">
	<div class="map" bind:this={container}></div>
	{#if route}
		<div class="legend" aria-hidden="true">
			<span>{m.map_before()}</span>
			<span class="ramp" style:background={legendRamp}></span>
			<span>{m.map_after()}</span>
			<span class="note">{m.map_legend_closer()}</span>
		</div>
	{/if}
</div>

<style>
	.wrap {
		position: relative;
		width: 100%;
		height: 100%;
	}
	.legend {
		position: absolute;
		left: 0.5rem;
		bottom: 0.5rem;
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.25rem 0.5rem;
		border-radius: 0.3rem;
		background: rgb(255 255 255 / 0.9);
		color: #24292f;
		font-size: 0.75rem;
	}
	.ramp {
		width: 6rem;
		height: 0.4rem;
		border-radius: 0.2rem;
	}
	.note {
		opacity: 0.75;
	}
	.map {
		width: 100%;
		height: 100%;
		min-height: 20rem;
		border-radius: 0.375rem;
		overflow: hidden;
	}
	/* Markers are created outside the component markup, so their styles are global. */
	:global(.steward-candidate) {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.6rem;
		height: 1.6rem;
		border-radius: 50%;
		border: 2px solid #fff;
		box-shadow: 0 1px 4px rgb(0 0 0 / 0.4);
		color: #fff;
		font:
			700 0.85rem/1 system-ui,
			sans-serif;
		cursor: pointer;
	}
	:global(.steward-preview) {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		color: #24292f;
		font:
			0.8rem/1.3 system-ui,
			sans-serif;
	}
	:global(.steward-preview .item) {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}
	:global(.steward-preview .item + .item) {
		margin-top: 0.4rem;
		padding-top: 0.4rem;
		border-top: 1px solid #d0d7de;
	}
	:global(.steward-preview img) {
		width: 100%;
		max-height: 9rem;
		object-fit: cover;
		border-radius: 0.25rem;
	}
	:global(.steward-preview .name) {
		font-weight: 600;
		word-break: break-all;
	}
	/* The marker of the suggestion hovered in the list. Not a transform: MapLibre positions
	   markers with it. */
	:global(.steward-candidate.steward-part) {
		border-style: dashed;
	}
	:global(.steward-candidate.steward-highlight) {
		z-index: 5;
		outline: 3px solid #0969da;
		outline-offset: 2px;
	}
	:global(.steward-candidate.steward-shape-square) {
		border-radius: 0.3rem;
	}
	/* A square turned behind the number, so that the number stays upright. */
	:global(.steward-candidate.steward-shape-diamond) {
		position: relative;
		border: none;
		box-shadow: none;
		background: none !important;
	}
	:global(.steward-candidate.steward-shape-diamond::before) {
		content: '';
		position: absolute;
		inset: 0.2rem;
		z-index: -1;
		transform: rotate(45deg);
		background: var(--marker-color);
		border: 2px solid #fff;
		border-radius: 0.15rem;
		box-shadow: 0 1px 4px rgb(0 0 0 / 0.4);
	}
	:global(.steward-candidate.steward-shape-diamond.steward-part::before) {
		border-style: dashed;
	}
	:global(.steward-tag) {
		padding: 0.1rem 0.35rem;
		border-radius: 0.25rem;
		background: rgb(36 41 47 / 0.85);
		color: #fff;
		font:
			0.75rem/1.3 system-ui,
			sans-serif;
		white-space: nowrap;
		cursor: pointer;
	}
</style>
