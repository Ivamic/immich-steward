<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- A drop-down list like a <select>, with a search field on top when the list is long: typing
     keeps the names that contain it (any part, whatever the case and the accents). The arrows
     move, Enter picks, Esc closes. The first entry ("any") clears the choice. -->
<script module lang="ts">
	export interface SearchOption {
		value: string;
		label: string;
		/** Shown after the label, e.g. the number of photos. */
		hint?: string;
	}
</script>

<script lang="ts">
	import { m } from '#lib/paraglide/messages.js';
	import { matches } from '#lib/search.js';
	import Icon from './Icon.svelte';
	import type { IconName } from './icons.js';

	// Shorter lists open without the search field.
	const SEARCH_FROM = 8;

	let {
		options,
		value,
		label,
		anyLabel,
		icon,
		onchange
	}: {
		options: SearchOption[];
		/** The value picked; null: "any". */
		value: string | null;
		/** What the list chooses, for screen readers. */
		label: string;
		/** The first entry, which clears the choice. */
		anyLabel: string;
		icon?: IconName;
		onchange: (value: string | null) => void;
	} = $props();

	const id = $props.id();
	let open = $state(false);
	let query = $state('');
	let active = $state(0);
	let root = $state<HTMLDivElement>();
	let trigger = $state<HTMLButtonElement>();
	let list = $state<HTMLUListElement>();
	let search = $state<HTMLInputElement>();

	const searchable = $derived(options.length >= SEARCH_FROM);
	const any: SearchOption = $derived({ value: '', label: anyLabel });
	// "Any" stays first while nothing is typed.
	const shown = $derived(
		query.trim() ? options.filter((o) => matches(o.label, query)) : [any, ...options]
	);
	const current = $derived(options.find((o) => o.value === value) ?? null);

	function show() {
		open = true;
		query = '';
		active = Math.max(
			0,
			shown.findIndex((o) => o.value === (value ?? ''))
		);
		// After the list is drawn.
		queueMicrotask(() => {
			(searchable ? search : list)?.focus();
			scrollToActive();
		});
	}

	function close(focusTrigger = true) {
		open = false;
		if (focusTrigger) trigger?.focus();
	}

	function pick(option: SearchOption) {
		onchange(option.value || null);
		close();
	}

	function scrollToActive() {
		list?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' });
	}

	function onkeydown(event: KeyboardEvent) {
		const last = shown.length - 1;
		const moves: Record<string, number> = {
			ArrowDown: Math.min(last, active + 1),
			ArrowUp: Math.max(0, active - 1),
			Home: 0,
			End: last,
			PageDown: Math.min(last, active + 8),
			PageUp: Math.max(0, active - 8)
		};
		if (event.key in moves && !(searchable && (event.key === 'Home' || event.key === 'End'))) {
			event.preventDefault();
			active = moves[event.key];
			scrollToActive();
		} else if (event.key === 'Enter') {
			event.preventDefault();
			if (shown[active]) pick(shown[active]);
		} else if (event.key === 'Escape') {
			event.preventDefault();
			event.stopPropagation();
			close();
		} else if (event.key === 'Tab') {
			close(false);
		}
	}

	function closeOutside(event: PointerEvent) {
		if (open && root && !root.contains(event.target as Node)) close(false);
	}
</script>

<svelte:window onpointerdown={closeOutside} />

<div class="wrap" bind:this={root}>
	<button
		bind:this={trigger}
		type="button"
		class="st-input st-input--select st-input--sm trigger"
		aria-label={label}
		aria-haspopup="listbox"
		aria-expanded={open}
		onclick={() => (open ? close() : show())}
		onkeydown={(e) => {
			if (!open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
				e.preventDefault();
				show();
			}
		}}
	>
		{#if icon}<Icon name={icon} size={14} />{/if}
		<span class="value">
			{current ? current.label : anyLabel}
			{#if current?.hint}<span class="hint">{current.hint}</span>{/if}
		</span>
		<span class="st-select__chev"><Icon name="chevron-down" size={14} /></span>
	</button>

	{#if open}
		<div class="panel st-menu">
			{#if searchable}
				<label class="st-input st-input--sm find">
					<Icon name="search" size={14} />
					<input
						bind:this={search}
						type="search"
						role="combobox"
						aria-label={m.search_in_list({ list: label })}
						aria-controls="{id}-list"
						aria-expanded="true"
						aria-autocomplete="list"
						aria-activedescendant={shown.length ? `${id}-${active}` : undefined}
						placeholder={m.search_in_list_placeholder()}
						bind:value={query}
						oninput={() => (active = 0)}
						{onkeydown}
					/>
				</label>
			{/if}
			<ul
				bind:this={list}
				id="{id}-list"
				role="listbox"
				aria-label={label}
				tabindex={searchable ? -1 : 0}
				aria-activedescendant={!searchable && shown.length ? `${id}-${active}` : undefined}
				onkeydown={searchable ? undefined : onkeydown}
			>
				{#each shown as option, index (option.value)}
					<!-- The keys go to the search field or the list (aria-activedescendant). -->
					<!-- svelte-ignore a11y_click_events_have_key_events -->
					<li
						id="{id}-{index}"
						role="option"
						class="st-menu__item"
						data-index={index}
						data-active={index === active}
						aria-selected={option.value === (value ?? '')}
						onpointermove={() => (active = index)}
						onclick={() => pick(option)}
					>
						<span class="st-menu__label">{option.label}</span>
						{#if option.hint}<span class="st-menu__hint">{option.hint}</span>{/if}
						{#if option.value === (value ?? '')}
							<span class="st-menu__check"><Icon name="check" size={14} /></span>
						{/if}
					</li>
				{:else}
					<li class="empty" role="presentation">{m.search_in_list_none()}</li>
				{/each}
			</ul>
		</div>
	{/if}
</div>

<style>
	.wrap {
		position: relative;
		display: inline-flex;
	}
	.trigger {
		max-width: 14rem;
		padding-inline-start: var(--space-2);
		padding-inline-end: var(--space-8);
		color: var(--color-text);
		font: inherit;
		font-size: var(--text-sm);
		cursor: pointer;
	}
	.value {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.hint {
		color: var(--color-text-subtle);
	}
	.panel {
		position: absolute;
		top: calc(100% + 4px);
		inset-inline-start: 0;
		gap: var(--space-1);
		min-width: 16rem;
		overflow: hidden;
	}
	.find {
		flex-shrink: 0;
		margin: var(--space-1);
	}
	/* The field draws the focus ring, not the input inside it. */
	.find input {
		width: 100%;
		outline: none;
		box-shadow: none;
	}
	ul {
		display: flex;
		flex-direction: column;
		min-height: 0;
		margin: 0;
		padding: 0;
		overflow-y: auto;
		list-style: none;
		outline: none;
	}
	.empty {
		padding: var(--space-2);
		color: var(--color-text-muted);
		font-size: var(--text-sm);
	}
</style>
