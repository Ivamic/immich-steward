<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Street-level images near the point of the photo card (D-244): a switch under the map (off
     by default, remembered for the account), then the images around the point, nearest first,
     to compare with the photo by eye. Asked once the point stops; only the point leaves the
     server, and only while the switch is on. A click shows an image large, with its author and
     license, and can put the point where it was taken. -->
<script lang="ts">
	import { resolve } from '$app/paths';
	import {
		compareStreet,
		getStreetComparison,
		getStreetNear,
		getStreetSources,
		streetImageUrl,
		type Direction,
		type StreetComparison,
		type StreetImage,
		type StreetMatch,
		type StreetNear
	} from '#lib/api.js';
	import { accountSettings } from '#lib/accountSettings.svelte.js';
	import type { LatLon } from '#lib/coords.js';
	import { errorMessage } from '#lib/errors.js';
	import type { StreetMark } from '#lib/map/markers.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import Dialog from '#lib/ui/Dialog.svelte';
	import Icon from '#lib/ui/Icon.svelte';
	import PairView from '#lib/ui/PairView.svelte';

	let {
		assetId,
		point,
		photo,
		active = $bindable(null),
		// eslint-disable-next-line no-useless-assignment -- bound: the map of the card reads it
		marks = $bindable([]),
		onpick
	}: {
		/** The photo of the card, compared with the images on a worker; null: none yet. */
		assetId: string | null;
		/** Where to look: the picked point, else the location of the photo. */
		point: LatLon | null;
		/** The photo of the card as shown there, beside the image opened large; null: none. */
		photo: string | null;
		/** The image picked ("source:id"), also on the map. */
		active?: string | null;
		/** The images as the map shows them. */
		marks?: StreetMark[];
		/** "Put the point here", with the way the image looks (null: a panorama, or unknown). */
		onpick: (point: LatLon, direction: Direction | null) => void;
	} = $props();

	// Asked once the point stopped moving for this long.
	const WAIT_MS = 600;
	const RADIUS_M = 100;
	// How far off the way an image looks may be from the way the photo looks (D-245).
	const STREET_ACCURACY = 30;
	// As many as the core gives for all sources together.
	const NEAR_MOST = 40;
	// Points that fit one scene: from this many the image shows the very place of the photo,
	// from the lower number it may (as the details of similar photos, D-225).
	const SURE = 100;
	const MAYBE = 50;
	const COMPARE_POLL_MS = 2500;

	// The card may be the first page opened: the personal settings are loaded here too.
	accountSettings.load();
	const shown = $derived(accountSettings.values.street_shown);
	// The sources switched on in the settings (asked once the images are shown).
	let enabled = $state.raw<string[] | null>(null);
	// The answer of each source to the latest search; the sources still asked.
	let parts = $state.raw<Record<string, StreetNear>>({});
	let waiting = $state.raw<string[]>([]);
	let error = $state<string | null>(null);
	let opened = $state<StreetImage | null>(null);
	// The latest search: an answer to an older one is dropped.
	let asked = 0;
	const meters = new Intl.NumberFormat(getLocale(), { maximumFractionDigits: 0 });
	const dates = new Intl.DateTimeFormat(getLocale(), { year: 'numeric', month: 'short' });

	const key = (image: StreetImage) => `${image.source}:${image.id}`;

	$effect(() => {
		if (!shown || enabled !== null) return;
		getStreetSources()
			.then((sources) => (enabled = sources.filter((s) => s.enabled).map((s) => s.id)))
			.catch((e) => (error = errorMessage(e)));
	});

	// Each source is asked on its own: its images show as soon as it answers, a slow one holds
	// up only itself.
	$effect(() => {
		const at = point;
		const ids = enabled;
		if (!shown || !at || ids === null) {
			parts = {};
			waiting = [];
			return;
		}
		const search = ++asked;
		const timer = setTimeout(() => {
			waiting = [...ids];
			for (const id of ids) {
				getStreetNear(at.lat, at.lon, RADIUS_M, id)
					.then((found) => {
						if (search !== asked) return;
						parts = { ...parts, [id]: found };
						error = null;
					})
					.catch((e) => {
						if (search !== asked) return;
						const rest = { ...parts };
						delete rest[id];
						parts = rest;
						error = errorMessage(e);
					})
					.finally(() => {
						if (search === asked) waiting = waiting.filter((w) => w !== id);
					});
			}
		}, WAIT_MS);
		return () => clearTimeout(timer);
	});

	const images = $derived(
		Object.values(parts)
			.flatMap((part) => part.images)
			.sort((a, b) => a.distance_m - b.distance_m)
			.slice(0, NEAR_MOST)
	);
	const answers = $derived(Object.values(parts).flatMap((part) => part.sources));

	// The comparison of the photo with the images, on a worker (D-244).
	let comparison = $state.raw<StreetComparison | null>(null);
	const comparing = $derived(comparison?.status === 'queued' || comparison?.status === 'running');
	const matchOf = $derived(
		new Map((comparison?.status === 'done' ? comparison.results : []).map((r) => [r.key, r]))
	);
	const sure = (r: StreetMatch | undefined) => Boolean(r?.checked && r.inliers >= SURE);
	const maybe = (r: StreetMatch | undefined) =>
		Boolean(r?.checked && r.inliers >= MAYBE && r.inliers < SURE);

	// A comparison made before for this photo: its answers show on the images still near.
	$effect(() => {
		const id = assetId;
		comparison = null;
		if (!id || !shown) return;
		getStreetComparison(id)
			.then((found) => {
				if (assetId === id) comparison = found;
			})
			.catch(() => {
				// Not known: the button asks anew.
			});
	});

	// Asked again while a worker is at it.
	$effect(() => {
		const id = assetId;
		if (!id || !comparing) return;
		const timer = setTimeout(async () => {
			try {
				const found = await getStreetComparison(id);
				if (assetId === id) comparison = found;
			} catch (e) {
				error = errorMessage(e);
			}
		}, COMPARE_POLL_MS);
		return () => clearTimeout(timer);
	});

	async function startCompare() {
		if (!assetId || !images.length) return;
		try {
			comparison = await compareStreet(assetId, images.map(key));
			error = null;
		} catch (e) {
			error = errorMessage(e);
		}
	}

	// Compared: those showing the very place first, then the most alike; else nearest first.
	const ordered = $derived.by(() => {
		if (!matchOf.size) return images;
		const points = (image: StreetImage) => {
			const r = matchOf.get(key(image));
			return r?.checked && r.inliers >= MAYBE ? r.inliers : 0;
		};
		const alike = (image: StreetImage) => matchOf.get(key(image))?.similarity ?? -2;
		return [...images].sort((a, b) => points(b) - points(a) || alike(b) - alike(a));
	});
	const sureCount = $derived(images.filter((i) => sure(matchOf.get(key(i)))).length);
	const maybeCount = $derived(images.filter((i) => maybe(matchOf.get(key(i)))).length);
	const loading = $derived(waiting.length > 0);

	$effect(() => {
		marks = images.map((image) => ({
			key: key(image),
			lat: image.latitude,
			lon: image.longitude,
			heading: image.heading,
			pano: image.pano,
			active: key(image) === active
		}));
	});

	// Picked on the map: the strip scrolls to it.
	$effect(() => {
		if (active) {
			document
				.getElementById(`street-${active}`)
				?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
		}
	});

	async function toggle() {
		await accountSettings.set({ street_shown: !shown });
		if (!accountSettings.values.street_shown) {
			active = null;
			opened = null;
		}
	}

	function open(image: StreetImage) {
		active = key(image);
		opened = image;
	}

	const openedIndex = $derived(opened ? ordered.findIndex((i) => key(i) === key(opened!)) : -1);

	/** The next or the previous image of the strip, in the window. */
	function step(by: number) {
		if (openedIndex < 0 || !ordered.length) return;
		open(ordered[(openedIndex + by + ordered.length) % ordered.length]);
	}

	function onkeydown(event: KeyboardEvent) {
		if (!opened) return;
		if (event.key === 'ArrowRight') step(1);
		else if (event.key === 'ArrowLeft') step(-1);
		else return;
		event.preventDefault();
	}

	/** Which way the photo looks, put on this image: from the points both show when they were
	 * matched (narrow), else the way the image looks (wide, not from a panorama). */
	function directionFrom(image: StreetImage): Direction | null {
		if (image.heading === null) return null;
		const r = matchOf.get(key(image));
		if (r?.checked && r.inliers >= MAYBE && r.offset !== null) {
			const spread = r.spread ?? 10;
			return {
				heading: (((image.heading + r.offset) % 360) + 360) % 360,
				accuracy: Math.round(Math.min(45, Math.max(5, 2 * spread + (image.pano ? 10 : 12)))),
				source: 'street_match',
				source_ref: key(image)
			};
		}
		if (image.pano) return null;
		return {
			heading: image.heading,
			accuracy: STREET_ACCURACY,
			source: 'street',
			source_ref: key(image)
		};
	}

	function pickHere(image: StreetImage) {
		const direction = directionFrom(image);
		onpick({ lat: image.latitude, lon: image.longitude }, direction);
		opened = null;
	}

	const sourceName = (id: string) => (id === 'mapillary' ? 'Mapillary' : 'Panoramax');
	const problems = $derived(answers.filter((s) => s.status !== 'ok'));
	const noSource = $derived(enabled !== null && enabled.length === 0);

	function problem(status: string): string {
		if (status === 'no_key') return m.street_problem_no_key();
		if (status === 'invalid_key') return m.street_problem_invalid();
		return m.street_problem_unavailable();
	}

	// An arrow that points the way the camera looked (north up, as the map).
	const arrow = (heading: number | null) => (heading === null ? '' : `rotate(${heading}deg)`);
