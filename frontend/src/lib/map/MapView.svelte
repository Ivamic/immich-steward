<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  Map of the photo card. Grey marker: the location currently stored in Immich. Red marker:
  the point the user picked (click on the map or drag the marker).
-->
<script lang="ts">
	import {
		Map as MapLibreMap,
		Marker,
		NavigationControl,
		setWorkerUrl,
		type MapMouseEvent
	} from 'maplibre-gl';
	// MapLibre looks for its worker next to its own module, but the bundler moves that module
	// into a chunk; without an explicit URL vector tiles are never parsed (blank map on zoom).
	import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
	import { untrack } from 'svelte';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import type { LatLon } from '#lib/coords.js';

	let {
		styleUrl,
		current,
		picked,
		onpick
	}: {
		styleUrl: string;
		current: LatLon | null;
		picked: LatLon | null;
		onpick: (point: LatLon) => void;
	} = $props();

	setWorkerUrl(workerUrl);

	const WORLD: [number, number] = [15, 45];
	const CLOSE_ZOOM = 14;

	let container: HTMLDivElement;
	let map = $state.raw<MapLibreMap>();
	let currentMarker: Marker | undefined;
	let pickedMarker: Marker | undefined;

	/** Moves the view to a point, e.g. a geocoder result. */
	export function flyTo(point: LatLon, zoom = CLOSE_ZOOM) {
		map?.flyTo({ center: [point.lon, point.lat], zoom });
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
		instance.on('click', (event: MapMouseEvent) =>
			onpick({ lat: event.lngLat.lat, lon: event.lngLat.lng })
		);
		currentMarker = pickedMarker = undefined;
		map = instance;
		return () => {
			instance.remove();
			map = undefined;
		};
	});

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
</script>

<div class="map" bind:this={container}></div>

<style>
	.map {
		width: 100%;
		height: 100%;
		min-height: 20rem;
		border-radius: 0.375rem;
		overflow: hidden;
	}
</style>
