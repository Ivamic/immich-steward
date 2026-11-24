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
	import { metersBetween, type LatLon } from '#lib/coords.js';
	import { commonHeading, directionText } from '#lib/direction.js';
	import { errorMessage } from '#lib/errors.js';
	import type { StreetMark } from '#lib/map/markers.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import BetaBadge from '#lib/ui/BetaBadge.svelte';
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
		onpick,
		ondirection
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
		/** "Take the direction": the way the photo looks by the images matched, the point kept. */
		ondirection?: (direction: Direction) => void;
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
	// Searched around an image instead of the point (D-246): its key and place; the point of the
	// photo stays where it is. Back to the point when the point moves.
	let center = $state<{ key: string; at: LatLon } | null>(null);
	// Every image found for this photo, also by the searches before: an image matched with the
	// photo stays in the strip when the search moves on.
	let seen = $state.raw<Map<string, StreetImage>>(new Map());
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
	// By value: the card gives a new object for the same point when the photo is saved.
	const pointKey = $derived(point ? `${point.lat},${point.lon}` : '');
	$effect(() => {
		void pointKey;
		center = null;
	});

	$effect(() => {
		const at = center?.at ?? point;
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
						seen = new Map([...seen, ...found.images.map((i) => [key(i), i] as const)]);
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

	// Metres from the point of the photo, also when searched around an image.
	const distanceOf = (image: StreetImage) =>
		point ? metersBetween(point, { lat: image.latitude, lon: image.longitude }) : image.distance_m;
	// Those of the latest search, and the ones matched by the searches before.
	const images = $derived.by(() => {
		const near = Object.values(parts)
			.flatMap((part) => part.images)
			.sort((a, b) => a.distance_m - b.distance_m)
			.slice(0, NEAR_MOST);
		const keys = new Set(near.map(key));
		const earlier = [...seen.values()].filter((image) => {
			const r = matchOf.get(key(image));
			return !keys.has(key(image)) && r?.checked && r.inliers >= MAYBE;
		});
		return [...near, ...earlier].sort((a, b) => distanceOf(a) - distanceOf(b));
	});
	const answers = $derived(Object.values(parts).flatMap((part) => part.sources));

	// The comparison of the photo with the images, on a worker (D-244).
	let comparison = $state.raw<StreetComparison | null>(null);
	const comparing = $derived(comparison?.status === 'queued' || comparison?.status === 'running');
	// The answers kept: while a worker compares new images, those about the earlier ones stay.
	let lastDone = $state.raw<StreetComparison | null>(null);
	$effect(() => {
		if (comparison?.status === 'done') lastDone = comparison;
	});
	const matchOf = $derived(new Map((lastDone?.results ?? []).map((r) => [r.key, r])));
	const sure = (r: StreetMatch | undefined) => Boolean(r?.checked && r.inliers >= SURE);
	const maybe = (r: StreetMatch | undefined) =>
		Boolean(r?.checked && r.inliers >= MAYBE && r.inliers < SURE);

	// A comparison made before for this photo: its answers show on the images still near.
	$effect(() => {
		const id = assetId;
		comparison = null;
		lastDone = null;
		seen = new Map();
		if (!id || !shown) return;
		getStreetComparison(id)
			.then((found) => {
				if (assetId === id) comparison = found;
			})
			.catch(() => {
				// Not known: the button asks anew.
			});
	});

	// Asked again while a worker is at it. Each answer starts the next wait: the effect reads the
	// comparison itself, not only whether it is going on, which stays the same between answers.
	$effect(() => {
		const id = assetId;
		const current = comparison;
		if (!id || !(current?.status === 'queued' || current?.status === 'running')) return;
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

	// Not compared yet: only these go to the worker, the answers about the rest are kept.
	const fresh = $derived(images.filter((image) => !matchOf.has(key(image))));

	async function startCompare() {
		if (!assetId || !fresh.length) return;
		try {
			comparison = await compareStreet(assetId, fresh.map(key));
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

	const matchLevel = (image: StreetImage): 0 | 1 | 2 => {
		const r = matchOf.get(key(image));
		return sure(r) ? 2 : maybe(r) ? 1 : 0;
	};
	const anyMatch = $derived(sureCount + maybeCount > 0);

	$effect(() => {
		marks = images.map((image) => ({
			key: key(image),
			lat: image.latitude,
			lon: image.longitude,
			heading: image.heading,
			pano: image.pano,
			active: key(image) === active,
			match: matchLevel(image),
			faded: anyMatch && matchLevel(image) === 0
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

	// The way the photo looks by each image matched with it: the image's own heading turned by
	// as much as the points both show tell.
	const headings = $derived(
		images.flatMap((image) => {
			const r = matchOf.get(key(image));
			if (image.heading === null || !r?.checked || r.inliers < MAYBE || r.offset === null)
				return [];
			return [
				{
					heading: (((image.heading + r.offset) % 360) + 360) % 360,
					weight: r.inliers,
					accuracy: Math.min(45, Math.max(5, 2 * (r.spread ?? 10) + (image.pano ? 10 : 12))),
					key: key(image)
				}
			];
		})
	);
	// By all of them together (D-246): one image alone is right only if the photo was taken
	// where it was.
	const common = $derived(commonHeading(headings));
	const commonDirection = $derived<Direction | null>(
		common
			? {
					heading: common.heading,
					accuracy: common.accuracy,
					source: 'street_match',
					source_ref: common.key
				}
			: null
	);

	/** Which way the photo looks, put on this image: by the images matched with the photo when
	 * there are any (narrow), else the way this image looks (wide, not from a panorama). */
	function directionFrom(image: StreetImage): Direction | null {
		if (commonDirection) return commonDirection;
		if (image.heading === null || image.pano) return null;
		return {
			heading: image.heading,
			accuracy: STREET_ACCURACY,
			source: 'street',
			source_ref: key(image)
		};
	}

	function searchAround(image: StreetImage) {
		center = { key: key(image), at: { lat: image.latitude, lon: image.longitude } };
		opened = null;
	}

	function pickHere(image: StreetImage) {
		const direction = directionFrom(image);
		onpick({ lat: image.latitude, lon: image.longitude }, direction);
		opened = null;
	}

	const sourceName = (id: string) => (id === 'mapillary' ? 'Mapillary' : 'Panoramax');
	// Mapillary asks for its name and a link to it wherever its images are shown (terms §11);
	// as text, as in its own tiles: no file of its trademark in the project.
	const MAPILLARY_URL = 'https://www.mapillary.com/';
	const anyMapillary = $derived(images.some((image) => image.source === 'mapillary'));
	const problems = $derived(answers.filter((s) => s.status !== 'ok'));
	// How many of the images shown each source gave, also none: with more than one source, so
	// that a source with nothing here is told from one that did not answer.
	const bySource = $derived.by(() => {
		const ok = answers.filter((s) => s.status === 'ok');
		if (ok.length < 2) return [];
		return ok.map((s) => ({
			id: s.id,
			count: images.filter((image) => image.source === s.id).length
		}));
	});
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
		<BetaBadge />
		{#if shown && assetId && images.length}
			<button
				type="button"
				class="st-btn st-btn--sm st-btn--secondary"
				disabled={comparing || !fresh.length}
				title={fresh.length ? m.street_compare_hint() : m.street_compare_all_done()}
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
					{#if bySource.length}
						<span>
							({bySource
								.map((s) => m.street_by_source({ source: sourceName(s.id), count: s.count }))
								.join(' · ')})
						</span>
					{/if}
				{:else if loading || enabled === null}
					{m.street_loading()}
				{:else}
					{m.street_none({ radius: RADIUS_M })}
				{/if}
				{#if point && center}
					<span>
						{m.street_around({ meters: meters.format(metersBetween(point, center.at)) })}
						<button
							type="button"
							class="st-btn st-btn--ghost st-btn--sm"
							onclick={() => (center = null)}>{m.street_around_back()}</button
						>
					</span>
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
				{#if !comparing && commonDirection && common}
					<span>
						{m.street_direction_found({
							count: common.used,
							direction: directionText(commonDirection)
						})}
						{#if common.disagree}
							<span class="problem">{m.street_direction_disagree()}</span>
						{/if}
						{#if ondirection}
							<button
								type="button"
								class="st-btn st-btn--ghost st-btn--sm"
								title={m.street_direction_take_hint()}
								onclick={() => ondirection(commonDirection)}
							>
								<Icon name="compass" size={14} />
								{m.street_direction_take()}
							</button>
						{/if}
					</span>
				{/if}
				{#if anyMapillary}
					<a class="credit" href={MAPILLARY_URL} target="_blank" rel="noopener">© Mapillary</a>
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
						class:sure={sure(found)}
						class:maybe={maybe(found)}
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
							{m.street_distance({ meters: meters.format(distanceOf(image)) })}
						</span>
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<svelte:window {onkeydown} />

{#snippet credits(image: StreetImage)}
	{#if image.source === 'mapillary'}
		<a href={MAPILLARY_URL} target="_blank" rel="noopener">© Mapillary</a> ·
	{/if}
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
	· {m.street_distance({ meters: meters.format(distanceOf(image)) })}
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
			{#if center?.key !== key(image)}
				<button
					type="button"
					class="st-btn st-btn--secondary"
					title={m.street_search_here_hint({ radius: RADIUS_M })}
					onclick={() => searchAround(image)}
				>
					<Icon name="crosshair" size={16} />
					{m.street_search_here()}
				</button>
			{/if}
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
	.credit {
		color: inherit;
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
	/* Matched with the photo: in the colours of the map. */
	.shot.sure {
		border-color: #8250df;
	}
	.shot.maybe {
		border-color: #9a6700;
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
	/* The colours of the matched images on the map. */
	.mark.sure {
		background: #8250df;
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
