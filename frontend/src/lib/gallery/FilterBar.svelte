<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- One row of filter chips over the gallery; it stays in view under the header. The period and
     the processing errors open a small panel with their fields. -->
<script lang="ts">
	import {
		ANY_MODULE,
		getFilterOptions,
		SHOW_CATEGORIES,
		type FilterOptions,
		type GalleryFilter,
		type ShowCategory
	} from '#lib/api.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import {
		cameraName,
		FAILURE_GROUPS,
		failureGroupName,
		failureReason,
		moduleName
	} from '#lib/suggestions/format.js';
	import ChipPopover from '#lib/ui/ChipPopover.svelte';
	import SearchSelect from '#lib/ui/SearchSelect.svelte';
	import Icon from '#lib/ui/Icon.svelte';
	import Tooltip from '#lib/ui/Tooltip.svelte';
	import Dialog from '#lib/ui/Dialog.svelte';
	import { activeFilters, defaultFilter, filterToUrl } from './filter.js';

	let {
		filter,
		total = null,
		height = $bindable(0),
		// eslint-disable-next-line no-useless-assignment -- bound: the gallery reads it
		nearbyMinutes = $bindable(15),
		onchange
	}: {
		filter: GalleryFilter;
		/** Photos and videos under the filter; null while loading. */
		total?: number | null;
		/** Height of the bar: it grows when the chips wrap to a second row. */
		height?: number;
		/** How close in time a located photo makes another one "nearby" (a setting of the core). */
		nearbyMinutes?: number;
		onchange: (f: GalleryFilter) => void;
	} = $props();

	let options = $state<FilterOptions>({
		cameras: [],
		albums: [],
		failed_modules: [],
		nearby_minutes: 15
	});

	$effect(() => {
		getFilterOptions()
			.then((result) => {
				options = result;
				nearbyMinutes = result.nearby_minutes;
			})
			.catch(() => {});
	});

	const set = (patch: Partial<GalleryFilter>) => onchange({ ...filter, ...patch });
	const showLabels: Record<ShowCategory, () => string> = {
		todo: m.filter_view_todo,
		with: m.filter_view_with,
		skipped: m.filter_view_skipped,
		not_applicable: m.filter_view_not_applicable
	};
	const types = [
		['all', m.filter_type_all],
		['image', m.filter_type_image],
		['video', m.filter_type_video]
	] as const;

	// At least one group stays chosen: the last one cannot be turned off.
	function toggleShow(category: ShowCategory) {
		const checked = !filter.show.includes(category);
		if (!checked && filter.show.length === 1) return;
		const chosen = checked ? [...filter.show, category] : filter.show.filter((c) => c !== category);
		set({ show: SHOW_CATEGORIES.filter((c) => chosen.includes(c)) });
	}
	const cameraLabel = (make: string, model: string) =>
		cameraName(make, model) || m.filter_camera_unknown();

	const dayFormat = $derived(new Intl.DateTimeFormat(getLocale(), { dateStyle: 'medium' }));
	function day(value: string): string {
		const [y, mo, d] = value.split('-').map(Number);
		return dayFormat.format(new Date(y, mo - 1, d));
	}
	const periodLabel = $derived.by(() => {
		const { date_from: from, date_to: to } = filter;
		if (from && to) return m.filter_period_range({ from: day(from), to: day(to) });
		if (from) return m.filter_period_from({ date: day(from) });
		if (to) return m.filter_period_to({ date: day(to) });
		return m.filter_period();
	});
	const failedLabel = $derived.by(() => {
		if (!filter.failed_module) return m.filter_failed();
		const module =
			filter.failed_module === ANY_MODULE
				? m.filter_failed_module_any()
				: moduleName(filter.failed_module);
		const reason = filter.failure ? ` · ${failureReason(filter.failure)}` : '';
		return `${m.filter_failed()}: ${module}${reason}`;
	});
	const isDefault = $derived(filterToUrl(filter) === filterToUrl(defaultFilter));
	const active = $derived(activeFilters(filter));
	let sheet = $state(false);
</script>

