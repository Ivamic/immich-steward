<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- A newer release is out: a link to its release notes in the header, until closed. -->
<script lang="ts">
	import { m } from '#lib/paraglide/messages.js';
	import { updates } from '#lib/updates.svelte.js';
	import Icon from '#lib/ui/Icon.svelte';

	// Twice a day the core asks GitHub; an open tab looks again every few hours.
	const REFRESH_MS = 3 * 60 * 60_000;

	$effect(() => {
		updates.load();
		const timer = setInterval(() => updates.load(), REFRESH_MS);
		return () => clearInterval(timer);
	});
</script>

{#if updates.offered && updates.info?.url}
	{@const version = updates.offered}
	<span class="update">
		<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- release notes on GitHub -->
		<a
			href={updates.info.url}
			target="_blank"
			rel="noopener"
			title="{m.update_badge({ version })}. {m.update_badge_hint()}"
		>
			<Icon name="refresh-cw" size={14} />
			<span class="text">{m.update_badge({ version })}</span>
		</a>
		<button
			type="button"
			class="st-iconbtn st-iconbtn--sm"
			aria-label={m.update_dismiss()}
			title={m.update_dismiss()}
			onclick={() => updates.dismiss(version)}
		>
			<Icon name="x" size={12} />
		</button>
	</span>
{/if}

<style>
	.update {
		display: inline-flex;
		align-items: center;
		gap: var(--space-0-5);
		padding-inline-start: var(--space-2);
		border-radius: var(--radius-full);
		background: var(--color-accent-subtle);
		font-size: var(--text-sm);
		white-space: nowrap;
	}
	a {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		color: var(--color-accent-text);
		text-decoration: none;
	}
	a:hover {
		text-decoration: underline;
	}
	/* Narrow screens: the icon only; the version is in the tooltip. */
	@media (max-width: 48rem) {
		.text {
			position: absolute;
			width: 1px;
			height: 1px;
			overflow: hidden;
			clip-path: inset(50%);
			white-space: nowrap;
		}
	}
</style>
