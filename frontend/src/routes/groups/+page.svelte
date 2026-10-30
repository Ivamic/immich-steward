<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Groups of photos, one tab per way of grouping: "Environment" for now, more may come. Those
     named by the user come first, then the largest; the views narrow the list. -->
<script lang="ts">
	import {
		bringBackGroup,
		getGroups,
		getTrashedPhotos,
		isActive,
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
	import EmptyState from '#lib/ui/EmptyState.svelte';
	import Icon from '#lib/ui/Icon.svelte';
	import Skeleton from '#lib/ui/Skeleton.svelte';
	import { afterNavigate, goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { tick } from 'svelte';

	const PAGE = 60;
	// The most the server gives at a time.
	const MOST = 200;
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

	function loadTrashed() {
		return getTrashedPhotos()
			.then((answer) => (trashed = answer))
			.catch((e) => (error = errorMessage(e)));
	}

	/** Storage may be unavailable: the list then just opens from the top. */
	function rememberPlace() {
		try {
			const place = { view, shown: shown.length, top: window.scrollY };
			sessionStorage.setItem(PLACE_KEY, JSON.stringify(place));
		} catch {
			// nothing to do
		}
	}

	function rememberedPlace(): { shown: number; top: number } | null {
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
		await Promise.all([load(view, place.shown), view === 'trash' ? loadTrashed() : null]);
		await tick();
		window.scrollTo({ top: place.top });
	});

	async function bringBack(id: string) {
		try {
			trashed = await restorePhotos([id]);
		} catch (e) {
			error = errorMessage(e);
		}
	}

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
		<div class="photos">
			{#each trashed.photos as photo (photo.id)}
				<div class="cell">
					<a href={resolve('/photo/[id]', { id: photo.id })} title={photo.file_name}>
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
						onclick={() => bringBack(photo.id)}
					>
						<Icon name="rotate-ccw" size={14} strokeWidth={2.5} />
					</button>
				</div>
			{/each}
		</div>
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
						<span class="numbers">{m.groups_photos({ count: count(group.photos) })}</span>
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
		color: white;
		cursor: pointer;
	}
	.more {
		height: 1px;
	}
</style>
