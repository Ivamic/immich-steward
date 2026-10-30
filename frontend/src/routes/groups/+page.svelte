<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Groups of photos, one tab per way of grouping: "Environment" for now, more may come. Those
     named by the user come first, then the largest; the views narrow the list. -->
<script lang="ts">
	import {
		bringBackGroup,
		getGroups,
		getTrashedPhotos,
		isActive,
		restoreAllPhotos,
		restorePhotos,
		thumbnailUrl,
		type GroupList,
		type GroupOut,
		type GroupView,
		type TrashedPhotos
	} from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { nearScreen } from '#lib/gallery/nearScreen.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import Dialog from '#lib/ui/Dialog.svelte';
	import EmptyState from '#lib/ui/EmptyState.svelte';
	import Icon from '#lib/ui/Icon.svelte';
	import Skeleton from '#lib/ui/Skeleton.svelte';
	import { afterNavigate, goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { tick } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';

	const PAGE = 60;
	// The most the server gives at a time.
	const MOST = 200;
	// Photos with no sign of a place: a page of them, the most at a time, the most sent at a time.
	const TRASHED_PAGE = 120;
	const TRASHED_MOST = 500;
	const SENT_MOST = 2000;
	const POLL_MS = 5000;
	// Where the list was when a group was opened.
	const PLACE_KEY = 'steward.groups.place';
	const VIEWS: { id: GroupView; label: () => string }[] = [
		{ id: 'all', label: m.groups_view_all },
		{ id: 'ready', label: m.groups_view_ready },
		{ id: 'no_location', label: m.groups_view_no_location },
		{ id: 'with_location', label: m.groups_view_with_location },
		{ id: 'spread', label: m.groups_view_spread },
		{ id: 'trash', label: m.groups_view_trash },
		{ id: 'dissolved', label: m.groups_view_dissolved }
	];

	let list = $state.raw<GroupList | null>(null);
	let shown = $state.raw<GroupOut[]>([]);
	let error = $state<string | null>(null);
	let loadingMore = $state(false);
	let trashed = $state.raw<TrashedPhotos | null>(null);
	let loadingTrashed = false;
	let restoring = $state(false);
	let confirmRestore = $state(false);
	const chosenTrashed = new SvelteSet<string>();
	// Only the answer to the last request counts.
	let latest = 0;
	let loading = false;

	const numbers = new Intl.NumberFormat(getLocale());
	const count = (n: number) => numbers.format(n);
	const similarities = new Intl.NumberFormat(getLocale(), {
		minimumFractionDigits: 2,
		maximumFractionDigits: 2
	});
	const similarity = (value: number) => similarities.format(value);

	const view = $derived.by((): GroupView => {
		const asked = page.url.searchParams.get('view');
		return VIEWS.find((v) => v.id === asked)?.id ?? 'all';
	});
	// Goes along to a group, for its way back to this view.
	const query = $derived<'' | `?${string}`>(view === 'all' ? '' : `?view=${view}`);
	const status = $derived(list?.status ?? null);
	const working = $derived(isActive(status?.job ?? null));
	const total = $derived(list?.counts[view] ?? 0);

	/** The groups with the new ones at the end: a rebuild may move a group from page to page. */
	function joined(groups: GroupOut[], next: GroupOut[]) {
		const known = new Set(groups.map((group) => group.id));
		return [...groups, ...next.filter((group) => !known.has(group.id))];
	}

	/** The first page, or as many as are shown (a new look at the same list). */
	async function load(wanted: GroupView, limit: number) {
		const asked = ++latest;
		loading = true;
		try {
			const answer = await getGroups(wanted, 0, Math.min(limit, MOST));
			let groups = answer.groups;
			while (groups.length < Math.min(limit, answer.counts[wanted])) {
				const left = Math.min(limit - groups.length, MOST);
				const next = joined(groups, (await getGroups(wanted, groups.length, left)).groups);
				if (next.length === groups.length) break;
				groups = next;
			}
			if (asked !== latest) return;
			list = answer;
			shown = groups;
			error = null;
		} catch (e) {
			if (asked === latest) error = errorMessage(e);
		} finally {
			if (asked === latest) loading = false;
		}
	}

	async function more() {
		if (loadingMore) return;
		const wanted = view;
		loadingMore = true;
		try {
			const answer = await getGroups(wanted, shown.length, PAGE);
			if (wanted === view) shown = joined(shown, answer.groups);
		} catch (e) {
			error = errorMessage(e);
		} finally {
			loadingMore = false;
		}
	}

	function choose(next: GroupView) {
		chosenTrashed.clear();
		goto(resolve(next === 'all' ? '/groups' : `/groups?view=${next}`), {
			replace: true,
			reset: false
		});
	}

	async function bringBackDissolved(id: string) {
		try {
			await bringBackGroup(id);
			await load(view, Math.max(shown.length, PAGE));
		} catch (e) {
			error = errorMessage(e);
		}
	}

	/** The first page, or as many as were shown. */
	async function loadTrashed(upTo = TRASHED_PAGE) {
		try {
			const answer = await getTrashedPhotos(0, Math.min(upTo, TRASHED_MOST));
			let photos = answer.photos;
			while (photos.length < Math.min(upTo, answer.total)) {
				const left = Math.min(upTo - photos.length, TRASHED_MOST);
				const next = await getTrashedPhotos(photos.length, left);
				if (next.photos.length === 0) break;
				photos = [...photos, ...next.photos];
			}
			trashed = { total: answer.total, photos };
		} catch (e) {
			error = errorMessage(e);
		}
	}

	async function moreTrashed() {
		if (loadingTrashed || !trashed) return;
		loadingTrashed = true;
		try {
			const answer = await getTrashedPhotos(trashed.photos.length, TRASHED_PAGE);
			const known = new Set(trashed.photos.map((photo) => photo.id));
			const fresh = answer.photos.filter((photo) => !known.has(photo.id));
			trashed = { total: answer.total, photos: [...trashed.photos, ...fresh] };
		} catch (e) {
			error = errorMessage(e);
		} finally {
			loadingTrashed = false;
		}
	}

	function toggleTrashed(id: string) {
		if (!chosenTrashed.delete(id)) chosenTrashed.add(id);
	}

	/** While some are chosen a click chooses, as among the photos of a group. */
	function clickTrashed(event: MouseEvent, id: string) {
		if (chosenTrashed.size === 0) return;
		event.preventDefault();
		toggleTrashed(id);
	}

	/** Takes the mark off, a part at a time: a request is bounded. The groups are built again. */
	async function restore(ids: string[]) {
		restoring = true;
		try {
			let total = trashed?.total ?? 0;
			for (let start = 0; start < ids.length; start += SENT_MOST) {
				total = (await restorePhotos(ids.slice(start, start + SENT_MOST))).total;
			}
			const gone = new Set(ids);
			const left = (trashed?.photos ?? []).filter((photo) => !gone.has(photo.id));
			trashed = { total, photos: left };
			ids.forEach((id) => chosenTrashed.delete(id));
			await load(view, Math.max(shown.length, PAGE));
		} catch (e) {
			error = errorMessage(e);
		} finally {
			restoring = false;
		}
	}

	async function restoreAll() {
		confirmRestore = false;
		restoring = true;
		try {
			trashed = await restoreAllPhotos();
			chosenTrashed.clear();
			await load(view, Math.max(shown.length, PAGE));
		} catch (e) {
			error = errorMessage(e);
		} finally {
			restoring = false;
		}
	}

	/** Storage may be unavailable: the list then just opens from the top. */
	function rememberPlace() {
		try {
			const trashedShown = trashed?.photos.length ?? 0;
			const place = { view, shown: shown.length, trashedShown, top: window.scrollY };
			sessionStorage.setItem(PLACE_KEY, JSON.stringify(place));
		} catch {
			// nothing to do
		}
	}

	function rememberedPlace(): { shown: number; trashedShown?: number; top: number } | null {
		try {
			const place = JSON.parse(sessionStorage.getItem(PLACE_KEY) ?? 'null');
			return place?.view === view ? place : null;
		} catch {
			return null;
		}
	}

	// Back from a group: as many groups as were there, at the same height.
	afterNavigate(async ({ from }) => {
		if (from?.route.id !== '/groups/[id]') return;
		const place = rememberedPlace();
		if (!place) return;
		await Promise.all([
			load(view, place.shown),
			view === 'trash' ? loadTrashed(place.trashedShown || TRASHED_PAGE) : null
		]);
		await tick();
		window.scrollTo({ top: place.top });
	});

	$effect(() => {
		load(view, PAGE);
	});

	$effect(() => {
		if (view === 'trash') loadTrashed();
	});

	// While the groups are being worked on, the numbers and the list change.
	$effect(() => {
		if (!working) return;
		const timer = setInterval(() => {
			if (!loading) load(view, Math.max(shown.length, PAGE));
		}, POLL_MS);
		return () => clearInterval(timer);
	});
</script>

<h1>{m.nav_groups()}</h1>

<nav class="tabs">
	<a href={resolve('/groups')} aria-current="page">{m.groups_tab_environment()}</a>
</nav>

{#if status && working}
	<p class="status" role="status">
		<span class="st-spin"><Icon name="loader-circle" size={14} /></span>
		{status.searched < status.vectors
			? m.groups_searching({ done: count(status.searched), total: count(status.vectors) })
			: m.groups_building()}
	</p>
{:else if status?.job?.status === 'failed'}
	<p class="status bad" role="status">{m.groups_failed()}</p>
{/if}

{#if error}
	<p class="bad" role="alert">{error}</p>
{/if}

{#if list}
	<div class="views">
		{#each VIEWS as item (item.id)}
			<button
				type="button"
				class="st-btn st-btn--sm"
				class:st-btn--secondary={item.id === view}
				class:st-btn--ghost={item.id !== view}
				aria-pressed={item.id === view}
				onclick={() => choose(item.id)}
			>
				{item.label()}
				<span class="count">{count(list.counts[item.id])}</span>
			</button>
		{/each}
	</div>

	{#if view === 'trash' && trashed && trashed.total > 0}
		<h2>{m.groups_trashed_heading({ count: count(trashed.total) })}</h2>
		<p class="muted">{m.groups_trashed_hint()}</p>
		<div class="trashed-tools">
			{#if chosenTrashed.size > 0}
				<button
					type="button"
					class="st-btn st-btn--primary st-btn--sm"
					disabled={restoring}
					onclick={() => restore([...chosenTrashed])}
				>
					<Icon name="rotate-ccw" size={14} />
					{m.groups_restore_chosen({ count: count(chosenTrashed.size) })}
				</button>
				<button
					type="button"
					class="st-btn st-btn--ghost st-btn--sm"
					onclick={() => chosenTrashed.clear()}
				>
					{m.selection_clear()}
				</button>
			{/if}
			<button
				type="button"
				class="st-btn st-btn--secondary st-btn--sm"
				disabled={restoring}
				onclick={() => (confirmRestore = true)}
			>
				<Icon name="rotate-ccw" size={14} />
				{m.groups_restore_all({ count: count(trashed.total) })}
			</button>
			{#if restoring}
				<span class="st-spin"><Icon name="loader-circle" size={14} /></span>
			{/if}
		</div>
		<div class="photos">
			{#each trashed.photos as photo (photo.id)}
				{@const chosen = chosenTrashed.has(photo.id)}
				<div class="cell" class:chosen>
					<a
						href={resolve('/photo/[id]', { id: photo.id })}
						title={photo.file_name}
						onclick={(event) => clickTrashed(event, photo.id)}
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
						class="back"
						aria-label={m.groups_bring_back()}
						title={m.groups_bring_back()}
						disabled={restoring}
						onclick={() => restore([photo.id])}
					>
						<Icon name="rotate-ccw" size={14} strokeWidth={2.5} />
					</button>
					<button
						type="button"
						class="pick"
						aria-pressed={chosen}
						aria-label={m.groups_choose_photo()}
						title={m.groups_choose_photo()}
						onclick={() => toggleTrashed(photo.id)}
					>
						<Icon name="check" size={12} strokeWidth={3} />
					</button>
				</div>
			{/each}
		</div>
		{#if trashed.photos.length < trashed.total}
			<div class="more" use:nearScreen={{ at: trashed.photos.length, onnear: moreTrashed }}></div>
		{/if}
	{/if}

	{#if shown.length > 0}
		<div class="grid">
			{#each shown as group (group.id)}
				{#if view === 'dissolved'}
					<div class="group">
						<span class="cover">
							{#if group.cover}
								<img
									src={thumbnailUrl(group.cover.id, 'thumbnail', 0, group.cover.version)}
									alt=""
									loading="lazy"
									decoding="async"
								/>
							{/if}
						</span>
						<span class="name" class:unnamed={!group.name}>{group.name ?? m.groups_unnamed()}</span>
						<span class="numbers">{m.groups_photos({ count: count(group.photos) })}</span>
						<button
							type="button"
							class="st-btn st-btn--secondary st-btn--sm"
							onclick={() => bringBackDissolved(group.id)}
						>
							<Icon name="rotate-ccw" size={14} />
							{m.groups_bring_back()}
						</button>
					</div>
				{:else}
					<a
						class="group"
						href={resolve(`/groups/[id]${query}`, { id: group.id })}
						onclick={rememberPlace}
					>
						<span class="cover">
							{#if group.cover}
								<img
									src={thumbnailUrl(group.cover.id, 'thumbnail', 0, group.cover.version)}
									alt=""
									loading="lazy"
									decoding="async"
								/>
							{/if}
						</span>
						<span class="name" class:unnamed={!group.name}>{group.name ?? m.groups_unnamed()}</span>
						<span class="numbers">
							{m.groups_photos({ count: count(group.photos || group.marked) })}
						</span>
						<span class="badges">
							{#if group.with_location > 0}
								<span class="st-badge st-badge--success">
									<Icon name="map-pin" size={11} />
									<span>{m.groups_with_location({ count: count(group.with_location) })}</span>
								</span>
							{/if}
							{#if group.without_location > 0}
								<span class="st-badge st-badge--info">
									<Icon name="map-pin-off" size={11} />
									<span>{m.groups_without_location({ count: count(group.without_location) })}</span>
								</span>
							{/if}
							{#if group.spread}
								<span class="st-badge st-badge--warning" title={m.groups_spread_hint()}>
									<Icon name="route" size={11} />
									<span>{m.groups_spread()}</span>
								</span>
							{/if}
							{#if group.similarity !== null}
								<span class="st-badge" title={m.groups_similarity_hint()}>
									<span>{m.groups_similarity({ value: similarity(group.similarity) })}</span>
								</span>
							{/if}
						</span>
					</a>
				{/if}
			{/each}
		</div>
		{#if shown.length < total}
			<div class="more" use:nearScreen={{ at: shown.length, onnear: more }}></div>
		{/if}
	{:else if list.counts.all + list.counts.trash === 0}
		<EmptyState icon="images" title={m.groups_empty_title()} text={m.groups_empty_text()} />
	{:else}
		<p class="muted">{m.groups_view_empty()}</p>
	{/if}
{:else if !error}
	<Skeleton />
{/if}

{#if confirmRestore && trashed}
	<Dialog
		title={m.groups_restore_all({ count: count(trashed.total) })}
		icon="triangle-alert"
		onclose={() => (confirmRestore = false)}
	>
		<p>{m.groups_restore_all_warning()}</p>
		{#snippet footer()}
			<button
				type="button"
				class="st-btn st-btn--secondary"
				onclick={() => (confirmRestore = false)}
			>
				{m.groups_reset_cancel()}
			</button>
			<button type="button" class="st-btn st-btn--danger" onclick={restoreAll}>
				{m.groups_restore_all({ count: count(trashed?.total ?? 0) })}
			</button>
		{/snippet}
	</Dialog>
{/if}

<style>
	h1 {
		margin: 0 0 var(--space-4);
	}
	.tabs {
		display: flex;
		gap: var(--space-4);
		margin-bottom: var(--space-4);
		border-bottom: 1px solid var(--color-border);
	}
	.tabs a {
		padding: var(--space-2) var(--space-1);
		margin-bottom: -1px;
		border-bottom: 2px solid transparent;
		color: var(--color-text-muted);
		text-decoration: none;
	}
	.tabs a[aria-current='page'] {
		border-bottom-color: var(--color-accent);
		color: var(--color-text);
		font-weight: var(--weight-medium);
	}
	.status {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		margin: 0 0 var(--space-3);
		color: var(--color-text-muted);
		font-size: var(--text-sm);
	}
	.bad {
		color: var(--color-danger-text);
	}
	.muted {
		color: var(--color-text-muted);
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
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr));
		gap: var(--space-4);
	}
	.group {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		min-width: 0;
		color: inherit;
		text-decoration: none;
	}
	.cover {
		display: block;
		aspect-ratio: 4 / 3;
		overflow: hidden;
		border-radius: var(--radius-md);
		background: var(--color-surface-sunken);
	}
	.cover img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.group:hover .cover {
		outline: 2px solid var(--color-accent);
	}
	.name {
		overflow: hidden;
		font-weight: var(--weight-medium);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.name.unnamed {
		color: var(--color-text-muted);
		font-weight: normal;
	}
	.numbers {
		color: var(--color-text-muted);
		font-size: var(--text-sm);
	}
	.badges {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-1);
	}
	h2 {
		margin: 0 0 var(--space-2);
		font-size: var(--text-lg);
	}
	.photos {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(7rem, 1fr));
		gap: var(--space-1);
		margin-bottom: var(--space-6);
	}
	.cell {
		position: relative;
		aspect-ratio: 1;
		overflow: hidden;
		background: var(--color-surface-sunken);
	}
	.cell a,
	.cell img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.back {
		position: absolute;
		top: var(--space-1);
		right: var(--space-1);
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
		color: white;
		cursor: pointer;
	}
	.more {
		height: 1px;
	}
	/* Stays under the header: the list can be thousands of photos long. */
	.trashed-tools {
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
	.cell.chosen img {
		opacity: 0.75;
		outline: 3px solid var(--color-accent);
		outline-offset: -3px;
	}
	.pick {
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
	.pick:hover {
		color: white;
	}
	.pick[aria-pressed='true'] {
		border-color: var(--color-accent);
		background: var(--color-accent);
		color: white;
	}
</style>
