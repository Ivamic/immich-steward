<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- The albums of Immich (D-233): the account's own and the ones shared with it, as tiles. An
     album opens in the gallery of the app, with every filter and both orders; it can also be
     opened in Immich. Own albums are made, renamed and deleted here (in Immich, at once). -->
<script lang="ts">
	import {
		albumCoverUrl,
		createAlbum,
		deleteAlbum,
		getAlbums,
		renameAlbum,
		SHOW_CATEGORIES,
		type Album,
		type AlbumList
	} from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { bulkNotices } from '#lib/gallery/bulk.svelte.js';
	import { defaultFilter, filterToUrl } from '#lib/gallery/filter.js';
	import GroupName from '#lib/groups/GroupName.svelte';
	import { m } from '#lib/paraglide/messages.js';
	import { matches } from '#lib/search.js';
	import Dialog from '#lib/ui/Dialog.svelte';
	import EmptyState from '#lib/ui/EmptyState.svelte';
	import Icon from '#lib/ui/Icon.svelte';
	import Skeleton from '#lib/ui/Skeleton.svelte';
	import { resolve } from '$app/paths';

	type Sort = 'recent' | 'name' | 'taken';
	const SORTS: [Sort, () => string][] = [
		['recent', m.albums_sort_recent],
		['name', m.albums_sort_name],
		['taken', m.albums_sort_taken]
	];
	const SORT_KEY = 'steward.albums.sort';

	let list = $state<AlbumList | null>(null);
	let error = $state('');
	let query = $state('');
	let sort = $state<Sort>(storedSort());
	let creating = $state(false);
	let newName = $state('');
	let busy = $state(false);
	let dialogError = $state('');
	let deleting = $state<Album | null>(null);

	$effect(() => {
		load();
	});

	async function load() {
		try {
			list = await getAlbums();
			error = '';
		} catch (e) {
			error = errorMessage(e);
		}
	}

	function storedSort(): Sort {
		try {
			const value = localStorage.getItem(SORT_KEY);
			if (value === 'name' || value === 'taken' || value === 'recent') return value;
		} catch {
			// No storage (a private window): the default.
		}
		return 'recent';
	}

	function setSort(value: Sort) {
		sort = value;
		try {
			localStorage.setItem(SORT_KEY, value);
		} catch {
			// Remembered for this visit only.
		}
	}

	const shown = $derived.by(() => {
		const albums = (list?.albums ?? []).filter((a) => !query.trim() || matches(a.name, query));
		const byName = (a: Album, b: Album) => a.name.localeCompare(b.name);
		if (sort === 'name') return albums.sort(byName);
		if (sort === 'recent') return albums.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
		// The newest photos first; empty albums at the end.
		return albums.sort(
			(a, b) => (b.end_date ?? '').localeCompare(a.end_date ?? '') || byName(a, b)
		);
	});

	/** The album in the gallery of the app: all its photos, the archived ones too. */
	function galleryHref(album: Album): string {
		const filter = {
			...defaultFilter,
			show: [...SHOW_CATEGORIES],
			archived: 'with' as const,
			album: album.id
		};
		return resolve(`/${filterToUrl(filter)}`);
	}

	function period(album: Album): string | null {
		if (!album.start_date) return null;
		const format = (date: string) =>
			new Date(date).toLocaleDateString(undefined, {
				year: 'numeric',
				month: 'short',
				timeZone: 'UTC'
			});
		const first = format(album.start_date);
		const last = album.end_date ? format(album.end_date) : first;
		return first === last ? first : `${first} – ${last}`;
	}

	function replace(album: Album) {
		if (list) list.albums = list.albums.map((a) => (a.id === album.id ? album : a));
	}

	async function create(event: SubmitEvent) {
		event.preventDefault();
		const name = newName.trim();
		if (!name) return;
		busy = true;
		dialogError = '';
		try {
			await createAlbum(name);
			creating = false;
			newName = '';
			await load();
		} catch (e) {
			dialogError = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	async function remove(album: Album) {
		busy = true;
		dialogError = '';
		try {
			await deleteAlbum(album.id);
			deleting = null;
			if (list) list.albums = list.albums.filter((a) => a.id !== album.id);
			bulkNotices.done(m.album_create_undone({ album: album.name }));
		} catch (e) {
			dialogError = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	function openDialog(open: () => void) {
		dialogError = '';
		open();
	}
</script>

<div class="head">
	<h1>{m.nav_albums()}</h1>
	{#if list}
		<button
			type="button"
			class="st-btn st-btn--primary st-btn--sm"
			disabled={!list.allowed.create}
			title={list.allowed.create
				? undefined
				: m.album_cannot_create({ permission: list.permissions.create })}
			onclick={() => openDialog(() => (creating = true))}
		>
			<Icon name="plus" size={14} />
			{m.albums_new()}
		</button>
	{/if}
</div>

{#if error}
	<p class="bad" role="alert">{error}</p>
{:else if !list}
	<div class="grid" aria-busy="true" aria-label={m.album_loading()}>
		{#each { length: 8 }, i (i)}
			<Skeleton width="100%" height="7rem" />
		{/each}
	</div>
{:else if !list.albums.length}
	<EmptyState icon="images" title={m.album_none()} text={m.albums_empty_text()} />
{:else}
	<div class="tools">
		<input
			class="st-input st-input--sm search"
			type="search"
			placeholder={m.album_search()}
			aria-label={m.album_search()}
			bind:value={query}
		/>
		<div class="st-seg" role="radiogroup" aria-label={m.albums_sort()}>
			{#each SORTS as [value, label] (value)}
				<button
					type="button"
					role="radio"
					aria-checked={sort === value}
					onclick={() => setSort(value)}>{label()}</button
				>
			{/each}
		</div>
		<span class="count">{m.albums_count({ count: shown.length })}</span>
	</div>

	{#if !shown.length}
		<p class="note">{m.album_no_match()}</p>
	{/if}
	<div class="grid">
		{#each shown as album (album.id)}
			{@const href = galleryHref(album)}
			<div class="album">
				<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- resolved in galleryHref -->
				<a class="cover" {href} aria-label={album.name}>
					{#if album.has_cover}
						<img src={albumCoverUrl(album)} alt="" loading="lazy" decoding="async" />
					{:else}
						<span class="empty-cover"><Icon name="images" size={28} /></span>
					{/if}
				</a>
				<GroupName
					id={album.id}
					name={album.name}
					{href}
					label={m.albums_name()}
					required
					canRename={album.owned && list.allowed.rename}
					rename={async (name) => {
						const renamed = await renameAlbum(album.id, name);
						replace(renamed);
						return renamed.name;
					}}
					onrenamed={() => {}}
				/>
				<span class="numbers">
					{m.album_photos({ count: album.count })}
					{#if album.own_count !== album.count}
						· {m.albums_own_photos({ count: album.own_count })}
					{/if}
				</span>
				{#if period(album)}<span class="numbers">{period(album)}</span>{/if}
				<span class="actions">
					{#if album.shared}
						<span
							class="st-badge"
							title={album.owned
								? undefined
								: album.can_change_photos
									? m.albums_role_editor()
									: m.albums_role_viewer()}
						>
							<Icon name="users" size={11} />
							<span>{m.albums_shared()}</span>
						</span>
					{/if}
					<span class="spacer"></span>
					{#if list.immich_url}
						<!-- eslint-disable svelte/no-navigation-without-resolve -- external link -->
						<a
							class="st-iconbtn st-iconbtn--sm"
							href="{list.immich_url}/albums/{album.immich_id}"
							target="_blank"
							rel="noopener noreferrer"
							aria-label={m.photo_open_in_immich()}
							title={m.photo_open_in_immich()}
						>
							<Icon name="external-link" size={14} />
						</a>
						<!-- eslint-enable svelte/no-navigation-without-resolve -->
					{/if}
					{#if album.owned}
						<button
							type="button"
							class="st-iconbtn st-iconbtn--sm"
							disabled={!list.allowed.delete}
							aria-label={m.albums_delete()}
							title={list.allowed.delete
								? m.albums_delete()
								: m.album_cannot_delete({ permission: list.permissions.delete })}
							onclick={() => openDialog(() => (deleting = album))}
						>
							<Icon name="trash-2" size={14} />
						</button>
					{/if}
				</span>
			</div>
		{/each}
	</div>
{/if}

{#if creating}
	<Dialog title={m.albums_new()} icon="folder-plus" onclose={() => (creating = false)}>
		<form id="album-new" onsubmit={create}>
			<label class="st-field">
				<span class="st-field__label">{m.albums_name()}</span>
				<!-- svelte-ignore a11y_autofocus -->
				<input
					class="st-input"
					maxlength="200"
					required
					disabled={busy}
					bind:value={newName}
					autofocus
				/>
			</label>
			{#if dialogError}<p class="bad" role="alert">{dialogError}</p>{/if}
		</form>
		{#snippet footer()}
			<button type="button" class="st-btn st-btn--secondary" onclick={() => (creating = false)}>
				{m.groups_reset_cancel()}
			</button>
			<button
				type="submit"
				form="album-new"
				class="st-btn st-btn--primary"
				disabled={busy || !newName.trim()}
			>
				{m.albums_create()}
			</button>
		{/snippet}
	</Dialog>
{/if}

{#if deleting}
	{@const album = deleting}
	<Dialog title={m.albums_delete()} icon="triangle-alert" onclose={() => (deleting = null)}>
		<p>{m.albums_delete_warning({ album: album.name })}</p>
		{#if dialogError}<p class="bad" role="alert">{dialogError}</p>{/if}
		{#snippet footer()}
			<button type="button" class="st-btn st-btn--secondary" onclick={() => (deleting = null)}>
				{m.groups_reset_cancel()}
			</button>
			<button
				type="button"
				class="st-btn st-btn--danger"
				disabled={busy}
				onclick={() => remove(album)}
			>
				{m.albums_delete()}
			</button>
		{/snippet}
	</Dialog>
{/if}

<style>
	.head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-2);
		margin-bottom: var(--space-4);
	}
	h1 {
		margin: 0;
	}
	.tools {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2) var(--space-3);
		margin-bottom: var(--space-4);
	}
	.search {
		width: min(18rem, 100%);
	}
	.count,
	.note,
	.numbers {
		color: var(--color-text-muted);
		font-size: var(--text-sm);
		font-variant-numeric: tabular-nums;
	}
	.note {
		margin: 0 0 var(--space-4);
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(10rem, 1fr));
		gap: var(--space-4);
	}
	.album {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		min-width: 0;
	}
	/* As the covers of the groups. */
	.cover {
		display: block;
		aspect-ratio: 4 / 3;
		overflow: hidden;
		border-radius: var(--radius-md);
		background: var(--color-surface-sunken);
	}
	.cover:hover {
		outline: 2px solid var(--color-accent);
	}
	.cover img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.empty-cover {
		display: grid;
		place-items: center;
		height: 100%;
		color: var(--color-text-subtle);
	}
	.actions {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		min-height: var(--control-sm);
	}
	.spacer {
		flex: 1;
	}
	.bad {
		color: var(--color-danger-text);
	}
</style>
