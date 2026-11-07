<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- A folder of groups (D-201): its groups together, as one, or one by one. Together: all their
     photos, the map with a color per group, the place most of them share and the choice as in a
     group; the groups themselves do not change. -->
<script lang="ts">
	import {
		deleteFolder,
		getFolder,
		getMapConfig,
		markPhotos,
		setGroupFolder,
		thumbnailUrl,
		updateFolder,
		type AssetItem,
		type FolderDetail,
		type MapConfig
	} from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { bulkNotices } from '#lib/gallery/bulk.svelte.js';
	import { nearScreen } from '#lib/gallery/nearScreen.js';
	import SelectionBar from '#lib/gallery/SelectionBar.svelte';
	import SelectionLocation from '#lib/gallery/SelectionLocation.svelte';
	import { galleryChanged, galleryChanges, Selection } from '#lib/gallery/selection.svelte.js';
	import type { LatLon } from '#lib/coords.js';
	import MapView from '#lib/map/MapView.svelte';
	import FolderDialog from '#lib/groups/FolderDialog.svelte';
	import GroupName from '#lib/groups/GroupName.svelte';
	import { GROUP_COLORS } from '#lib/map/markers.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import Dialog from '#lib/ui/Dialog.svelte';
	import EmptyState from '#lib/ui/EmptyState.svelte';
	import Icon from '#lib/ui/Icon.svelte';
	import Skeleton from '#lib/ui/Skeleton.svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { untrack } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';

	type Shown = 'together' | 'groups';
	type PhotoFilter = 'all' | 'with' | 'without' | 'chosen';
	// Photos drawn at a time: a folder can hold thousands.
	const PART = 120;
	const SENT_MOST = 2000;

	const id = $derived(page.params.id ?? '');
	let detail = $state.raw<FolderDetail | null>(null);
	let mapConfig = $state<MapConfig | null>(null);
	let error = $state<string | null>(null);
	let busy = $state(false);
	let name = $state('');
	let shownAs = $state<Shown>('together');
	let filter = $state<PhotoFilter>('all');
	let shownCount = $state(PART);
	let locationOpen = $state(false);
	let locationPoint = $state<LatLon | null>(null);
	let confirmDelete = $state(false);
	let mapView = $state<MapView>();
	const selection = new Selection();
	const chosenIds = $derived(new Set(selection.ids));

	const numbers = new Intl.NumberFormat(getLocale());
	const count = (n: number) => numbers.format(n);

	const located = $derived(new Set((detail?.points ?? []).map((point) => point.id)));
	/** Group -> its color on the map, in the order of the groups. */
	const colorOf = $derived(
		new Map(
			(detail?.groups ?? []).map((group, i) => [group.id, GROUP_COLORS[i % GROUP_COLORS.length]])
		)
	);
	// The groups chosen in the legend: only their photos are shown; none chosen, all of them.
	const shownGroups = new SvelteSet<string>();
	// Groups chosen on the tab of the groups, and those to put into another folder.
	const chosenGroups = new SvelteSet<string>();
	let moving = $state<string[] | null>(null);
	const inShownGroup = (photoId: string) =>
		shownGroups.size === 0 || shownGroups.has(detail?.group_of[photoId] ?? '');
	const listed = $derived.by((): AssetItem[] => {
		const photos = (detail?.photos ?? []).filter((photo) => inShownGroup(photo.id));
		if (filter === 'with') return photos.filter((photo) => located.has(photo.id));
		if (filter === 'without') return photos.filter((photo) => !located.has(photo.id));
		if (filter === 'chosen') return photos.filter((photo) => chosenIds.has(photo.id));
		return photos;
	});
	const withoutLocation = $derived(
		(detail?.photos ?? []).filter((photo) => !located.has(photo.id))
	);
	const allTrash = $derived(!!detail?.groups.length && detail.groups.every((group) => group.trash));
	const dots = $derived(
		(detail?.points ?? [])
			.filter((point) => shownGroups.size === 0 || shownGroups.has(point.group_id))
			.map((point) => ({
				id: point.id,
				lat: point.latitude,
				lon: point.longitude,
				chosen: chosenIds.has(point.id),
				color: colorOf.get(point.group_id)
			}))
	);
	const FILTERS: { id: PhotoFilter; label: () => string }[] = [
		{ id: 'all', label: m.groups_view_all },
		{ id: 'with', label: m.groups_filter_with },
		{ id: 'without', label: m.groups_filter_without },
		{ id: 'chosen', label: m.groups_filter_chosen }
	];

	async function load(folder: string) {
		try {
			const answer = await getFolder(folder);
			if (folder !== id) return;
			detail = answer;
			name = answer.folder.name;
			error = null;
		} catch (e) {
			error = errorMessage(e);
		}
	}

	$effect(() => {
		const folder = id;
		// Photos given a place elsewhere (the location dialog) come back changed.
		void galleryChanges.count;
		untrack(() => load(folder));
	});

	$effect(() => {
		getMapConfig()
			.then((config) => (mapConfig = config))
			.catch((e) => (error = errorMessage(e)));
	});

	let fitted = false;
	$effect(() => {
		if (fitted || !mapView || dots.length === 0) return;
		fitted = true;
		untrack(() => mapView?.fitTo(dots));
	});

	async function act(work: () => Promise<FolderDetail>) {
		busy = true;
		try {
			detail = await work();
			error = null;
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	function saveName() {
		const wanted = name.trim();
		if (!detail || !wanted || wanted === detail.folder.name) {
			if (detail) name = detail.folder.name;
			return;
		}
		act(() => updateFolder(id, { name: wanted }));
	}

	async function remove() {
		confirmDelete = false;
		try {
			await deleteFolder(id);
			goto(resolve('/groups'));
		} catch (e) {
			error = errorMessage(e);
		}
	}

	async function takeOut(groupIds: string[]) {
		busy = true;
		try {
			for (const groupId of groupIds) await setGroupFolder(groupId, {});
			groupIds.forEach((groupId) => chosenGroups.delete(groupId));
			await load(id);
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	/** The photos without a location get the place most of them share, after a look at the map. */
	function setSpot() {
		if (!detail?.spot) return;
		selection.clear();
		selection.setAll(withoutLocation, true);
		locationPoint = { lat: detail.spot.latitude, lon: detail.spot.longitude };
		locationOpen = true;
	}

	function chooseDots(ids: string[]) {
		const wanted = new Set(ids);
		const items = (detail?.photos ?? []).filter((photo) => wanted.has(photo.id));
		selection.setAll(items, !items.every((photo) => chosenIds.has(photo.id)));
	}

	async function mark() {
		busy = true;
		try {
			const ids = selection.ids;
			for (let start = 0; start < ids.length; start += SENT_MOST) {
				await markPhotos(ids.slice(start, start + SENT_MOST));
			}
			selection.clear();
			galleryChanged();
			bulkNotices.done(m.candidates_marked({ count: ids.length }));
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	function clickTile(event: MouseEvent, photo: AssetItem) {
		if (event.shiftKey && selection.anchor) {
			event.preventDefault();
			selection.extend(photo, listed);
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
</script>

<svelte:window {onkeydown} />

<a class="st-btn st-btn--ghost st-btn--sm back" href={resolve('/groups')}>
	<Icon name="arrow-left" size={14} />
	{m.groups_back()}
</a>

{#if error}
	<p class="bad" role="alert">{error}</p>
{/if}

{#if detail}
	<div class="head">
		<Icon name="folder" size={20} />
		<span class="st-input title">
			<input
				aria-label={m.folder_name()}
				maxlength="200"
				bind:value={name}
				onblur={saveName}
				onkeydown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
			/>
		</span>
		{#if detail.groups.length > 0}
			<button
				type="button"
				class="st-btn st-btn--secondary st-btn--sm"
				disabled={busy}
				onclick={() => act(() => updateFolder(id, { trash: !allTrash }))}
			>
				<Icon name="eye-off" size={14} />
				{allTrash ? m.folder_unmark_all() : m.folder_mark_all()}
			</button>
		{/if}
		<button
			type="button"
			class="st-btn st-btn--ghost st-btn--sm"
			disabled={busy}
			onclick={() => (confirmDelete = true)}
		>
			<Icon name="trash-2" size={14} />
			{m.folder_delete()}
		</button>
	</div>
	<p class="numbers">
		<span>{m.folder_groups({ count: count(detail.groups.length) })}</span>
		<span>{m.groups_photos({ count: count(detail.photos.length) })}</span>
		{#if detail.points.length > 0}
			<span class="st-badge st-badge--success">
				<Icon name="map-pin" size={11} />
				<span>{m.groups_with_location({ count: count(detail.points.length) })}</span>
			</span>
		{/if}
		{#if withoutLocation.length > 0}
			<span class="st-badge st-badge--info">
				<Icon name="map-pin-off" size={11} />
				<span>{m.groups_without_location({ count: count(withoutLocation.length) })}</span>
			</span>
		{/if}
	</p>

	{#if detail.groups.length === 0}
		<EmptyState icon="folder" title={m.folder_empty_title()} text={m.folder_empty_text()} />
	{:else}
		<div class="views">
			{#each [{ id: 'together', label: m.folder_together }, { id: 'groups', label: m.folder_by_group }] as item (item.id)}
				<button
					type="button"
					class="st-btn st-btn--sm"
					class:st-btn--secondary={item.id === shownAs}
					class:st-btn--ghost={item.id !== shownAs}
					aria-pressed={item.id === shownAs}
					onclick={() => (shownAs = item.id as Shown)}
				>
					{item.label()}
				</button>
			{/each}
		</div>

		{#if shownAs === 'groups'}
			{#if chosenGroups.size > 0}
				<div class="tools">
					<button
						type="button"
						class="st-btn st-btn--primary st-btn--sm"
						disabled={busy}
						onclick={() => (moving = [...chosenGroups])}
					>
						<Icon name="folder" size={14} />
						{m.folder_move_chosen({ count: count(chosenGroups.size) })}
					</button>
					<button
						type="button"
						class="st-btn st-btn--secondary st-btn--sm"
						disabled={busy}
						onclick={() => takeOut([...chosenGroups])}
					>
						{m.folder_take_out_chosen({ count: count(chosenGroups.size) })}
					</button>
					<button
						type="button"
						class="st-btn st-btn--ghost st-btn--sm"
						onclick={() => chosenGroups.clear()}
					>
						{m.selection_clear()}
					</button>
				</div>
			{/if}
			<div class="grid">
				{#each detail.groups as group, i (group.id)}
					{@const chosen = chosenGroups.has(group.id)}
					<div class="group st-tile-cell" class:chosen class:choosing={chosenGroups.size > 0}>
						<button
							type="button"
							class="st-tile-check"
							aria-pressed={chosen}
							aria-label={m.groups_choose_group()}
							title={m.groups_choose_group()}
							onclick={() => {
								if (!chosenGroups.delete(group.id)) chosenGroups.add(group.id);
							}}
						>
							<Icon name="check" size={12} strokeWidth={3} />
						</button>
						<a
							class="cover"
							href={resolve(`/groups/[id]?folder=${encodeURIComponent(id)}`, { id: group.id })}
						>
							{#if group.cover}
								<img
									src={thumbnailUrl(group.cover.id, 'thumbnail', 0, group.cover.version)}
									alt=""
									loading="lazy"
									decoding="async"
								/>
							{/if}
							<span class="swatch" style:background={GROUP_COLORS[i % GROUP_COLORS.length]}></span>
						</a>
						<GroupName
							id={group.id}
							name={group.name}
							href={resolve(`/groups/[id]?folder=${encodeURIComponent(id)}`, { id: group.id })}
							onrenamed={(renamed) => {
								if (detail)
									detail = {
										...detail,
										groups: detail.groups.map((g) =>
											g.id === group.id ? { ...g, name: renamed } : g
										)
									};
							}}
						/>
						<span class="numbers">{m.groups_photos({ count: count(group.photos) })}</span>
						{#if group.trash}
							<span class="st-badge"
								><Icon name="eye-off" size={11} /><span>{m.groups_view_trash()}</span></span
							>
						{/if}
						<span class="actions">
							<button
								type="button"
								class="st-btn st-btn--ghost st-btn--sm"
								disabled={busy}
								onclick={() => (moving = [group.id])}
							>
								{m.folder_move()}
							</button>
							<button
								type="button"
								class="st-btn st-btn--ghost st-btn--sm"
								disabled={busy}
								onclick={() => takeOut([group.id])}
							>
								{m.folder_take_out()}
							</button>
						</span>
					</div>
				{/each}
			</div>
		{:else}
			{#if detail.main_spot && detail.spot && withoutLocation.length > 0 && !allTrash}
				<div class="ready">
					<p>
						{m.groups_ready_text({
							photos: count(detail.spot.photos),
							located: count(detail.points.length)
						})}
					</p>
					<button type="button" class="st-btn st-btn--primary st-btn--sm" onclick={setSpot}>
						<Icon name="map-pin" size={14} />
						{m.groups_ready_set({ count: count(withoutLocation.length) })}
					</button>
				</div>
			{/if}
			{#if detail.groups.length > 1}
				<div class="legend" role="group" aria-label={m.folder_legend()}>
					{#each detail.groups as group (group.id)}
						<button
							type="button"
							class="st-chip"
							aria-pressed={shownGroups.has(group.id)}
							title={m.folder_legend_hint()}
							onclick={() => {
								if (!shownGroups.delete(group.id)) shownGroups.add(group.id);
								shownCount = PART;
							}}
						>
							<span class="st-chip__dot" style:background={colorOf.get(group.id)}></span>
							{group.name ?? m.groups_unnamed()}
						</button>
					{/each}
					{#if shownGroups.size > 0}
						<button
							type="button"
							class="st-btn st-btn--ghost st-btn--sm"
							onclick={() => shownGroups.clear()}
						>
							{m.folder_legend_all()}
						</button>
					{/if}
				</div>
			{/if}
			{#if mapConfig && detail.points.length > 0}
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
				<p class="hint">{m.groups_map_hint()} {m.folder_map_colors()}</p>
			{/if}
			<div class="views">
				{#each FILTERS as item (item.id)}
					{#if item.id !== 'chosen' || selection.size > 0}
						<button
							type="button"
							class="st-btn st-btn--sm"
							class:st-btn--secondary={item.id === filter}
							class:st-btn--ghost={item.id !== filter}
							aria-pressed={item.id === filter}
							onclick={() => {
								filter = item.id;
								shownCount = PART;
							}}
						>
							{item.label()}
						</button>
					{/if}
				{/each}
				<button
					type="button"
					class="st-btn st-btn--ghost st-btn--sm"
					onclick={() => selection.setAll(listed, true)}
				>
					{m.candidates_choose_all()}
				</button>
			</div>
			<div class="st-tile-grid">
				{#each listed.slice(0, shownCount) as photo (photo.id)}
					{@const chosen = chosenIds.has(photo.id)}
					<div class="st-tile-cell" class:chosen class:choosing={selection.size > 0}>
						<a
							class="st-tile"
							href={resolve(`/photo/[id]?folder=${encodeURIComponent(id)}`, { id: photo.id })}
							title={photo.file_name}
							onclick={(event) => clickTile(event, photo)}
						>
							<img
								src={thumbnailUrl(photo.id, 'thumbnail', 0, photo.version)}
								alt={photo.file_name}
								loading="lazy"
								decoding="async"
							/>
							<span class="swatch" style:background={colorOf.get(detail.group_of[photo.id] ?? '')}
							></span>
						</a>
						<button
							type="button"
							class="st-tile-check"
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
			{#if shownCount < listed.length}
				<div
					class="more"
					use:nearScreen={{ at: shownCount, onnear: () => (shownCount += PART) }}
				></div>
			{/if}
		{/if}
	{/if}
{:else if !error}
	<Skeleton />
{/if}

{#if selection.size}
	<SelectionBar {selection} onlocation={() => (locationOpen = true)}>
		<button type="button" class="st-btn st-btn--ghost st-btn--sm" disabled={busy} onclick={mark}>
			<Icon name="eye-off" size={14} />
			{m.groups_photos_trash()}
		</button>
	</SelectionBar>
{/if}
{#if locationOpen}
	<SelectionLocation
		items={[...selection.items.values()]}
		folderId={id}
		point={locationPoint}
		onsaved={() => {
			locationOpen = false;
			locationPoint = null;
			selection.clear();
		}}
		onclose={() => {
			locationOpen = false;
			locationPoint = null;
		}}
	/>
{/if}
{#if moving && detail}
	<FolderDialog
		groupIds={moving}
		current={detail.folder}
		ondone={() => {
			moving?.forEach((groupId) => chosenGroups.delete(groupId));
			moving = null;
			load(id);
		}}
		onclose={() => (moving = null)}
	/>
{/if}
{#if confirmDelete}
	<Dialog title={m.folder_delete()} icon="triangle-alert" onclose={() => (confirmDelete = false)}>
		<p>{m.folder_delete_warning()}</p>
		{#snippet footer()}
			<button
				type="button"
				class="st-btn st-btn--secondary"
				onclick={() => (confirmDelete = false)}
			>
				{m.groups_reset_cancel()}
			</button>
			<button type="button" class="st-btn st-btn--danger" onclick={remove}>
				{m.folder_delete()}
			</button>
		{/snippet}
	</Dialog>
{/if}

<style>
	.back {
		margin: var(--space-1) 0 var(--space-3);
	}
	.bad {
		color: var(--color-danger-text);
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
	.tools {
		position: sticky;
		top: calc(var(--header-height) + var(--space-2));
		z-index: var(--z-panel);
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2);
		margin-bottom: var(--space-3);
		padding: var(--space-1) var(--space-2);
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface);
		box-shadow: var(--shadow-sm);
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-1);
	}
	.group.chosen .cover {
		outline: 3px solid var(--color-accent);
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		margin-bottom: var(--space-3);
	}
	.views {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		margin-bottom: var(--space-4);
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
		flex: 1 1 18rem;
		margin: 0;
	}
	.map {
		height: min(24rem, 50dvh);
		margin-bottom: var(--space-2);
		overflow: hidden;
		border-radius: var(--radius-md);
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr));
		gap: var(--space-4);
	}
	.group {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--space-1);
		min-width: 0;
	}
	.cover {
		position: relative;
		display: block;
		width: 100%;
		aspect-ratio: 4 / 3;
		overflow: hidden;
		border-radius: var(--radius-md);
		background: var(--color-surface-sunken);
	}
	.cover img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	/* The color of the group on the map. */
	.swatch {
		position: absolute;
		right: 6px;
		bottom: 6px;
		width: 12px;
		height: 12px;
		border: 2px solid var(--gray-0);
		border-radius: 50%;
		box-shadow: var(--shadow-badge);
	}
	.st-tile {
		position: relative;
	}
	.st-tile-grid {
		margin-bottom: var(--space-16);
	}
	.more {
		height: 1px;
	}
</style>