<!-- On a phone the chips take the whole screen: one button opens them in a window instead. -->
{#snippet controls()}
	<div class="group" role="group" aria-label={m.filter_view()}>
		{#each SHOW_CATEGORIES as category (category)}
			{@const checked = filter.show.includes(category)}
			<button
				type="button"
				class="st-chip"
				aria-pressed={checked}
				onclick={() => toggleShow(category)}
			>
				{showLabels[category]()}
			</button>
		{/each}
	</div>
	<span class="sep" aria-hidden="true"></span>

	<Tooltip text={m.filter_geoclip_confident_hint()} below>
		<button
			type="button"
			class="st-chip"
			aria-pressed={filter.geoclip_confident}
			onclick={() => set({ geoclip_confident: !filter.geoclip_confident })}
		>
			<span class="st-chip__dot" style:background="var(--module-2)"></span>
			{m.filter_geoclip_confident()}
		</button>
	</Tooltip>

	<Tooltip text={m.filter_similar_confident_hint()} below>
		<button
			type="button"
			class="st-chip"
			aria-pressed={filter.similar_confident}
			onclick={() => set({ similar_confident: !filter.similar_confident })}
		>
			<span class="st-chip__dot" style:background="var(--module-3)"></span>
			{m.filter_similar_confident()}
		</button>
	</Tooltip>

	<Tooltip text={m.filter_nearby_hint({ minutes: options.nearby_minutes })} below>
		<button
			type="button"
			class="st-chip"
			aria-pressed={filter.nearby}
			onclick={() => set({ nearby: !filter.nearby })}
		>
			<span class="st-chip__dot" style:background="var(--module-1)"></span>
			{m.filter_nearby()}
		</button>
	</Tooltip>

	<div class="st-seg" role="radiogroup" aria-label={m.filter_type()}>
		{#each types as [value, label] (value)}
			<button
				type="button"
				role="radio"
				aria-checked={filter.type === value}
				onclick={() => set({ type: value })}
			>
				{label()}
			</button>
		{/each}
	</div>

	<SearchSelect
		icon="camera"
		label={m.filter_camera()}
		anyLabel={m.filter_camera_any()}
		value={filter.camera}
		options={options.cameras.map((camera) => ({
			value: camera.value,
			label: cameraLabel(camera.make, camera.model),
			hint: String(camera.count)
		}))}
		onchange={(camera) => set({ camera })}
	/>

	{#if options.albums.length || filter.album}
		<SearchSelect
			icon="images"
			label={m.filter_album()}
			anyLabel={m.filter_album_any()}
			value={filter.album}
			options={options.albums.map((album) => ({
				value: album.id,
				label: album.name,
				hint: String(album.count)
			}))}
			onchange={(album) => set({ album })}
		/>
	{/if}

	<ChipPopover
		label={periodLabel}
		icon="calendar"
		active={Boolean(filter.date_from || filter.date_to)}
		clearLabel={m.filter_clear()}
		onclear={() => set({ date_from: null, date_to: null })}
	>
		<label class="st-field">
			<span class="st-field__label">{m.filter_date_from()}</span>
			<input
				type="date"
				value={filter.date_from ?? ''}
				onchange={(e) => set({ date_from: e.currentTarget.value || null })}
			/>
		</label>
		<label class="st-field">
			<span class="st-field__label">{m.filter_date_to()}</span>
			<input
				type="date"
				value={filter.date_to ?? ''}
				onchange={(e) => set({ date_to: e.currentTarget.value || null })}
			/>
		</label>
	</ChipPopover>

	<ChipPopover
		label={failedLabel}
		icon="triangle-alert"
		active={Boolean(filter.failed_module)}
		clearLabel={m.filter_clear()}
		onclear={() => set({ failed_module: null, failure: null })}
	>
		<label class="st-field">
			<span class="st-field__label">{m.filter_failed()}</span>
			<select
				value={filter.failed_module ?? ''}
				onchange={(e) => set({ failed_module: e.currentTarget.value || null, failure: null })}
			>
				<option value="">{m.filter_failed_none()}</option>
				<option value={ANY_MODULE}>{m.filter_failed_module_any()}</option>
				{#each options.failed_modules as module (module)}
					<option value={module}>{moduleName(module)}</option>
				{/each}
			</select>
		</label>
		{#if filter.failed_module}
			<label class="st-field">
				<span class="st-field__label">{m.filter_failed_reason()}</span>
				<select
					value={filter.failure ?? ''}
					onchange={(e) => set({ failure: e.currentTarget.value || null })}
				>
					<option value="">{m.filter_failed_any()}</option>
					{#each FAILURE_GROUPS as { group, codes } (group)}
						<optgroup label={failureGroupName(group)}>
							{#each codes as code (code)}
								<option value={code}>{failureReason(code)}</option>
							{/each}
						</optgroup>
					{/each}
				</select>
			</label>
		{/if}
	</ChipPopover>

	<button
		type="button"
		class="st-chip"
		aria-pressed={filter.archived}
		onclick={() => set({ archived: !filter.archived })}
	>
		{m.filter_archived()}
	</button>

	{#if !isDefault}
		<button
			type="button"
			class="st-btn st-btn--ghost st-btn--sm"
			onclick={() => onchange(defaultFilter)}
		>
			<Icon name="rotate-ccw" size={14} />
			{m.filter_reset()}
		</button>
	{/if}
{/snippet}

<div class="bar" bind:offsetHeight={height}>
	<button type="button" class="filters st-btn st-btn--sm" onclick={() => (sheet = true)}>
		<Icon name="filter" size={14} />
		{m.filter_button()}
		{#if active}<span class="active">{active}</span>{/if}
	</button>
	<div class="chips">{@render controls()}</div>
	{#if total !== null}
		<span class="total">{m.gallery_total({ count: new Intl.NumberFormat().format(total) })}</span>
	{/if}
</div>

{#if sheet}
	<Dialog title={m.filter_button()} icon="filter" onclose={() => (sheet = false)}>
		<div class="sheet">{@render controls()}</div>
	</Dialog>
{/if}

<style>
	/* Stays under the sticky header; the side margins cover the page padding. */
	.bar {
		position: sticky;
		top: var(--header-height);
		z-index: var(--z-sticky);
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2);
		margin: calc(var(--space-6) * -1) calc(var(--space-6) * -1) 0;
		/* the end stays clear of the timeline scrubber */
		padding: var(--space-3) 4rem var(--space-3) var(--space-6);
		background: var(--color-bg);
	}
	.group,
	.chips {
		display: contents;
	}
	.filters {
		display: none;
	}
	.active {
		display: inline-grid;
		place-items: center;
		min-width: 1.25rem;
		height: 1.25rem;
		padding-inline: var(--space-1);
		border-radius: var(--radius-full);
		background: var(--color-accent);
		color: var(--gray-0);
		font-size: var(--text-xs);
	}
	/* In the window: the same chips, wrapped. */
	.sheet {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2);
	}
	/* A phone: the filter button and the total only. */
	@media (max-width: 40rem) {
		.bar {
			padding-inline-end: var(--space-6);
		}
		.filters {
			display: inline-flex;
		}
		.chips {
			display: none;
		}
	}
	.sep {
		width: 1px;
		height: 1.25rem;
		margin-inline: var(--space-1);
		background: var(--color-border-strong);
	}
	.total {
		margin-inline-start: auto;
		color: var(--color-text-muted);
		font-size: var(--text-sm);
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}
</style>
