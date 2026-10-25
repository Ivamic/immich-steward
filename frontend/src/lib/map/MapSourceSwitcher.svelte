<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- The bar above the map: the plain map or a satellite source (a year for EOX), what "Auto"
     switches between and "Auto" itself with its state always visible (switch by zoom as the
     settings say, linked by the gear), labels over the imagery, how the likely areas are drawn.
     Sources that cannot be used are greyed with the reason; they are switched on in the
     settings. -->
<script lang="ts">
	import type { MapAuto, MapKeyProblem, MapSourceConfig, MapSourceStatus } from '#lib/api.js';
	import { m } from '#lib/paraglide/messages.js';
	import Icon from '#lib/ui/Icon.svelte';
	import { resolve } from '$app/paths';
	import { AREA_MODES, AUTO_ANCHOR, SCHEME, type AreaMode } from './sources.js';

	let {
		sources,
		areas,
		hasAreas,
		auto,
		autoOn,
		labels,
		year,
		active,
		zoom,
		problems,
		onchoice,
		onauto,
		onlabels,
		onareas,
		onyear
	}: {
		/** The satellite sources; none: the bar shows only the areas. */
		sources: MapSourceConfig[];
		areas: AreaMode;
		/** Whether the map has likely areas to draw. */
		hasAreas: boolean;
		/** The auto switching of the settings; null: none. */
		auto: MapAuto | null;
		autoOn: boolean;
		labels: boolean;
		/** The EOX year shown. */
		year: string;
		/** What the map shows now. */
		active: string;
		/** The zoom of the map now. */
		zoom: number;
		/** Key problems the tiles told in this page. */
		problems: Record<string, MapKeyProblem>;
		onchoice: (id: string) => void;
		onauto: (on: boolean) => void;
		onlabels: (on: boolean) => void;
		onareas: (mode: AreaMode) => void;
		onyear: (year: string) => void;
	} = $props();

	// Short names for the bar; the settings show the full ones.
	const SHORT: Record<string, string> = { eox: 'Sentinel-2', esri: 'Esri', maptiler: 'MapTiler' };
	const short = (id: string | null) =>
		id === null || id === SCHEME
			? m.mapsrc_scheme()
			: (SHORT[id] ?? sources.find((s) => s.id === id)?.name ?? id);
	const autoSet = $derived(auto !== null && (auto.far !== null || auto.near !== null));
	const near = $derived(auto !== null && zoom >= auto.switch_zoom);
	const eox = $derived(sources.find((s) => s.id === 'eox') ?? null);
	const AREA_LABEL: Record<AreaMode, () => string> = {
		fill: m.map_areas_fill,
		line: m.map_areas_line,
		none: m.map_areas_none
	};

	/** Why a source cannot be picked; null: it can. */
	function blocked(source: MapSourceConfig): string | null {
		if (!source.enabled) {
			return source.status === 'no_key' ? m.mapsrc_need_key() : m.mapsrc_turn_on();
		}
		const problem: MapSourceStatus = problems[source.id] ?? source.status;
		if (problem === 'exhausted') return m.mapsrc_exhausted();
		if (problem === 'invalid') return m.mapsrc_invalid();
		if (problem === 'no_key') return m.mapsrc_need_key();
		return null;
	}

	function pick(id: string) {
		// Picking by hand ends the automatic switching.
		if (autoOn) onauto(false);
		onchoice(id);
	}
</script>

