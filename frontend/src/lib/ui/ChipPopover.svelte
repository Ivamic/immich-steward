<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- A filter chip that opens a small panel with the filter's fields. When the filter is set the
     chip is highlighted and shows a clear button. The panel closes on a click outside and on Esc. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from './Icon.svelte';
	import type { IconName } from './icons.js';

	let {
		label,
		icon,
		active = false,
		clearLabel,
		onclear,
		children
	}: {
		label: string;
		icon?: IconName;
		active?: boolean;
		clearLabel?: string;
		onclear?: () => void;
		children: Snippet;
	} = $props();

	let open = $state(false);
	let root: HTMLDivElement | undefined = $state();

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
		class="st-chip"
		aria-pressed={active}
		aria-expanded={open}
		onclick={() => (open = !open)}
	>
		{#if icon}<Icon name={icon} size={14} />{/if}
		<span class="st-chip__text">{label}</span>
		{#if active && onclear}
			<!-- A nested button is not allowed; the clear icon is a separate control below. -->
			<span class="clear-space"></span>
		{:else}
			<Icon name="chevron-down" size={14} />
		{/if}
	</button>
	{#if active && onclear}
		<button
			type="button"
			class="clear"
			aria-label={clearLabel}
			title={clearLabel}
			onclick={onclear}
		>
			<Icon name="x" size={12} />
		</button>
	{/if}
	{#if open}
		<div class="panel st-menu">
			{@render children()}
		</div>
	{/if}
</div>

<style>
	.wrap {
		position: relative;
		display: inline-flex;
		align-items: center;
	}
	.clear-space {
		width: 0.75rem;
	}
	.clear {
		position: absolute;
		inset-inline-end: var(--space-1-5);
		display: grid;
		place-items: center;
		width: 1.125rem;
		height: 1.125rem;
		padding: 0;
		border: 0;
		border-radius: var(--radius-full);
		background: none;
		color: var(--color-accent-text);
		cursor: pointer;
	}
	.clear:hover {
		background: var(--color-surface-active);
	}
	.clear:focus-visible {
		outline: none;
		box-shadow: var(--focus-ring);
	}
	.panel {
		position: absolute;
		top: calc(100% + 4px);
		inset-inline-start: 0;
		gap: var(--space-2);
		padding: var(--space-3);
		min-width: 16rem;
		max-height: none;
		overflow: visible;
		animation: panel-in var(--motion-fast) var(--ease-out);
	}
	@keyframes panel-in {
		from {
			opacity: 0;
			transform: translateY(calc(var(--motion-distance) * -1));
		}
	}
</style>
