<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Actions on the photos chosen in the gallery (D-149), in a bar at the bottom of the window:
     a location for all of them (the map opens), turning them in Immich (videos are left as they
     are), skip or "not applicable". -->
<script lang="ts">
	import { rotateSelection, setSelectionReview, type ReviewStatus } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import Icon from '#lib/ui/Icon.svelte';
	import Tooltip from '#lib/ui/Tooltip.svelte';
	import { bulkNotices } from './bulk.svelte.js';
	import { galleryChanged, type Selection } from './selection.svelte.js';

	let { selection, onlocation }: { selection: Selection; onlocation: () => void } = $props();

	let busy = $state(false);
	let error = $state<string | null>(null);
	const photos = $derived(selection.size - selection.videos);

	async function rotate(turn: 90 | 180 | 270) {
		await act(async () => {
			// Videos go too: the core counts them, and leaves them as they are.
			const job = await rotateSelection(selection.ids, turn);
			const images = [...selection.items.values()].filter((item) => item.type !== 'VIDEO');
			bulkNotices.followRotation(
				job,
				images.map((item) => item.id),
				photos
			);
		});
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
	</span>

	<span class="group" title={photos ? undefined : m.selection_rotate_videos_only()}>
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
	</span>

	<span class="group">
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
	{#if error}<p class="error" role="alert">{error}</p>{/if}
</div>

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
		align-items: center;
		gap: var(--space-1);
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
