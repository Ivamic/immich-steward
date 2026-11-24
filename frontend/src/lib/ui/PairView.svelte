<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  Two images side by side with lines between the details both show (an answer of the `details`
  or `street` module of a worker): enlarged by the buttons under them and scrolled, a line under
  the pointer stands out. Without lines it is just the two images, to compare by eye.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import { m } from '#lib/paraglide/messages.js';
	import Icon from '#lib/ui/Icon.svelte';

	let {
		first,
		second,
		lines = [],
		secondCaption,
		note
	}: {
		first: { src: string; alt: string; caption: string };
		second: { src: string; alt: string; caption?: string };
		/** x, y in the first image and x, y in the second, 0..1 of their sides. */
		lines?: [number, number, number, number][];
		/** The caption of the second image, when it is more than text (links of a source). */
		secondCaption?: Snippet;
		/** Said beside the zoom buttons. */
		note?: Snippet;
	} = $props();

	// The images enlarged: 1 fits both in the window, more is scrolled.
	const ZOOM = { min: 1, max: 4, step: 0.5 };
	let zoom = $state(1);
	// The pair of details under the pointer: it stands out, the others fade.
	let active = $state<number | null>(null);

	let frame = $state<HTMLElement>();
	let firstImage = $state<HTMLImageElement>();
	let secondImage = $state<HTMLImageElement>();
	type Box = { left: number; top: number; width: number; height: number };
	// The two images as they lie in the frame, in its pixels.
	let boxes = $state<{ a: Box; b: Box; frame: Box } | null>(null);

	/** Where an element lies in the frame. By the layout, not by what is on the screen: the
	 * window opens with a scale animation, and measured on the screen meanwhile every point
	 * would be off, the more the farther from the corner of the frame. */
	function placed(element: HTMLElement): Box {
		let left = 0;
		let top = 0;
		for (
			let node: HTMLElement | null = element;
			node && node !== frame;
			node = node.offsetParent as HTMLElement | null
		) {
			left += node.offsetLeft;
			top += node.offsetTop;
		}
		return { left, top, width: element.offsetWidth, height: element.offsetHeight };
	}

	function measure() {
		if (!frame || !firstImage || !secondImage) return;
		if (!firstImage.naturalWidth || !secondImage.naturalWidth) return;
		boxes = {
			a: placed(firstImage),
			b: placed(secondImage),
			frame: { left: 0, top: 0, width: frame.offsetWidth, height: frame.offsetHeight }
		};
	}

	$effect(() => {
		if (!frame) return;
		const observer = new ResizeObserver(measure);
		observer.observe(frame);
		return () => observer.disconnect();
	});

	// Another image in the second place (stepping through a strip): measured anew once loaded.
	$effect(() => {
		void second.src;
		boxes = null;
		active = null;
	});

	const segments = $derived.by(() => {
		if (!boxes) return [];
		const { a, b } = boxes;
		return lines.map(([x1, y1, x2, y2]) => ({
			x1: a.left + x1 * a.width,
			y1: a.top + y1 * a.height,
			x2: b.left + x2 * b.width,
			y2: b.top + y2 * b.height
		}));
	});
</script>

