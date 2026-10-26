<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copies a text with a click: the icon turns into a check for a moment. When the browser refuses
     (rare, see clipboard.ts), `onfailed` lets the caller select the text, and the button says to
     press Ctrl+C. -->
<script lang="ts">
	import { copyText } from '#lib/clipboard.js';
	import { m } from '#lib/paraglide/messages.js';
	import Icon from '#lib/ui/Icon.svelte';

	const SHOWN_MS = 1500;

	let {
		text,
		label = m.copy(),
		onfailed
	}: {
		text: string;
		label?: string;
		/** The copy failed: select the text so that Ctrl+C copies it. */
		onfailed?: () => void;
	} = $props();

	let state = $state<'idle' | 'copied' | 'failed'>('idle');
	let timer: ReturnType<typeof setTimeout> | undefined;

	async function copy(event: MouseEvent) {
		// Inside a label, the click would also focus the field.
		event.preventDefault();
		clearTimeout(timer);
		state = (await copyText(text)) ? 'copied' : 'failed';
		if (state === 'failed') onfailed?.();
		timer = setTimeout(() => (state = 'idle'), state === 'failed' ? 4 * SHOWN_MS : SHOWN_MS);
	}

	$effect(() => () => clearTimeout(timer));

	const title = $derived(
		state === 'copied' ? m.copy_done() : state === 'failed' ? m.copy_failed() : label
	);
</script>

<button
	type="button"
	class="st-iconbtn st-iconbtn--sm"
	class:copied={state === 'copied'}
	aria-label={title}
	{title}
	onclick={copy}
>
	<Icon name={state === 'copied' ? 'check' : 'copy'} />
</button>
<span class="status" role="status">
	{state === 'idle' ? '' : title}
</span>

<style>
	.copied {
		color: var(--color-success-text);
	}
	/* For screen readers only. */
	.status {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
		white-space: nowrap;
	}
</style>
