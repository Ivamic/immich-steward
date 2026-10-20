<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  Choosing a part of the photo for a module to look at (FR-35). The photo fills the window;
  the wheel zooms where the pointer is, dragging draws a frame, its corners and inside move it.
  The photo moves with the right or middle button, or while Space is held.
-->
<script lang="ts">
	import type { Region } from '#lib/api.js';
	import { m } from '#lib/paraglide/messages.js';
	import { untrack } from 'svelte';

	let {
		src,
		alt,
		initial = null,
		onrun,
		onclose
	}: {
		src: string;
		alt: string;
		/** The part chosen last time, to adjust. */
		initial?: Region | null;
		onrun: (region: Region) => void;
		onclose: () => void;
	} = $props();

	// Parts smaller than this (px of the photo) are too small to recognize anything.
	const MIN_PART_PX = 64;
	const HANDLE_PX = 14; // how close to a corner grabs it
	const MAX_ZOOM = 8; // times the size that fits the window

	type Point = { x: number; y: number }; // shares of the photo's width and height
	type Drag =
		| { kind: 'draw'; anchor: Point }
		| { kind: 'move'; start: Point; base: Region }
		// A side of the frame: only the width or only the height changes; `fixed` is the
		// opposite side.
		| { kind: 'side'; axis: 'x' | 'y'; fixed: number; base: Region }
		| { kind: 'pan'; x: number; y: number; ox: number; oy: number };

	let dialog: HTMLDialogElement;
	let stage = $state<HTMLDivElement>();
	let stageWidth = $state(0);
	let stageHeight = $state(0);
	let natural = $state<{ w: number; h: number } | null>(null);
	// Photo px -> stage px: offset + scale * px.
	let scale = $state(1);
	let ox = $state(0);
	let oy = $state(0);
	// Starts from the part chosen last time; later changes of the prop do not matter.
	let region = $state<Region | null>(untrack(() => initial));
	let drag: Drag | null = null;
	let spaceHeld = $state(false);
	let cursor = $state('crosshair');

	const fitScale = $derived(
		natural ? Math.min(stageWidth / natural.w, stageHeight / natural.h) : 1
	);
	const frame = $derived(
		region && natural
			? {
					left: ox + region.x * natural.w * scale,
					top: oy + region.y * natural.h * scale,
					width: region.w * natural.w * scale,
					height: region.h * natural.h * scale
				}
			: null
	);
	const partPx = $derived(
		region && natural
			? { w: Math.round(region.w * natural.w), h: Math.round(region.h * natural.h) }
			: null
	);
	const tooSmall = $derived(partPx !== null && Math.min(partPx.w, partPx.h) < MIN_PART_PX);

	$effect(() => {
		dialog.showModal();
		return () => dialog.close();
	});

	function fit() {
		if (!natural) return;
		scale = fitScale;
		ox = (stageWidth - natural.w * scale) / 2;
		oy = (stageHeight - natural.h * scale) / 2;
	}

	function onload(event: Event) {
		const image = event.currentTarget as HTMLImageElement;
		natural = { w: image.naturalWidth, h: image.naturalHeight };
		fit();
	}

	const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));

	function pointAt(event: PointerEvent | WheelEvent): Point {
		const box = stage!.getBoundingClientRect();
		return {
			x: clamp((event.clientX - box.left - ox) / (scale * natural!.w), 0, 1),
			y: clamp((event.clientY - box.top - oy) / (scale * natural!.h), 0, 1)
		};
	}

	// Handles at the corners and in the middle of the sides, as shares of the frame.
	const HANDLES = [
		[0, 0, 'nwse-resize'],
		[1, 1, 'nwse-resize'],
		[1, 0, 'nesw-resize'],
		[0, 1, 'nesw-resize'],
		[0.5, 0, 'ns-resize'],
		[0.5, 1, 'ns-resize'],
		[0, 0.5, 'ew-resize'],
		[1, 0.5, 'ew-resize']
	] as const;

	/** What dragging the handle under the pointer does: a corner keeps the opposite one in
	 *  place, a side keeps the opposite side. */
	function grabbedHandle(event: PointerEvent): { drag: Drag; cursor: string } | null {
		if (!frame || !region || !stage) return null;
		const box = stage.getBoundingClientRect();
		const x = event.clientX - box.left;
		const y = event.clientY - box.top;
		for (const [hx, hy, handleCursor] of HANDLES) {
			const px = frame.left + hx * frame.width;
			const py = frame.top + hy * frame.height;
			if (Math.abs(x - px) > HANDLE_PX || Math.abs(y - py) > HANDLE_PX) continue;
			const base = region;
			const drag: Drag =
				hx === 0.5
					? { kind: 'side', axis: 'y', fixed: base.y + (1 - hy) * base.h, base }
					: hy === 0.5
						? { kind: 'side', axis: 'x', fixed: base.x + (1 - hx) * base.w, base }
						: {
								kind: 'draw',
								anchor: { x: base.x + (1 - hx) * base.w, y: base.y + (1 - hy) * base.h }
							};
			return { drag, cursor: handleCursor };
		}
		return null;
	}

	const inside = (p: Point, r: Region) =>
		p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h;

	const between = (a: Point, b: Point): Region => ({
		x: Math.min(a.x, b.x),
		y: Math.min(a.y, b.y),
		w: Math.abs(a.x - b.x),
		h: Math.abs(a.y - b.y)
	});

	function onpointerdown(event: PointerEvent) {
		if (!natural || !stage) return;
		stage.setPointerCapture(event.pointerId);
		if (event.button === 1 || event.button === 2 || spaceHeld) {
			drag = { kind: 'pan', x: event.clientX, y: event.clientY, ox, oy };
			return;
		}
		if (event.button !== 0) return;
		const point = pointAt(event);
		const handle = grabbedHandle(event);
		if (handle) drag = handle.drag;
		else if (region && inside(point, region)) drag = { kind: 'move', start: point, base: region };
		else {
			drag = { kind: 'draw', anchor: point };
			region = null;
		}
	}

	function onpointermove(event: PointerEvent) {
		if (!natural) return;
		if (!drag) {
			const point = pointAt(event);
			cursor = spaceHeld
				? 'grab'
				: (grabbedHandle(event)?.cursor ??
					(region && inside(point, region) ? 'move' : 'crosshair'));
			return;
		}
		if (drag.kind === 'pan') {
			ox = drag.ox + event.clientX - drag.x;
			oy = drag.oy + event.clientY - drag.y;
		} else if (drag.kind === 'draw') {
			region = between(drag.anchor, pointAt(event));
		} else if (drag.kind === 'side') {
			const point = pointAt(event);
			const { base, fixed } = drag;
			region =
				drag.axis === 'x'
					? { ...base, x: Math.min(fixed, point.x), w: Math.abs(point.x - fixed) }
					: { ...base, y: Math.min(fixed, point.y), h: Math.abs(point.y - fixed) };
		} else {
			const point = pointAt(event);
			const { base } = drag;
			region = {
				...base,
				x: clamp(base.x + point.x - drag.start.x, 0, 1 - base.w),
				y: clamp(base.y + point.y - drag.start.y, 0, 1 - base.h)
			};
		}
	}

	function onpointerup() {
		drag = null;
		if (region && (region.w === 0 || region.h === 0)) region = null;
	}

	/** Zooms in or out keeping the spot under the pointer in place. */
	function onwheel(event: WheelEvent) {
		if (!natural || !stage) return;
		event.preventDefault();
		const box = stage.getBoundingClientRect();
		const cx = event.clientX - box.left;
		const cy = event.clientY - box.top;
		const next = clamp(scale * Math.exp(-event.deltaY * 0.0015), fitScale, fitScale * MAX_ZOOM);
		ox = cx - ((cx - ox) / scale) * next;
		oy = cy - ((cy - oy) / scale) * next;
		scale = next;
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key !== ' ') return;
		event.preventDefault(); // no page scrolling, no button press
		spaceHeld = true;
		cursor = 'grab';
	}

	function onkeyup(event: KeyboardEvent) {
		if (event.key === ' ') spaceHeld = false;
	}

	function run() {
		if (!region) return;
		// Rounded, and kept inside the photo after rounding.
		const r = (value: number) => Math.round(value * 10_000) / 10_000;
		const x = r(region.x);
		const y = r(region.y);
		onrun({ x, y, w: Math.min(r(region.w), 1 - x), h: Math.min(r(region.h), 1 - y) });
	}
