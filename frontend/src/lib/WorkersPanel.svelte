<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Workers known to the core, and a block per worker module: its pause, the workers running
     it, the progress of its runs on this library and its failures. -->
<script lang="ts">
	import { resolve } from '$app/paths';
	import {
		getWorkers,
		rerunFailed,
		type ModuleStatus,
		type WorkerInfo,
		type WorkersOverview
	} from '#lib/api.js';
	import { pause } from '#lib/pause.svelte.js';
	import { errorMessage } from '#lib/errors.js';
	import { failedFilter, filterToUrl } from '#lib/gallery/filter.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import { failureReason, moduleName } from '#lib/suggestions/format.js';

	const REFRESH_MS = 10_000;
	// Run statuses in the order the counters and the progress bar show them.
	const STATUSES: ModuleStatus[] = ['done', 'running', 'queued', 'failed'];

	let overview = $state<WorkersOverview | null>(null);
	let error = $state<string | null>(null);
	// "module:code" of the rerun in progress, and the outcome of the last one (per module).
	let rerunning = $state<string | null>(null);
	let rerunNotice = $state<{ module: string; text: string } | null>(null);
	let pausing = $state(false);

	const load = () =>
		getWorkers()
			.then((result) => {
				overview = result;
				pause.update(result.pause);
				error = null;
			})
			.catch((e) => (error = errorMessage(e)));

	$effect(() => {
		load();
		const timer = setInterval(load, REFRESH_MS);
		return () => clearInterval(timer);
	});

	async function togglePause(module: string | null, paused: boolean) {
		pausing = true;
		try {
			await pause.set(module, paused);
			error = null;
		} catch (e) {
			error = errorMessage(e);
		} finally {
			pausing = false;
		}
	}

	async function rerun(module: string, code: string) {
		rerunning = `${module}:${code}`;
		rerunNotice = null;
		try {
			const { queued } = await rerunFailed(module, code);
			rerunNotice = { module, text: m.workers_failures_rerun_done({ count: String(queued) }) };
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

	const total = (counts: Partial<Record<ModuleStatus, number>>) =>
		STATUSES.reduce((sum, status) => sum + (counts[status] ?? 0), 0);

	function statusLabel(status: ModuleStatus): string {
		switch (status) {
			case 'done':
				return m.module_card_done();
			case 'running':
				return m.module_card_running();
			case 'queued':
				return m.module_card_queued();
			default:
				return m.module_card_failed();
		}
	}

	const number = new Intl.NumberFormat(getLocale());
	const relative = new Intl.RelativeTimeFormat(getLocale(), { numeric: 'auto' });
	const seconds = new Intl.NumberFormat(getLocale(), { style: 'unit', unit: 'second' });
	const minutes = new Intl.NumberFormat(getLocale(), { style: 'unit', unit: 'minute' });

	/** How long the worker has been in its state, e.g. "40 s" or "3 min". */
	function lasting(iso: string): string {
		const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
		return s < 120 ? seconds.format(s) : minutes.format(Math.round(s / 60));
	}

	function stateText(worker: WorkerInfo): string | null {
		const module = moduleName(worker.state_module ?? '');
		const time = worker.state_since ? lasting(worker.state_since) : '';
		switch (worker.state) {
			case 'idle':
				return m.worker_state_idle();
			case 'busy':
				return m.worker_state_busy();
			case 'downloading':
				return m.worker_state_downloading({ module, time });
			case 'loading':
				return m.worker_state_loading({ module, time });
			case 'working':
				return m.worker_state_working({ module });
			default:
				return null;
		}
	}

	const slow = (worker: WorkerInfo) => worker.state === 'downloading' || worker.state === 'loading';

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
						<span class="muted">{worker.modules.map(moduleName).join(', ')}</span>
						<span class:active={worker.active} class="muted">
							· {worker.active
								? m.workers_active()
								: m.workers_seen({ when: ago(worker.last_seen_at) })}
						</span>
						{#if stateText(worker)}
							<span class="state" class:slow={slow(worker)}>· {stateText(worker)}</span>
						{/if}
					</li>
				{/each}
			</ul>
		{:else}
			<p>{m.workers_none()}</p>
		{/if}

		<div class="pause-all" class:on={pause.all}>
			<button
				type="button"
				aria-pressed={pause.all}
				disabled={pausing}
				onclick={() => togglePause(null, !pause.all)}
			>
				{pause.all ? m.workers_resume_all() : m.workers_pause_all()}
			</button>
			<span class="muted">{m.workers_pause_hint()}</span>
		</div>

		<div class="modules">
			{#each overview.modules as module (module.id)}
				{@const counts = overview.runs[module.id] ?? {}}
				{@const sum = total(counts)}
				{@const paused = pause.isPaused(module.id)}
				{@const runners = overview.workers.filter((w) => w.active && w.modules.includes(module.id))}
				{@const index = overview.index[module.id]}
				{@const failures = overview.failures[module.id]}
				<article class="module" class:paused>
					<header>
						<span class="swatch shape-{module.shape}" style:background={module.color}></span>
						<h3>{moduleName(module.id)}</h3>
						{#if paused}
							<span class="badge paused-badge">
								{pause.all ? m.module_card_paused_all() : m.module_card_paused()}
							</span>
						{/if}
						<span class="badge">
							{overview.auto_modules.includes(module.id)
								? m.module_card_auto()
								: m.module_card_manual()}
						</span>
						<span class="spacer"></span>
						{#if !pause.all}
							<button
								type="button"
								aria-pressed={paused}
								disabled={pausing}
								onclick={() => togglePause(module.id, !paused)}
							>
								{paused ? m.workers_resume() : m.workers_pause()}
							</button>
						{/if}
					</header>

					{#if runners.length}
						<ul class="runners">
							{#each runners as worker (worker.name)}
								<li>
									<strong>{worker.name}</strong>
									<span class="device">{worker.device}</span>
									{#if stateText(worker)}
										<span class="state" class:slow={slow(worker)}>{stateText(worker)}</span>
									{/if}
								</li>
							{/each}
						</ul>
					{:else}
						<p class="warning">{m.module_card_no_worker()}</p>
					{/if}

					{#if sum}
						<div class="progress" aria-hidden="true">
							{#each STATUSES as status (status)}
								{#if counts[status]}
									<span class="bar-{status}" style:flex-grow={counts[status]}></span>
								{/if}
							{/each}
						</div>
					{/if}
					<dl class="stats">
						{#each STATUSES as status (status)}
							<div class="stat stat-{status}">
								<dt>{statusLabel(status)}</dt>
								<dd>{number.format(counts[status] ?? 0)}</dd>
							</div>
						{/each}
					</dl>

					{#if index}
						<p class="muted">
							{m.workers_index({
								indexed: number.format(index.indexed),
								located: number.format(index.located)
							})}
						</p>
					{/if}

					{#if failures && Object.keys(failures).length}
						<div class="failures">
							<h4>{m.workers_failures_heading()}</h4>
							<ul>
								{#each reasons(failures) as [code, count] (code)}
									<li>
										<span>{failureReason(code)} — {number.format(count)}</span>
										<span class="actions">
											<a href={resolve(`/${filterToUrl(failedFilter(module.id, code))}`)}>
												{m.workers_failures_show()}
											</a>
											<button
												type="button"
												disabled={rerunning !== null}
												onclick={() => rerun(module.id, code)}
											>
												{m.workers_failures_rerun()}
											</button>
										</span>
									</li>
								{/each}
							</ul>
							{#if rerunNotice?.module === module.id}
								<p class="muted" role="status">{rerunNotice.text}</p>
							{/if}
						</div>
					{/if}
				</article>
			{/each}
		</div>
	{/if}
</section>

<style>
	section {
		margin-bottom: 2.5rem;
	}
	.workers,
	.runners,
	.failures ul {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}
	.workers {
		margin-bottom: 1rem;
	}
	.device {
		display: inline-block;
		padding: 0 0.35rem;
		border-radius: 0.25rem;
		background: rgb(127 127 127 / 0.15);
		font-size: 0.8rem;
		text-transform: uppercase;
	}
	.pause-all {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem 0.75rem;
		margin-bottom: 1rem;
		padding: 0.5rem 0.75rem;
		border-radius: 0.4rem;
		background: rgb(127 127 127 / 0.08);
	}
	.pause-all.on {
		background: rgb(191 135 0 / 0.15);
	}
	.pause-all .muted {
		flex: 1 1 16rem;
		font-size: 0.9rem;
	}
	.modules {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
	.module {
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
		padding: 0.9rem 1rem;
		border: 1px solid rgb(127 127 127 / 0.3);
		border-radius: 0.5rem;
	}
	.module.paused {
		border-color: #bf8700;
	}
	.module header {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
	}
	.module h3 {
		margin: 0;
		font-size: 1.05rem;
	}
	.spacer {
		flex: 1;
	}
	.swatch {
		width: 0.85rem;
		height: 0.85rem;
		flex: none;
	}
	.shape-circle {
		border-radius: 50%;
	}
	.shape-diamond {
		transform: rotate(45deg) scale(0.85);
	}
	.badge {
		padding: 0.05rem 0.45rem;
		border-radius: 1rem;
		background: rgb(127 127 127 / 0.15);
		font-size: 0.8rem;
	}
	.paused-badge {
		background: rgb(191 135 0 / 0.2);
	}
	.runners li {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 0.5rem;
		font-size: 0.95rem;
	}
	.progress {
		display: flex;
		height: 0.4rem;
		overflow: hidden;
		border-radius: 0.2rem;
		background: rgb(127 127 127 / 0.15);
	}
	.bar-done {
		background: #1a7f37;
	}
	.bar-running {
		background: #0969da;
	}
	.bar-queued {
		background: rgb(127 127 127 / 0.45);
	}
	.bar-failed {
		background: #cf222e;
	}
	.stats {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1.5rem;
		margin: 0;
	}
	.stat dt {
		font-size: 0.8rem;
		opacity: 0.7;
	}
	.stat dd {
		margin: 0;
		font-size: 1.1rem;
		font-variant-numeric: tabular-nums;
	}
	.stat-failed dd {
		color: #cf222e;
	}
	.failures h4 {
		margin: 0.25rem 0;
		font-size: 0.95rem;
	}
	.failures li {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 0.75rem;
	}
	/* The link and the button stay together when the reason is long. */
	.failures .actions {
		display: inline-flex;
		align-items: baseline;
		gap: 0.75rem;
		white-space: nowrap;
	}
	.active {
		color: #1a7f37;
		opacity: 1;
	}
	.state.slow {
		color: #9a6700;
	}
	.muted {
		opacity: 0.7;
	}
	.warning {
		margin: 0;
		color: #9a6700;
	}
	.error {
		color: #cf222e;
	}
	p {
		margin: 0;
	}
	@media (prefers-color-scheme: dark) {
		.state.slow,
		.warning {
			color: #d29922;
		}
	}
</style>
