<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
	import {
		ApiError,
		getLibrary,
		isActive,
		startSimilarHints,
		startSync,
		type Library
	} from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import Icon from '#lib/ui/Icon.svelte';

	const POLL_MS = 1500;
	// The next sync times are shown relative to now.
	const CLOCK_MS = 30_000;
	const MINUTE_MS = 60_000;
	const HOUR_MS = 60 * MINUTE_MS;

	let library = $state<Library | null>(null);
	let error = $state<string | null>(null);

	const numbers = new Intl.NumberFormat(getLocale());
	const dates = new Intl.DateTimeFormat(getLocale(), { dateStyle: 'medium', timeStyle: 'short' });
	const relative = new Intl.RelativeTimeFormat(getLocale(), { numeric: 'auto' });
	const count = (n: number) => numbers.format(n);

	let now = $state(Date.now());

	/** "≈ in 12 minutes" within the hour, the date and time later; the scheduler is approximate. */
	function due(iso: string): string {
		const at = new Date(iso);
		const left = at.getTime() - now;
		if (left <= MINUTE_MS) return m.library_sync_soon();
		if (left < HOUR_MS) return `≈ ${relative.format(Math.ceil(left / MINUTE_MS), 'minute')}`;
		return dates.format(at);
	}

	const job = $derived(library?.sync_job ?? null);
	const syncing = $derived(isActive(job));
	// The badge "similar with a location" of the gallery, computed in the background.
	const hintsJob = $derived(library?.similar_hints_job ?? null);
	const hinting = $derived(isActive(hintsJob));

	async function load() {
		try {
			library = await getLibrary();
			error = null;
		} catch (e) {
			error = errorMessage(e);
		}
	}

	async function refreshHints() {
		try {
			await startSimilarHints();
			await load();
		} catch (e) {
			error = errorMessage(e);
		}
	}

	async function sync(full: boolean | null) {
		try {
			await startSync(full);
			await load();
		} catch (e) {
			error = errorMessage(e);
		}
	}

	$effect(() => {
		load();
	});

	$effect(() => {
		const timer = setInterval(() => {
			now = Date.now();
			// A sync that is due starts within a minute: pick it up.
			if (!syncing && library?.next_sync_at && new Date(library.next_sync_at).getTime() <= now)
				load();
		}, CLOCK_MS);
		return () => clearInterval(timer);
	});

	// Poll while a sync or a pass of the badge is queued or running.
	$effect(() => {
		if (!syncing && !hinting) return;
		const timer = setInterval(load, POLL_MS);
		return () => clearInterval(timer);
	});
</script>

<section>
	<h1>{m.library_heading()}</h1>

	{#if library}
		<dl class="st-mcard__stats">
			<div class="st-stat">
				<dt class="st-stat__label">{m.library_assets()}</dt>
				<dd class="st-stat__value">{count(library.assets)}</dd>
				<dd class="sub">{m.library_videos({ count: count(library.videos) })}</dd>
			</div>
			<div class="st-stat">
				<dt class="st-stat__label">{m.library_without_gps()}</dt>
				<dd class="st-stat__value">{count(library.without_gps)}</dd>
			</div>
			<div class="st-stat">
				<dt class="st-stat__label">{m.library_with_gps()}</dt>
				<dd class="st-stat__value">{count(library.with_gps)}</dd>
			</div>
			<div class="st-stat">
				<dt class="st-stat__label">{m.library_albums()}</dt>
				<dd class="st-stat__value">{count(library.albums)}</dd>
			</div>
		</dl>

		<dl class="sync">
			<dt>{m.library_synced_at()}</dt>
			<dd>
				{library.synced_at ? dates.format(new Date(library.synced_at)) : m.library_never_synced()}
			</dd>
			<dt>{m.library_next_sync()}</dt>
			<dd>
				{#if library.next_sync_at}
					{due(library.next_sync_at)}
					{#if library.next_full_sync_at}
						· {m.library_next_full_sync({ when: due(library.next_full_sync_at) })}
					{/if}
				{:else}
					{m.library_auto_sync_off()}
				{/if}
			</dd>
			<dt>{m.library_similar_hints()}</dt>
			<dd>
				{#if hinting}
					{@const progress = hintsJob?.progress ?? {}}
					{m.library_similar_hints_running({
						done: count(Number(progress.done ?? 0)),
						total: count(Number(progress.total ?? 0))
					})}
				{:else if library.similar_hints_at}
					{dates.format(new Date(library.similar_hints_at))}
				{:else}
					{m.library_similar_hints_never()}
				{/if}
			</dd>
		</dl>

		{#if syncing}
			<div class="st-progress st-progress--indeterminate" role="status">
				<div class="st-progress__row">
					{m.library_syncing({ count: count(Number(job?.progress.assets ?? 0)) })}
				</div>
				<div class="st-progress__track"><div class="st-progress__bar"></div></div>
			</div>
		{:else if job?.status === 'failed'}
			<p class="error" role="alert">
				{m.library_sync_failed({ reason: errorMessage(new ApiError(0, job.error ?? '')) })}
			</p>
		{/if}

		<div class="buttons">
			<button type="button" class="st-btn" onclick={() => sync(null)} disabled={syncing}>
				<Icon name="refresh-cw" />
				{m.library_sync()}
			</button>
			<button
				type="button"
				class="st-btn st-btn--ghost"
				onclick={() => sync(true)}
				disabled={syncing}
			>
				{m.library_sync_full()}
			</button>
			<button
				type="button"
				class="st-btn st-btn--ghost"
				title={m.library_similar_hints_hint()}
				onclick={refreshHints}
				disabled={hinting}
			>
				{m.library_similar_hints_refresh()}
			</button>
		</div>
	{/if}

	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
</section>

<style>
	section {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		margin-bottom: var(--space-10);
	}
	h1 {
		margin: 0;
	}
	dl,
	dd {
		margin: 0;
	}
	.sub {
		font-size: var(--text-xs);
		color: var(--color-text-muted);
	}
	.sync {
		display: grid;
		grid-template-columns: max-content minmax(0, 1fr);
		gap: var(--space-1) var(--space-4);
		font-size: var(--text-sm);
	}
	.sync dt {
		color: var(--color-text-muted);
	}
	.buttons {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}
	.error {
		margin: 0;
		color: var(--color-danger-text);
	}
</style>
