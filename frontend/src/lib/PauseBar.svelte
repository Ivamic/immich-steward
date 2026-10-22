<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- A thin bar while background runs are paused, so that a pause is not forgotten. -->
<script lang="ts">
	import { resolve } from '$app/paths';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { formatUntil, pause } from '#lib/pause.svelte.js';
	import { moduleName } from '#lib/suggestions/format.js';

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
	<p class="bar" role="status">
		<span>
			{pause.all
				? pause.allUntil
					? m.pause_bar_all_until({ time: formatUntil(pause.allUntil) })
					: m.pause_bar_all()
				: m.pause_bar_modules({ modules: pause.modules.map(pausedModule).join(', ') })}
		</span>
		<button type="button" disabled={busy} onclick={resume}>{m.pause_resume()}</button>
		<a href={resolve('/library')}>{m.pause_manage()}</a>
		{#if error}<span class="error">{error}</span>{/if}
	</p>
{/if}

<style>
	.bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.25rem 0.75rem;
		margin: 0 0 0.5rem;
		padding: 0.2rem 0.75rem;
		border-left: 3px solid #bf8700;
		background: rgb(191 135 0 / 0.12);
		font-size: 0.9rem;
	}
	button {
		padding: 0.1rem 0.6rem;
		font-size: 0.85rem;
	}
	.error {
		color: #cf222e;
	}
</style>
