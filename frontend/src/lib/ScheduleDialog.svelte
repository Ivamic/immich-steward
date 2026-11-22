<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- The hours a worker gets background jobs (D-238): a week by 24 hours, painted by dragging
     across it, by the clock of the server. -->
<script lang="ts">
	import { setWorkerSchedule, type ServerClock, type WorkerInfo } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import {
		DAYS,
		FULL_DAY,
		HOURS,
		dayOrder,
		serverNow,
		weekdayNames
	} from '#lib/workers/schedule.js';
	import Dialog from '#lib/ui/Dialog.svelte';

	let {
		worker,
		clock,
		onclose,
		onsaved
	}: {
		worker: WorkerInfo;
		clock: ServerClock | null;
		onclose: () => void;
		onsaved: () => void;
	} = $props();

	// Monday first, as the core keeps it; shown in the order of the language.
	// svelte-ignore state_referenced_locally
	let days = $state<number[]>(worker.schedule ? [...worker.schedule] : Array(DAYS).fill(FULL_DAY));
	let busy = $state(false);
	let error = $state<string | null>(null);
	// While dragging: whether the cells passed over are painted or cleared.
	let painting: boolean | null = null;
	// The cell the drag passed last, as row (in the order shown) and hour.
	let last: [number, number] | null = null;

	const order = dayOrder(getLocale());
	const names = weekdayNames(getLocale());
	const hours = Array.from({ length: HOURS }, (_, h) => h);
	const now = $derived(clock ? serverNow(clock) : null);
	const empty = $derived(days.every((day) => day === 0));
	const time = new Intl.DateTimeFormat(getLocale(), {
		hour: '2-digit',
		minute: '2-digit',
		timeZone: 'UTC'
	});

	const isOn = (day: number, hour: number) => ((days[day] >> hour) & 1) === 1;

	function set(day: number, hour: number, on: boolean) {
		if (isOn(day, hour) === on) return;
		days[day] = on ? days[day] | (1 << hour) : days[day] & ~(1 << hour);
	}

	function cellAt(x: number, y: number): [number, number] | null {
		const cell = document.elementFromPoint(x, y)?.closest<HTMLElement>('[data-day]');
		if (!cell) return null;
		return [Number(cell.dataset.day), Number(cell.dataset.hour)];
	}

	function start(event: PointerEvent, day: number, hour: number) {
		if (event.button !== 0) return;
		event.preventDefault();
		// A touch would keep sending its moves to the first cell.
		(event.target as HTMLElement).releasePointerCapture?.(event.pointerId);
		painting = !isOn(day, hour);
		set(day, hour, painting);
		last = [order.indexOf(day), hour];
	}

	function move(event: PointerEvent) {
		if (painting === null) return;
		const cell = cellAt(event.clientX, event.clientY);
		if (!cell) return;
		const to: [number, number] = [order.indexOf(cell[0]), cell[1]];
		// A quick drag skips cells between two moves: paint the line between them too.
		for (const [row, hour] of line(last ?? to, to)) set(order[row], hour, painting);
		last = to;
	}

	/** The cells on the straight line from one cell to another, both included. */
	function line(from: [number, number], to: [number, number]): [number, number][] {
		const steps = Math.max(Math.abs(to[0] - from[0]), Math.abs(to[1] - from[1]));
		return Array.from({ length: steps + 1 }, (_, i) => {
			const t = steps ? i / steps : 0;
			return [
				Math.round(from[0] + (to[0] - from[0]) * t),
				Math.round(from[1] + (to[1] - from[1]) * t)
			];
		});
	}

	async function save() {
		busy = true;
		error = null;
		try {
			await setWorkerSchedule(worker.id, days);
			onsaved();
		} catch (e) {
			error = errorMessage(e);
			busy = false;
		}
	}
</script>

<svelte:window
	onpointerup={() => ((painting = null), (last = null))}
	onpointercancel={() => ((painting = null), (last = null))}
/>

