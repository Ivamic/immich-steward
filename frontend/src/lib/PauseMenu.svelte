<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Pause of a worker module (or of all, `module` null): until resumed or for a while; when
     paused, the button resumes. The list closes on a click outside it and on Esc. -->
<script lang="ts">
	import { m } from '#lib/paraglide/messages.js';
	import { PAUSE_LENGTHS } from '#lib/pause.svelte.js';
	import Icon from '#lib/ui/Icon.svelte';

	let {
		paused,
		disabled = false,
		align = 'left',
		pauseLabel,
		resumeLabel,
		onpause,
		onresume
	}: {
		paused: boolean;
		disabled?: boolean;
		/** The side of the button the list of lengths lines up with. */
		align?: 'left' | 'right';
		pauseLabel: string;
		resumeLabel: string;
		onpause: (minutes: number | null) => void;
		onresume: () => void;
	} = $props();

	let open = $state(false);
	let menu: HTMLDetailsElement | undefined = $state();

	function lengthLabel(minutes: number | null): string {
		switch (minutes) {
			case null:
				return m.pause_until_resumed();
			case 30:
				return m.pause_for_30m();
			case 60:
				return m.pause_for_1h();
			case 12 * 60:
				return m.pause_for_12h();
			default:
				return m.pause_for_1d();
		}
	}

	function closeOutside(event: PointerEvent) {
		if (open && menu && !menu.contains(event.target as Node)) open = false;
	}

	function closeOnEscape(event: KeyboardEvent) {
		if (!open || event.key !== 'Escape') return;
		event.preventDefault();
		open = false;
		menu?.querySelector('summary')?.focus();
	}

	function choose(minutes: number | null) {
		open = false;
		onpause(minutes);
	}
</script>

<svelte:window onpointerdown={closeOutside} onkeydown={closeOnEscape} />

{#if paused}
	<button type="button" class="st-btn st-btn--sm" {disabled} onclick={onresume}>
		<Icon name="play" size={14} />
		{resumeLabel}
	</button>
{:else}
	<details class="menu" bind:open bind:this={menu}>
		<summary class="st-btn st-btn--sm" class:disabled>
			<Icon name="pause" size={14} />
			{pauseLabel}
			<Icon name="chevron-down" size={14} />
		</summary>
		<ul class="st-menu" class:right={align === 'right'}>
			{#each PAUSE_LENGTHS as minutes (minutes)}
				<li>
					<button type="button" class="st-menu__item" {disabled} onclick={() => choose(minutes)}>
						{lengthLabel(minutes)}
					</button>
				</li>
			{/each}
		</ul>
	</details>
{/if}

<style>
	.menu {
		position: relative;
		display: inline-block;
	}
	summary {
		list-style: none;
	}
	summary::-webkit-details-marker {
		display: none;
	}
	summary.disabled {
		pointer-events: none;
		opacity: 0.5;
	}
	ul {
		position: absolute;
		top: calc(100% + 4px);
		left: 0;
		margin: 0;
		list-style: none;
		animation: menu-in var(--motion-fast) var(--ease-out);
	}
	ul.right {
		right: 0;
		left: auto;
	}
	li button {
		width: 100%;
	}
	@keyframes menu-in {
		from {
			opacity: 0;
			transform: translateY(calc(var(--motion-distance) * -1));
		}
	}
</style>
