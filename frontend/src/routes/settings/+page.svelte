<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Settings of this account. A list of the sections goes beside them on a wide screen (above them
     on a narrow one); each section has its address (`/settings#locked`), and the one in view is
     marked in the list. -->
<script lang="ts">
	import { m } from '#lib/paraglide/messages.js';
	import GalleryPanel from '#lib/GalleryPanel.svelte';
	import GroupsPanel from '#lib/GroupsPanel.svelte';
	import LockedFolderPanel from '#lib/LockedFolderPanel.svelte';
	import MapSourcesPanel from '#lib/MapSourcesPanel.svelte';
	import ModuleDisplayPanel from '#lib/ModuleDisplayPanel.svelte';
	import UpdatesPanel from '#lib/UpdatesPanel.svelte';

	const sections = [
		{ id: 'gallery', label: m.gallery_settings_heading },
		{ id: 'groups', label: m.groups_settings_heading },
		{ id: 'suggestions', label: m.display_heading },
		{ id: 'maps', label: m.mapsrc_heading },
		{ id: 'locked', label: m.locked_heading },
		{ id: 'updates', label: m.updates_heading }
	];

	let current = $state(sections[0].id);
	// Chosen in the list: stays marked while in view, also at the end of the page, where the
	// sections below it cannot scroll to the top.
	let chosen: string | null = null;

	function update() {
		const line = window.innerHeight * 0.25;
		const tops = sections.map((s) => ({
			id: s.id,
			rect: document.getElementById(s.id)?.getBoundingClientRect()
		}));
		const chosenRect = tops.find((t) => t.id === chosen)?.rect;
		if (chosenRect && chosenRect.top < window.innerHeight && chosenRect.bottom > 0) {
			current = chosen!;
			return;
		}
		chosen = null;
		// The last section whose top passed the line near the top of the window.
		current = tops.filter((t) => t.rect && t.rect.top <= line).at(-1)?.id ?? sections[0].id;
	}

	function choose(id: string) {
		chosen = id;
		current = id;
	}

	$effect(() => {
		update();
		window.addEventListener('scroll', update, { passive: true });
		return () => window.removeEventListener('scroll', update);
	});
</script>

<h1>{m.settings_heading()}</h1>

<div class="settings">
	<nav class="toc" aria-label={m.settings_sections()}>
		{#each sections as section (section.id)}
			<a
				href="#{section.id}"
				onclick={() => choose(section.id)}
				aria-current={current === section.id ? 'location' : undefined}
				data-active={current === section.id}>{section.label()}</a
			>
		{/each}
	</nav>
	<div class="sections">
		<div id="gallery"><GalleryPanel /></div>
		<div id="groups"><GroupsPanel /></div>
		<div id="suggestions"><ModuleDisplayPanel /></div>
		<div id="maps"><MapSourcesPanel /></div>
		<div id="locked"><LockedFolderPanel /></div>
		<div id="updates"><UpdatesPanel /></div>
	</div>
</div>

<style>
	.sections > div {
		/* Below the header when reached by a link. */
		scroll-margin-top: calc(var(--header-height) + var(--space-4));
	}
	/* Narrow: a row of the sections above them, scrolled sideways if it does not fit. */
	.toc {
		display: flex;
		gap: var(--space-1);
		margin-bottom: var(--space-6);
		overflow-x: auto;
		scrollbar-width: none;
	}
	.toc a {
		flex: none;
		padding: var(--space-1) var(--space-3);
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-full);
		color: var(--color-text-muted);
		font-size: var(--text-sm);
		text-decoration: none;
		white-space: nowrap;
	}
	.toc a:hover {
		background: var(--color-surface-hover);
		color: var(--color-text);
	}
	.toc a[data-active='true'] {
		border-color: var(--color-accent-subtle-border);
		background: var(--color-accent-subtle);
		color: var(--color-accent-text);
	}
	/* Wide: a column beside the sections, in the margin left of the page, staying in view. */
	@media (min-width: 72rem) {
		.settings {
			display: grid;
			grid-template-columns: 11rem minmax(0, 1fr);
			gap: var(--space-6);
			margin-inline-start: -13rem;
		}
		.toc {
			position: sticky;
			top: calc(var(--header-height) + var(--space-6));
			align-self: start;
			flex-direction: column;
			margin: 0;
			overflow: visible;
		}
		.toc a {
			border: 0;
			border-inline-start: 2px solid transparent;
			border-radius: 0;
			padding: var(--space-1) var(--space-3);
			white-space: normal;
		}
		.toc a[data-active='true'] {
			border-inline-start-color: var(--color-accent);
			background: none;
		}
	}
</style>
