<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- One group: a map of its photos with a location, where a mistake shows as a point far from the
     others, and all its photos to choose from. The chosen ones get a location together or leave
     the group. Below, the photos just short of the group and those taken out of it. -->
<script lang="ts">
	import {
		dissolveGroup,
		excludeFromGroup,
		getGroup,
		getGroupNear,
		getGroupParts,
		getMapConfig,
		includeInGroup,
		thumbnailUrl,
		trashPhotos,
		updateGroup,
		type AssetItem,
		type GroupDetail,
		type MapConfig
	} from '#lib/api.js';
	import { accountSettings } from '#lib/accountSettings.svelte.js';
	import type { LatLon } from '#lib/coords.js';
	import { errorMessage } from '#lib/errors.js';
	import { hoverTip, type Tip } from '#lib/gallery/hoverTip.js';
	import { longpress } from '#lib/gallery/longpress.js';
	import { nearScreen } from '#lib/gallery/nearScreen.js';
	import PhotoPeek from '#lib/gallery/PhotoPeek.svelte';
	import SelectionBar from '#lib/gallery/SelectionBar.svelte';
	import SelectionLocation from '#lib/gallery/SelectionLocation.svelte';
	import {
		byMonth,
		byPart,
		firstPhotos,
		photosBySpot,
		spotLetter,
		type Section
	} from '#lib/gallery/sections.js';
	import { galleryChanges, Selection } from '#lib/gallery/selection.svelte.js';
	import TileTooltip from '#lib/gallery/TileTooltip.svelte';
	import MapView from '#lib/map/MapView.svelte';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import Dialog from '#lib/ui/Dialog.svelte';
	import Icon from '#lib/ui/Icon.svelte';
	import Skeleton from '#lib/ui/Skeleton.svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { untrack } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';

	type PhotoFilter = 'all' | 'center' | 'with' | 'without' | 'chosen';
	type Grouping = 'none' | 'month' | 'similar';

	// Photos added to the page at a time: a group may have thousands.
	const PART = 120;
	const FILTERS: { id: PhotoFilter; label: () => string }[] = [
		{ id: 'all', label: m.groups_view_all },
		{ id: 'center', label: m.groups_filter_center },
		{ id: 'with', label: m.groups_filter_with },
		{ id: 'without', label: m.groups_filter_without },
		{ id: 'chosen', label: m.groups_filter_chosen }
	];
	const GROUPINGS: { id: Grouping; label: () => string }[] = [
		{ id: 'none', label: m.groups_grouping_none },
		{ id: 'month', label: m.groups_grouping_month },
		{ id: 'similar', label: m.groups_grouping_similar }
	];
	// How strict the scenes of a group are.
	const LEVELS: { id: number; label: () => string }[] = [
		{ id: 1, label: m.groups_level_loose },
		{ id: 2, label: m.groups_level_medium },
		{ id: 3, label: m.groups_level_strict }
	];

	// Read only, and thousands of photos: not reactive one by one.
	let detail = $state.raw<GroupDetail | null>(null);
	let near = $state.raw<AssetItem[]>([]);
	let mapConfig = $state<MapConfig | null>(null);
	let mapView = $state<ReturnType<typeof MapView>>();
	let error = $state<string | null>(null);
	let name = $state('');
	let busy = $state(false);
	let locationOpen = $state(false);
	// The place the window of the location opens with.
	let locationPoint = $state<LatLon | null>(null);
	// The user took photos out: the groups are being built again without them.
	let recounting = $state(false);
	let confirmDissolve = $state(false);
	let peek = $state<AssetItem | null>(null);
	// The tile the mouse rests on, for its tooltip.
	let tip = $state<Tip>(null);
	let shownCount = $state(PART);
	let filter = $state<PhotoFilter>('all');
	let byCloseness = $state(false);
	let grouping = $state<Grouping>('none');
	let level = $state(2);
	// Scenes of the group at this level; null until they arrive.
	let parts = $state.raw<string[][] | null>(null);
	const selection = new Selection();
	// Photos just short of the group, chosen to be added.
	const nearChosen = new SvelteSet<string>();

	accountSettings.load();
	const tooltips = $derived(accountSettings.values.gallery_tooltip);

	const numbers = new Intl.NumberFormat(getLocale());
	const count = (n: number) => numbers.format(n);
	const similarities = new Intl.NumberFormat(getLocale(), {
		minimumFractionDigits: 2,
		maximumFractionDigits: 2
	});
	const similarity = (value: number) => similarities.format(value);

	const id = $derived(page.params.id ?? '');
	// The view of the list this group was opened from.
	const list = $derived.by(() => {
		const view = page.url.searchParams.get('view');
		return resolve(view ? `/groups?view=${encodeURIComponent(view)}` : '/groups');
	});
	const photos = $derived(detail?.photos ?? []);
	const centerIds = $derived(new Set(detail?.center ?? []));
	const center = $derived(photos.filter((photo) => centerIds.has(photo.id)));
	const withLocation = $derived(photos.filter((photo) => photo.has_location));
	const withoutLocation = $derived(photos.filter((photo) => !photo.has_location));
	const chosenIds = $derived(new Set(selection.ids));
	const chosenPhotos = $derived(photos.filter((photo) => chosenIds.has(photo.id)));
	const filtered = $derived<Record<PhotoFilter, AssetItem[]>>({
		all: photos,
		center,
		with: withLocation,
		without: withoutLocation,
		chosen: chosenPhotos
	});
	// "Chosen" is there only while there are some.
	const filters = $derived(FILTERS.filter((item) => item.id !== 'chosen' || selection.size > 0));
	const closeness = $derived(detail?.closeness ?? {});
	const listed = $derived.by(() => {
		if (!byCloseness) return filtered[filter];
		const of = (photo: AssetItem) => closeness[photo.id] ?? Infinity;
		return [...filtered[filter]].sort((a, b) => of(a) - of(b));
	});
	const spotOf = $derived(new Map((detail?.points ?? []).map((p) => [p.id, p.spot])));
	const spots = $derived(photosBySpot(photos, spotOf));
	const sections = $derived.by(() => {
		if (grouping === 'month') return byMonth(listed, spotOf);
		if (grouping !== 'similar' || !parts) return [];
		const title = (number: number) => m.groups_part({ number });
		return byPart(listed, parts, spotOf, title, m.groups_part_rest());
	});
	// As shown: Shift + click chooses by this order.
	const ordered = $derived(grouping === 'none' ? listed : sections.flatMap((s) => s.photos));
	const visible = $derived(listed.slice(0, shownCount));
	const visibleSections = $derived(firstPhotos(sections, shownCount));
	const dots = $derived(
		(detail?.points ?? []).map((point) => ({
			id: point.id,
			lat: point.latitude,
			lon: point.longitude,
			chosen: chosenIds.has(point.id)
		}))
	);

	/** Chooses the photos without a location of these sections: all of them, or up to a border. */
	function chooseWithout(chosen: Section[]) {
		selection.setAll(
			chosen.flatMap((part) => part.photos).filter((photo) => !photo.has_location),
			true
		);
	}

	/** The photos of a spot join the choice, which shows them on the map; or leave it. */
	function chooseSpot(of: AssetItem[]) {
		selection.setAll(of, !of.every((photo) => chosenIds.has(photo.id)));
	}

	/** Another filter or order starts from the top. */
	function restart(change: () => void) {
		change();
		shownCount = PART;
	}

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
		recounting = true;
	}

	async function dissolve() {
		confirmDissolve = false;
		try {
			await dissolveGroup(id);
			await goto(list);
		} catch (e) {
			error = errorMessage(e);
		}
	}

	async function toTrash() {
		const ids = selection.ids;
		await act(() => trashPhotos(id, ids));
		recounting = true;
	}

	function toggleNear(photo: AssetItem) {
		if (!nearChosen.delete(photo.id)) nearChosen.add(photo.id);
	}

	/** All the photos without a location, to the place the others share. */
	function setSpot() {
		const spot = detail?.group.spot;
		if (!spot) return;
		selection.clear();
		selection.setAll(withoutLocation, true);
		locationPoint = { lat: spot.latitude, lon: spot.longitude };
		locationOpen = true;
	}

	function closeLocation() {
		locationOpen = false;
		locationPoint = null;
	}

	async function trashNear() {
		const ids = [...nearChosen];
		await act(() => trashPhotos(id, ids));
		nearChosen.clear();
	}

	/** While some are chosen a click chooses, as among the photos of the group. */
	function clickNear(event: MouseEvent, photo: AssetItem) {
		if (nearChosen.size === 0) return;
		event.preventDefault();
		toggleNear(photo);
	}

	async function addNear() {
		const ids = [...nearChosen];
		await act(() => includeInGroup(id, ids));
		nearChosen.clear();
	}

	/** A click on the map: its photos join the choice, or leave it if all are chosen. */
	function chooseDots(ids: string[]) {
		const wanted = new Set(ids);
		const items = photos.filter((photo) => wanted.has(photo.id));
		selection.setAll(items, !items.every((photo) => chosenIds.has(photo.id)));
	}

	function clickTile(event: MouseEvent, photo: AssetItem) {
		if (event.shiftKey && selection.anchor) {
			event.preventDefault();
			selection.extend(photo, ordered);
		} else if (selection.size > 0 || event.ctrlKey || event.metaKey) {
			event.preventDefault();
			selection.toggle(photo);
		}
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'Escape' && selection.size && !locationOpen && !peek) {
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

	// A look at the photos as they are now, so again whenever they change.
	$effect(() => {
		if (grouping !== 'similar' || !detail) return;
		const asked = level;
		parts = null;
		getGroupParts(detail.group.id, asked)
			.then((answer) => {
				if (asked === level) parts = answer.parts;
			})
			.catch((e) => (error = errorMessage(e)));
	});

	// The last chosen photo gone: back from the filter of the chosen ones.
	$effect(() => {
		if (filter === 'chosen' && selection.size === 0) restart(() => (filter = 'all'));
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

{#snippet groupTile(photo: AssetItem)}
	{@const chosen = chosenIds.has(photo.id)}
	<div class="cell" class:chosen>
		<a
			class="tile"
			href={resolve('/photo/[id]', { id: photo.id })}
			title={tooltips ? undefined : photo.file_name}
			use:hoverTip={{ item: photo, enabled: tooltips, ontip: (next) => (tip = next) }}
			use:longpress={() => (peek = photo)}
			onclick={(event) => clickTile(event, photo)}
		>
			{@render thumbnail(photo)}
			{#if photo.has_location}
				<span class="pin" role="img" aria-label={m.asset_has_location()}>
					<Icon name="map-pin" size={13} strokeWidth={2.25} />
				</span>
			{/if}
			{#if centerIds.has(photo.id)}
				<span class="center" title={m.groups_center_hint()}>
					<Icon name="crosshair" size={13} strokeWidth={2.25} />
				</span>
			{/if}
			{#if byCloseness && closeness[photo.id] !== undefined}
				<span class="score">{similarity(closeness[photo.id])}</span>
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
{/snippet}

{#snippet thumbnail(photo: AssetItem)}
	<img
		src={thumbnailUrl(photo.id, 'thumbnail', 0, photo.version)}
		alt={photo.file_name}
		loading="lazy"
		decoding="async"
	/>
{/snippet}

<a class="back" href={list}>
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
		<button
			type="button"
			class="st-btn st-btn--ghost st-btn--sm"
			disabled={busy}
			onclick={() => (confirmDissolve = true)}
		>
			<Icon name="layers" size={14} />
			{m.groups_dissolve()}
		</button>
	</div>
	<p class="numbers">
		<span>{m.groups_photos({ count: count(detail.group.photos) })}</span>
		{#if detail.group.with_location > 0}
			<span class="st-badge st-badge--success">
				<Icon name="map-pin" size={11} />
				<span>{m.groups_with_location({ count: count(detail.group.with_location) })}</span>
			</span>
		{/if}
		{#if detail.group.without_location > 0}
			<span class="st-badge st-badge--info">
				<Icon name="map-pin-off" size={11} />
				<span>{m.groups_without_location({ count: count(detail.group.without_location) })}</span>
			</span>
		{/if}
		{#if detail.group.similarity !== null}
			<span class="st-badge" title={m.groups_similarity_hint()}>
				<span>{m.groups_similarity({ value: similarity(detail.group.similarity) })}</span>
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
	{#if recounting}
		<p class="hint" role="status">{m.groups_recount_hint()}</p>
	{/if}
	{#if detail.group.ready && detail.group.spot && !detail.group.trash}
		<div class="ready">
			<p>
				{m.groups_ready_text({
					photos: count(detail.group.spot.photos),
					located: count(detail.group.with_location)
				})}
			</p>
			<button type="button" class="st-btn st-btn--primary st-btn--sm" onclick={setSpot}>
				<Icon name="map-pin" size={14} />
				{m.groups_ready_set({ count: count(detail.group.without_location) })}
			</button>
		</div>
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

	{#if near.length > 0}
		<details>
			<summary>{m.groups_near_heading()} ({count(near.length)})</summary>
			<p class="hint">{m.groups_near_hint()}</p>
			<div class="tools">
				<button
					type="button"
					class="st-btn st-btn--primary st-btn--sm"
					disabled={busy || nearChosen.size === 0}
					onclick={addNear}
				>
					<Icon name="plus" size={14} />
					{m.groups_add_chosen({ count: count(nearChosen.size) })}
				</button>
				<button
					type="button"
					class="st-btn st-btn--ghost st-btn--sm"
					disabled={busy || nearChosen.size === 0}
					onclick={trashNear}
				>
					<Icon name="ban" size={14} />
					{m.groups_photos_trash()}
				</button>
				<button
					type="button"
					class="st-btn st-btn--ghost st-btn--sm"
					onclick={() => near.forEach((photo) => nearChosen.add(photo.id))}
				>
					{m.groups_select_all()}
				</button>
				{#if nearChosen.size > 0}
					<button
						type="button"
						class="st-btn st-btn--ghost st-btn--sm"
						onclick={() => nearChosen.clear()}
					>
						{m.selection_clear()}
					</button>
				{/if}
			</div>
			<div class="grid">
				{#each near as photo (photo.id)}
					{@const chosen = nearChosen.has(photo.id)}
					<div class="cell" class:chosen>
						<a
							class="tile"
							href={resolve('/photo/[id]', { id: photo.id })}
							title={tooltips ? undefined : photo.file_name}
							use:hoverTip={{ item: photo, enabled: tooltips, ontip: (next) => (tip = next) }}
							use:longpress={() => (peek = photo)}
							onclick={(event) => clickNear(event, photo)}
						>
							{@render thumbnail(photo)}
						</a>
						<button
							type="button"
							class="check"
							aria-pressed={chosen}
							aria-label={m.groups_choose_photo()}
							title={m.groups_choose_photo()}
							onclick={() => toggleNear(photo)}
						>
							<Icon name="check" size={12} strokeWidth={3} />
						</button>
					</div>
				{/each}
			</div>
		</details>
	{/if}

	{#if detail.excluded.length > 0}
		<details>
			<summary>{m.groups_excluded_heading({ count: count(detail.excluded.length) })}</summary>
			<div class="grid">
				{#each detail.excluded as photo (photo.id)}
					<div class="cell">
						<a
							class="tile"
							href={resolve('/photo/[id]', { id: photo.id })}
							title={tooltips ? undefined : photo.file_name}
							use:hoverTip={{ item: photo, enabled: tooltips, ontip: (next) => (tip = next) }}
							use:longpress={() => (peek = photo)}
						>
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

	{#if photos.length > 0}
		<div class="tools">
			{#each filters as item (item.id)}
				<button
					type="button"
					class="st-btn st-btn--sm"
					class:st-btn--secondary={item.id === filter}
					class:st-btn--ghost={item.id !== filter}
					aria-pressed={item.id === filter}
					onclick={() => restart(() => (filter = item.id))}
				>
					{item.label()}
					<span class="muted">{count(filtered[item.id].length)}</span>
				</button>
			{/each}
			<button
				type="button"
				class="st-btn st-btn--sm"
				class:st-btn--secondary={byCloseness}
				class:st-btn--ghost={!byCloseness}
				aria-pressed={byCloseness}
				title={m.groups_similarity_hint()}
				onclick={() => restart(() => (byCloseness = !byCloseness))}
			>
				{m.groups_sort_similarity()}
			</button>
		</div>
		<div class="tools">
			{#each GROUPINGS as item (item.id)}
				<button
					type="button"
					class="st-btn st-btn--sm"
					class:st-btn--secondary={item.id === grouping}
					class:st-btn--ghost={item.id !== grouping}
					aria-pressed={item.id === grouping}
					onclick={() => restart(() => (grouping = item.id))}
				>
					{item.label()}
				</button>
			{/each}
			{#if grouping === 'similar'}
				{#each LEVELS as item (item.id)}
					<button
						type="button"
						class="st-btn st-btn--sm st-btn--ghost"
						aria-pressed={item.id === level}
						title={m.groups_level_hint()}
						onclick={() => restart(() => (level = item.id))}
					>
						{#if item.id === level}<Icon name="check" size={12} />{/if}
						{item.label()}
					</button>
				{/each}
			{/if}
		</div>
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
				onclick={() => selection.setAll(listed, true)}
			>
				{m.groups_select_all()}
			</button>
		</div>
		{#if grouping !== 'none' && spots.length > 1}
			<div class="tools spots" aria-label={m.groups_spots()}>
				<span class="muted">{m.groups_spots()}</span>
				{#each spots as [number, of] (number)}
					<button
						type="button"
						class="st-btn st-btn--ghost st-btn--sm"
						title={m.groups_spot_hint()}
						onclick={() => chooseSpot(of)}
					>
						<span class="spot">{spotLetter(number)}</span>
						<span class="muted">{count(of.length)}</span>
					</button>
				{/each}
			</div>
		{/if}
		{#if grouping === 'similar' && !parts}
			<Skeleton />
		{:else if grouping === 'none'}
			<div class="grid">
				{#each visible as photo (photo.id)}
					{@render groupTile(photo)}
				{/each}
			</div>
		{:else}
			{#each visibleSections as part, index (part.key)}
				{@const whole = sections[index]}
				{@const without = whole.photos.filter((photo) => !photo.has_location).length}
				<section class="part">
					<div class="part-head">
						<h3>{part.title}</h3>
						<span class="muted">{m.groups_photos({ count: count(whole.photos.length) })}</span>
						{#if without > 0}
							<span class="muted">{m.groups_without_location({ count: count(without) })}</span>
						{/if}
						{#each part.spots as [number, photosThere] (number)}
							<span class="st-badge" title={m.groups_spot_hint()}>
								<span class="spot">{spotLetter(number)}</span>
								<span>{count(photosThere)}</span>
							</span>
						{/each}
						{#if without > 0}
							<button
								type="button"
								class="st-btn st-btn--ghost st-btn--sm"
								onclick={() => chooseWithout([whole])}
							>
								{m.groups_section_choose()}
							</button>
							{#if grouping === 'month'}
								<button
									type="button"
									class="st-btn st-btn--ghost st-btn--sm"
									title={m.groups_section_border_hint()}
									onclick={() => chooseWithout(sections.slice(0, index + 1))}
								>
									{m.groups_section_earlier()}
								</button>
								<button
									type="button"
									class="st-btn st-btn--ghost st-btn--sm"
									title={m.groups_section_border_hint()}
									onclick={() => chooseWithout(sections.slice(index))}
								>
									{m.groups_section_later()}
								</button>
							{/if}
						{/if}
					</div>
					<div class="grid">
						{#each part.photos as photo (photo.id)}
							{@render groupTile(photo)}
						{/each}
					</div>
				</section>
			{/each}
		{/if}
		{#if visible.length < listed.length}
			<div
				class="more"
				use:nearScreen={{ at: shownCount, onnear: () => (shownCount += PART) }}
			></div>
		{/if}
	{:else}
		<p class="numbers">{m.groups_no_photos()}</p>
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
		<button type="button" class="st-btn st-btn--ghost st-btn--sm" disabled={busy} onclick={toTrash}>
			<Icon name="ban" size={14} />
			{m.groups_photos_trash()}
		</button>
	</SelectionBar>
{/if}
{#if confirmDissolve}
	<Dialog
		title={m.groups_dissolve()}
		icon="triangle-alert"
		onclose={() => (confirmDissolve = false)}
	>
		<p>{m.groups_dissolve_warning()}</p>
		{#snippet footer()}
			<button
				type="button"
				class="st-btn st-btn--secondary"
				onclick={() => (confirmDissolve = false)}
			>
				{m.groups_reset_cancel()}
			</button>
			<button type="button" class="st-btn st-btn--danger" onclick={dissolve}>
				{m.groups_dissolve()}
			</button>
		{/snippet}
	</Dialog>
{/if}
{#if peek}
	<PhotoPeek item={peek} onclose={() => (peek = null)} />
{:else if tip}
	<TileTooltip item={tip.item} anchor={tip.anchor} onclose={() => (tip = null)} />
{/if}
{#if locationOpen}
	<SelectionLocation
		items={[...selection.items.values()]}
		groupId={id}
		point={locationPoint}
		onsaved={() => {
			closeLocation();
			selection.clear();
		}}
		onclose={closeLocation}
	/>
{/if}

<style>
	/* Stays under the header: a group can be thousands of photos long. */
	.back {
		position: sticky;
		top: calc(var(--header-height) + var(--space-2));
		z-index: var(--z-panel);
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		margin-bottom: var(--space-3);
		padding: var(--space-1) var(--space-3);
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-full);
		background: var(--color-surface);
		box-shadow: var(--shadow-sm);
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
	.ready {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2) var(--space-3);
		margin-bottom: var(--space-3);
		padding: var(--space-2) var(--space-3);
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface);
		font-size: var(--text-sm);
	}
	.ready p {
		flex: 1 1 16rem;
		margin: 0;
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
		/* A long press shows the preview, not the menu of the phone. */
		-webkit-touch-callout: none;
		user-select: none;
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
	.muted {
		color: var(--color-text-muted);
	}
	.center {
		position: absolute;
		top: var(--space-1);
		right: var(--space-1);
		display: flex;
		color: white;
		filter: drop-shadow(0 0 2px rgb(0 0 0 / 0.8));
	}
	.score {
		position: absolute;
		left: var(--space-1);
		bottom: var(--space-1);
		padding: 0 var(--space-1);
		border-radius: var(--radius-sm);
		background: rgb(0 0 0 / 0.6);
		color: white;
		font-size: var(--text-xs);
		font-variant-numeric: tabular-nums;
	}
	.more {
		height: 1px;
	}
	.part-head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-1) var(--space-2);
		margin-bottom: var(--space-2);
		font-size: var(--text-sm);
	}
	.part-head h3 {
		margin: 0;
		font-size: var(--text-base);
	}
	.spots {
		align-items: center;
		font-size: var(--text-sm);
	}
	.spot {
		font-weight: var(--weight-medium);
	}
	summary {
		margin-bottom: var(--space-3);
		color: var(--color-text-muted);
		cursor: pointer;
	}
</style>
