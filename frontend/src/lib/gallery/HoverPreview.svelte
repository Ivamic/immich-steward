<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- A larger look at a small thumbnail while the mouse is over it: below it, or above it near the
     bottom of the window, never past the edges. The thumbnail, already loaded, stands in until
     the preview arrives. -->
<script lang="ts">
	import { thumbnailUrl, type AssetItem } from '#lib/api.js';
	import { takenTitle } from './month.js';

	// The long side of the photo, px.
	const SIZE = 256;
	const GAP = 6;
	const MARGIN = 8;
	// Room for the caption under the photo.
	const CAPTION = 40;

	let { item, anchor }: { item: AssetItem; anchor: DOMRect } = $props();

	let loaded = $state(false);
	// Width over height; 4:3 while unknown.
	const ratio = $derived(item.width && item.height ? item.width / item.height : 4 / 3);
	const width = $derived(ratio >= 1 ? SIZE : Math.round(SIZE * ratio));
	const height = $derived(ratio >= 1 ? Math.round(SIZE / ratio) : SIZE);
	const left = $derived(
		Math.max(
			MARGIN,
			Math.min(anchor.left + anchor.width / 2 - width / 2, innerWidth - width - MARGIN)
		)
	);
	const top = $derived(
		anchor.bottom + GAP + height + CAPTION <= innerHeight - MARGIN
			? anchor.bottom + GAP
			: Math.max(MARGIN, anchor.top - GAP - height - CAPTION)
	);
</script>

<figure class="hover" style:left="{left}px" style:top="{top}px" style:width="{width}px">
	<div class="frame" style:height="{height}px">
		<img class="small" src={thumbnailUrl(item.id, 'thumbnail', 0, item.version)} alt="" />
		<img
			class="large"
			class:loaded
			src={thumbnailUrl(item.id, 'preview', 0, item.version)}
			alt={item.file_name}
			onload={() => (loaded = true)}
		/>
	</div>
	<figcaption>
		<span>{takenTitle(item.local_taken_at)}</span>
		<span class="name">{item.file_name}</span>
	</figcaption>
</figure>

<style>
	.hover {
		position: fixed;
		z-index: var(--z-tooltip);
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		margin: 0;
		padding: var(--space-1);
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface-raised);
		box-shadow: var(--shadow-md);
		pointer-events: none;
		animation: hover-in var(--motion-fast) var(--ease-out);
	}
	.frame {
		position: relative;
		overflow: hidden;
		border-radius: var(--radius-sm);
		background: var(--color-stage);
	}
	img {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: contain;
	}
	.small {
		filter: blur(4px);
	}
	.large {
		opacity: 0;
		transition: opacity var(--motion-fast);
	}
	.large.loaded {
		opacity: 1;
	}
	figcaption {
		display: flex;
		flex-direction: column;
		padding-inline: var(--space-1);
		font-size: var(--text-xs);
		line-height: var(--leading-snug);
	}
	figcaption span {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.name {
		color: var(--color-text-muted);
	}
	@keyframes hover-in {
		from {
			opacity: 0;
		}
	}
</style>
