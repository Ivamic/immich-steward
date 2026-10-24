<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Notices about saved locations: countdown with cancel, then result with undo or retry. -->
<script lang="ts">
	import { m } from '#lib/paraglide/messages.js';
	import { saves, type Save } from '#lib/saves.svelte.js';
	import Icon from '#lib/ui/Icon.svelte';

	let now = $state(Date.now());
	let expanded = $state(false);

	// When saving fast, only the newest notice is shown (and failures, which need attention);
	// the rest are one click away.
	let shown = $derived(
		expanded
			? saves.items
			: saves.items.filter(
					(item, index) => item.phase === 'failed' || index === saves.items.length - 1
				)
	);
	let hidden = $derived(saves.items.length - shown.length);

	$effect(() => {
		if (saves.items.length <= 1) expanded = false;
	});

	$effect(() => {
		if (!saves.items.some((item) => item.phase === 'pending')) return;
		const timer = setInterval(() => (now = Date.now()), 250);
		return () => clearInterval(timer);
	});

	function text(save: Save): string {
		const file = save.fileName;
		switch (save.phase) {
			case 'pending': {
				const seconds = Math.max(1, Math.ceil((save.sendAt - now) / 1000));
				return m.save_pending({ file, seconds: String(seconds) });
			}
			case 'saving':
				return m.save_saving({ file });
			case 'saved':
				return m.save_saved({ file });
			case 'undone':
				return m.save_undone({ file });
			case 'failed':
				return m.save_failed({ file, error: save.error ?? '' });
		}
	}
</script>

<svelte:window onpagehide={() => saves.flush()} />

{#if saves.items.length}
	<div class="notices" role="status" aria-live="polite">
		{#if hidden || expanded}
			<button type="button" class="st-btn st-btn--sm" onclick={() => (expanded = !expanded)}>
				<Icon name={expanded ? 'chevron-down' : 'chevron-up'} size={14} />
				{expanded ? m.save_notices_fewer() : m.save_notices_more({ count: String(hidden) })}
			</button>
		{/if}
		{#each shown as save (save.key)}
			<div
				class="st-toast"
				class:st-toast--saved={save.phase === 'saved'}
				class:st-toast--failed={save.phase === 'failed'}
			>
				<span class="st-toast__icon">
					{#if save.phase === 'pending'}
						<Icon name="clock" />
					{:else if save.phase === 'saving'}
						<span class="st-spin"><Icon name="loader-circle" /></span>
					{:else if save.phase === 'saved'}
						<!-- The check is drawn once: the one playful moment of the app. -->
						<span class="st-draw"><Icon name="circle-check" /></span>
					{:else if save.phase === 'failed'}
						<Icon name="circle-alert" />
					{:else}
						<Icon name="undo-2" />
					{/if}
				</span>
				<span class="st-toast__text">
					{text(save)}
					{#if save.error && save.phase !== 'failed'}<span class="error">{save.error}</span>{/if}
				</span>
				<span class="st-toast__actions">
					{#if save.phase === 'pending'}
						<button type="button" class="st-btn st-btn--sm" onclick={() => saves.cancel(save.key)}
							>{m.save_cancel()}</button
						>
					{:else if save.phase === 'failed'}
						<button type="button" class="st-btn st-btn--sm" onclick={() => saves.send(save.key)}
							>{m.save_retry()}</button
						>
					{:else if save.phase === 'saved' && save.canUndo}
						<button type="button" class="st-btn st-btn--sm" onclick={() => saves.undo(save.key)}
							>{m.save_undo()}</button
						>
					{/if}
					{#if save.phase !== 'pending' && save.phase !== 'saving'}
						<button
							type="button"
							class="st-iconbtn st-iconbtn--sm"
							aria-label={m.save_dismiss()}
							title={m.save_dismiss()}
							onclick={() => saves.dismiss(save.key)}
						>
							<Icon name="x" />
						</button>
					{/if}
				</span>
			</div>
		{/each}
	</div>
{/if}

<style>
	.notices {
		/* Bottom left, over the empty corner of the map: away from the suggestions the user
		   picks from on the right. */
		position: fixed;
		left: var(--space-4);
		bottom: var(--space-4);
		z-index: var(--z-toast);
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		align-items: flex-start;
		width: min(28rem, calc(100vw - 2rem));
	}
	.st-toast {
		width: 100%;
	}
	.st-spin,
	.st-draw {
		display: inline-flex;
	}
	.error {
		display: block;
		color: var(--color-text-muted);
	}
</style>
