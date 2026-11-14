<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  Why a suggestion of similar photos is confirmed: the photo and the similar one side by side, with
  lines between the details both show (the answer of the `details` module of a worker).
-->
<script lang="ts">
	import { getDetailPair, thumbnailUrl, type DetailPair } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import Dialog from '#lib/ui/Dialog.svelte';
	import Icon from '#lib/ui/Icon.svelte';

	let {
		assetId,
		other,
		onclose
	}: {
		assetId: string;
		other: { asset_id: string; file_name: string; version?: string | null };
		onclose: () => void;
	} = $props();

	let pair = $state<DetailPair | null>(null);
	let error = $state<string | null>(null);

	$effect(() => {
		getDetailPair(assetId, other.asset_id)
			.then((result) => (pair = result))
			.catch((e) => (error = errorMessage(e)));
	});

	// The photos enlarged: 1 fits both in the window, more is scrolled.
	const ZOOM = { min: 1, max: 4, step: 0.5 };
	let zoom = $state(1);
	// The pair of details under the pointer: it stands out, the others fade.
	let active = $state<number | null>(null);

	let frame = $state<HTMLElement>();
	let first = $state<HTMLImageElement>();
	let second = $state<HTMLImageElement>();
	// The two photos as they lie in the frame, in its pixels.
	let boxes = $state<{ a: DOMRect; b: DOMRect; frame: DOMRect } | null>(null);

	function measure() {
		if (!frame || !first || !second || !first.naturalWidth || !second.naturalWidth) return;
		boxes = {
			a: first.getBoundingClientRect(),
			b: second.getBoundingClientRect(),
			frame: frame.getBoundingClientRect()
		};
	}

	$effect(() => {
		if (!frame) return;
		const observer = new ResizeObserver(measure);
		observer.observe(frame);
		return () => observer.disconnect();
	});

	const segments = $derived.by(() => {
		if (!pair || !boxes) return [];
		const { a, b, frame: f } = boxes;
		return pair.lines.map(([x1, y1, x2, y2]) => ({
			x1: a.left - f.left + x1 * a.width,
			y1: a.top - f.top + y1 * a.height,
			x2: b.left - f.left + x2 * b.width,
			y2: b.top - f.top + y2 * b.height
		}));
	});
</script>

<Dialog title={m.details_dialog_title()} icon="scan-search" full {onclose}>
	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
	<div class="scroll">
		<div class="frame" bind:this={frame} style:width="{zoom * 100}%">
			<figure>
				<img
					bind:this={first}
					src={thumbnailUrl(assetId, 'preview')}
					alt={m.details_dialog_this()}
					onload={measure}
				/>
				<figcaption>{m.details_dialog_this()}</figcaption>
			</figure>
			<figure>
				<img
					bind:this={second}
					src={thumbnailUrl(other.asset_id, 'preview', 0, other.version ?? null)}
					alt={other.file_name}
					onload={measure}
				/>
				<figcaption>{m.details_dialog_other()} · {other.file_name}</figcaption>
			</figure>
			{#if boxes}
				<svg
					aria-hidden="true"
					width={boxes.frame.width}
					height={boxes.frame.height}
					class:picked={active !== null}
				>
					{#each segments as s, index (index)}
						<!-- A pointer aid only: the same pairs are counted in the note below. -->
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
		<p class="note">
			{#if pair}
				{m.details_dialog_note({
					shown: String(pair.lines.length),
					count: String(pair.inliers)
				})}
			{:else if !error}
				{m.details_dialog_loading()}
			{/if}
		</p>
	</div>
</Dialog>

<style>
	/* Enlarged photos are moved by scrolling. */
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
	/* The photos under the lines stay clickable and scrollable; only the lines take the pointer. */
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
	.error {
		margin: 0 0 var(--space-3);
		color: var(--color-danger-text);
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
	/* One photo under the other on a narrow screen: the lines still join them. */
	@media (max-width: 40rem) {
		.frame {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
