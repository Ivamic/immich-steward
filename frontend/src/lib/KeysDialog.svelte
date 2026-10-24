<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Keyboard shortcuts of the photo card (opened with "?"). -->
<script lang="ts">
	import { m } from '#lib/paraglide/messages.js';
	import Dialog from '#lib/ui/Dialog.svelte';
	import Kbd from '#lib/ui/Kbd.svelte';

	let { onclose }: { onclose: () => void } = $props();

	const rows: [string[], () => string][] = [
		[['1–9'], m.keys_choose],
		[['Enter'], m.keys_save],
		[['←', '→'], m.keys_previous_next],
		[['S'], m.keys_skip],
		[['N'], m.keys_not_applicable],
		[['U'], m.keys_back_to_todo],
		[['Z'], m.keys_zoom],
		[['R'], m.keys_part],
		[['[', ']'], m.keys_rotate],
		[['Esc'], m.keys_gallery],
		[['?'], m.keys_help]
	];
</script>

<Dialog title={m.photo_keys()} icon="keyboard" {onclose}>
	<dl>
		{#each rows as [keys, label] (label)}
			<dt>
				{#each keys as key (key)}<Kbd>{key}</Kbd>{/each}
			</dt>
			<dd>{label()}</dd>
		{/each}
	</dl>
	<p class="note">{m.keys_map()}</p>
	<p class="note">{m.photo_save_note()}</p>
</Dialog>

<style>
	dl {
		display: grid;
		grid-template-columns: max-content minmax(0, 1fr);
		gap: var(--space-2) var(--space-4);
		align-items: center;
		margin: 0 0 var(--space-3);
	}
	dt {
		display: flex;
		gap: var(--space-1);
	}
	dd {
		margin: 0;
	}
	.note {
		margin: var(--space-2) 0 0;
		font-size: var(--text-sm);
		color: var(--color-text-muted);
		text-wrap: pretty;
	}
</style>
