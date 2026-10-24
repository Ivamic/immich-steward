<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Over the map: the plain map or a satellite source (a year for EOX), "Auto" (switch by zoom
     as the settings say), labels over the imagery. Sources that cannot be used are shown greyed
     with the reason; the settings are where they are switched on. -->
<script lang="ts">
	import type { MapAuto, MapKeyProblem, MapSourceConfig, MapSourceStatus } from '#lib/api.js';
	import { m } from '#lib/paraglide/messages.js';
	import Icon from '#lib/ui/Icon.svelte';
	import { resolve } from '$app/paths';
	import { SCHEME } from './sources.js';

	let {
		sources,
		choice,
		auto,
		autoOn,
		labels,
		year,
		active,
		problems,
		onchoice,
		onauto,
		onlabels,
		onyear
	}: {
		sources: MapSourceConfig[];
		/** Picked by hand: a source id or SCHEME. */
		choice: string;
		/** The auto switching of the settings; null: none. */
		auto: MapAuto | null;
		autoOn: boolean;
		labels: boolean;
		/** The EOX year shown. */
		year: string;
		/** What the map shows now. */
		active: string;
		/** Key problems the tiles told in this page. */
		problems: Record<string, MapKeyProblem>;
		onchoice: (id: string) => void;
		onauto: (on: boolean) => void;
		onlabels: (on: boolean) => void;
		onyear: (year: string) => void;
	} = $props();

	let open = $state(false);
	let root: HTMLDivElement | undefined = $state();

	const name = (id: string | null) =>
		id === null || id === SCHEME
			? m.mapsrc_scheme()
			: (sources.find((s) => s.id === id)?.name ?? id);
	const activeName = $derived(active === 'eox' ? `${name(active)} ${year}` : name(active));
	const autoSet = $derived(auto !== null && (auto.far !== null || auto.near !== null));

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

	function closeOutside(event: PointerEvent) {
		if (open && root && !root.contains(event.target as Node)) open = false;
	}

	function closeOnEscape(event: KeyboardEvent) {
		if (!open || event.key !== 'Escape') return;
		event.preventDefault();
		open = false;
		root?.querySelector('button')?.focus();
	}
</script>

<svelte:window onpointerdown={closeOutside} onkeydown={closeOnEscape} />

<div class="wrap" bind:this={root}>
	<button
		type="button"
		class="toggle st-glass"
		aria-expanded={open}
		aria-label={m.mapsrc_button({ name: activeName })}
		title={m.mapsrc_button({ name: activeName })}
		onclick={() => (open = !open)}
	>
		<Icon name="layers" size={16} />
		<span class="label">{activeName}</span>
		{#if autoOn && autoSet}<span class="badge">{m.mapsrc_auto_badge()}</span>{/if}
		<Icon name="chevron-down" size={14} />
	</button>
	{#if open}
		<div class="panel st-menu" role="menu">
			<button
				type="button"
				class="st-menu__item"
				role="menuitemradio"
				aria-checked={!autoOn && choice === SCHEME}
				onclick={() => pick(SCHEME)}
			>
				<span class="st-menu__label">{m.mapsrc_scheme()}</span>
				{#if !autoOn && choice === SCHEME}<Icon name="check" size={14} />{/if}
			</button>
			{#each sources as source (source.id)}
				{@const reason = blocked(source)}
				{@const picked = !autoOn && choice === source.id}
				<button
					type="button"
					class="st-menu__item"
					role="menuitemradio"
					aria-checked={picked}
					disabled={reason !== null}
					title={reason ?? undefined}
					onclick={() => pick(source.id)}
				>
					<span class="st-menu__label">{source.name}</span>
					{#if problems[source.id] === 'exhausted' || source.status === 'exhausted'}
						<Icon name="triangle-alert" size={14} />
					{/if}
					{#if reason}<span class="st-menu__hint">{reason}</span>{/if}
					{#if picked}<Icon name="check" size={14} />{/if}
				</button>
				{#if source.id === 'eox' && reason === null && active === 'eox'}
					<label class="year">
						<span>{m.mapsrc_year()}</span>
						<select
							class="st-select"
							value={year}
							onchange={(e) => onyear((e.currentTarget as HTMLSelectElement).value)}
						>
							{#each source.variants as variant (variant.id)}
								<option value={variant.id}>{variant.id}</option>
							{/each}
						</select>
					</label>
				{/if}
			{/each}
			<div class="st-menu__sep"></div>
			<label class="st-check st-check--sm option">
				<input
					type="checkbox"
					checked={autoOn}
					disabled={!autoSet}
					onchange={(e) => onauto((e.currentTarget as HTMLInputElement).checked)}
				/>
				{m.mapsrc_auto()}
			</label>
			{#if auto && autoSet}
				<p class="st-menu__hint note">
					{m.mapsrc_auto_hint({
						far: name(auto.far),
						near: name(auto.near),
						zoom: auto.switch_zoom
					})}
				</p>
			{:else}
				<p class="st-menu__hint note">{m.mapsrc_auto_unset()}</p>
			{/if}
			<label class="st-check st-check--sm option">
				<input
					type="checkbox"
					checked={labels}
					disabled={active === SCHEME}
					onchange={(e) => onlabels((e.currentTarget as HTMLInputElement).checked)}
				/>
				{m.mapsrc_labels()}
			</label>
			<div class="st-menu__sep"></div>
			<a class="st-menu__item settings" href={resolve('/settings')}>
				<span class="st-menu__label">{m.mapsrc_settings()}</span>
			</a>
		</div>
	{/if}
</div>

<style>
	.wrap {
		position: relative;
	}
	.toggle {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1-5);
		max-width: 16rem;
		height: var(--control-sm);
		padding-inline: var(--space-2);
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-md);
		box-shadow: var(--shadow-sm);
		color: var(--color-text);
		font: var(--weight-medium) var(--text-sm) / 1 var(--font-sans);
		cursor: pointer;
	}
	.label {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.badge {
		padding: 0 var(--space-1);
		border-radius: var(--radius-xs);
		background: var(--color-accent-subtle);
		color: var(--color-accent-text);
		font-size: var(--text-xs);
	}
	.panel {
		position: absolute;
		top: calc(100% + var(--space-1));
		left: 0;
		min-width: 15rem;
	}
	.year {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-2);
		padding: var(--space-1) var(--space-2) var(--space-1) var(--space-4);
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	.option {
		padding: var(--space-1) var(--space-2);
	}
	.note {
		margin: 0;
		padding: 0 var(--space-2) var(--space-1) calc(var(--space-2) + 1.5rem);
		font-size: var(--text-xs);
	}
	.settings {
		color: var(--color-accent-text);
		text-decoration: none;
	}
</style>
