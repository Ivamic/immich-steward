<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  Map of the photo card. Grey pin: the location currently stored in Immich. Dark pin with a
  green dot: the point the user picked (click on the map or drag the pin). Module suggestions:
  numbered markers in the module color and shape with an error circle; time neighbors also draw the route of the
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
		type MapAuto,
		type MapKeyProblem,
		type MapSourceConfig,
		type ModuleSuggestions,
		type TrackPoint
	} from '#lib/api.js';
	import type { LatLon } from '#lib/coords.js';
	import { m } from '#lib/paraglide/messages.js';
	import {
		formatDelta,
		moduleName,
		neighborMeta,
		numberCandidates
	} from '#lib/suggestions/format.js';
	import { theme } from '#lib/theme.svelte.js';
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
	import { moduleColor, moduleOnColor, resolvedColor } from './modulePalette.js';
	import { markerElement, pinElement, shapeSvg } from './markers.js';
	import MapSourceSwitcher from './MapSourceSwitcher.svelte';
	import {
		areaMode,
		attributionHtml,
		effectiveSource,
		protocolUrl,
		SCHEME,
		shortAttribution
	} from './sources.js';
	import { onKeyProblem, registerTileProtocol } from './tileProtocol.js';

	let {
		styleUrl,
		styleUrlDark = null,
		sources = [],
		auto = null,
		current,
		picked,
		suggestions = [],
		onpick,
		highlight = null,
		onhighlight = () => {}
	}: {
		styleUrl: string;
		/** The map style for the dark theme; null: `styleUrl`, dimmed. */
		styleUrlDark?: string | null;
		/** Satellite imagery sources of the account (D-140). */
		sources?: MapSourceConfig[];
		/** Their automatic switching by zoom; null: none. */
		auto?: MapAuto | null;
		current: LatLon | null;
		picked: LatLon | null;
		suggestions?: ModuleSuggestions[];
		onpick: (point: LatLon) => void;
		/** The suggestion hovered in the list or on the map (FR-32). */
		highlight?: Highlight | null;
		onhighlight?: (highlight: Highlight | null) => void;
	} = $props();

	setWorkerUrl(workerUrl);
	registerTileProtocol();

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
	// The style follows the theme; switching it keeps the view (no new map).
	const style = $derived(theme.resolved === 'dark' && styleUrlDark ? styleUrlDark : styleUrl);

	// Satellite imagery: what was picked over the map is remembered in this browser.
	const SOURCE_KEY = 'steward-map-source';
	const AUTO_KEY = 'steward-map-auto';
	const LABELS_KEY = 'steward-map-labels';
	const AREAS_KEY = 'steward-map-areas';
	const IMAGERY = 'steward-imagery';
	let choice = $state(stored(SOURCE_KEY, SCHEME));
	// The plain map until something else is picked; auto switching only when turned on.
	let autoOn = $state(stored(AUTO_KEY, 'off') === 'on');
	let labels = $state(stored(LABELS_KEY, 'on') === 'on');
	// The fill of the areas may hide the imagery: it can be left out, or the areas altogether.
	let areas = $state(areaMode(stored(AREAS_KEY, 'fill')));
	// The latest EOX year unless another is picked in this page (D-146).
	let eoxYear = $state<string | null>(null);
	let zoom = $state(3);
	// Key problems the tiles told in this page: such a source is skipped at once.
	let problems = $state<Record<string, MapKeyProblem>>({});
	// Copyright texts the providers gave (Esri), by source.
	let copyrights = $state<Record<string, string>>({});
	// "Auto" does nothing until the settings name a far or a near source.
	const autoActive = $derived(autoOn && auto !== null && (auto.far !== null || auto.near !== null));
	const active = $derived(
		effectiveSource(sources, choice, autoActive ? auto : null, zoom, new Set(Object.keys(problems)))
	);
	const activeSource = $derived(sources.find((s) => s.id === active) ?? null);
	const year = $derived(eoxYear ?? sources.find((s) => s.id === 'eox')?.variants[0]?.id ?? '');
	// Without a dark style of its own, the light map is dimmed in the dark theme (detailed, and
	// no glaring white); markers and pins are HTML above it and keep their colors. Imagery is not.
	const dimmed = $derived(theme.resolved === 'dark' && !styleUrlDark && active === SCHEME);
	let appliedImagery = '';
	// Layers the style itself hides; showing them again after the imagery must not show these.
	let hiddenByStyle = new Set<string>();
	let appliedStyle = '';
	let currentMarker: Marker | undefined;
	let pickedMarker: Marker | undefined;
	let overlayMarkers: Marker[] = [];
	// Bumped when the markers are recreated, so that the highlight is applied to the new ones.
	let overlayVersion = $state(0);
	// Preview of a photo of the route: follows the pointer, or stays after a click (pinned).
	let popup: Popup | undefined;
	let popupPinned = false;

	const route = $derived(suggestions.find((s) => s.track.length) ?? null);
	const hasAreas = $derived(suggestions.some((s) => s.candidates.some((c) => c.radius_m)));
	const hasSources = $derived(sources.some((s) => s.enabled));
	// Modules with suggestions on the map, in the order of the list.
	const legend = $derived(
		suggestions
			.filter((s) => s.candidates.length)
			.map((s) => ({
				key: s.key,
				shape: s.shape,
				color: moduleColor(s.module, s.color),
				name: s.region
					? m.module_part_title({ module: moduleName(s.module) })
					: moduleName(s.module),
				count: s.candidates.length
			}))
	);
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
		appliedStyle = untrack(() => style);
		const instance = new MapLibreMap({
			container,
			style: appliedStyle,
			center: start ? [start.lon, start.lat] : WORLD,
			zoom: start ? CLOSE_ZOOM : 3,
			attributionControl: { compact: true }
		});
		// The full attribution opens with (i); the short one (CSS) is always visible.
		instance.once('idle', () =>
			container
				.querySelector('.maplibregl-ctrl-attrib')
				?.classList.remove('maplibregl-compact-show')
		);
		instance.addControl(new NavigationControl({ showCompass: false }), 'top-right');
		instance.on('click', (event: MapMouseEvent) => onclick(instance, event));
		zoom = instance.getZoom();
		instance.on('zoomend', () => (zoom = instance.getZoom()));
		instance.on('mousemove', 'steward-track-points', (event) => {
			instance.getCanvas().style.cursor = 'pointer';
			if (!popupPinned && event.features?.length)
				showFeaturePreview(instance, event.features[0], false);
		});
		instance.on('mouseleave', 'steward-track-points', () => {
			instance.getCanvas().style.cursor = '';
			if (!popupPinned) closePreview();
		});
		// Also after a change of the style (theme): it drops the layers of the app.
		instance.on('style.load', () => {
			addLayers(instance);
			const { labels: named, over } = styleLayers(instance);
			hiddenByStyle = new Set(
				[...named, ...over].filter((id) => instance.getLayoutProperty(id, 'visibility') === 'none')
			);
			appliedImagery = '';
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

	$effect(() => {
		const url = style;
		if (!map || url === appliedStyle) return;
		appliedStyle = url;
		ready = false;
		closePreview();
		map.setStyle(url, { diff: false });
	});

	function stored(key: string, fallback: string): string {
		try {
			return localStorage.getItem(key) ?? fallback;
		} catch {
			return fallback;
		}
	}

	function store(key: string, value: string) {
		try {
			localStorage.setItem(key, value);
		} catch {
			// Private mode or blocked storage: the choice lasts for this page only.
		}
	}

	$effect(() =>
		onKeyProblem((sourceId, problem) => {
			if (problems[sourceId] !== problem) problems = { ...problems, [sourceId]: problem };
		})
	);

	// The provider's copyright text, read once per page where it changes (Esri).
	$effect(() => {
		const source = activeSource;
		if (!source?.copyright_url || source.id in untrack(() => copyrights)) return;
		const { id, copyright } = source;
		// Our built-in text when the provider gives none.
		fetch(source.copyright_url)
			.then((response) => response.json())
			.then((body: { copyrightText?: unknown }) =>
				typeof body.copyrightText === 'string' && body.copyrightText
					? body.copyrightText
					: (copyright ?? '')
			)
			.catch(() => copyright ?? '')
			.then((text) => (copyrights = { ...copyrights, [id]: text }));
	});

	// The imagery under the labels of the style and our layers (D-143); again after a new style.
	$effect(() => {
		if (!map || !ready) return;
		const instance = map;
		const source = activeSource;
		const variant = source
			? (source.variants.find((v) => v.id === (source.id === 'eox' ? year : 'default')) ??
				source.variants[0])
			: null;
		// The tiles wait for the copyright text, so that they are not loaded twice.
		if (source?.copyright_url && !(source.id in copyrights)) return;
		const copyright = source ? (copyrights[source.id] ?? source.copyright) : null;
		const key = variant?.tiles ? `${source?.id}|${variant.id}|${copyright}` : '';
		if (key !== appliedImagery) {
			if (instance.getLayer(IMAGERY)) instance.removeLayer(IMAGERY);
			if (instance.getSource(IMAGERY)) instance.removeSource(IMAGERY);
			if (source && variant?.tiles) {
				instance.addSource(IMAGERY, {
					type: 'raster',
					tiles: [protocolUrl(source.id, variant.tiles)],
					tileSize: source.tile_size,
					maxzoom: source.max_zoom,
					attribution: attributionHtml(variant.attribution, copyright)
				});
				const labelsFrom = styleLayers(instance).firstLabel;
				instance.addLayer({ id: IMAGERY, type: 'raster', source: IMAGERY }, labelsFrom);
			}
			appliedImagery = key;
		}
		const { labels: named, over } = styleLayers(instance);
		const show = (id: string, visible: boolean) => {
			if (!hiddenByStyle.has(id))
				instance.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
		};
		for (const id of named) show(id, !key || labels);
		for (const id of over) show(id, !key);
	});

	/**
	 * Layers of the style (not ours) as the imagery sees them: `labels` are the names of places,
	 * roads and water, kept over the imagery when wanted; `over` would cover the imagery and go
	 * while it is shown: what the style draws above its first label (bridges, buildings, their 3D
	 * shapes, borders) and the icons of places of interest.
	 */
	function styleLayers(instance: MapLibreMap): {
		labels: string[];
		over: string[];
		firstLabel: string | undefined;
	} {
		const layers = instance.getStyle().layers.filter((l) => !l.id.startsWith('steward-'));
		const first = layers.findIndex((l) => l.type === 'symbol');
		const poi = (l: (typeof layers)[number]) => 'source-layer' in l && l['source-layer'] === 'poi';
		const labels = layers.filter((l) => l.type === 'symbol' && !poi(l)).map((l) => l.id);
		const over = layers
			.filter(
				(l, i) =>
					(l.type !== 'symbol' && first >= 0 && i > first) || (l.type === 'symbol' && poi(l))
			)
			.map((l) => l.id);
		return { labels, over, firstLabel: first >= 0 ? layers[first].id : undefined };
	}

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
			? new Marker({ element: pinElement('current', m.map_current()), anchor: 'bottom' })
					.setLngLat([current.lon, current.lat])
					.addTo(map)
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
			pickedMarker = new Marker({
				element: pinElement('picked', m.map_picked()),
				anchor: 'bottom',
				draggable: true
			})
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
		// Layer colors are computed from the theme: redraw when it changes.
		void theme.resolved;
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
							resolvedColor(moduleColor(module.module, module.color)),
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
				// Shape tells modules apart without relying on color (FR-31); a guess from a part of
				// the photo has a dashed rim.
				const pin = markerElement({
					shape: module.shape,
					number: numbers.get(c) ?? c.rank,
					color: moduleColor(module.module, module.color),
					on: moduleOnColor(module.module),
					part: Boolean(module.region),
					weak: c.tier === 'weak',
					label: `${moduleName(module.module)} ${numbers.get(c) ?? c.rank}`
				});
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

	// Also after a change of the style, which adds the layers again.
	$effect(() => {
		if (!map || !ready) return;
		map.setLayoutProperty(
			'steward-radius-fill',
			'visibility',
			areas === 'fill' ? 'visible' : 'none'
		);
		map.setLayoutProperty(
			'steward-radius-line',
			'visibility',
			areas === 'none' ? 'none' : 'visible'
		);
	});

	// Outline the highlighted marker; the markers themselves are not recreated.
	$effect(() => {
		void overlayVersion;
		const key = highlight ? `${highlight.module}:${highlight.rank}` : null;
		if (map && ready)
			map.setPaintProperty('steward-radius-fill', 'fill-opacity', radiusOpacity(key));
		for (const marker of overlayMarkers) {
			const element = marker.getElement();
			const shape = element.querySelector<HTMLElement>('.st-marker');
			if (element.dataset.candidate && shape) {
				const highlighted = element.dataset.candidate === key;
				if (highlighted) shape.dataset.state = 'highlight';
				else if (shape.dataset.weak) shape.dataset.state = 'weak';
				else delete shape.dataset.state;
				// Above the other markers while highlighted.
				element.style.zIndex = highlighted ? '2' : '';
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

<div class="frame">
	<!-- For an account that switched a satellite source on, or when there are areas to draw. -->
	{#if hasSources || hasAreas}
		<MapSourceSwitcher
			sources={hasSources ? sources : []}
			{areas}
			{hasAreas}
			{auto}
			autoOn={autoActive}
			{labels}
			{year}
			{active}
			{zoom}
			{problems}
			onchoice={(id) => {
				choice = id;
				store(SOURCE_KEY, id);
			}}
			onauto={(on) => {
				autoOn = on;
				store(AUTO_KEY, on ? 'on' : 'off');
			}}
			onlabels={(on) => {
				labels = on;
				store(LABELS_KEY, on ? 'on' : 'off');
			}}
			onareas={(mode) => {
				areas = mode;
				store(AREAS_KEY, mode);
			}}
			onyear={(picked) => (eoxYear = picked)}
		/>
	{/if}
	<div
		class="wrap"
		class:dimmed
		class:with-logo={activeSource?.logo_url}
		style:--_attrib-short={`'${shortAttribution(active)}'`}
	>
		<div class="map" bind:this={container}></div>
		{#if activeSource?.logo_url}
			<!-- Required on the map by the free plan of MapTiler; loaded from MapTiler with its tiles. -->
			<a class="logo" href="https://www.maptiler.com/" target="_blank" rel="noopener">
				<img src={activeSource.logo_url} alt={activeSource.name} width="67" height="20" />
			</a>
		{/if}
		{#if legend.length || route}
			<div class="legend st-glass st-legend" aria-hidden="true">
				{#each legend as row (row.key)}
					<div class="st-legend__row">
						<span
							class="st-marker st-marker--sm st-marker--{row.shape}"
							style:--_c={row.color}
							style:--_on="var(--gray-0)"
						>
							<!-- eslint-disable-next-line svelte/no-at-html-tags -- fixed markup from markers.ts -->
							{@html shapeSvg(row.shape)}
						</span>
						<span class="st-legend__name">{row.name}</span>
						<span class="st-legend__count">{row.count}</span>
					</div>
				{/each}
				{#if route}
					<div class="st-legend__route" class:first={!legend.length}>
						<span>{m.map_before()}</span>
						<span class="ramp" style:background={legendRamp}></span>
						<span>{m.map_after()}</span>
					</div>
					<div class="st-legend__note">{m.map_legend_closer()}</div>
				{/if}
			</div>
		{/if}
	</div>
</div>

<style>
	.frame {
		display: flex;
		flex-direction: column;
		width: 100%;
		height: 100%;
	}
	.wrap {
		position: relative;
		flex: 1;
		min-height: 0;
		width: 100%;
	}
	.legend {
		position: absolute;
		left: var(--space-2);
		bottom: var(--space-2);
		z-index: var(--z-map-ui);
	}
	.with-logo .legend {
		bottom: calc(var(--space-2) * 2 + 20px);
	}
	.logo {
		position: absolute;
		left: var(--space-2);
		bottom: var(--space-2);
		z-index: var(--z-map-ui);
		display: block;
		line-height: 0;
	}
	.st-legend__route.first {
		padding-top: 0;
		border-top: 0;
	}
	.ramp {
		flex: 1;
		min-width: 3rem;
		height: 0.375rem;
		border-radius: var(--radius-full);
	}
	.map {
		width: 100%;
		height: 100%;
		min-height: 20rem;
	}
	.dimmed .map :global(.maplibregl-canvas) {
		filter: brightness(0.7) contrast(1.05) saturate(0.85);
	}
	/* Markers and popups are created outside the component markup, so their styles are global. */
	.map :global(.steward-candidate) {
		cursor: pointer;
	}
	.map :global(.st-pin) {
		cursor: grab;
	}
	.map :global(.st-pin--current) {
		cursor: default;
	}
	.map :global(.maplibregl-popup-content) {
		padding: var(--space-2);
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface-raised);
		color: var(--color-text);
		box-shadow: var(--shadow-md);
	}
	.map :global(.maplibregl-popup-tip) {
		border-top-color: var(--color-surface-raised);
		border-bottom-color: var(--color-surface-raised);
	}
	.map :global(.maplibregl-popup-close-button) {
		color: var(--color-text-muted);
	}
	.map :global(.steward-preview) {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		font: var(--text-xs) / var(--leading-snug) var(--font-sans);
	}
	.map :global(.steward-preview .item) {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}
	.map :global(.steward-preview .item + .item) {
		margin-top: var(--space-1-5);
		padding-top: var(--space-1-5);
		border-top: var(--border-width) solid var(--color-border);
	}
	.map :global(.steward-preview img) {
		width: 100%;
		max-height: 9rem;
		object-fit: cover;
		border-radius: var(--radius-xs);
	}
	.map :global(.steward-preview .name) {
		font-weight: var(--weight-semibold);
		word-break: break-all;
	}
	.map :global(.steward-preview a) {
		color: var(--color-accent-text);
	}
	/* "Before" / "after" labels of the route. */
	.map :global(.steward-tag) {
		padding: 0.1rem var(--space-1-5);
		border-radius: var(--radius-xs);
		background: oklch(0.2 0 0 / 0.86);
		color: var(--gray-0);
		font: var(--weight-medium) var(--text-xs) / 1.4 var(--font-sans);
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
		cursor: pointer;
		box-shadow: var(--shadow-sm);
	}
	/* Map controls and attribution on glass, as the other panels over the map. */
	.map :global(.maplibregl-ctrl-group) {
		overflow: hidden;
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-glass);
		backdrop-filter: var(--blur-glass);
		box-shadow: var(--shadow-sm);
	}
	.map :global(.maplibregl-ctrl-group button + button) {
		border-top: var(--border-width) solid var(--color-border);
	}
	.map :global(.maplibregl-ctrl-attrib) {
		margin: 0 var(--space-2) var(--space-2) 0;
		border-radius: var(--radius-xs);
		background: var(--color-glass);
		backdrop-filter: var(--blur-glass);
		color: var(--color-text-muted);
		/* 12 px: the least Esri allows for its attribution. */
		font: 0.75rem / 1.25rem var(--font-sans);
	}
	.map :global(.maplibregl-ctrl-attrib a) {
		color: inherit;
	}
	/* Collapsed: the short attribution stays visible next to (i). */
	.map :global(.maplibregl-ctrl-attrib.maplibregl-compact:not(.maplibregl-compact-show)) {
		display: flex;
		align-items: center;
		padding: 0 1.5rem 0 var(--space-1-5);
		min-height: 1.25rem;
	}
	.map :global(.maplibregl-ctrl-attrib.maplibregl-compact:not(.maplibregl-compact-show))::before {
		content: var(--_attrib-short);
		white-space: nowrap;
	}
	/* MapLibre draws its control icons dark: light ones on the dark glass. */
	:global([data-theme='dark']) .map :global(.maplibregl-ctrl-icon),
	:global([data-theme='dark']) .map :global(.maplibregl-ctrl-attrib-button) {
		filter: invert(1);
	}
	.map :global(.maplibregl-ctrl-attrib-button) {
		top: 0;
		right: 0;
		width: 1.25rem;
		height: 1.25rem;
		background-size: 1rem;
	}
</style>
