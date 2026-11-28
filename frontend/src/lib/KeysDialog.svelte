<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Keyboard shortcuts of the photo card (opened with "?"); while looking at the library
     (D-254), only those that work then. -->
<script lang="ts">
	import { m } from '#lib/paraglide/messages.js';
	import Dialog from '#lib/ui/Dialog.svelte';
	import Kbd from '#lib/ui/Kbd.svelte';
	import { mode } from '#lib/mode.svelte.js';

	let { onclose }: { onclose: () => void } = $props();

	// The keys of the work on the place: off while looking at the library.
	const rows: [string[], () => string, 'work' | 'both'][] = [
		[['1–9'], m.keys_choose, 'work'],
		[['Shift', '1–9'], m.keys_locate, 'work'],
		[['Enter'], m.keys_save, 'work'],
		[['←', '→'], m.keys_previous_next, 'both'],
		[['S'], m.keys_skip, 'work'],
		[['N'], m.keys_not_applicable, 'work'],
		[['U'], m.keys_back_to_todo, 'work'],
		[['Z'], m.keys_zoom, 'both'],
		[['R'], m.keys_part, 'work'],
		[['[', ']'], m.keys_rotate, 'both'],
		[['A'], m.keys_album, 'both'],
		[['Esc'], m.keys_gallery, 'both'],
		[['?'], m.keys_help, 'both']
	];
	const shown = $derived(rows.filter(([, , when]) => when === 'both' || !mode.viewing));
</script>

<Dialog title={m.photo_keys()} icon="keyboard" {onclose}>
	<dl>
		{#each shown as [keys, label] (label)}
			<dt>
				{#each keys as key (key)}<Kbd>{key}</Kbd>{/each}
			</dt>
			<dd>{label()}</dd>
		{/each}
	</dl>
	{#if !mode.viewing}
		<p class="note">{m.keys_map()}</p>
		<p class="note">{m.photo_save_note()}</p>
	{/if}
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
