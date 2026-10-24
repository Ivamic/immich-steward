<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Short hint over a control, shown on hover after a pause and on keyboard focus. It never takes
     pointer events, so in a dense row it cannot cover the neighbor the pointer moves to. The
     wrapped control keeps its own aria-label: the tooltip is for sighted mouse users. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import Kbd from './Kbd.svelte';

	let {
		text,
		keys,
		below = false,
		end = false,
		children
	}: {
		text: string;
		/** Keyboard shortcut shown after the text. */
		keys?: string;
		/** Below the control (for controls at the top edge of the page). */
		below?: boolean;
		/** Lined up with the end of the control (for controls at the end of a row). */
		end?: boolean;
		children: Snippet;
	} = $props();
</script>

<span class="st-tipwrap" class:st-tipwrap--bottom={below} class:end>
	{@render children()}
	<span class="st-tooltip" aria-hidden="true">
		{text}
		{#if keys}<Kbd>{keys}</Kbd>{/if}
	</span>
</span>

<style>
	/* Centered under a control at the window edge, the tooltip would stick out of the page. */
	.end > :global(.st-tooltip) {
		left: auto;
		right: 0;
		transform: none;
	}
</style>
