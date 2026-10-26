<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- The version of the app and the check for a newer one: for the whole installation. -->
<script lang="ts">
	import { checkUpdates, setUpdates, type Updates } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import { updates } from '#lib/updates.svelte.js';

	let busy = $state(false);
	let error = $state<string | null>(null);

	const when = new Intl.DateTimeFormat(getLocale(), { dateStyle: 'medium', timeStyle: 'short' });

	$effect(() => {
		updates.load();
	});

	async function run(action: () => Promise<Updates>) {
		busy = true;
		try {
			updates.info = await action();
			error = null;
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	function result(info: Updates): string {
		if (info.error === 'unreachable') return m.updates_error_unreachable();
		if (info.error) return m.updates_error({ code: info.error });
		if (!info.latest) return m.updates_none_yet();
		return info.newer ? m.updates_newer({ version: info.latest }) : m.updates_latest();
	}
</script>

<section aria-busy={busy}>
	<h2>{m.updates_heading()}</h2>
	<p class="hint">{m.updates_hint()}</p>
	{#if updates.info}
		{@const info = updates.info}
		<p>{m.updates_current({ version: info.current })}</p>
		<label class="st-check">
			<input
				type="checkbox"
				checked={info.enabled}
				disabled={busy}
				onchange={(e) => run(() => setUpdates((e.currentTarget as HTMLInputElement).checked))}
			/>
			{m.updates_enable()}
		</label>
		<p class="hint">{m.updates_privacy()}</p>
		<div class="row">
			{#if info.checked_at}
				<span>
					{result(info)}
					{#if info.newer && info.url}
						<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- release notes on GitHub -->
						<a href={info.url} target="_blank" rel="noopener">{m.updates_whats_new()}</a>
					{/if}
				</span>
				<span class="hint"
					>{m.updates_checked({ when: when.format(new Date(info.checked_at)) })}</span
				>
			{/if}
			<button
				type="button"
				class="st-btn st-btn--sm"
				disabled={busy}
				onclick={() => run(checkUpdates)}
			>
				{m.updates_check_now()}
			</button>
		</div>
	{/if}
	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
</section>

<style>
	section {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		margin-bottom: var(--space-10);
	}
	h2,
	p {
		margin: 0;
	}
	.hint {
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	.row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2) var(--space-4);
	}
	.error {
		color: var(--color-danger-text);
	}
</style>
