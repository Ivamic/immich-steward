<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Notices about saved locations: countdown with cancel, then result with undo or retry. -->
<script lang="ts">
	import { m } from '#lib/paraglide/messages.js';
	import { saves, type Save } from '#lib/saves.svelte.js';

	let now = $state(Date.now());

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
		{#each saves.items as save (save.key)}
			<div class="notice" class:failed={save.phase === 'failed'}>
				<span class="text">
					{text(save)}
					{#if save.error && save.phase !== 'failed'}<span class="error">{save.error}</span>{/if}
				</span>
				{#if save.phase === 'pending'}
					<button type="button" onclick={() => saves.cancel(save.key)}>{m.save_cancel()}</button>
				{:else if save.phase === 'failed'}
					<button type="button" onclick={() => saves.send(save.key)}>{m.save_retry()}</button>
				{:else if save.phase === 'saved' && save.canUndo}
					<button type="button" onclick={() => saves.undo(save.key)}>{m.save_undo()}</button>
				{/if}
				{#if save.phase !== 'pending' && save.phase !== 'saving'}
					<button
						type="button"
						class="close"
						aria-label={m.save_dismiss()}
						title={m.save_dismiss()}
						onclick={() => saves.dismiss(save.key)}>×</button
					>
				{/if}
			</div>
		{/each}
	</div>
{/if}

<style>
	.notices {
		position: fixed;
		right: 1rem;
		bottom: 1rem;
		z-index: 10;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		max-width: min(32rem, calc(100vw - 2rem));
	}
	.notice {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.6rem 0.8rem;
		border-radius: 0.4rem;
		background: #24292f;
		color: #fff;
		box-shadow: 0 2px 8px rgb(0 0 0 / 0.25);
	}
	.notice.failed {
		background: #82071e;
	}
	.text {
		flex: 1;
		word-break: break-word;
	}
	.error {
		display: block;
		opacity: 0.85;
	}
	.close {
		background: none;
		border: none;
		color: inherit;
		font-size: 1.2rem;
		cursor: pointer;
	}
</style>
