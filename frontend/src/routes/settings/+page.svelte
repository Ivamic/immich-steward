<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Settings of this account; more will come (thresholds of the view groups, D-129). -->
<script lang="ts">
	import { m } from '#lib/paraglide/messages.js';
	import MapSourcesPanel from '#lib/MapSourcesPanel.svelte';
	import ModuleDisplayPanel from '#lib/ModuleDisplayPanel.svelte';
</script>

<h1>{m.settings_heading()}</h1>

<ModuleDisplayPanel />
<MapSourcesPanel />
