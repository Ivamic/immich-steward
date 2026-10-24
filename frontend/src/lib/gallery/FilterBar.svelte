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
	import Icon from '#lib/ui/Icon.svelte';
	import Tooltip from '#lib/ui/Tooltip.svelte';
	import { defaultFilter, filterToUrl } from './filter.js';

	let {
		filter,
		total = null,
		onchange
	}: {
		filter: GalleryFilter;
		/** Photos and videos under the filter; null while loading. */
		total?: number | null;
		onchange: (f: GalleryFilter) => void;
	} = $props();

	let options = $state<FilterOptions>({ cameras: [], albums: [], failed_modules: [] });

	$effect(() => {
		getFilterOptions()
			.then((result) => (options = result))
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
</script>

<div class="bar">
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

	<label class="st-input st-input--select st-input--sm">
		<Icon name="camera" size={14} />
		<select
			aria-label={m.filter_camera()}
			value={filter.camera ?? ''}
			onchange={(e) => {
				const index = e.currentTarget.selectedIndex - 1;
				set({ camera: index < 0 ? null : options.cameras[index].value });
			}}
		>
			<option value="">{m.filter_camera_any()}</option>
			{#each options.cameras as camera (camera.value)}
				<option value={camera.value}
					>{cameraLabel(camera.make, camera.model)} ({camera.count})</option
				>
			{/each}
		</select>
		<span class="st-select__chev"><Icon name="chevron-down" size={14} /></span>
	</label>

	{#if options.albums.length || filter.album}
		<label class="st-input st-input--select st-input--sm">
			<Icon name="images" size={14} />
			<select
				aria-label={m.filter_album()}
				value={filter.album ?? ''}
				onchange={(e) => set({ album: e.currentTarget.value || null })}
			>
				<option value="">{m.filter_album_any()}</option>
				{#each options.albums as album (album.id)}
					<option value={album.id}>{album.name} ({album.count})</option>
				{/each}
			</select>
			<span class="st-select__chev"><Icon name="chevron-down" size={14} /></span>
		</label>
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

	{#if total !== null}
		<span class="total">{m.gallery_total({ count: new Intl.NumberFormat().format(total) })}</span>
	{/if}
</div>

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
	.group {
		display: contents;
	}
	.sep {
		width: 1px;
		height: 1.25rem;
		margin-inline: var(--space-1);
		background: var(--color-border-strong);
	}
	.st-input--select {
		max-width: 14rem;
		padding-inline-start: var(--space-2);
	}
	.total {
		margin-inline-start: auto;
		color: var(--color-text-muted);
		font-size: var(--text-sm);
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}
</style>
