<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
	import { ApiError, getLibrary, isActive, startSync, type Library } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';

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

	async function load() {
		try {
			library = await getLibrary();
			error = null;
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

	// Poll while a sync is queued or running.
	$effect(() => {
		if (!syncing) return;
		const timer = setInterval(load, POLL_MS);
		return () => clearInterval(timer);
	});
</script>

<section>
	<h1>{m.library_heading()}</h1>

	{#if library}
		<dl>
			<dt>{m.library_assets()}</dt>
			<dd>{count(library.assets)} ({m.library_videos({ count: count(library.videos) })})</dd>
			<dt>{m.library_without_gps()}</dt>
			<dd><strong>{count(library.without_gps)}</strong></dd>
			<dt>{m.library_with_gps()}</dt>
			<dd>{count(library.with_gps)}</dd>
			<dt>{m.library_albums()}</dt>
			<dd>{count(library.albums)}</dd>
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
		</dl>

		{#if syncing}
			<p role="status">
				{m.library_syncing({ count: count(Number(job?.progress.assets ?? 0)) })}
			</p>
		{:else if job?.status === 'failed'}
			<p class="error" role="alert">
				{m.library_sync_failed({ reason: errorMessage(new ApiError(0, job.error ?? '')) })}
			</p>
		{/if}

		<div class="buttons">
			<button type="button" onclick={() => sync(null)} disabled={syncing}>
				{m.library_sync()}
			</button>
			<button type="button" onclick={() => sync(true)} disabled={syncing}>
				{m.library_sync_full()}
			</button>
		</div>
	{/if}

	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
</section>

<style>
	dl {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 0.5rem 1.5rem;
	}
	dt {
		font-weight: 600;
	}
	dd {
		margin: 0;
	}
	.buttons {
		display: flex;
		gap: 0.75rem;
	}
	.error {
		color: #cf222e;
	}
	section {
		margin-bottom: 2.5rem;
	}
</style>
