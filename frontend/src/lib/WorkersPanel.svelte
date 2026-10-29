<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Workers known to the core, and a block per worker module: its pause, the workers running
     it, the progress of its runs on this library and its failures. -->
<script lang="ts">
	import { resolve } from '$app/paths';
	import {
		forgetWorker,
		switchWorkerModule,
		getWorkers,
		rerunFailed,
		type ModuleStatus,
		type WorkerInfo,
		type WorkersOverview
	} from '#lib/api.js';
	import PauseMenu from '#lib/PauseMenu.svelte';
	import StatusBadge from '#lib/ui/StatusBadge.svelte';
	import Tooltip from '#lib/ui/Tooltip.svelte';
	import AddDeviceDialog from '#lib/AddDeviceDialog.svelte';
	import Icon from '#lib/ui/Icon.svelte';
	import { formatUntil, pause } from '#lib/pause.svelte.js';
	import { errorMessage } from '#lib/errors.js';
	import { failedFilter, filterToUrl } from '#lib/gallery/filter.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import { moduleColor } from '#lib/map/modulePalette.js';
	import { older } from '#lib/versions.js';
	import {
		failureGroup,
		failureGroupName,
		failureReason,
		moduleName
	} from '#lib/suggestions/format.js';

	const REFRESH_MS = 10_000;
	const WORKERS_DOCS = 'https://github.com/Ivamic/immich-steward/blob/main/docs/workers.md';
	// Run statuses in the order the counters and the progress bar show them.
	const STATUSES: ModuleStatus[] = ['done', 'running', 'queued', 'failed'];

	let overview = $state<WorkersOverview | null>(null);
	let error = $state<string | null>(null);
	// "module:code" of the rerun in progress, and the outcome of the last one (per module).
	let rerunning = $state<string | null>(null);
	let rerunNotice = $state<{ module: string; text: string } | null>(null);
	let pausing = $state(false);
	let forgetting = $state<string | null>(null);

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

	async function togglePause(
		module: string | null,
		paused: boolean,
		minutes: number | null = null
	) {
		pausing = true;
		try {
			await pause.set(module, paused, minutes);
			error = null;
		} catch (e) {
			error = errorMessage(e);
		} finally {
			pausing = false;
		}
	}

	let adding = $state(false);
	// "worker:module" of the switch being saved.
	let switching = $state<string | null>(null);

	async function switchModule(worker: WorkerInfo, module: string, enabled: boolean) {
		switching = `${worker.id}:${module}`;
		try {
			await switchWorkerModule(worker.id, module, enabled);
			await load();
		} catch (e) {
			error = errorMessage(e);
		} finally {
			switching = null;
		}
	}

	async function forget(id: string) {
		forgetting = id;
		try {
			await forgetWorker(id);
			await load();
		} catch (e) {
			error = errorMessage(e);
		} finally {
			forgetting = null;
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
	<div class="heading">
		<h2>{m.workers_heading()}</h2>
		<button type="button" class="st-btn st-btn--sm" onclick={() => (adding = true)}>
			<Icon name="plus" size={14} />
			{m.add_device()}
		</button>
	</div>
	<p class="muted">{m.workers_intro()}</p>
	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
	{#if overview}
		{#if overview.workers.length || overview.refused.length}
			<div class="workers">
				{#each overview.refused as refused (refused.name)}
					<article class="worker">
						<header>
							<h3>{refused.name}</h3>
							<span class="muted">{refused.version}</span>
							<span class="spacer"></span>
							<StatusBadge tone="warning">{m.workers_refused()}</StatusBadge>
						</header>
						<p>
							{refused.reason === 'worker_too_old'
								? m.workers_refused_worker_too_old({ core: overview.core_version })
								: m.workers_refused_core_too_old()}
							<a href={WORKERS_DOCS} target="_blank" rel="noreferrer">{m.workers_update_how()}</a>
						</p>
					</article>
				{/each}
				{#each overview.workers as worker (worker.id)}
					<article class="worker" class:gone={!worker.active}>
						<header>
							<h3>{worker.name}</h3>
							<span class="device">{worker.device}</span>
							<span class="muted">{worker.version}</span>
							{#if worker.active && older(worker.version, overview.core_version)}
								<a
									class="update"
									href={WORKERS_DOCS}
									target="_blank"
									rel="noreferrer"
									title={m.workers_update_hint()}
								>
									{m.workers_update_available({ version: overview.core_version })}
								</a>
							{/if}
							<span class="spacer"></span>
							{#if worker.active}
								<StatusBadge tone="success" dot>{m.workers_active()}</StatusBadge>
							{:else}
								<StatusBadge outline
									>{m.workers_seen({ when: ago(worker.last_seen_at) })}</StatusBadge
								>
								<button
									type="button"
									class="st-btn st-btn--ghost st-btn--sm"
									title={m.workers_forget_hint()}
									disabled={forgetting !== null}
									onclick={() => forget(worker.id)}
								>
									{m.workers_forget()}
								</button>
							{/if}
						</header>
						{#if worker.active && stateText(worker)}
							<p class="state">
								<StatusBadge
									tone={slow(worker)
										? 'warning'
										: worker.state === 'working'
											? 'accent'
											: 'neutral'}
									live={worker.state === 'working' || slow(worker)}
								>
									{stateText(worker)}
								</StatusBadge>
							</p>
						{/if}
						<div class="worker-modules" role="group" aria-label={m.workers_modules_label()}>
							<span class="muted">{m.workers_modules_label()}</span>
							{#each worker.modules as module (module)}
								{@const enabled = !worker.disabled_modules.includes(module)}
								<Tooltip text={enabled ? m.workers_module_on_hint() : m.workers_module_off_hint()}>
									<button
										type="button"
										class="st-chip"
										aria-pressed={enabled}
										disabled={switching !== null}
										onclick={() => switchModule(worker, module, !enabled)}
									>
										<span class="st-chip__dot" style:background={moduleColor(module, '')}></span>
										{moduleName(module)}
									</button>
								</Tooltip>
							{/each}
						</div>
					</article>
				{/each}
			</div>
		{:else}
			<p>{m.workers_none()}</p>
		{/if}

		<div class="pause-all" class:on={pause.all}>
			<PauseMenu
				paused={pause.all}
				disabled={pausing}
				pauseLabel={m.workers_pause_all()}
				resumeLabel={m.workers_resume_all()}
				onpause={(minutes) => togglePause(null, true, minutes)}
				onresume={() => togglePause(null, false)}
			/>
			{#if pause.all && pause.allUntil}
				<strong>{m.pause_until({ time: formatUntil(pause.allUntil) })}</strong>
			{/if}
			<span class="muted">{m.workers_pause_hint()}</span>
		</div>

		<div class="modules">
			{#each overview.modules as module (module.id)}
				{@const counts = overview.runs[module.id] ?? {}}
				{@const sum = total(counts)}
				{@const paused = pause.isPaused(module.id)}
				{@const runners = overview.workers.filter(
					(w) =>
						w.active && w.modules.includes(module.id) && !w.disabled_modules.includes(module.id)
				)}
				{@const index = overview.index[module.id]}
				{@const failures = overview.failures[module.id]}
				<article class="module" class:paused>
					<header>
						<span
							class="swatch shape-{module.shape}"
							style:background={moduleColor(module.id, module.color)}
						></span>
						<h3>{moduleName(module.id)}</h3>
						{#if paused}
							{@const until = pause.untilOf(module.id)}
							<StatusBadge tone="warning">
								{pause.all ? m.module_card_paused_all() : m.module_card_paused()}
								{#if until}· {m.pause_until({ time: formatUntil(until) })}{/if}
							</StatusBadge>
						{/if}
						<StatusBadge>
							{overview.auto_modules.includes(module.id)
								? m.module_card_auto()
								: m.module_card_manual()}
						</StatusBadge>
						<span class="spacer"></span>
						{#if !pause.all}
							<PauseMenu
								{paused}
								disabled={pausing}
								align="right"
								pauseLabel={m.workers_pause()}
								resumeLabel={m.workers_resume()}
								onpause={(minutes) => togglePause(module.id, true, minutes)}
								onresume={() => togglePause(module.id, false)}
							/>
						{/if}
					</header>

					{#if runners.length}
						<p class="muted">
							{m.module_card_run_by({ workers: runners.map((w) => w.name).join(', ') })}
						</p>
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
					<dl class="st-mcard__stats">
						{#each STATUSES as status (status)}
							<div class="st-stat" class:st-stat--danger={status === 'failed' && counts[status]}>
								<dt class="st-stat__label">{statusLabel(status)}</dt>
								<dd class="st-stat__value">{number.format(counts[status] ?? 0)}</dd>
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
										<span>
											<span class="group">{failureGroupName(failureGroup(code))}:</span>
											{failureReason(code)} — {number.format(count)}
										</span>
										<span class="actions">
											<a href={resolve(`/${filterToUrl(failedFilter(module.id, code))}`)}>
												{m.workers_failures_show()}
											</a>
											<button
												type="button"
												class="st-btn st-btn--sm"
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

{#if adding}
	<AddDeviceDialog docs={WORKERS_DOCS} onclose={() => (adding = false)} />
{/if}

<style>
	section {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		margin-bottom: var(--space-10);
	}
	h2 {
		margin: 0;
	}
	.failures ul {
		display: flex;
		flex-direction: column;
		gap: var(--space-1-5);
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.workers {
		display: flex;
		flex-direction: column;
		margin: 0;
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface);
	}
	.worker {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		padding: var(--space-3) var(--space-4);
		font-size: var(--text-sm);
	}
	.worker + .worker {
		border-top: var(--border-width) solid var(--color-border);
	}
	.worker.gone h3,
	.worker.gone .muted {
		color: var(--color-text-subtle);
	}
	.worker header {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2);
	}
	.worker h3 {
		margin: 0;
		font-size: var(--text-base);
	}
	.update {
		font-size: var(--text-xs);
	}
	.device {
		padding: 0 var(--space-1-5);
		border-radius: var(--radius-xs);
		background: var(--color-surface-sunken);
		font-family: var(--font-mono);
		font-size: var(--text-xs);
	}
	.pause-all {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2) var(--space-3);
		padding: var(--space-2) var(--space-3);
		border-radius: var(--radius-md);
		background: var(--color-surface-sunken);
	}
	.pause-all.on {
		background: var(--color-warning-subtle);
	}
	.pause-all .muted {
		flex: 1 1 16rem;
		font-size: var(--text-sm);
	}
	.heading {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-2);
	}
	.worker-modules {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-1-5);
		margin: 0;
	}
	.worker-modules .muted {
		font-size: var(--text-sm);
	}
	.modules {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}
	.module {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		padding: var(--space-4);
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-surface);
	}
	.module.paused {
		border-color: color-mix(in oklab, var(--color-warning), transparent 40%);
	}
	.module header {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2) var(--space-3);
	}
	.module h3 {
		margin: 0;
		font-size: var(--text-md);
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
	.progress {
		display: flex;
		height: 0.375rem;
		overflow: hidden;
		border-radius: var(--radius-full);
		background: var(--color-confidence-track);
	}
	.bar-done {
		background: var(--color-success);
	}
	.bar-running {
		background: var(--color-info);
	}
	.bar-queued {
		background: var(--color-text-subtle);
	}
	.bar-failed {
		background: var(--color-danger);
	}
	.st-mcard__stats {
		margin: 0;
	}
	.st-stat dd {
		margin: 0;
	}
	.failures {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		font-size: var(--text-sm);
	}
	.failures .group {
		color: var(--color-text-muted);
	}
	.failures h4 {
		margin: 0;
		font-size: var(--text-sm);
	}
	.failures li {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-1) var(--space-3);
	}
	/* The link and the button stay together when the reason is long. */
	.failures .actions {
		display: inline-flex;
		align-items: center;
		gap: var(--space-3);
		white-space: nowrap;
	}
	.muted {
		color: var(--color-text-muted);
	}
	.warning {
		margin: 0;
		color: var(--color-warning-text);
	}
	.error {
		color: var(--color-danger-text);
	}
	p {
		margin: 0;
	}
</style>
