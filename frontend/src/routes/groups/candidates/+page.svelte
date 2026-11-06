<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Photos that may show no sign of a place (A1.3, D-200), for the user to mark: found by a
     description through the smart search of Immich, or alike photos that lie far apart. Nothing is
     marked until the user chooses; the choice works as in the gallery. -->
<script lang="ts">
	import {
		getDescribedCandidates,
		getScatteredCandidates,
		markPhotos,
		thumbnailUrl,
		type AssetItem
	} from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { bulkNotices } from '#lib/gallery/bulk.svelte.js';
	import SelectionBar from '#lib/gallery/SelectionBar.svelte';
	import SelectionLocation from '#lib/gallery/SelectionLocation.svelte';
	import { galleryChanged, Selection } from '#lib/gallery/selection.svelte.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import EmptyState from '#lib/ui/EmptyState.svelte';
	import Icon from '#lib/ui/Icon.svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';

	type Tab = 'described' | 'scattered';

	/** Ready descriptions: sent in English, which every model of Immich understands. */
	const PRESETS: { query: string; label: () => string }[] = [
		{ query: 'a document or a page of text', label: m.candidates_preset_document },
		{ query: 'a screenshot of a phone or computer screen', label: m.candidates_preset_screenshot },
		{ query: 'a receipt or a ticket', label: m.candidates_preset_receipt },
		{ query: 'a close-up photo of a dog', label: m.candidates_preset_dog },
		{ query: 'a close-up photo of a cat', label: m.candidates_preset_cat },
		{ query: 'food on a plate', label: m.candidates_preset_food },
		{ query: 'a whiteboard or a presentation slide', label: m.candidates_preset_slide },
		{ query: 'a close-up photo of a flower', label: m.candidates_preset_flower }
	];

	const tab = $derived<Tab>(
		page.url.searchParams.get('tab') === 'scattered' ? 'scattered' : 'described'
	);
	let text = $state('');
	// The description searched last: a ready one (by its English text) or the user's own.
	let asked = $state<string | null>(null);
	let photos = $state.raw<AssetItem[] | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let busy = $state(false);
	let locationOpen = $state(false);
	const selection = new Selection();
	const chosenIds = $derived(new Set(selection.ids));
	// Only the answer to the last request counts.
	let latest = 0;

	async function load(work: () => Promise<{ photos: AssetItem[] }>) {
		const mine = ++latest;
		loading = true;
		error = null;
		selection.clear();
		try {
			const answer = await work();
			if (mine === latest) photos = answer.photos;
		} catch (e) {
			if (mine === latest) {
				photos = null;
				error = errorMessage(e);
			}
		} finally {
			if (mine === latest) loading = false;
		}
	}

	function searchPreset(query: string) {
		asked = query;
		load(() => getDescribedCandidates(query));
	}

	function searchOwn(event: SubmitEvent) {
		event.preventDefault();
		const query = text.trim();
		if (!query) return;
		asked = query;
		load(() => getDescribedCandidates(query, getLocale()));
	}

	function choose(next: Tab) {
		photos = null;
		asked = null;
		error = null;
		selection.clear();
		goto(
			resolve(next === 'described' ? '/groups/candidates' : '/groups/candidates?tab=scattered'),
			{
				replace: true,
				reset: false
			}
		);
	}

	$effect(() => {
		if (tab === 'scattered') load(getScatteredCandidates);
	});

	/** Marks the chosen photos: they leave the list, the suggestions and the groups. */
	async function mark() {
		busy = true;
		try {
			const ids = selection.ids;
			await markPhotos(ids);
			const gone = new Set(ids);
			photos = (photos ?? []).filter((photo) => !gone.has(photo.id));
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
		if (event.shiftKey && selection.anchor && photos) {
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
</script>

<svelte:window {onkeydown} />

<a class="st-btn st-btn--ghost st-btn--sm back" href={resolve('/groups?view=trash')}>
	<Icon name="arrow-left" size={14} />
	{m.groups_view_trash()}
</a>

<h1>{m.candidates_title()}</h1>
<p class="muted">{m.candidates_intro()}</p>

<div class="views">
	{#each [{ id: 'described', label: m.candidates_tab_described }, { id: 'scattered', label: m.candidates_tab_scattered }] as item (item.id)}
		<button
			type="button"
			class="st-btn st-btn--sm"
			class:st-btn--secondary={item.id === tab}
			class:st-btn--ghost={item.id !== tab}
			aria-pressed={item.id === tab}
			onclick={() => choose(item.id as Tab)}
		>
			{item.label()}
		</button>
	{/each}
	<a class="st-btn st-btn--ghost st-btn--sm" href={resolve('/groups?view=spread')}>
		<Icon name="route" size={14} />
		{m.candidates_groups_link()}
	</a>
</div>

{#if tab === 'described'}
	<p class="muted">{m.candidates_described_hint()}</p>
	<div class="presets">
		{#each PRESETS as preset (preset.query)}
			<button
				type="button"
				class="st-btn st-btn--sm"
				class:st-btn--secondary={asked === preset.query}
				class:st-btn--ghost={asked !== preset.query}
				aria-pressed={asked === preset.query}
				disabled={loading}
				onclick={() => searchPreset(preset.query)}
			>
				{preset.label()}
			</button>
		{/each}
	</div>
	<form class="own" onsubmit={searchOwn}>
		<span class="st-input st-input--sm">
			<input
				type="search"
				maxlength="200"
				placeholder={m.candidates_query_placeholder()}
				aria-label={m.candidates_query_placeholder()}
				bind:value={text}
			/>
		</span>
		<button
			type="submit"
			class="st-btn st-btn--secondary st-btn--sm"
			disabled={loading || !text.trim()}
		>
			<Icon name="search" size={14} />
			{m.candidates_search()}
		</button>
	</form>
{:else}
	<p class="muted">{m.candidates_scattered_hint()}</p>
{/if}

{#if error}
	<p class="bad" role="alert">{error}</p>
{/if}

{#if loading}
	<p class="muted" role="status">
		<span class="st-spin"><Icon name="loader-circle" size={14} /></span>
		{m.candidates_searching()}
	</p>
{:else if photos}
	{#if photos.length}
		<div class="found">
			<span class="muted">{m.candidates_found({ count: photos.length })}</span>
			<button
				type="button"
				class="st-btn st-btn--ghost st-btn--sm"
				onclick={() => selection.setAll(photos ?? [], true)}
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
						onclick={(event) => clickTile(event, photo)}
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
	{:else}
		<EmptyState icon="images" title={m.candidates_none()} text={m.candidates_none_text()} />
	{/if}
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
		onsaved={() => {
			locationOpen = false;
			selection.clear();
		}}
		onclose={() => (locationOpen = false)}
	/>
{/if}

<style>
	h1 {
		margin: var(--space-3) 0 var(--space-2);
	}
	.back {
		margin-top: var(--space-1);
	}
	.muted {
		margin: 0 0 var(--space-3);
		color: var(--color-text-muted);
	}
	.bad {
		color: var(--color-danger-text);
	}
	.views,
	.presets,
	.found {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2);
		margin-bottom: var(--space-4);
	}
	.presets {
		margin-bottom: var(--space-2);
	}
	.own {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		margin-bottom: var(--space-4);
	}
	.own .st-input {
		flex: 1 1 16rem;
		max-width: 32rem;
	}
	.found .muted {
		margin: 0;
	}
	/* Room for the bar of the chosen photos at the bottom. */
	.st-tile-grid {
		margin-bottom: var(--space-16);
	}
</style>
