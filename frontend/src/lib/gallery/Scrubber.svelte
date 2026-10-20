<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  Timeline scrubber on the right edge, like in Immich: year labels and month ticks placed in
  proportion to where the months are in the page. Hovering shows the month, clicking or
  dragging scrolls there.
-->
<script lang="ts">
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import { scrubberMarks, type Segment } from './scrubber.js';

	let { timeline }: { timeline: HTMLElement } = $props();

	let bar = $state<HTMLElement>();
	let barHeight = $state(0);
	let segments = $state<Segment[]>([]);
	let total = $state(1);
	let scrollRatio = $state(0);
	let hover = $state<{ y: number; month: string } | null>(null);
	let dragging = false;

	const monthLabel = (month: string) =>
		new Intl.DateTimeFormat(getLocale(), { month: 'long', year: 'numeric' }).format(
			new Date(`${month}-01T00:00:00`)
		);

	function measure() {
		const base = timeline.offsetTop;
		segments = [...timeline.querySelectorAll<HTMLElement>('[data-month]')].map((el) => ({
			month: el.dataset.month ?? '',
			top: el.offsetTop - base,
			height: el.offsetHeight
		}));
		total = Math.max(1, timeline.offsetHeight);
		updateScroll();
	}

	function updateScroll() {
		const position = window.scrollY - timeline.offsetTop + window.innerHeight * 0.2;
		scrollRatio = Math.min(1, Math.max(0, position / total));
	}

	const toY = (px: number) => (px / total) * barHeight;

	const marks = $derived(scrubberMarks(segments, toY));

	function segmentAt(clientY: number): Segment | undefined {
		if (!bar) return undefined;
		const px = ((clientY - bar.getBoundingClientRect().top) / barHeight) * total;
		return segments.findLast((s) => s.top <= px) ?? segments[0];
	}

	function scrollToPointer(clientY: number) {
		if (!bar) return;
		const ratio = Math.min(1, Math.max(0, (clientY - bar.getBoundingClientRect().top) / barHeight));
		window.scrollTo({ top: timeline.offsetTop + ratio * total - window.innerHeight * 0.2 });
	}

	function onpointermove(event: PointerEvent) {
		const segment = segmentAt(event.clientY);
		if (segment && bar) {
			hover = { y: event.clientY - bar.getBoundingClientRect().top, month: segment.month };
		}
		if (dragging) scrollToPointer(event.clientY);
	}

	function onpointerdown(event: PointerEvent) {
		dragging = true;
		bar?.setPointerCapture(event.pointerId);
		scrollToPointer(event.clientY);
	}

	$effect(() => {
		measure();
		// Month heights change when their photos load; re-measure on any size change.
		const observer = new ResizeObserver(measure);
		observer.observe(timeline);
		window.addEventListener('scroll', updateScroll, { passive: true });
		window.addEventListener('resize', measure);
		return () => {
			observer.disconnect();
			window.removeEventListener('scroll', updateScroll);
			window.removeEventListener('resize', measure);
		};
	});
</script>

<div
	class="scrubber"
	role="scrollbar"
	aria-controls="timeline"
	aria-orientation="vertical"
	aria-valuenow={Math.round(scrollRatio * 100)}
	aria-label={m.gallery_scrubber()}
	tabindex="-1"
	bind:this={bar}
	bind:clientHeight={barHeight}
	{onpointermove}
	{onpointerdown}
	onpointerup={() => (dragging = false)}
	onpointerleave={() => (hover = null)}
>
	{#each marks.dots as y (y)}
		<span class="dot" style:top="{y}px"></span>
	{/each}
	{#each marks.years as label (label.year)}
		<span class="year" style:top="{label.y}px">{label.year}</span>
	{/each}
	<span class="position" style:top="{scrollRatio * barHeight}px"></span>
	{#if hover}
		<span class="hover-line" style:top="{hover.y}px"></span>
		<span class="hover-label" style:top="{hover.y}px">{monthLabel(hover.month)}</span>
	{/if}
</div>

<style>
	.scrubber {
		position: fixed;
		top: 4.5rem;
		bottom: 1rem;
		right: 0;
		width: 3.25rem;
		cursor: row-resize;
		user-select: none;
		touch-action: none;
		z-index: 10;
	}
	/* Dots and labels end at the bottom of their month, as in Immich. */
	.dot {
		position: absolute;
		right: 0.5rem;
		width: 4px;
		height: 4px;
		border-radius: 50%;
		transform: translateY(-100%);
		background: currentColor;
		opacity: 0.3;
	}
	.year {
		position: absolute;
		right: 1.1rem;
		transform: translateY(-100%);
		font-family: ui-monospace, monospace;
		font-size: 0.75rem;
		line-height: 1;
		opacity: 0.8;
	}
	.position {
		position: absolute;
		right: 0;
		width: 100%;
		height: 2px;
		background: #0969da;
	}
	.hover-line {
		position: absolute;
		right: 0;
		width: 100%;
		height: 1px;
		background: #cf222e;
	}
	.hover-label {
		position: absolute;
		right: 3.5rem;
		transform: translateY(-50%);
		white-space: nowrap;
		padding: 0.2rem 0.5rem;
		border-radius: 0.25rem;
		font-size: 0.8rem;
		color: white;
		background: rgb(0 0 0 / 0.8);
		pointer-events: none;
	}
</style>
