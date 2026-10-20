<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Workers known to the core and the progress of module runs on this library. -->
<script lang="ts">
	import { resolve } from '$app/paths';
	import { getWorkers, rerunFailed, type WorkersOverview } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { failedFilter, filterToUrl } from '#lib/gallery/filter.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import { failureReason, moduleName } from '#lib/suggestions/format.js';

	const REFRESH_MS = 10_000;

	let overview = $state<WorkersOverview | null>(null);
	let error = $state<string | null>(null);
	// "module:code" of the rerun in progress, and the outcome of the last one.
	let rerunning = $state<string | null>(null);
	let rerunNotice = $state<string | null>(null);

	const load = () =>
		getWorkers()
			.then((result) => {
				overview = result;
				error = null;
			})
			.catch((e) => (error = errorMessage(e)));

	$effect(() => {
		load();
		const timer = setInterval(load, REFRESH_MS);
		return () => clearInterval(timer);
	});

	async function rerun(module: string, code: string) {
		rerunning = `${module}:${code}`;
		rerunNotice = null;
		try {
			const { queued } = await rerunFailed(module, code);
			rerunNotice = m.workers_failures_rerun_done({ count: String(queued) });
			await load();
		} catch (e) {
			error = errorMessage(e);
		} finally {
			rerunning = null;
		}
	}

	// Most frequent reason first.
	const reasons = (counts: Record<string, number>) =>
		Object.entries(counts).sort(([, a], [, b]) => b - a);

	const relative = new Intl.RelativeTimeFormat(getLocale(), { numeric: 'auto' });

	function ago(iso: string): string {
		const minutes = Math.round((new Date(iso).getTime() - Date.now()) / 60_000);
		if (Math.abs(minutes) < 60) return relative.format(minutes, 'minute');
		const hours = Math.round(minutes / 60);
		if (Math.abs(hours) < 48) return relative.format(hours, 'hour');
		return relative.format(Math.round(hours / 24), 'day');
	}
</script>

<section>
	<h2>{m.workers_heading()}</h2>
	<p class="muted">{m.workers_intro()}</p>
	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
	{#if overview}
		{#if overview.workers.length}
			<ul class="workers">
				{#each overview.workers as worker (worker.name)}
					<li>
						<strong>{worker.name}</strong>
						<span class="device">{worker.device}</span>
						{worker.modules.map(moduleName).join(', ')}
						<span class:active={worker.active} class="muted">
							· {worker.active
								? m.workers_active()
								: m.workers_seen({ when: ago(worker.last_seen_at) })}
						</span>
					</li>
				{/each}
			</ul>
		{:else}
			<p>{m.workers_none()}</p>
		{/if}

		{#each Object.entries(overview.runs) as [module, counts] (module)}
			<p>
				{m.workers_runs({
					module: moduleName(module),
					done: String(counts.done ?? 0),
					queued: String(counts.queued ?? 0),
					running: String(counts.running ?? 0),
					failed: String(counts.failed ?? 0)
				})}
			</p>
			{@const failures = overview.failures[module]}
			{#if failures && Object.keys(failures).length}
				<div class="failures">
					<h3>{m.workers_failures_heading()}</h3>
					<ul>
						{#each reasons(failures) as [code, count] (code)}
							<li>
								<span>{failureReason(code)} — {count}</span>
								<a href={resolve(`/${filterToUrl(failedFilter(module, code))}`)}>
									{m.workers_failures_show()}
								</a>
								<button
									type="button"
									disabled={rerunning !== null}
									onclick={() => rerun(module, code)}
								>
									{m.workers_failures_rerun()}
								</button>
							</li>
						{/each}
					</ul>
					{#if rerunNotice}
						<p class="muted" role="status">{rerunNotice}</p>
					{/if}
				</div>
			{/if}
		{/each}
		<p class="muted">
			{overview.auto_modules.length
				? m.workers_auto({ modules: overview.auto_modules.map(moduleName).join(', ') })
				: m.workers_auto_off()}
		</p>
	{/if}
</section>

<style>
	.workers {
		list-style: none;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}
	.device {
		display: inline-block;
		padding: 0 0.35rem;
		border-radius: 0.25rem;
		background: rgb(127 127 127 / 0.15);
		font-size: 0.8rem;
		text-transform: uppercase;
	}
	.failures h3 {
		margin: 0.5rem 0 0.25rem;
		font-size: 0.95rem;
	}
	.failures ul {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}
	.failures li {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 0.75rem;
	}
	.active {
		color: #1a7f37;
		opacity: 1;
	}
	.muted {
		opacity: 0.7;
	}
	.error {
		color: #cf222e;
	}
</style>
