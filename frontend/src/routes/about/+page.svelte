<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- About the app: versions, the license with the source code of the running version (AGPL §13),
     third-party components, AI assistance and support. Open without signing in too: the workers
     are listed only for a signed-in user. -->
<script lang="ts">
	import { fileUrl, REPOSITORY, releaseTag, sourceUrl } from '#lib/about.js';
	import { getHealth, getWorkers, type Health, type WorkerInfo } from '#lib/api.js';
	import { m } from '#lib/paraglide/messages.js';
	import { session } from '#lib/session.svelte.js';
	import { displayVersion } from '#lib/versions.js';

	let health = $state<Health | null>(null);
	let workers = $state<WorkerInfo[]>([]);

	$effect(() => {
		getHealth()
			.then((result) => (health = result))
			.catch(() => {});
	});

	$effect(() => {
		if (!session.user) return;
		getWorkers()
			.then((overview) => (workers = overview.workers))
			.catch(() => {});
	});

	const version = $derived(health?.version ?? null);

	interface Component {
		name: string;
		url: string;
		role: () => string;
		license: string;
	}

	const components: Component[] = [
		{
			name: 'GeoCLIP',
			url: 'https://github.com/VicenteVivan/geo-clip',
			role: m.about_role_geoclip,
			license: 'MIT'
		},
		{
			name: 'MegaLoc',
			url: 'https://github.com/gmberton/MegaLoc',
			role: m.about_role_megaloc,
			license: 'MIT'
		},
		{
			name: 'OpenFreeMap',
			url: 'https://openfreemap.org',
			role: m.about_role_tiles,
			license: ''
		},
		{
			name: '© OpenStreetMap',
			url: 'https://www.openstreetmap.org/copyright',
			role: m.about_role_map_data,
			license: 'ODbL'
		},
		{
			name: 'Photon',
			url: 'https://photon.komoot.io',
			role: m.about_role_geocoder,
			license: ''
		},
		{ name: 'Lucide', url: 'https://lucide.dev', role: m.about_role_icons, license: 'ISC' }
	];
</script>

<svelte:head>
	<title>{m.about_heading()} · {m.app_title()}</title>
</svelte:head>

<h1>{m.about_heading()}</h1>
<p class="lead">{m.app_title()} — {m.app_tagline()}</p>

<!-- eslint-disable svelte/no-navigation-without-resolve -- links to GitHub and the components -->
<section>
	<h2>{m.about_versions()}</h2>
	<dl class="versions">
		<dt>Steward</dt>
		<dd>
			{#if version}
				<span class="st-coords">{displayVersion(version)}</span>
				{#if !releaseTag(version)}<span class="hint">({m.about_dev_build()})</span>{/if}
			{:else}
				…
			{/if}
		</dd>
		<dt>Immich</dt>
		<dd>
			{#if health?.immich.version}
				<span class="st-coords">{health.immich.version}</span>
			{:else if health}
				<span class="hint">{m.about_unreachable()}</span>
			{:else}
				…
			{/if}
		</dd>
		{#if workers.length}
			<dt>{m.workers_heading()}</dt>
			<dd>
				<ul class="workers">
					{#each workers as worker (worker.id)}
						<li>{worker.name} <span class="st-coords">{displayVersion(worker.version)}</span></li>
					{/each}
				</ul>
			</dd>
		{/if}
	</dl>
</section>

<section>
	<h2>{m.about_license_heading()}</h2>
	<p>{m.about_license_text()}</p>
	{#if version}
		<p class="links">
			<a href={sourceUrl(version)} target="_blank" rel="noopener">{m.about_source()}</a>
			<a href={fileUrl(version, 'LICENSE')} target="_blank" rel="noopener"
				>{m.about_license_link()}</a
			>
		</p>
	{/if}
</section>

<section>
	<h2>{m.about_components_heading()}</h2>
	<ul class="components">
		{#each components as item (item.name)}
			<li>
				<a href={item.url} target="_blank" rel="noopener">{item.name}</a>
				— {item.role()}{#if item.license}<span class="hint">, {item.license}</span>{/if}
			</li>
		{/each}
	</ul>
	<p class="hint">{m.about_satellite_note()}</p>
	{#if version}
		<p>
			<a href={fileUrl(version, 'THIRD_PARTY_NOTICES.md')} target="_blank" rel="noopener"
				>{m.about_all_components()}</a
			>
		</p>
	{/if}
	<p class="hint">{m.about_in_image({ path: '/app/THIRD_PARTY_NOTICES.md' })}</p>
</section>

<section>
	<h2>{m.about_ai_heading()}</h2>
	<p>{m.about_ai_text()}</p>
</section>

<section>
	<h2>{m.about_support_heading()}</h2>
	<p>{m.about_support_text()}</p>
	<p class="links">
		<a href="{REPOSITORY}#support-the-project" target="_blank" rel="noopener">{m.about_donate()}</a>
		<a href="{REPOSITORY}/issues" target="_blank" rel="noopener">{m.about_report()}</a>
	</p>
</section>

<!-- eslint-enable svelte/no-navigation-without-resolve -->

<style>
	h1 {
		margin-bottom: var(--space-2);
	}
	.lead {
		margin: 0 0 var(--space-8);
		color: var(--color-text-muted);
	}
	section {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		margin-bottom: var(--space-10);
	}
	h2,
	p,
	dl {
		margin: 0;
	}
	.hint {
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	.versions {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: var(--space-2) var(--space-6);
	}
	.versions dt {
		color: var(--color-text-muted);
	}
	.versions dd {
		margin: 0;
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		align-items: baseline;
		min-width: 0;
	}
	.workers,
	.components {
		margin: 0;
		padding: 0;
		list-style: none;
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}
	.links {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2) var(--space-6);
	}
</style>
