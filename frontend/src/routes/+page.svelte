<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
	import { getHealth, type Health } from '#lib/api.js';
	import { m } from '#lib/paraglide/messages.js';
	import LibraryPanel from '#lib/LibraryPanel.svelte';

	let health = $state<Health | null>(null);
	let coreReachable = $state(true);
	let loading = $state(true);

	async function refresh() {
		loading = true;
		try {
			health = await getHealth();
			coreReachable = true;
		} catch {
			health = null;
			coreReachable = false;
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		refresh();
	});
</script>

<LibraryPanel />

<h2>{m.status_heading()}</h2>

{#if loading && !health}
	<p>{m.status_loading()}</p>
{:else}
	<dl>
		<dt>{m.status_core()}</dt>
		<dd class:bad={!coreReachable}>
			{health ? m.status_core_ok({ version: health.version }) : m.status_core_unreachable()}
		</dd>

		{#if health}
			<dt>{m.status_immich()}</dt>
			<dd class:bad={!health.immich.reachable || !health.immich.supported}>
				{#if !health.immich.configured}
					{m.status_immich_not_configured()}
				{:else if !health.immich.reachable}
					{m.status_immich_unreachable()}
				{:else if !health.immich.supported}
					{m.status_immich_unsupported({ version: health.immich.version ?? '?' })}
				{:else}
					{m.status_immich_ok({ version: health.immich.version ?? '?' })}
				{/if}
			</dd>

			<dt>{m.status_database()}</dt>
			<dd class:bad={!health.database.ok}>
				{health.database.ok
					? m.status_database_ok({ version: health.database.server_version ?? '?' })
					: m.status_database_unreachable({ code: health.database.error ?? '?' })}
			</dd>

			{#if health.database.ok}
				<dt>{m.status_pgvector()}</dt>
				<dd class:bad={!health.database.pgvector_version}>
					{health.database.pgvector_version
						? m.status_pgvector_ok({ version: health.database.pgvector_version })
						: m.status_pgvector_missing()}
				</dd>
			{/if}
		{/if}
	</dl>
{/if}

<button type="button" onclick={refresh} disabled={loading}>{m.status_refresh()}</button>

<style>
	dl {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 0.5rem 1.5rem;
	}
	dt {
		font-weight: 600;
	}
	dd {
		margin: 0;
		color: #1a7f37;
	}
	dd.bad {
		color: #cf222e;
	}
</style>
