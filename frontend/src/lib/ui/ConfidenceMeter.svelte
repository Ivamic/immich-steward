<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- How sure a module is about a suggestion. The bars show the module's own tier (weak / normal /
     confident: each module sets them by its thresholds), so they read the same for every module;
     the percent is the module's score and compares only within one module. -->
<script lang="ts">
	import type { Candidate } from '#lib/api.js';

	let {
		score,
		tier,
		label,
		title
	}: { score: number; tier: Candidate['tier']; label?: string; title?: string } = $props();

	const level = $derived(tier === 'confident' ? 'high' : tier === 'weak' ? 'low' : 'medium');
</script>

<span class="st-conf st-conf--{level}" {title}>
	<span class="st-conf__bars" aria-hidden="true"><i></i><i></i><i></i></span>
	<span class="st-conf__pct">{Math.round(score * 100)}%</span>
	{#if label}<span class="st-conf__label">{label}</span>{/if}
</span>
