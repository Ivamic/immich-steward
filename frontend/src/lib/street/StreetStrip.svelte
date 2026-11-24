<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Street-level images near the point of the photo card (D-244): a switch under the map (off
     by default, remembered for the account), then the images around the point, nearest first,
     to compare with the photo by eye. Asked once the point stops; only the point leaves the
     server, and only while the switch is on. A click shows an image large, with its author and
     license, and can put the point where it was taken. -->
<script lang="ts">
	import { resolve } from '$app/paths';
	import { getStreetNear, streetImageUrl, type StreetImage, type StreetNear } from '#lib/api.js';
	import { accountSettings } from '#lib/accountSettings.svelte.js';
	import type { LatLon } from '#lib/coords.js';
	import { errorMessage } from '#lib/errors.js';
	import type { StreetMark } from '#lib/map/markers.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import Dialog from '#lib/ui/Dialog.svelte';
	import Icon from '#lib/ui/Icon.svelte';

	let {
		point,
		active = $bindable(null),
		// eslint-disable-next-line no-useless-assignment -- bound: the map of the card reads it
		marks = $bindable([]),
		onpick
	}: {
		/** Where to look: the picked point, else the location of the photo. */
		point: LatLon | null;
		/** The image picked ("source:id"), also on the map. */
		active?: string | null;
		/** The images as the map shows them. */
		marks?: StreetMark[];
		/** "Put the point here". */
		onpick: (point: LatLon) => void;
	} = $props();

	// Asked once the point stopped moving for this long.
	const WAIT_MS = 600;
	const RADIUS_M = 100;

	// The card may be the first page opened: the personal settings are loaded here too.
	accountSettings.load();
	const shown = $derived(accountSettings.values.street_shown);
	let answer = $state.raw<StreetNear | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let opened = $state<StreetImage | null>(null);
	// The latest search: an answer to an older one is dropped.
	let asked = 0;
	const meters = new Intl.NumberFormat(getLocale(), { maximumFractionDigits: 0 });
	const dates = new Intl.DateTimeFormat(getLocale(), { year: 'numeric', month: 'short' });

	const key = (image: StreetImage) => `${image.source}:${image.id}`;

	$effect(() => {
		const at = point;
		if (!shown || !at) {
			answer = null;
			return;
		}
		const search = ++asked;
		const timer = setTimeout(async () => {
			loading = true;
			try {
				const found = await getStreetNear(at.lat, at.lon, RADIUS_M);
				if (search !== asked) return;
				answer = found;
				error = null;
			} catch (e) {
				if (search === asked) error = errorMessage(e);
			} finally {
				if (search === asked) loading = false;
			}
		}, WAIT_MS);
		return () => clearTimeout(timer);
	});

	$effect(() => {
		marks = (answer?.images ?? []).map((image) => ({
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

	function pickHere(image: StreetImage) {
		onpick({ lat: image.latitude, lon: image.longitude });
		opened = null;
	}

	const sourceName = (id: string) => (id === 'mapillary' ? 'Mapillary' : 'Panoramax');
	const problems = $derived((answer?.sources ?? []).filter((s) => s.status !== 'ok'));
	const noSource = $derived(answer !== null && answer.sources.length === 0);

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
		{#if shown}
			<span class="status" role="status">
				{#if !point}
					{m.street_no_point()}
				{:else if loading && !answer}
					{m.street_loading()}
				{:else if noSource}
					{m.street_no_source()}
					<a href={resolve('/settings#street')}>{m.street_settings_link()}</a>
				{:else if answer}
					{answer.images.length
						? m.street_found({ count: answer.images.length, radius: RADIUS_M })
						: m.street_none({ radius: RADIUS_M })}
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
	{#if shown && answer?.images.length}
		<ul class="strip" class:loading>
			{#each answer.images as image (key(image))}
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

{#if opened}
	{@const image = opened}
	<Dialog
		title={`${sourceName(image.source)}${image.taken_at ? ` · ${dates.format(new Date(image.taken_at))}` : ''}`}
		icon="camera"
		full
		onclose={() => (opened = null)}
	>
		<div class="large" class:pano={image.pano}>
			<img src={streetImageUrl(image, 'large')} alt={m.street_image_alt()} />
		</div>
		<p class="credits">
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
		</p>
		{#snippet footer()}
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
	.shot {
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
	.large {
		display: flex;
		justify-content: center;
	}
	.large img {
		max-width: 100%;
		max-height: 70vh;
		object-fit: contain;
	}
	/* A 360-degree panorama: as wide as it is, scrolled sideways. */
	.large.pano {
		justify-content: flex-start;
		overflow-x: auto;
	}
	.large.pano img {
		max-width: none;
		height: 60vh;
		max-height: none;
	}
	.credits {
		margin: var(--space-2) 0 0;
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
</style>