<Dialog title={m.workers_schedule_title({ name: worker.name })} icon="clock" wide {onclose}>
	<p class="hint">{m.workers_schedule_hint()}</p>
	<div class="tools">
		<button
			type="button"
			class="st-btn st-btn--sm st-btn--secondary"
			onclick={() => (days = Array(DAYS).fill(FULL_DAY))}
		>
			{m.workers_schedule_always()}
		</button>
		<button
			type="button"
			class="st-btn st-btn--sm st-btn--secondary"
			onclick={() => (days = Array(DAYS).fill(0))}
		>
			{m.workers_schedule_clear()}
		</button>
		<span class="legend"><span class="swatch on"></span>{m.workers_schedule_legend_on()}</span>
		<span class="legend"><span class="swatch"></span>{m.workers_schedule_legend_off()}</span>
	</div>
	<div class="scroll">
		<table class="grid" onpointermove={move}>
			<thead>
				<tr>
					<th></th>
					{#each hours as hour (hour)}
						<th scope="col">{hour}</th>
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each order as day (day)}
					<tr>
						<th scope="row">{names[day]}</th>
						{#each hours as hour (hour)}
							<td>
								<button
									type="button"
									class="cell"
									class:on={isOn(day, hour)}
									class:now={now?.day === day && now?.hour === hour}
									data-day={day}
									data-hour={hour}
									aria-pressed={isOn(day, hour)}
									aria-label={m.workers_schedule_cell({
										day: names[day],
										hour: String(hour).padStart(2, '0')
									})}
									onpointerdown={(e) => start(e, day, hour)}
									onclick={(e) => {
										// A press with the mouse or a finger has painted it already.
										if (e.detail === 0) set(day, hour, !isOn(day, hour));
									}}
								></button>
							</td>
						{/each}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	<p class="hint">
		{#if clock?.zone}
			{m.workers_schedule_clock({
				zone: clock.zone,
				time: now ? time.format(now.date) : ''
			})}
		{:else}
			{m.workers_schedule_clock_utc({ time: now ? time.format(now.date) : '' })}
		{/if}
	</p>
	{#if empty}
		<p class="warning">{m.workers_schedule_empty()}</p>
	{/if}
	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
	{#snippet footer()}
		<button type="button" class="st-btn st-btn--secondary" onclick={onclose}>
			{m.save_cancel()}
		</button>
		<button type="button" class="st-btn st-btn--primary" disabled={busy} onclick={save}>
			{m.mapsrc_save()}
		</button>
	{/snippet}
</Dialog>

<style>
	.hint {
		margin: 0 0 var(--space-3);
		color: var(--color-text-muted);
		font-size: var(--text-sm);
	}
	.tools {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2) var(--space-3);
		margin-bottom: var(--space-3);
		font-size: var(--text-sm);
	}
	.legend {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1-5);
	}
	.swatch {
		width: 0.9rem;
		height: 0.9rem;
		border: var(--border-width) solid var(--color-border-strong);
		border-radius: var(--radius-xs);
		background: var(--color-surface);
	}
	.swatch.on {
		border-color: var(--color-accent);
		background: var(--color-accent);
	}
	.scroll {
		margin-bottom: var(--space-3);
		overflow-x: auto;
	}
	.grid {
		border-collapse: collapse;
		/* Dragging paints instead of scrolling or selecting. */
		touch-action: none;
		user-select: none;
		font-size: var(--text-xs);
	}
	.grid th {
		padding: 0 var(--space-1);
		color: var(--color-text-muted);
		font-weight: 500;
		text-align: center;
	}
	.grid th[scope='row'] {
		text-align: left;
	}
	.grid td {
		padding: 1px;
	}
	.cell {
		display: block;
		width: 1.4rem;
		height: 1.4rem;
		padding: 0;
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-xs);
		background: var(--color-surface);
		cursor: pointer;
	}
	.cell.on {
		border-color: var(--color-accent);
		background: var(--color-accent);
	}
	.cell.now {
		outline: 2px solid var(--color-warning);
		outline-offset: 1px;
	}
	.cell:focus-visible {
		outline: 2px solid var(--color-focus);
		outline-offset: 1px;
	}
	.warning {
		margin: 0 0 var(--space-2);
		color: var(--color-warning-text);
		font-size: var(--text-sm);
	}
	.error {
		margin: 0;
		color: var(--color-danger-text);
	}
</style>