</script>

<dialog
	bind:this={dialog}
	aria-label={m.region_title()}
	oncancel={(e) => {
		e.preventDefault();
		onclose();
	}}
	{onkeydown}
	{onkeyup}
>
	<header>
		<h2>{m.region_title()}</h2>
		<p class="muted">{m.region_hint()}</p>
	</header>

	<div
		class="stage"
		role="application"
		aria-label={alt}
		bind:this={stage}
		bind:clientWidth={stageWidth}
		bind:clientHeight={stageHeight}
		style:cursor
		{onpointerdown}
		{onpointermove}
		{onpointerup}
		onpointercancel={onpointerup}
		{onwheel}
		oncontextmenu={(e) => e.preventDefault()}
	>
		{#if !natural}<p class="loading">{m.photo_viewer_loading()}</p>{/if}
		<img
			{src}
			{alt}
			draggable="false"
			{onload}
			style:transform="translate({ox}px, {oy}px) scale({scale})"
			style:visibility={natural ? 'visible' : 'hidden'}
		/>
		{#if frame}
			<div
				class="frame"
				style:left="{frame.left}px"
				style:top="{frame.top}px"
				style:width="{frame.width}px"
				style:height="{frame.height}px"
			>
				<span class="handle nw"></span><span class="handle ne"></span>
				<span class="handle sw"></span><span class="handle se"></span>
				<span class="handle n"></span><span class="handle s"></span>
				<span class="handle w"></span><span class="handle e"></span>
			</div>
		{/if}
	</div>

	<footer>
		<span class="size" class:warning={tooSmall} role="status">
			{#if partPx}
				{tooSmall
					? m.region_too_small({ w: String(partPx.w), h: String(partPx.h) })
					: m.region_size({ w: String(partPx.w), h: String(partPx.h) })}
			{:else}
				{m.region_none()}
			{/if}
		</span>
		<span class="spacer"></span>
		<button type="button" onclick={fit}>{m.region_fit()}</button>
		<button type="button" disabled={!region} onclick={() => (region = null)}>
			{m.region_reset()}
		</button>
		<button type="button" onclick={onclose}>{m.region_cancel()}</button>
		<button type="button" class="primary" disabled={!region} onclick={run}>
			{m.region_run()}
		</button>
	</footer>
</dialog>

<style>
	dialog {
		width: 100vw;
		height: 100vh;
		max-width: none;
		max-height: none;
		margin: 0;
		padding: 0;
		border: none;
		display: flex;
		flex-direction: column;
		background: #111;
		color: #eee;
	}
	dialog::backdrop {
		background: rgb(0 0 0 / 0.85);
	}
	header,
	footer {
		display: flex;
		align-items: baseline;
		flex-wrap: wrap;
		gap: 0.5rem 1rem;
		padding: 0.6rem 1rem;
	}
	h2 {
		margin: 0;
		font-size: 1.05rem;
	}
	header p {
		margin: 0;
		font-size: 0.85rem;
	}
	.muted {
		opacity: 0.75;
	}
	.stage {
		position: relative;
		flex: 1;
		overflow: hidden;
		touch-action: none;
		user-select: none;
	}
	.stage img {
		position: absolute;
		left: 0;
		top: 0;
		max-width: none;
		transform-origin: 0 0;
		pointer-events: none;
	}
	.loading {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
		margin: 0;
	}
	/* The photo outside the frame is darkened. */
	.frame {
		position: absolute;
		outline: 2px solid #fff;
		box-shadow: 0 0 0 100vmax rgb(0 0 0 / 0.55);
		pointer-events: none;
	}
	.handle {
		position: absolute;
		width: 10px;
		height: 10px;
		background: #fff;
		border: 1px solid #333;
	}
	.nw {
		left: -6px;
		top: -6px;
	}
	.ne {
		right: -6px;
		top: -6px;
	}
	.sw {
		left: -6px;
		bottom: -6px;
	}
	.se {
		right: -6px;
		bottom: -6px;
	}
	.n,
	.s {
		left: calc(50% - 6px);
	}
	.n {
		top: -6px;
	}
	.s {
		bottom: -6px;
	}
	.w,
	.e {
		top: calc(50% - 6px);
	}
	.w {
		left: -6px;
	}
	.e {
		right: -6px;
	}
	.spacer {
		flex: 1;
	}
	.size {
		font-size: 0.85rem;
	}
	.warning {
		color: #ffb86b;
	}
	.primary {
		font-weight: 600;
	}
</style>