</script>

<!-- eslint-disable svelte/no-navigation-without-resolve -- links to the providers -->
<section class="street">
	<div class="head">
		<button
			type="button"
			class="st-btn st-btn--sm"
			class:st-btn--secondary={shown}
			class:st-btn--ghost={!shown}
			aria-pressed={shown}
			title={m.street_toggle_hint()}
			onclick={toggle}
		>
			<Icon name="camera" size={14} />
			{m.street_toggle()}
		</button>
		{#if shown && assetId && images.length}
			<button
				type="button"
				class="st-btn st-btn--sm st-btn--secondary"
				disabled={comparing}
				title={m.street_compare_hint()}
				onclick={startCompare}
			>
				<Icon name="scan-search" size={14} />
				{m.street_compare()}
			</button>
		{/if}
		{#if shown}
			<span class="status" role="status">
				{#if !point}
					{m.street_no_point()}
				{:else if noSource}
					{m.street_no_source()}
					<a href={resolve('/settings#street')}>{m.street_settings_link()}</a>
				{:else if images.length}
					{m.street_found({ count: images.length, radius: RADIUS_M })}
				{:else if loading || enabled === null}
					{m.street_loading()}
				{:else}
					{m.street_none({ radius: RADIUS_M })}
				{/if}
				{#if loading && images.length}
					<span>{m.street_waiting({ sources: waiting.map(sourceName).join(', ') })}</span>
				{/if}
				{#if comparing}
					<span>
						{comparison?.workers ? m.street_comparing() : m.street_compare_no_worker()}
					</span>
				{:else if comparison?.status === 'failed'}
					<span class="problem">{m.street_compare_failed()}</span>
				{:else if matchOf.size}
					<span>{m.street_compare_done({ sure: sureCount, maybe: maybeCount })}</span>
				{/if}
				{#each problems as found (found.id)}
					<span class="problem">
						{sourceName(found.id)}: {problem(found.status)}
						{#if found.status !== 'unavailable'}
							<a href={resolve('/settings#street')}>{m.street_settings_link()}</a>
						{/if}
					</span>
				{/each}
			</span>
		{/if}
	</div>
	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
	{#if shown && point && !noSource}
		<!-- Its place is kept while it waits: the map above keeps its size. -->
		<ul class="strip" class:loading class:empty={!images.length}>
			{#each ordered as image (key(image))}
				{@const found = matchOf.get(key(image))}
				<li>
					<button
						type="button"
						id="street-{key(image)}"
						class="shot"
						class:active={active === key(image)}
						title={image.author
							? `${sourceName(image.source)} · ${image.author}`
							: sourceName(image.source)}
						onclick={() => open(image)}
						onmouseenter={() => (active = key(image))}
					>
						<img src={streetImageUrl(image)} alt="" loading="lazy" />
						{#if sure(found)}
							<span class="mark sure">{m.street_match_sure({ count: found?.inliers ?? 0 })}</span>
						{:else if maybe(found)}
							<span class="mark maybe">{m.street_match_maybe()}</span>
						{/if}
						<span class="meta">
							{#if image.heading !== null && !image.pano}
								<span class="arrow" style:transform={arrow(image.heading)} aria-hidden="true"
									>↑</span
								>
							{/if}
							{#if image.pano}<span class="pano">360°</span>{/if}
							{m.street_distance({ meters: meters.format(image.distance_m) })}
						</span>
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<svelte:window {onkeydown} />

{#snippet credits(image: StreetImage)}
	{#if image.author}{m.street_author({ author: image.author })} ·{/if}
	{#if image.license}
		{#if image.license_url}
			<a href={image.license_url} target="_blank" rel="noopener">{image.license}</a>
		{:else}{image.license}{/if}
		·
	{/if}
	<a href={image.page_url} target="_blank" rel="noopener">
		{m.street_open_at({ source: sourceName(image.source) })}
	</a>
	· {m.street_distance({ meters: meters.format(image.distance_m) })}
	{#if image.pano}· 360°{/if}
{/snippet}

{#if opened}
	{@const image = opened}
	<Dialog
		title={`${sourceName(image.source)}${image.taken_at ? ` · ${dates.format(new Date(image.taken_at))}` : ''}`}
		icon="camera"
		full
		onclose={() => (opened = null)}
	>
		{@const found = matchOf.get(key(image))}
		{#if photo}
			<PairView
				first={{ src: photo, alt: m.street_your_photo(), caption: m.street_your_photo() }}
				second={{ src: streetImageUrl(image, 'large'), alt: m.street_image_alt() }}
				lines={found?.checked ? found.lines : []}
			>
				{#snippet secondCaption()}{@render credits(image)}{/snippet}
				{#snippet note()}
					{#if found?.checked}
						{m.street_match_note({ count: found.inliers })}
					{:else if found?.similarity != null}
						{m.street_similarity({ percent: Math.round(Math.max(0, found.similarity) * 100) })}
					{/if}
				{/snippet}
			</PairView>
		{:else}
			<figure class="side" class:pano={image.pano}>
				<div class="frame">
					<img src={streetImageUrl(image, 'large')} alt={m.street_image_alt()} />
				</div>
				<figcaption>{@render credits(image)}</figcaption>
			</figure>
		{/if}
		{#snippet footer()}
			<span class="stepper">
				<button
					type="button"
					class="st-iconbtn"
					aria-label={m.street_previous()}
					title={m.street_previous()}
					disabled={ordered.length < 2}
					onclick={() => step(-1)}
				>
					<Icon name="chevron-left" />
				</button>
				<span class="count">{openedIndex + 1} / {ordered.length}</span>
				<button
					type="button"
					class="st-iconbtn"
					aria-label={m.street_next()}
					title={m.street_next()}
					disabled={ordered.length < 2}
					onclick={() => step(1)}
				>
					<Icon name="chevron-right" />
				</button>
			</span>
			<button type="button" class="st-btn st-btn--secondary" onclick={() => (opened = null)}>
				{m.street_close()}
			</button>
			<button type="button" class="st-btn st-btn--primary" onclick={() => pickHere(image)}>
				<Icon name="map-pin" size={16} />
				{m.street_pick_here()}
			</button>
		{/snippet}
	</Dialog>
{/if}

<style>
	.street {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		margin-top: var(--space-2);
	}
	.head {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-2);
	}
	.status {
		display: inline-flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	.problem {
		color: var(--color-warning-text, var(--color-text-muted));
	}
	.error {
		margin: 0;
		color: var(--color-danger-text);
	}
	.strip {
		display: flex;
		gap: var(--space-2);
		margin: 0;
		padding: 0 0 var(--space-1);
		list-style: none;
		overflow-x: auto;
	}
	.strip.loading {
		opacity: 0.6;
	}
	/* The height of a row of images: kept while there are none yet. */
	.strip.empty {
		min-height: calc(6rem + 1.75rem);
	}
	.shot {
		position: relative;
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		padding: 2px;
		border: 2px solid transparent;
		border-radius: var(--radius-md);
		background: none;
		cursor: pointer;
	}
	.shot.active {
		border-color: #bc4c00;
	}
	.shot img {
		display: block;
		width: 9rem;
		height: 6rem;
		object-fit: cover;
		border-radius: var(--radius-sm);
		background: var(--color-surface-sunken, var(--color-surface));
	}
	/* What the comparison found, on the image. */
	.mark {
		position: absolute;
		top: 6px;
		left: 6px;
		padding: 0 var(--space-1-5);
		border-radius: var(--radius-sm);
		font-size: var(--text-xs, var(--text-sm));
		font-weight: var(--weight-medium);
		color: #ffffff;
	}
	.mark.sure {
		background: #1a7f37;
	}
	.mark.maybe {
		background: #9a6700;
	}
	.meta {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		font-size: var(--text-xs, var(--text-sm));
		color: var(--color-text-muted);
	}
	.arrow {
		display: inline-block;
		font-weight: var(--weight-medium);
	}
	.pano {
		font-weight: var(--weight-medium);
	}
	.side {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		margin: 0;
		min-width: 0;
	}
	.side img {
		display: block;
		width: 100%;
		max-height: 65vh;
		object-fit: contain;
		background: var(--color-stage);
		border-radius: var(--radius-md);
	}
	/* A 360-degree panorama: as wide as it is, scrolled sideways. */
	.side.pano .frame {
		overflow-x: auto;
	}
	.side.pano img {
		width: auto;
		max-width: none;
		height: 50vh;
		max-height: none;
	}
	figcaption {
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	.stepper {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		margin-right: auto;
	}
	.count {
		font-size: var(--text-sm);
		font-variant-numeric: tabular-nums;
		color: var(--color-text-muted);
	}
</style>
