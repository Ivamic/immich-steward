<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Turned photos (D-237): the photos the orientation module of a worker finds lying on a side or
     upside down, in groups by how. The previews show them turned back already; nothing changes in
     Immich until the user turns the chosen ones (the same job as the rotate of the gallery), or
     keeps them as they are. -->
<script lang="ts">
	import {
		getKeptTurned,
		getTurned,
		keepTurned,
		rotateSelection,
		thumbnailUrl,
		type AssetItem,
		type Turn,
		type TurnedGroup,
		type TurnedPhotos
	} from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { bulkNotices } from '#lib/gallery/bulk.svelte.js';
	import { longpress } from '#lib/gallery/longpress.js';
	import PhotoPeek from '#lib/gallery/PhotoPeek.svelte';
	import SelectionBar from '#lib/gallery/SelectionBar.svelte';
	import SelectionLocation from '#lib/gallery/SelectionLocation.svelte';
	import { galleryChanged, Selection } from '#lib/gallery/selection.svelte.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import EmptyState from '#lib/ui/EmptyState.svelte';
	import GroupsTabs from '#lib/groups/GroupsTabs.svelte';
	import Icon from '#lib/ui/Icon.svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';

	const PAGE = 200;

	let answer = $state.raw<TurnedPhotos | null>(null);
	// The photos of each group loaded so far, by turn.
	let shown = $state<Record<number, AssetItem[]>>({});
	let error = $state<string | null>(null);
	let busy = $state(false);
	let locationOpen = $state(false);
	const selection = new Selection();
	const chosenIds = $derived(new Set(selection.ids));
	// Photos turned or kept on this page: they leave the list at once.
	let gone = $state(new Set<string>());
	const number = new Intl.NumberFormat(getLocale());
	// The photo of a long press, shown large (turned as the page offers it).
	let peek = $state<{ item: AssetItem; turn: Turn } | null>(null);
	// The filter, in the address so that it stays on reload: all groups, one turn, or the photos
	// kept as they are.
	const keptView = $derived(page.url.searchParams.get('view') === 'kept');
	const only = $derived(keptView ? null : Number(page.url.searchParams.get('turn')) || null);
	// The photos kept as they are, loaded while that filter is on.
	let kept = $state.raw<AssetItem[] | null>(null);
	let keptTotal = $state(0);

	function choose(filter: number | 'kept' | null) {
		selection.clear();
		const to = {
			kept: resolve('/groups/turned?view=kept'),
			1: resolve('/groups/turned?turn=1'),
			2: resolve('/groups/turned?turn=2'),
			3: resolve('/groups/turned?turn=3')
		};
		goto(filter === null ? resolve('/groups/turned') : to[filter as keyof typeof to], {
			replace: true,
			reset: false
		});
	}

	async function loadKept(more = false) {
		try {
			const answer = await getKeptTurned(more ? (kept ?? []).length : 0, PAGE);
			kept = more ? [...(kept ?? []), ...answer.photos] : answer.photos;
			keptTotal = answer.total;
		} catch (e) {
			error = errorMessage(e);
		}
	}

	$effect(() => {
		if (keptView) loadKept();
	});

	/** The chosen photos kept as they are go back to the list of turned photos. */
	async function offerAgain() {
		busy = true;
		error = null;
		try {
			const ids = selection.ids;
			const { changed } = await keepTurned(ids, false);
			selection.clear();
			bulkNotices.done(m.turned_kept_undone({ count: changed }));
			await Promise.all([load(), loadKept()]);
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	async function load() {
		try {
			const result = await getTurned(null, 0, PAGE);
			answer = result;
			keptTotal = result.kept ?? 0;
			shown = Object.fromEntries(result.groups.map((g) => [g.turn, g.photos]));
			gone = new Set();
			error = null;
		} catch (e) {
			error = errorMessage(e);
		}
	}

	$effect(() => {
		load();
	});

	async function more(group: TurnedGroup) {
		try {
			const loaded = shown[group.turn] ?? [];
			const next = await getTurned(group.turn, loaded.length, PAGE);
			shown[group.turn] = [...loaded, ...(next.groups[0]?.photos ?? [])];
		} catch (e) {
			error = errorMessage(e);
		}
	}

	const left = (group: TurnedGroup) => (shown[group.turn] ?? []).filter((p) => !gone.has(p.id));
	const total = $derived((answer?.groups ?? []).reduce((sum, g) => sum + g.total, 0) - gone.size);
	// What a group still counts: less the photos turned or kept on this page.
	const groupTotal = (group: TurnedGroup) =>
		group.total - (shown[group.turn] ?? []).filter((p) => gone.has(p.id)).length;
	const visible = $derived((answer?.groups ?? []).filter((g) => only === null || g.turn === only));

	function filterLabel(group: TurnedGroup): string {
		return group.turn === 1
			? m.turned_view_right()
			: group.turn === 3
				? m.turned_view_left()
				: m.turned_view_upside_down();
	}

	function groupTitle(group: TurnedGroup): string {
		return group.turn === 1
			? m.turned_group_right()
			: group.turn === 3
				? m.turned_group_left()
				: m.turned_group_upside_down();
	}

	/** Turns the chosen photos in Immich, each group by its own turn. */
	async function turn() {
		busy = true;
		error = null;
		try {
			for (const group of answer?.groups ?? []) {
				const photos = left(group).filter((p) => chosenIds.has(p.id) && p.type !== 'VIDEO');
				if (!photos.length) continue;
				const ids = photos.map((p) => p.id);
				const jobs = await rotateSelection(ids, group.fix);
				bulkNotices.followRotation(jobs, ids, ids.length);
				gone = new Set([...gone, ...ids]);
			}
			selection.clear();
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	/** The chosen photos are right as they are; the notice can bring them back. */
	async function keep() {
		busy = true;
		error = null;
		try {
			const ids = selection.ids;
			const { changed } = await keepTurned(ids, true);
			gone = new Set([...gone, ...ids]);
			keptTotal = (answer?.kept ?? 0) + changed;
			if (answer) answer = { ...answer, kept: keptTotal };
			selection.clear();
			bulkNotices.undoable(m.turned_kept({ count: changed }), [], async () => {
				const back = await keepTurned(ids, false);
				await load();
				return m.turned_kept_undone({ count: back.changed });
			});
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	function clickTile(event: MouseEvent, photo: AssetItem, photos: AssetItem[]) {
		if (event.shiftKey && selection.anchor) {
			event.preventDefault();
			selection.extend(photo, photos);
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
</script>

<svelte:window {onkeydown} />

<h1>{m.nav_groups()}</h1>

<GroupsTabs current="turned" turned={answer ? Math.max(0, total) : null} />

<p class="muted">{m.turned_intro()}</p>

{#if error}
	<p class="bad" role="alert">{error}</p>
{/if}

{#if answer}
	{#if answer.checked === 0}
		<EmptyState icon="cpu" title={m.turned_not_checked()} text={m.turned_not_checked_text()} />
	{:else if total <= 0 && !keptTotal}
		<EmptyState
			icon="images"
			title={m.turned_none()}
			text={m.turned_none_text({ count: number.format(answer.checked) })}
		/>
	{:else}
		<div class="views">
			<button
				type="button"
				class="st-btn st-btn--sm"
				class:st-btn--secondary={only === null}
				class:st-btn--ghost={only !== null}
				aria-pressed={only === null}
				onclick={() => choose(null)}
			>
				{m.groups_view_all()}
				<span class="count">{number.format(Math.max(0, total))}</span>
			</button>
			{#each answer.groups as group (group.turn)}
				<button
					type="button"
					class="st-btn st-btn--sm"
					class:st-btn--secondary={only === group.turn}
					class:st-btn--ghost={only !== group.turn}
					aria-pressed={only === group.turn}
					onclick={() => choose(group.turn)}
				>
					{filterLabel(group)}
					<span class="count">{number.format(groupTotal(group))}</span>
				</button>
			{/each}
			{#if keptTotal}
				<button
					type="button"
					class="st-btn st-btn--sm"
					class:st-btn--secondary={keptView}
					class:st-btn--ghost={!keptView}
					aria-pressed={keptView}
					title={m.turned_view_kept_hint()}
					onclick={() => choose('kept')}
				>
					{m.turned_view_kept()}
					<span class="count">{number.format(keptTotal)}</span>
				</button>
			{/if}
		</div>
		{#if keptView}
			<p class="muted">{m.turned_kept_intro()}</p>
			{#if kept}
				<div class="st-tile-grid">
					{#each kept as photo (photo.id)}
						{@const chosen = chosenIds.has(photo.id)}
						<div class="st-tile-cell" class:chosen class:choosing={selection.size > 0}>
							<a
								class="st-tile"
								href={resolve('/photo/[id]', { id: photo.id })}
								title={photo.file_name}
								use:longpress={() => (peek = { item: photo, turn: 0 })}
								onclick={(event) => clickTile(event, photo, kept ?? [])}
							>
								<img
									src={thumbnailUrl(photo.id, 'thumbnail', 0, photo.version)}
									alt={photo.file_name}
									loading="lazy"
									decoding="async"
								/>
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
				{#if kept.length < keptTotal}
					<button
						type="button"
						class="st-btn st-btn--secondary st-btn--sm"
						onclick={() => loadKept(true)}
					>
						{m.turned_more()}
					</button>
				{/if}
			{/if}
		{/if}
		{#each keptView ? [] : visible as group (group.turn)}
			{@const photos = left(group)}
			{#if photos.length}
				<section>
					<div class="found">
						<h2>{groupTitle(group)}</h2>
						<span class="muted">{number.format(groupTotal(group))}</span>
						<button
							type="button"
							class="st-btn st-btn--ghost st-btn--sm"
							onclick={() => selection.setAll(photos, true)}
						>
							{m.candidates_choose_all()}
						</button>
					</div>
					<div class="st-tile-grid">
						{#each photos as photo (photo.id)}
							{@const chosen = chosenIds.has(photo.id)}
							<div class="st-tile-cell" class:chosen class:choosing={selection.size > 0}>
								<a
									class="st-tile"
									href={resolve('/photo/[id]', { id: photo.id })}
									title={photo.file_name}
									use:longpress={() => (peek = { item: photo, turn: group.fix })}
									onclick={(event) => clickTile(event, photo, photos)}
								>
									<img
										src={thumbnailUrl(photo.id, 'thumbnail', group.fix, photo.version)}
										alt={photo.file_name}
										loading="lazy"
										decoding="async"
									/>
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
					{#if (shown[group.turn]?.length ?? 0) < group.total}
						<button
							type="button"
							class="st-btn st-btn--secondary st-btn--sm"
							onclick={() => more(group)}
						>
							{m.turned_more()}
						</button>
					{/if}
				</section>
			{/if}
		{/each}
	{/if}
{:else if !error}
	<p class="muted" role="status">
		<span class="st-spin"><Icon name="loader-circle" size={14} /></span>
	</p>
{/if}

{#if peek}
	<PhotoPeek item={peek.item} turn={peek.turn} onclose={() => (peek = null)} />
{/if}

{#if selection.size && keptView}
	<SelectionBar {selection} onlocation={() => (locationOpen = true)}>
		<button
			type="button"
			class="st-btn st-btn--ghost st-btn--sm"
			disabled={busy}
			onclick={offerAgain}
		>
			<Icon name="undo-2" size={14} />
			{m.turned_offer_again()}
		</button>
	</SelectionBar>
{:else if selection.size}
	<SelectionBar {selection} rotation={false} onlocation={() => (locationOpen = true)}>
		<button type="button" class="st-btn st-btn--primary st-btn--sm" disabled={busy} onclick={turn}>
			<Icon name="rotate-cw" size={14} />
			{m.turned_turn()}
		</button>
		<button type="button" class="st-btn st-btn--ghost st-btn--sm" disabled={busy} onclick={keep}>
			<Icon name="check" size={14} />
			{m.turned_keep()}
		</button>
	</SelectionBar>
{/if}
{#if locationOpen}
	<SelectionLocation
		items={[...selection.items.values()]}
		onsaved={() => {
			locationOpen = false;
			selection.clear();
			galleryChanged();
		}}
		onclose={() => (locationOpen = false)}
	/>
{/if}

<style>
	h1 {
		margin: 0 0 var(--space-4);
	}
	h2 {
		margin: 0;
		font-size: var(--text-md);
	}
	.views {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		margin-bottom: var(--space-4);
	}
	.count {
		color: var(--color-text-muted);
		font-variant-numeric: tabular-nums;
	}
	.muted {
		margin: 0 0 var(--space-3);
		color: var(--color-text-muted);
	}
	.bad {
		color: var(--color-danger-text);
	}
	section {
		margin-bottom: var(--space-8);
	}
	.found {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2);
		margin-bottom: var(--space-3);
	}
	.found .muted {
		margin: 0;
	}
	.st-tile-grid {
		margin-bottom: var(--space-3);
	}
	/* Room for the bar of the chosen photos at the bottom. */
	section:last-of-type {
		margin-bottom: var(--space-16);
	}
</style>
