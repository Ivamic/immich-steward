<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Settings of this account. -->
<script lang="ts">
	import { m } from '#lib/paraglide/messages.js';
	import GalleryPanel from '#lib/GalleryPanel.svelte';
	import GroupsPanel from '#lib/GroupsPanel.svelte';
	import MapSourcesPanel from '#lib/MapSourcesPanel.svelte';
	import ModuleDisplayPanel from '#lib/ModuleDisplayPanel.svelte';
	import UpdatesPanel from '#lib/UpdatesPanel.svelte';
</script>

<h1>{m.settings_heading()}</h1>

<GalleryPanel />
<GroupsPanel />
<ModuleDisplayPanel />
<MapSourcesPanel />
<UpdatesPanel />
