<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Logo and name. The mark: four frame corners in module colors around a confirmed check; its
     colors come from the theme tokens, so one drawing serves both themes. -->
<script lang="ts">
	import { m } from '#lib/paraglide/messages.js';

	let { large = false, href }: { large?: boolean; href?: string } = $props();
</script>

<svelte:element this={href ? 'a' : 'span'} {href} class="st-brand" class:large>
	<svg viewBox="0 0 48 48" aria-hidden="true">
		<g fill="none" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
			<path d="M6 15V9a3 3 0 0 1 3-3h6" stroke="var(--module-1)" />
			<path d="M33 6h6a3 3 0 0 1 3 3v6" stroke="var(--module-2)" />
			<path d="M42 33v6a3 3 0 0 1-3 3h-6" stroke="var(--module-3)" />
			<path d="M15 42H9a3 3 0 0 1-3-3v-6" stroke="var(--module-4)" />
			<circle cx="24" cy="24" r="10" fill="var(--color-text)" stroke="none" />
			<path d="M19.3 24.4l3.2 3.2 6.2-6.6" stroke="var(--color-text-inverse)" stroke-width="3" />
		</g>
	</svg>
	<span class="name">
		<span class="word">Steward</span>
		<span class="for">{m.brand_for_immich()}</span>
	</span>
</svelte:element>

<style>
	svg {
		width: 1.5rem;
		height: 1.5rem;
		border-radius: 0;
	}
	.name {
		display: inline-flex;
		align-items: baseline;
		gap: var(--space-1-5);
		white-space: nowrap;
	}
	.word {
		font-size: var(--text-md);
		font-weight: var(--weight-semibold);
		letter-spacing: var(--tracking-tight);
		color: var(--color-text);
	}
	.for {
		font-size: var(--text-xs);
		color: var(--color-text-muted);
	}
	.large {
		gap: var(--space-2-5);
	}
	.large svg {
		width: 2.5rem;
		height: 2.5rem;
	}
	.large .name {
		flex-direction: column;
		gap: var(--space-1);
	}
	.large .word {
		font-size: var(--text-xl);
		line-height: 1.25rem;
	}
	.large .for {
		font-size: var(--text-sm);
		line-height: 1rem;
	}
</style>
