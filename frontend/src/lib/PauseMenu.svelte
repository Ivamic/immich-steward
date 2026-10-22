<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Pause of a worker module (or of all, `module` null): until resumed or for a while; when
     paused, the button resumes. -->
<script lang="ts">
	import { m } from '#lib/paraglide/messages.js';
	import { PAUSE_LENGTHS } from '#lib/pause.svelte.js';

	let {
		paused,
		disabled = false,
		align = 'left',
		pauseLabel,
		resumeLabel,
		onpause,
		onresume
	}: {
		paused: boolean;
		disabled?: boolean;
		/** The side of the button the list of lengths lines up with. */
		align?: 'left' | 'right';
		pauseLabel: string;
		resumeLabel: string;
		onpause: (minutes: number | null) => void;
		onresume: () => void;
	} = $props();

	let open = $state(false);

	function lengthLabel(minutes: number | null): string {
		switch (minutes) {
			case null:
				return m.pause_until_resumed();
			case 30:
				return m.pause_for_30m();
			case 60:
				return m.pause_for_1h();
			case 12 * 60:
				return m.pause_for_12h();
			default:
				return m.pause_for_1d();
		}
	}

	function choose(minutes: number | null) {
		open = false;
		onpause(minutes);
	}
</script>

{#if paused}
	<button type="button" {disabled} onclick={onresume}>{resumeLabel}</button>
{:else}
	<details class="menu" bind:open>
		<summary class:disabled>{pauseLabel} ▾</summary>
		<ul class:right={align === 'right'}>
			{#each PAUSE_LENGTHS as minutes (minutes)}
				<li>
					<button type="button" {disabled} onclick={() => choose(minutes)}>
						{lengthLabel(minutes)}
					</button>
				</li>
			{/each}
		</ul>
	</details>
{/if}

<style>
	.menu {
		position: relative;
		display: inline-block;
	}
	summary {
		list-style: none;
		cursor: pointer;
		padding: 0.2rem 0.6rem;
		border: 1px solid rgb(127 127 127 / 0.5);
		border-radius: 0.3rem;
		background: rgb(127 127 127 / 0.08);
		user-select: none;
	}
	summary::-webkit-details-marker {
		display: none;
	}
	summary.disabled {
		pointer-events: none;
		opacity: 0.5;
	}
	ul {
		position: absolute;
		z-index: 5;
		left: 0;
		min-width: 12rem;
		margin: 0.25rem 0 0;
		padding: 0.25rem;
		list-style: none;
		border: 1px solid rgb(127 127 127 / 0.4);
		border-radius: 0.4rem;
		background: #fff;
		box-shadow: 0 4px 12px rgb(0 0 0 / 0.15);
	}
	ul.right {
		right: 0;
		left: auto;
	}
	li button {
		width: 100%;
		padding: 0.35rem 0.6rem;
		border: none;
		background: none;
		color: inherit;
		text-align: left;
		cursor: pointer;
	}
	li button:hover {
		background: rgb(127 127 127 / 0.12);
	}
	@media (prefers-color-scheme: dark) {
		ul {
			background: #161b22;
		}
	}
</style>