<div class="scroll">
	<div class="frame" bind:this={frame} style:width="{zoom * 100}%">
		<figure>
			<img bind:this={firstImage} src={first.src} alt={first.alt} onload={measure} />
			<figcaption>{first.caption}</figcaption>
		</figure>
		<figure>
			<img bind:this={secondImage} src={second.src} alt={second.alt} onload={measure} />
			<figcaption>
				{#if secondCaption}{@render secondCaption()}{:else}{second.caption}{/if}
			</figcaption>
		</figure>
		{#if boxes && segments.length}
			<svg
				aria-hidden="true"
				width={boxes.frame.width}
				height={boxes.frame.height}
				class:picked={active !== null}
			>
				{#each segments as s, index (index)}
					<!-- A pointer aid only: the same pairs are counted in the note. -->
					<g
						class:active={active === index}
						role="presentation"
						onmouseenter={() => (active = index)}
						onmouseleave={() => (active = null)}
					>
						<!-- Wider than the line it shows, so that it is easy to point at. -->
						<line class="hit" x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} />
						<line class="shown" x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} />
						<circle cx={s.x1} cy={s.y1} r={active === index ? 5 : 2.5} />
						<circle cx={s.x2} cy={s.y2} r={active === index ? 5 : 2.5} />
					</g>
				{/each}
				<!-- Drawn again on top: among many lines the picked one is not covered. -->
				{#if active !== null && segments[active]}
					{@const s = segments[active]}
					<g class="active top">
						<line class="shown" x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} />
						<circle cx={s.x1} cy={s.y1} r="5" />
						<circle cx={s.x2} cy={s.y2} r="5" />
					</g>
				{/if}
			</svg>
		{/if}
	</div>
</div>
<div class="bar">
	<button
		type="button"
		class="st-btn st-btn--ghost st-btn--sm"
		aria-label={m.details_dialog_zoom_out()}
		title={m.details_dialog_zoom_out()}
		disabled={zoom <= ZOOM.min}
		onclick={() => (zoom = Math.max(ZOOM.min, zoom - ZOOM.step))}
	>
		<Icon name="zoom-out" size={16} />
	</button>
	<span class="zoom">{Math.round(zoom * 100)}%</span>
	<button
		type="button"
		class="st-btn st-btn--ghost st-btn--sm"
		aria-label={m.details_dialog_zoom_in()}
		title={m.details_dialog_zoom_in()}
		disabled={zoom >= ZOOM.max}
		onclick={() => (zoom = Math.min(ZOOM.max, zoom + ZOOM.step))}
	>
		<Icon name="zoom-in" size={16} />
	</button>
	{#if note}<p class="note">{@render note()}</p>{/if}
</div>

<style>
	/* Enlarged images are moved by scrolling. */
	.scroll {
		max-height: calc(100vh - 13rem);
		overflow: auto;
	}
	.frame {
		position: relative;
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: var(--space-3);
		align-items: start;
	}
	figure {
		margin: 0;
	}
	img {
		display: block;
		width: 100%;
		height: auto;
		border-radius: var(--radius-sm);
		background: var(--color-surface-sunken);
	}
	figcaption {
		margin-top: var(--space-1);
		font-size: var(--text-sm);
		color: var(--color-text-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	svg {
		position: absolute;
		inset: 0;
		pointer-events: none;
	}
	/* The images under the lines stay clickable and scrollable; only the lines take the pointer. */
	g {
		pointer-events: auto;
		cursor: pointer;
	}
	g.top {
		pointer-events: none;
	}
	.hit {
		stroke: transparent;
		stroke-width: 10;
	}
	.shown {
		stroke: var(--color-accent);
		stroke-width: 1;
		opacity: 0.7;
		pointer-events: none;
	}
	circle {
		fill: var(--color-accent);
		stroke: var(--gray-0);
		stroke-width: 0.75;
	}
	/* One pair picked: it is drawn strong, the rest fade. */
	svg.picked g:not(.active) {
		opacity: 0.2;
	}
	g.active .shown {
		stroke: var(--color-warning-text);
		stroke-width: 2.5;
		opacity: 1;
	}
	g.active circle {
		fill: var(--color-warning-text);
		stroke-width: 1.5;
	}
	.bar {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		margin-top: var(--space-3);
	}
	.zoom {
		min-width: 3rem;
		text-align: center;
		font-size: var(--text-sm);
		font-variant-numeric: tabular-nums;
		color: var(--color-text-muted);
	}
	.note {
		margin: 0 0 0 var(--space-2);
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	/* One image under the other on a narrow screen: the lines still join them. */
	@media (max-width: 40rem) {
		.frame {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
