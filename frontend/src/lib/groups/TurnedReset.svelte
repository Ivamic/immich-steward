<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Forgets the turns the orientation module found, so that it looks at the photos again (from
     Turned photos and from the module on Processing). Says how many photos first; the photos
     kept as they are stay so unless the user says otherwise. -->
<script lang="ts">
	import { getTurnedReset, resetTurned } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import Dialog from '#lib/ui/Dialog.svelte';

	let { onclose, ondone }: { onclose: () => void; ondone: (photos: number) => void } = $props();

	let keepKept = $state(true);
	// How many photos the module would look at again, for the choice as it is now.
	let count = $state<number | null>(null);
	let busy = $state(false);
	let error = $state<string | null>(null);
	const number = new Intl.NumberFormat(getLocale());

	$effect(() => {
		const keep = keepKept;
		count = null;
		getTurnedReset(keep)
			.then((answer) => {
				if (keep === keepKept) count = answer.photos;
			})
			.catch((e) => (error = errorMessage(e)));
	});

	async function confirm() {
		busy = true;
		error = null;
		try {
			const { photos } = await resetTurned(keepKept);
			ondone(photos);
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}
</script>

<Dialog title={m.turned_reset_title()} icon="rotate-ccw" {onclose}>
	<p>
		{count === null
			? m.turned_reset_counting()
			: m.turned_reset_text({ count: number.format(count) })}
	</p>
	<label class="st-check">
		<input type="checkbox" bind:checked={keepKept} disabled={busy} />
		<span>
			{m.turned_reset_keep_kept()}
			<span class="hint">{m.turned_reset_keep_kept_hint()}</span>
		</span>
	</label>
	<p class="hint">{m.turned_reset_note()}</p>
	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
	{#snippet footer()}
		<button type="button" class="st-btn st-btn--secondary" onclick={onclose}>
			{m.turned_reset_cancel()}
		</button>
		<button type="button" class="st-btn st-btn--danger" disabled={busy || !count} onclick={confirm}>
			{m.turned_reset_confirm()}
		</button>
	{/snippet}
</Dialog>

<style>
	p {
		margin: 0 0 var(--space-3);
	}
	.hint {
		display: block;
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	p.hint {
		margin-top: var(--space-3);
	}
	.error {
		color: var(--color-danger-text);
	}
</style>
