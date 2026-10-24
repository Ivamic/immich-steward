<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- A thin bar while background runs are paused, so that a pause is not forgotten. -->
<script lang="ts">
	import { resolve } from '$app/paths';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { formatUntil, pause } from '#lib/pause.svelte.js';
	import { moduleName } from '#lib/suggestions/format.js';
	import Icon from '#lib/ui/Icon.svelte';

	const REFRESH_MS = 60_000;

	let error = $state<string | null>(null);
	let busy = $state(false);

	$effect(() => {
		const load = () => pause.load().catch(() => {});
		load();
		const timer = setInterval(load, REFRESH_MS);
		return () => clearInterval(timer);
	});

	/** "GeoCLIP (until 18:30)" */
	function pausedModule(module: string): string {
		const until = pause.until[module];
		return until
			? `${moduleName(module)} (${m.pause_until({ time: formatUntil(until) })})`
			: moduleName(module);
	}

	async function resume() {
		busy = true;
		try {
			await pause.resume();
			error = null;
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}
</script>

{#if pause.any}
	<div class="bar st-banner st-banner--warning" role="status">
		<Icon name="pause" />
		<span class="st-banner__body">
			{pause.all
				? pause.allUntil
					? m.pause_bar_all_until({ time: formatUntil(pause.allUntil) })
					: m.pause_bar_all()
				: m.pause_bar_modules({ modules: pause.modules.map(pausedModule).join(', ') })}
			{#if error}<span class="error">{error}</span>{/if}
		</span>
		<span class="st-banner__actions">
			<button type="button" class="st-btn st-btn--sm" disabled={busy} onclick={resume}>
				<Icon name="play" size={14} />
				{m.pause_resume()}
			</button>
			<a class="st-btn st-btn--ghost st-btn--sm" href={resolve('/processing')}>{m.pause_manage()}</a
			>
		</span>
	</div>
{/if}

<style>
	.bar {
		margin: 0 0 var(--space-3);
		padding-block: var(--space-1-5);
	}
	a.st-btn {
		text-decoration: none;
	}
	.error {
		display: block;
		color: var(--color-danger-text);
	}
</style>
