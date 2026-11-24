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
	import PairView from '#lib/ui/PairView.svelte';

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
</script>

<Dialog title={m.details_dialog_title()} icon="scan-search" full {onclose}>
	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
	<PairView
		first={{
			src: thumbnailUrl(assetId, 'preview'),
			alt: m.details_dialog_this(),
			caption: m.details_dialog_this()
		}}
		second={{
			src: thumbnailUrl(other.asset_id, 'preview', 0, other.version ?? null),
			alt: other.file_name,
			caption: `${m.details_dialog_other()} · ${other.file_name}`
		}}
		lines={pair?.lines ?? []}
	>
		{#snippet note()}
			{#if pair}
				{m.details_dialog_note({
					shown: String(pair.lines.length),
					count: String(pair.inliers)
				})}
			{:else if !error}
				{m.details_dialog_loading()}
			{/if}
		{/snippet}
	</PairView>
</Dialog>

<style>
	.error {
		margin: 0 0 var(--space-3);
		color: var(--color-danger-text);
	}
</style>
