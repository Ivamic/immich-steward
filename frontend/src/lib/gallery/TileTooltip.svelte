<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- What a tile is, on hovering it with a mouse: the file name, when it was taken, the camera,
     the size. Below the tile, or above it near the bottom of the window; it goes on scrolling. -->
<script lang="ts">
	import type { AssetItem } from '#lib/api.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import { cameraName } from '#lib/suggestions/format.js';
	import { takenTitle } from './month.js';

	const GAP = 6;
	const MARGIN = 8;

	let { item, anchor, onclose }: { item: AssetItem; anchor: DOMRect; onclose: () => void } =
		$props();

	let box = $state<HTMLDivElement>();
	let position = $state({ left: 0, top: 0, ready: false });

	const camera = $derived(cameraName(item.camera_make, item.camera_model));
	const size = $derived.by(() => {
		if (!item.width || !item.height) return null;
		const megapixels = new Intl.NumberFormat(getLocale(), { maximumFractionDigits: 1 }).format(
			(item.width * item.height) / 1e6
		);
		return `${item.width} × ${item.height} · ${m.asset_megapixels({ value: megapixels })}`;
	});

	$effect(() => {
		if (!box) return;
		const { width, height } = box.getBoundingClientRect();
		const below = anchor.bottom + GAP + height <= window.innerHeight - MARGIN;
		const left = anchor.left + anchor.width / 2 - width / 2;
		position = {
			left: Math.min(Math.max(MARGIN, left), window.innerWidth - width - MARGIN),
			top: below ? anchor.bottom + GAP : Math.max(MARGIN, anchor.top - GAP - height),
			ready: true
		};
	});
</script>

<svelte:window onscroll={onclose} onresize={onclose} />

<div
	bind:this={box}
	class="st-tooltip tip"
	role="tooltip"
	style:left="{position.left}px"
	style:top="{position.top}px"
	style:visibility={position.ready ? 'visible' : 'hidden'}
>
	<span class="name">{item.file_name}</span>
	<span>{takenTitle(item.local_taken_at)}</span>
	{#if camera}<span>{camera}</span>{/if}
	{#if size}<span class="muted">{size}</span>{/if}
</div>

<style>
	/* The colors of the other tooltips (.st-tooltip), a line per fact. */
	.tip {
		position: fixed;
		flex-direction: column;
		align-items: flex-start;
		gap: 1px;
		padding: var(--space-1-5) var(--space-2);
		font-size: var(--text-sm);
		pointer-events: none;
	}
	.name {
		font-weight: 600;
		overflow-wrap: anywhere;
	}
	.muted {
		opacity: 0.75;
		font-variant-numeric: tabular-nums;
	}
</style>
