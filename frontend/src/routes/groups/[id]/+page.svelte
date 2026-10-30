<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- One group: a map of its photos with a location, where a mistake shows as a point far from the
     others, and all its photos to choose from. The chosen ones get a location together or leave
     the group. Below, the photos just short of the group and those taken out of it. -->
<script lang="ts">
	import {
		excludeFromGroup,
		getGroup,
		getGroupNear,
		getMapConfig,
		includeInGroup,
		thumbnailUrl,
		updateGroup,
		type AssetItem,
		type GroupDetail,
		type MapConfig
	} from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import SelectionBar from '#lib/gallery/SelectionBar.svelte';
	import SelectionLocation from '#lib/gallery/SelectionLocation.svelte';
	import { galleryChanges, Selection } from '#lib/gallery/selection.svelte.js';
	import MapView from '#lib/map/MapView.svelte';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import Icon from '#lib/ui/Icon.svelte';
	import Skeleton from '#lib/ui/Skeleton.svelte';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { untrack } from 'svelte';

	let detail = $state<GroupDetail | null>(null);
	let near = $state<AssetItem[]>([]);
	let mapConfig = $state<MapConfig | null>(null);
	let mapView = $state<ReturnType<typeof MapView>>();
	let error = $state<string | null>(null);
	let name = $state('');
	let busy = $state(false);
	let locationOpen = $state(false);
	const selection = new Selection();

	const numbers = new Intl.NumberFormat(getLocale());
	const count = (n: number) => numbers.format(n);

	const id = $derived(page.params.id ?? '');
	const photos = $derived(detail?.photos ?? []);
	const withoutLocation = $derived(photos.filter((photo) => !photo.has_location));
	const dots = $derived(
		(detail?.points ?? []).map((point) => ({
			id: point.id,
			lat: point.latitude,
			lon: point.longitude,
			chosen: selection.has(point.id)
		}))
	);

	function show(answer: GroupDetail) {
		detail = answer;
		name = answer.group.name ?? '';
		error = null;
		const here = new Set(answer.photos.map((photo) => photo.id));
		for (const chosen of selection.ids) if (!here.has(chosen)) selection.items.delete(chosen);
	}

	async function load(group: string) {
		try {
			show(await getGroup(group));
			near = await getGroupNear(group);
		} catch (e) {
			error = errorMessage(e);
		}
	}

	async function act(work: () => Promise<GroupDetail>) {
		busy = true;
		try {
			show(await work());
			near = await getGroupNear(id);
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	function saveName() {
		if (!detail || name.trim() === (detail.group.name ?? '')) return;
		act(() => updateGroup(id, { name }));
	}

	async function exclude() {
		const ids = selection.ids;
		await act(() => excludeFromGroup(id, ids));
	}

	/** A click on the map: its photos join the choice, or leave it if all are chosen. */
	function chooseDots(ids: string[]) {
		const items = photos.filter((photo) => ids.includes(photo.id));
		selection.setAll(items, !items.every((photo) => selection.has(photo.id)));
	}

	function clickTile(event: MouseEvent, photo: AssetItem) {
		if (event.shiftKey && selection.anchor) {
			event.preventDefault();
			selection.extend(photo, photos);
		} else if (selection.size > 0 || event.ctrlKey || event.metaKey) {
			event.preventDefault();
			selection.toggle(photo);
		}
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'Escape' && selection.size && !locationOpen) {
			event.preventDefault();
			selection.clear();
		}
	}

	$effect(() => {
		getMapConfig()
			.then((config) => (mapConfig = config))
			.catch((e) => (error = errorMessage(e)));
	});

	// Also after a location saved anywhere: the points move.
	$effect(() => {
		void galleryChanges.count;
		load(id);
	});

	// The first look at the map shows all the points.
	let fitted = false;
	$effect(() => {
		if (fitted || !mapView || !detail || dots.length === 0) return;
		fitted = true;
		untrack(() => mapView?.fitTo(dots));
	});
</script>

<svelte:window {onkeydown} />

{#snippet thumbnail(photo: AssetItem)}
	<img
		src={thumbnailUrl(photo.id, 'thumbnail', 0, photo.version)}
		alt={photo.file_name}
		loading="lazy"
		decoding="async"
	/>
{/snippet}

<a class="back" href={resolve('/groups')}>
	<Icon name="arrow-left" size={14} />
	{m.groups_back()}
</a>

{#if error}
	<p class="bad" role="alert">{error}</p>
{/if}

{#if detail}
	<div class="head">
		<span class="st-input title">
			<input
				aria-label={m.groups_name()}
				placeholder={m.groups_unnamed()}
				maxlength="200"
				bind:value={name}
				onblur={saveName}
				onkeydown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
			/>
		</span>
		<button
			type="button"
			class="st-btn st-btn--secondary st-btn--sm"
			disabled={busy}
			onclick={() => act(() => updateGroup(id, { trash: !detail?.group.trash }))}
		>
			<Icon name="ban" size={14} />
			{detail.group.trash ? m.groups_untrash() : m.groups_trash()}
		</button>
	</div>
	<p class="numbers">
		<span>{m.groups_photos({ count: count(detail.group.photos) })}</span>
		{#if detail.group.without_location > 0}
			<span class="st-badge st-badge--info">
				<Icon name="map-pin-off" size={11} />
				<span>{m.groups_without_location({ count: count(detail.group.without_location) })}</span>
			</span>
		{/if}
		{#if detail.group.spread}
			<span class="st-badge st-badge--warning" title={m.groups_spread_hint()}>
				<Icon name="route" size={11} />
				<span>{m.groups_spread()}</span>
			</span>
		{/if}
	</p>
	{#if detail.group.trash}
		<p class="hint">{m.groups_trash_hint()}</p>
	{/if}

	{#if mapConfig && dots.length > 0}
		<div class="map">
			<MapView
				bind:this={mapView}
				styleUrl={mapConfig.style_url}
				styleUrlDark={mapConfig.style_url_dark}
				sources={mapConfig.sources}
				auto={mapConfig.auto}
				current={null}
				picked={null}
				onpick={() => {}}
				{dots}
				ondots={chooseDots}
				scrollingPage
			/>
		</div>
		<p class="hint">{m.groups_map_hint()}</p>
	{/if}

	{#if photos.length > 0}
		<div class="tools">
			{#if withoutLocation.length > 0}
				<button
					type="button"
					class="st-btn st-btn--secondary st-btn--sm"
					onclick={() => selection.setAll(withoutLocation, true)}
				>
					<Icon name="map-pin-off" size={14} />
					{m.groups_select_without_location({ count: count(withoutLocation.length) })}
				</button>
			{/if}
			<button
				type="button"
				class="st-btn st-btn--ghost st-btn--sm"
				onclick={() => selection.setAll(photos, true)}
			>
				{m.groups_select_all()}
			</button>
		</div>
		<div class="grid">
			{#each photos as photo (photo.id)}
				{@const chosen = selection.has(photo.id)}
				<div class="cell" class:chosen>
					<a
						class="tile"
						href={resolve('/photo/[id]', { id: photo.id })}
						title={photo.file_name}
						onclick={(event) => clickTile(event, photo)}
					>
						{@render thumbnail(photo)}
						{#if photo.has_location}
							<span class="pin" role="img" aria-label={m.asset_has_location()}>
								<Icon name="map-pin" size={13} strokeWidth={2.25} />
							</span>
						{/if}
					</a>
					<button
						type="button"
						class="check"
						aria-pressed={chosen}
						aria-label={m.groups_choose_photo()}
						title={m.groups_choose_photo()}
						onclick={() => selection.toggle(photo)}
					>
						<Icon name="check" size={12} strokeWidth={3} />
					</button>
				</div>
			{/each}
		</div>
	{:else}
		<p class="numbers">{m.groups_no_photos()}</p>
	{/if}

	{#if near.length > 0}
		<h2>{m.groups_near_heading()}</h2>
		<p class="hint">{m.groups_near_hint()}</p>
		<div class="grid">
			{#each near as photo (photo.id)}
				<div class="cell">
					<a class="tile" href={resolve('/photo/[id]', { id: photo.id })} title={photo.file_name}>
						{@render thumbnail(photo)}
					</a>
					<button
						type="button"
						class="corner"
						disabled={busy}
						aria-label={m.groups_add()}
						title={m.groups_add()}
						onclick={() => act(() => includeInGroup(id, [photo.id]))}
					>
						<Icon name="plus" size={14} strokeWidth={2.5} />
					</button>
				</div>
			{/each}
		</div>
	{/if}

	{#if detail.excluded.length > 0}
		<details>
			<summary>{m.groups_excluded_heading({ count: count(detail.excluded.length) })}</summary>
			<div class="grid">
				{#each detail.excluded as photo (photo.id)}
					<div class="cell">
						<a class="tile" href={resolve('/photo/[id]', { id: photo.id })} title={photo.file_name}>
							{@render thumbnail(photo)}
						</a>
						<button
							type="button"
							class="corner"
							disabled={busy}
							aria-label={m.groups_bring_back()}
							title={m.groups_bring_back()}
							onclick={() => act(() => includeInGroup(id, [photo.id]))}
						>
							<Icon name="rotate-ccw" size={14} strokeWidth={2.5} />
						</button>
					</div>
				{/each}
			</div>
		</details>
	{/if}
{:else if !error}
	<Skeleton />
{/if}

{#if selection.size}
	<SelectionBar {selection} onlocation={() => (locationOpen = true)}>
		<button type="button" class="st-btn st-btn--ghost st-btn--sm" disabled={busy} onclick={exclude}>
			<Icon name="x" size={14} />
			{m.groups_exclude()}
		</button>
	</SelectionBar>
{/if}
{#if locationOpen}
	<SelectionLocation
		items={[...selection.items.values()]}
		groupId={id}
		onsaved={() => {
			locationOpen = false;
			selection.clear();
		}}
		onclose={() => (locationOpen = false)}
	/>
{/if}

<style>
	.back {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		margin-bottom: var(--space-3);
		font-size: var(--text-sm);
	}
	.head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2);
		margin-bottom: var(--space-2);
	}
	.title {
		flex: 1 1 14rem;
		max-width: 32rem;
	}
	.numbers {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2);
		margin: 0 0 var(--space-3);
		color: var(--color-text-muted);
		font-size: var(--text-sm);
	}
	.hint {
		margin: 0 0 var(--space-3);
		color: var(--color-text-muted);
		font-size: var(--text-sm);
	}
	.bad {
		color: var(--color-danger-text);
	}
	.map {
		height: min(24rem, 50dvh);
		margin-bottom: var(--space-2);
		overflow: hidden;
		border-radius: var(--radius-md);
	}
	.tools {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		margin-bottom: var(--space-3);
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(7rem, 1fr));
		gap: var(--space-1);
		/* Room for the bar of actions over the last row. */
		margin-bottom: var(--space-8);
	}
	.cell {
		position: relative;
		aspect-ratio: 1;
		overflow: hidden;
		background: var(--color-surface-sunken);
	}
	.cell.chosen .tile {
		outline: 3px solid var(--color-accent);
		outline-offset: -3px;
	}
	.cell.chosen img {
		opacity: 0.75;
	}
	.tile {
		display: block;
		width: 100%;
		height: 100%;
	}
	.tile img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.pin {
		position: absolute;
		right: var(--space-1);
		bottom: var(--space-1);
		display: flex;
		color: white;
		filter: drop-shadow(0 0 2px rgb(0 0 0 / 0.7));
	}
	.check,
	.corner {
		position: absolute;
		top: var(--space-1);
		left: var(--space-1);
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.5rem;
		height: 1.5rem;
		min-height: 0;
		padding: 0;
		border: 2px solid white;
		border-radius: var(--radius-full);
		background: rgb(0 0 0 / 0.35);
		color: transparent;
		cursor: pointer;
	}
	.check:hover {
		color: white;
	}
	.check[aria-pressed='true'] {
		border-color: var(--color-accent);
		background: var(--color-accent);
		color: white;
	}
	.corner {
		color: white;
	}
	.corner:disabled {
		opacity: 0.5;
		cursor: default;
	}
	h2 {
		margin: 0 0 var(--space-2);
		font-size: var(--text-lg);
	}
	summary {
		margin-bottom: var(--space-3);
		color: var(--color-text-muted);
		cursor: pointer;
	}
</style>
