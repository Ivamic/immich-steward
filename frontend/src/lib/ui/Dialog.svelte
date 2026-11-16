<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- A modal window over the page (native <dialog>: focus stays inside, Esc closes it). Closes
     also on the close button and on a click beside the window. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import { m } from '#lib/paraglide/messages.js';
	import Icon from './Icon.svelte';
	import type { IconName } from './icons.js';

	let {
		title,
		icon,
		wide = false,
		full = false,
		onclose,
		children,
		footer
	}: {
		title: string;
		icon?: IconName;
		wide?: boolean;
		/** As large as the window allows: for looking at photos. */
		full?: boolean;
		onclose: () => void;
		children: Snippet;
		footer?: Snippet;
	} = $props();

	let dialog: HTMLDialogElement;
	// The press of the current click was beside the window (on the backdrop).
	let pressedBeside = false;

	$effect(() => {
		dialog.showModal();
		return () => dialog.close();
	});
</script>

<dialog
	bind:this={dialog}
	class="st-dialog"
	class:st-dialog--wide={wide}
	class:st-dialog--full={full}
	aria-label={title}
	oncancel={(e) => {
		e.preventDefault();
		onclose();
	}}
	onkeydown={(e) => {
		// Esc closes the window only, not what the page does with it (e.g. clear the choice).
		if (e.key === 'Escape') e.stopPropagation();
	}}
	onpointerdown={(e) => (pressedBeside = e.target === e.currentTarget)}
	onclick={(e) => {
		// Only a click that also began beside the window: selecting text in it and letting go
		// outside it is not one.
		if (pressedBeside && e.target === e.currentTarget) onclose();
		pressedBeside = false;
	}}
>
	<div class="st-dialog__head">
		{#if icon}<span class="st-dialog__icon"><Icon name={icon} /></span>{/if}
		<h2 class="st-dialog__title">{title}</h2>
		<button
			type="button"
			class="st-iconbtn st-iconbtn--sm"
			aria-label={m.save_dismiss()}
			onclick={onclose}
		>
			<Icon name="x" />
		</button>
	</div>
	<div class="st-dialog__body">{@render children()}</div>
	{#if footer}<div class="st-dialog__foot">{@render footer()}</div>{/if}
</dialog>

<style>
	dialog {
		padding: 0;
	}
	dialog::backdrop {
		background: var(--color-scrim);
		animation: st-fade var(--motion-base) var(--ease-out);
	}
</style>
