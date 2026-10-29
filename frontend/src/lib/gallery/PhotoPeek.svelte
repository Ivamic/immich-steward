<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- The large preview of a long press on a tile: over the gallery, until the pointer is let go
     (or Esc). The thumbnail, already loaded, stands in until the preview arrives. A video plays at
     once, in a loop: muted, or with its sound when so set and the browser lets it. -->
<script lang="ts">
	import { accountSettings } from '#lib/accountSettings.svelte.js';
	import { thumbnailUrl, videoUrl, type AssetItem } from '#lib/api.js';
	import { takenTitle } from './month.js';

	let { item, onclose }: { item: AssetItem; onclose: () => void } = $props();

	let loaded = $state(false);
	let player = $state<HTMLVideoElement>();

	// Not the autoplay attribute: a browser that refuses the sound would not start it at all.
	$effect(() => {
		if (!player) return;
		const video = player;
		video.muted = !accountSettings.values.video_sound;
		video.play().catch(() => {
			video.muted = true;
			video.play().catch(() => {});
		});
	});
	// Width over height; 4:3 while unknown.
	const ratio = $derived(item.width && item.height ? item.width / item.height : 4 / 3);
</script>

<svelte:window
	onpointerup={onclose}
	onpointercancel={onclose}
	onkeydown={(e) => {
		if (e.key === 'Escape') {
			e.preventDefault();
			onclose();
		}
	}}
	onwheel={onclose}
/>

<div class="peek" role="dialog" aria-modal="true" aria-label={item.file_name}>
	<figure>
		<div class="frame" style:--ratio={ratio}>
			<img class="small" src={thumbnailUrl(item.id, 'thumbnail', 0, item.version)} alt="" />
			{#if item.type === 'VIDEO'}
				<!-- Videos of a library have no captions to offer. -->
				<!-- svelte-ignore a11y_media_has_caption -->
				<video
					bind:this={player}
					class="large"
					class:loaded
					src={videoUrl(item.id)}
					poster={thumbnailUrl(item.id, 'preview', 0, item.version)}
					loop
					playsinline
					aria-label={item.file_name}
					onloadeddata={() => (loaded = true)}
				></video>
			{:else}
				<img
					class="large"
					class:loaded
					src={thumbnailUrl(item.id, 'preview', 0, item.version)}
					alt={item.file_name}
					onload={() => (loaded = true)}
				/>
			{/if}
		</div>
		<figcaption>
			<span>{takenTitle(item.local_taken_at)}</span>
			<span class="name">{item.file_name}</span>
		</figcaption>
	</figure>
</div>

<style>
	.peek {
		position: fixed;
		inset: 0;
		z-index: var(--z-dialog);
		display: grid;
		place-items: center;
		padding: 5vmin;
		background: oklch(0 0 0 / 0.72);
		user-select: none;
		-webkit-touch-callout: none;
		animation: peek-in var(--motion-fast) var(--ease-out);
	}
	figure {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-2);
		max-width: 100%;
		max-height: 100%;
		margin: 0;
	}
	.frame {
		position: relative;
		/* As large as fits: 90 % of the width, or of the height less the caption. */
		width: min(90vw, calc((90vh - 3rem) * var(--ratio)));
		aspect-ratio: var(--ratio);
		border-radius: var(--radius-md);
		overflow: hidden;
		background: var(--gray-900);
		box-shadow: var(--shadow-lg);
	}
	img,
	video {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: contain;
		pointer-events: none;
	}
	.small {
		filter: blur(6px);
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
		flex-wrap: wrap;
		justify-content: center;
		gap: var(--space-1) var(--space-3);
		color: var(--gray-0);
		font-size: var(--text-sm);
	}
	.name {
		opacity: 0.75;
	}
	@keyframes peek-in {
		from {
			opacity: 0;
		}
	}
</style>
