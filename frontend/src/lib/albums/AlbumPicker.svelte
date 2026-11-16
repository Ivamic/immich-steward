<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Puts photos into an album of Immich (D-233): a search field over the albums the account may
     add to (the ones changed lately first), which also names a new album. Arrows move, Enter
     picks. Closes once Immich has the photos; the notice that follows can undo it. -->
<script lang="ts">
	import { albumsContaining, getAlbums, type Album, type AlbumList } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { foldText, matches } from '#lib/search.js';
	import Dialog from '#lib/ui/Dialog.svelte';
	import Icon from '#lib/ui/Icon.svelte';
	import { putIntoAlbum, type AlbumTarget } from './albums.js';

	let {
		ids,
		onclose,
		ondone
	}: {
		/** The photos to put in. */
		ids: string[];
		onclose: () => void;
		/** After Immich has the photos. */
		ondone?: () => void;
	} = $props();

	let list = $state<AlbumList | null>(null);
	// Album id -> how many of the photos are in it already.
	let counts = $state<Record<string, number>>({});
	let query = $state('');
	let active = $state(0);
	let busy = $state(false);
	let error = $state('');

	$effect(() => {
		getAlbums()
			.then((result) => (list = result))
			.catch((e) => (error = errorMessage(e)));
		// Only marks: the list works without them.
		albumsContaining(ids)
			.then((result) => (counts = result.counts))
			.catch(() => (counts = {}));
	});

	const canAdd = $derived(list?.allowed.add ?? false);
	const canCreate = $derived(list?.allowed.create ?? false);
	const writable = $derived(
		(list?.albums ?? [])
			.filter((album) => album.can_change_photos)
			.sort((a, b) => b.updated_at.localeCompare(a.updated_at))
	);
	const name = $derived(query.trim());
	const shown = $derived(name ? writable.filter((a) => matches(a.name, name)) : writable);
	// A new album is offered for a name no album has yet.
	const offerNew = $derived(!!name && !writable.some((a) => foldText(a.name) === foldText(name)));
	// The rows the arrows move over: the albums, then the new one.
	const rows = $derived<AlbumTarget[]>([
		...(canAdd ? shown.map((album) => ({ album })) : []),
		...(offerNew && canCreate ? [{ name }] : [])
	]);

	$effect(() => {
		// Back to the first row whenever the list changes.
		void rows.length;
		active = 0;
	});

	async function pick(target: AlbumTarget) {
		busy = true;
		error = '';
		try {
			await putIntoAlbum(target, ids, list?.allowed.delete ?? false);
			ondone?.();
			onclose();
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	function onkeydown(event: KeyboardEvent) {
		if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && rows.length) {
			event.preventDefault();
			const step = event.key === 'ArrowDown' ? 1 : -1;
			active = (active + step + rows.length) % rows.length;
		} else if (event.key === 'Enter' && rows[active] && !busy) {
			event.preventDefault();
			pick(rows[active]);
		}
	}

	/** Whether the photos are in the album: all of them, some, or none. */
	function inAlbum(album: Album): 'all' | 'some' | null {
		const count = counts[album.id] ?? 0;
		if (!count) return null;
		return count >= ids.length ? 'all' : 'some';
	}

	function period(album: Album): string | null {
		if (!album.start_date) return null;
		const year = (date: string) => new Date(date).getUTCFullYear();
		const first = year(album.start_date);
		const last = album.end_date ? year(album.end_date) : first;
		return first === last ? String(first) : `${first}–${last}`;
	}
</script>

<Dialog title={m.album_picker_title({ count: ids.length })} icon="folder-plus" {onclose}>
	<div class="picker">
		<!-- svelte-ignore a11y_autofocus -->
		<input
			class="st-input"
			type="search"
			placeholder={canCreate ? m.album_search_or_new() : m.album_search()}
			aria-label={canCreate ? m.album_search_or_new() : m.album_search()}
			bind:value={query}
			{onkeydown}
			disabled={busy}
			autofocus
		/>

		{#if list && !canAdd}
			<p class="st-field__hint">{m.album_cannot_add({ permission: list.permissions.add })}</p>
		{/if}

		<div class="rows" role="listbox" aria-label={m.album_picker_title({ count: ids.length })}>
			{#if !list && !error}
				<p class="note">{m.album_loading()}</p>
			{/if}
			{#each rows as row, index ('album' in row ? row.album.id : 'new')}
				<button
					type="button"
					class="st-menu__item"
					role="option"
					aria-selected={index === active}
					data-active={index === active}
					disabled={busy}
					onmouseenter={() => (active = index)}
					onclick={() => pick(row)}
				>
					{#if 'album' in row}
						{@const state = inAlbum(row.album)}
						<!-- Whether the photos are in it: all (a check), some (a dash) or none (empty). -->
						<span
							class="st-check__box"
							data-state={state}
							role="img"
							aria-label={state === 'all' ? m.album_has_all() : undefined}
							aria-hidden={state === 'all' ? undefined : 'true'}
						></span>
						<span class="st-menu__label"
							>{row.album.name}{#if row.album.shared}<span class="shared" title={m.albums_shared()}
									><Icon name="users" size={12} /></span
								>{/if}</span
						>
						<span class="st-menu__hint">
							{[
								state === 'some'
									? m.album_has_some({ count: counts[row.album.id], total: ids.length })
									: period(row.album),
								m.album_photos({ count: row.album.count })
							]
								.filter(Boolean)
								.join(' · ')}
						</span>
					{:else}
						<Icon name="plus" size={16} />
						<span class="st-menu__label">{m.album_new({ name: row.name })}</span>
					{/if}
				</button>
			{/each}
			{#if list && canAdd && !rows.length}
				<p class="note">
					{name ? m.album_no_match() : writable.length ? '' : m.album_none()}
					{#if canCreate}{m.album_new_hint()}{/if}
				</p>
			{/if}
		</div>

		{#if list && offerNew && !canCreate}
			<p class="st-field__hint">{m.album_cannot_create({ permission: list.permissions.create })}</p>
		{/if}
		{#if error}<p class="st-field__error" role="alert">{error}</p>{/if}
	</div>
</Dialog>

<style>
	.picker {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		width: min(28rem, 100%);
	}
	.rows {
		display: flex;
		flex-direction: column;
		max-height: min(22rem, 55vh);
		overflow-y: auto;
	}
	.shared {
		margin-inline-start: var(--space-1-5);
		color: var(--color-text-subtle);
		vertical-align: -1px;
	}
	.note {
		margin: 0;
		padding: var(--space-2);
		color: var(--color-text-muted);
		font-size: var(--text-sm);
	}
</style>