<div class="bar">
	{#if sources.length}
		<span class="title">{m.mapsrc_basemap()}</span>
		<div class="st-seg" role="radiogroup" aria-label={m.mapsrc_basemap()}>
			<button
				type="button"
				role="radio"
				aria-checked={active === SCHEME}
				onclick={() => pick(SCHEME)}>{m.mapsrc_scheme()}</button
			>
			{#each sources as source (source.id)}
				{@const reason = blocked(source)}
				<button
					type="button"
					role="radio"
					aria-checked={active === source.id}
					disabled={reason !== null}
					title={reason ? `${source.name}: ${reason}` : source.name}
					onclick={() => pick(source.id)}
				>
					{short(source.id)}
					{#if problems[source.id] === 'exhausted' || source.status === 'exhausted'}
						<Icon name="triangle-alert" size={12} />
					{/if}
				</button>
			{/each}
		</div>
		{#if eox && active === 'eox'}
			<select
				class="st-select year"
				aria-label={m.mapsrc_year()}
				value={year}
				onchange={(e) => onyear((e.currentTarget as HTMLSelectElement).value)}
			>
				{#each eox.variants as variant (variant.id)}
					<option value={variant.id}>{variant.id}</option>
				{/each}
			</select>
		{/if}
		{#if active !== SCHEME}
			<label class="st-check st-check--sm">
				<input
					type="checkbox"
					checked={labels}
					onchange={(e) => onlabels((e.currentTarget as HTMLInputElement).checked)}
				/>
				{m.mapsrc_labels()}
			</label>
		{/if}
	{/if}
	{#if hasAreas}
		<span class="title">{m.map_areas()}</span>
		<div class="st-seg" role="radiogroup" aria-label={m.map_areas()} title={m.map_areas_hint()}>
			{#each AREA_MODES as mode (mode)}
				<button
					type="button"
					role="radio"
					aria-checked={areas === mode}
					onclick={() => onareas(mode)}>{AREA_LABEL[mode]()}</button
				>
			{/each}
		</div>
	{/if}
	{#if sources.length}
		{#if auto && autoSet}
			<!-- What "Auto" shows; with it on, the part for the zoom now is in bold. -->
			<span class="summary" class:on={autoOn} title={m.mapsrc_zoom_scale()}>
				{#if auto.far === auto.near}
					<span class:now={autoOn}>{short(auto.far)}</span>
				{:else}
					<span class:now={autoOn && !near}>{short(auto.far)}</span>
					→
					<span class:now={autoOn && near}>{short(auto.near)}</span>
					{m.mapsrc_auto_summary_zoom({ zoom: auto.switch_zoom })}
				{/if}
			</span>
		{/if}
		<button
			type="button"
			class="auto"
			class:push={!autoSet}
			aria-pressed={autoOn}
			disabled={!autoSet}
			title={auto && autoSet
				? m.mapsrc_auto_hint({
						far: short(auto.far),
						near: short(auto.near),
						zoom: auto.switch_zoom
					})
				: m.mapsrc_auto_unset()}
			onclick={() => onauto(!autoOn)}
		>
			<span class="dot" aria-hidden="true"></span>
			{autoOn ? m.mapsrc_auto_on() : m.mapsrc_auto_off()}
		</button>
	{/if}
	<!-- eslint-disable svelte/no-navigation-without-resolve -- resolved, with an anchor added -->
	<a
		class="gear"
		class:push={!sources.length}
		href={`${resolve('/settings')}#${AUTO_ANCHOR}`}
		title={m.mapsrc_auto_settings_link()}
		aria-label={m.mapsrc_auto_settings_link()}
	>
		<Icon name="settings" size={14} />
	</a>
	<!-- eslint-enable svelte/no-navigation-without-resolve -->
</div>

<style>
	.bar {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-1-5) var(--space-2);
		padding: var(--space-1-5) var(--space-2);
		border-bottom: var(--border-width) solid var(--color-border);
		background: var(--color-surface);
		font-size: var(--text-sm);
	}
	.title {
		color: var(--color-text-muted);
	}
	.year {
		width: auto;
		height: var(--control-sm);
		padding-block: 0;
		font-size: var(--text-sm);
	}
	.summary {
		margin-inline-start: auto;
		color: var(--color-text-disabled);
	}
	.summary.on {
		color: var(--color-text-muted);
	}
	.now {
		color: var(--color-text);
		font-weight: var(--weight-semibold);
	}
	.auto {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1-5);
		height: var(--control-sm);
		padding-inline: var(--space-2);
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-full);
		background: var(--color-surface);
		color: var(--color-text-muted);
		font: inherit;
		font-weight: var(--weight-medium);
		cursor: pointer;
	}
	.auto[aria-pressed='true'] {
		border-color: var(--color-accent);
		background: var(--color-accent-subtle);
		color: var(--color-accent-text);
	}
	.auto:disabled {
		color: var(--color-text-disabled);
		cursor: not-allowed;
	}
	.dot {
		width: 0.5rem;
		height: 0.5rem;
		border: 1.5px solid currentColor;
		border-radius: 50%;
	}
	.auto[aria-pressed='true'] .dot {
		background: currentColor;
	}
	/* Without the summary, "Auto" starts the group at the end of the bar. */
	.push {
		margin-inline-start: auto;
	}
	.gear {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: var(--control-sm);
		height: var(--control-sm);
		border-radius: var(--radius-full);
		color: var(--color-text-muted);
	}
	.gear:hover {
		background: var(--color-surface-hover);
		color: var(--color-text);
	}
</style>
