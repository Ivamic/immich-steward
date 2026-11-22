<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Actions on the photos chosen in the gallery (D-149), in a bar at the bottom of the window:
     their own location first (a location for all of them, the map opens; skip; "not applicable"),
     then putting them into an album (D-233), turning them in Immich (videos are left as they are),
     then the actions of the page. -->
<script lang="ts">
	import AlbumPicker from '#lib/albums/AlbumPicker.svelte';
	import { takeOutOfAlbum } from '#lib/albums/albums.js';
	import {
		getAlbums,
		rotateSelection,
		setSelectionReview,
		type Album,
		type AlbumList,
		type ReviewStatus
	} from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { shortcutKey } from '#lib/keys.js';
	import { m } from '#lib/paraglide/messages.js';
	import Icon from '#lib/ui/Icon.svelte';
	import Tooltip from '#lib/ui/Tooltip.svelte';
	import type { Snippet } from 'svelte';
	import { bulkNotices } from './bulk.svelte.js';
	import { galleryChanged, type Selection } from './selection.svelte.js';

	let {
		selection,
		onlocation,
		albumId = null,
		rotation = true,
		children
	}: {
		selection: Selection;
		onlocation: () => void;
		/** The gallery shows this album: the photos can be taken out of it. */
		albumId?: string | null;
		/** The buttons that turn the photos; off where the page turns them its own way. */
		rotation?: boolean;
		/** Actions of the page, in a group of their own at the end. */
		children?: Snippet;
	} = $props();

	let busy = $state(false);
	let picking = $state(false);
	// The album the gallery shows, when the photos can be taken out of it.
	let albums = $state<AlbumList | null>(null);
	const shownAlbum = $derived<Album | null>(
		albums?.albums.find((a) => a.id === albumId && a.can_change_photos) ?? null
	);

	$effect(() => {
		if (!albumId) return;
		getAlbums()
			.then((result) => (albums = result))
			.catch(() => (albums = null));
	});
	let error = $state<string | null>(null);
	const photos = $derived(selection.size - selection.videos);

	async function rotate(turn: 90 | 180 | 270) {
		await act(async () => {
			// Videos go too: the core counts them, and leaves them as they are.
			const jobs = await rotateSelection(selection.ids, turn);
			const images = [...selection.items.values()].filter((item) => item.type !== 'VIDEO');
			bulkNotices.followRotation(
				jobs,
				images.map((item) => item.id),
				photos
			);
		});
	}

	/** A: the chosen photos into an album, unless a field or a window has the keys. */
	function onkeydown(event: KeyboardEvent) {
		if (event.ctrlKey || event.metaKey || event.altKey || picking || busy) return;
		if ((event.target as HTMLElement).closest('input, textarea, select, dialog')) return;
		if (document.querySelector('dialog[open]')) return;
		if (shortcutKey(event) !== 'a') return;
		event.preventDefault();
		picking = true;
	}

	async function takeOut(album: Album) {
		await act(() => takeOutOfAlbum(album, selection.ids));
	}

	async function review(status: ReviewStatus) {
		await act(async () => {
			const { changed } = await setSelectionReview(selection.ids, status);
			galleryChanged();
			bulkNotices.done(
				status === 'skipped'
					? m.review_done_skipped({ count: changed })
					: m.review_done_not_applicable({ count: changed })
			);
		});
	}

	async function act(work: () => Promise<void>) {
		busy = true;
		error = null;
		try {
			await work();
			selection.clear();
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}
</script>

<svelte:window {onkeydown} />

<div class="bar" role="toolbar" aria-label={m.selection_actions()}>
	<Tooltip text={m.selection_clear()} keys="Esc">
		<button
			type="button"
			class="st-iconbtn st-iconbtn--sm"
			aria-label={m.selection_clear()}
			onclick={() => selection.clear()}
		>
			<Icon name="x" />
		</button>
	</Tooltip>
	<span class="count">
		<strong>{m.selection_count({ count: selection.size })}</strong>
		{#if selection.located}<span class="meta"
				>{m.selection_located({ count: selection.located })}</span
			>{/if}
		{#if selection.videos}<span class="meta">{m.selection_videos({ count: selection.videos })}</span
			>{/if}
	</span>

	<span class="group">
		<button
			type="button"
			class="st-btn st-btn--primary st-btn--sm"
			disabled={busy}
			onclick={onlocation}
		>
			<Icon name="map-pin" size={14} />
			{m.selection_location()}
		</button>
		<button
			type="button"
			class="st-btn st-btn--ghost st-btn--sm"
			disabled={busy}
			onclick={() => review('skipped')}
		>
			<Icon name="skip-forward" size={14} />
			{m.photo_skip()}
		</button>
		<button
			type="button"
			class="st-btn st-btn--ghost st-btn--sm"
			disabled={busy}
			onclick={() => review('not_applicable')}
		>
			<Icon name="ban" size={14} />
			{m.photo_not_applicable()}
		</button>
	</span>

	<span class="group">
		<Tooltip text={m.album_add()} keys="A">
			<button
				type="button"
				class="st-btn st-btn--ghost st-btn--sm"
				disabled={busy}
				onclick={() => (picking = true)}
			>
				<Icon name="folder-plus" size={14} />
				{m.album_add()}
			</button>
		</Tooltip>
		{#if shownAlbum && albums}
			<button
				type="button"
				class="st-btn st-btn--ghost st-btn--sm"
				disabled={busy || !albums.allowed.remove}
				title={albums.allowed.remove
					? undefined
					: m.album_cannot_remove({ permission: albums.permissions.remove })}
				onclick={() => shownAlbum && takeOut(shownAlbum)}
			>
				<Icon name="minus" size={14} />
				{m.album_remove({ album: shownAlbum.name })}
			</button>
		{/if}
	</span>

	{#if rotation}<span class="group" title={photos ? undefined : m.selection_rotate_videos_only()}>
			<Tooltip text={m.photo_turn_left()}>
				<button
					type="button"
					class="st-iconbtn st-iconbtn--sm"
					aria-label={m.photo_turn_left()}
					disabled={busy || !photos}
					onclick={() => rotate(270)}
				>
					<Icon name="rotate-ccw" />
				</button>
			</Tooltip>
			<Tooltip text={m.photo_turn_right()}>
				<button
					type="button"
					class="st-iconbtn st-iconbtn--sm"
					aria-label={m.photo_turn_right()}
					disabled={busy || !photos}
					onclick={() => rotate(90)}
				>
					<Icon name="rotate-cw" />
				</button>
			</Tooltip>
			<Tooltip text={m.selection_turn_180()}>
				<button
					type="button"
					class="st-btn st-btn--ghost st-btn--sm"
					aria-label={m.selection_turn_180()}
					disabled={busy || !photos}
					onclick={() => rotate(180)}>180°</button
				>
			</Tooltip>
		</span>{/if}

	<!-- Actions of the page: what the photos are to other photos, to their group. -->
	{#if children}
		<span class="group">{@render children()}</span>
	{/if}
	{#if error}<p class="error" role="alert">{error}</p>{/if}
</div>

{#if picking}
	<AlbumPicker
		ids={selection.ids}
		onclose={() => (picking = false)}
		ondone={() => selection.clear()}
	/>
{/if}

<style>
	.bar {
		position: fixed;
		inset-inline: 0;
		bottom: var(--space-4);
		z-index: var(--z-toast);
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: center;
		gap: var(--space-2) var(--space-3);
		width: fit-content;
		max-width: calc(100vw - 2rem);
		margin-inline: auto;
		padding: var(--space-2) var(--space-3);
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-surface);
		box-shadow: var(--shadow-lg);
		font-size: var(--text-sm);
	}
	.count {
		display: inline-flex;
		align-items: baseline;
		gap: var(--space-2);
		font-variant-numeric: tabular-nums;
	}
	.meta {
		color: var(--color-text-muted);
	}
	.group {
		display: inline-flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: center;
		gap: var(--space-1);
		max-width: 100%;
		padding-inline-start: var(--space-3);
		border-inline-start: var(--border-width) solid var(--color-border);
	}
	.error {
		flex-basis: 100%;
		margin: 0;
		text-align: center;
		color: var(--color-danger-text);
	}
</style>
