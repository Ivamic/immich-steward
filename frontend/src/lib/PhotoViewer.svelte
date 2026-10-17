<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  The photo in full size over the page. A click on the photo switches between "fit the screen"
  and actual size (scrollable); Esc, the close button or a click beside the photo closes it.
-->
<script lang="ts">
	import { m } from '#lib/paraglide/messages.js';

	let { src, alt, onclose }: { src: string; alt: string; onclose: () => void } = $props();

	let dialog: HTMLDialogElement;
	let closeButton: HTMLButtonElement;
	let actualSize = $state(false);
	let loaded = $state(false);

	$effect(() => {
		dialog.showModal();
		// Otherwise the photo gets the focus ring.
		closeButton.focus();
		return () => dialog.close();
	});
</script>

<dialog
	bind:this={dialog}
	aria-label={alt}
	oncancel={(e) => {
		e.preventDefault();
		onclose();
	}}
	onclick={(e) => e.target === e.currentTarget && onclose()}
>
	<div
		class="frame"
		class:actual={actualSize}
		role="presentation"
		onclick={(e) => e.target === e.currentTarget && onclose()}
	>
		{#if !loaded}<p class="loading">{m.photo_viewer_loading()}</p>{/if}
		<button
			type="button"
			class="image"
			title={actualSize ? m.photo_viewer_fit() : m.photo_viewer_actual()}
			onclick={() => (actualSize = !actualSize)}
		>
			<img {src} {alt} onload={() => (loaded = true)} />
		</button>
	</div>
	<button
		bind:this={closeButton}
		type="button"
		class="close"
		aria-label={m.save_dismiss()}
		onclick={onclose}>×</button
	>
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
		background: rgb(0 0 0 / 0.92);
	}
	dialog::backdrop {
		background: transparent;
	}
	.frame {
		width: 100%;
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.frame.actual {
		display: block;
		overflow: auto;
	}
	.image {
		padding: 0;
		border: none;
		background: none;
		cursor: zoom-in;
	}
	.frame:not(.actual) img {
		display: block;
		max-width: 100vw;
		max-height: 100vh;
	}
	.frame.actual .image {
		cursor: zoom-out;
	}
	.frame.actual img {
		display: block;
		max-width: none;
	}
	.loading {
		position: absolute;
		color: #fff;
	}
	.close {
		position: fixed;
		top: 0.75rem;
		right: 1rem;
		border: none;
		background: rgb(0 0 0 / 0.5);
		color: #fff;
		font-size: 2rem;
		line-height: 1;
		padding: 0.2rem 0.6rem;
		border-radius: 0.4rem;
		cursor: pointer;
	}
</style>
