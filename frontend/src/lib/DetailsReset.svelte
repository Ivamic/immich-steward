<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Forgets every comparison of details, so that the module compares the photos again by itself,
     with the masks of the settings now (D-250). Says how many photos first, as the reset of the
     turned photos does. -->
<script lang="ts">
	import { getDetailsReset, resetDetails } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import Dialog from '#lib/ui/Dialog.svelte';

	let { onclose, ondone }: { onclose: () => void; ondone: (photos: number) => void } = $props();

	let count = $state<number | null>(null);
	let busy = $state(false);
	let error = $state<string | null>(null);
	const number = new Intl.NumberFormat(getLocale());

	$effect(() => {
		getDetailsReset()
			.then((answer) => (count = answer.photos))
			.catch((e) => (error = errorMessage(e)));
	});

	async function confirm() {
		busy = true;
		error = null;
		try {
			ondone((await resetDetails()).photos);
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}
</script>

<Dialog title={m.details_reset_title()} icon="rotate-ccw" {onclose}>
	<p>
		{count === null
			? m.details_reset_counting()
			: m.details_reset_text({ count: number.format(count) })}
	</p>
	<p class="hint">{m.details_reset_note()}</p>
	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
	{#snippet footer()}
		<button type="button" class="st-btn st-btn--secondary" onclick={onclose}>
			{m.turned_reset_cancel()}
		</button>
		<button type="button" class="st-btn st-btn--danger" disabled={busy || !count} onclick={confirm}>
			{m.details_reset_confirm()}
		</button>
	{/snippet}
</Dialog>

<style>
	p {
		margin: 0 0 var(--space-3);
	}
	.hint {
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	.error {
		color: var(--color-danger-text);
	}
</style>
