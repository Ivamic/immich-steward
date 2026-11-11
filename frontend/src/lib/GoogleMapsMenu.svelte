<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Opens a point in Google Maps in a new tab: the satellite view or the nearest Street View.
     Only the coordinates go to Google, and only on a click (no referrer). The list closes on a
     click outside it, on Esc and on choosing a link. -->
<script lang="ts">
	import type { LatLon } from '#lib/coords.js';
	import { googleSatelliteUrl, googleStreetViewUrl } from '#lib/externalMaps.js';
	import { m } from '#lib/paraglide/messages.js';
	import Icon from '#lib/ui/Icon.svelte';

	let { at }: { at: LatLon } = $props();

	let open = $state(false);
	let menu: HTMLDetailsElement | undefined = $state();

	function closeOutside(event: PointerEvent) {
		if (open && menu && !menu.contains(event.target as Node)) open = false;
	}

	// On the menu itself, not on the window: Esc must not reach the page too (in the photo card
	// it leads back to the gallery).
	function closeOnEscape(event: KeyboardEvent) {
		if (!open || event.key !== 'Escape') return;
		event.preventDefault();
		event.stopPropagation();
		open = false;
		menu?.querySelector('summary')?.focus();
	}
</script>

<svelte:window onpointerdown={closeOutside} />

<!-- Esc pressed on the button or on a link inside closes the menu. -->
<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<details class="menu" bind:open bind:this={menu} onkeydown={closeOnEscape}>
	<summary
		class="st-iconbtn st-iconbtn--sm"
		aria-label={m.google_maps_open()}
		title={m.google_maps_open()}
	>
		<Icon name="external-link" />
	</summary>
	<!-- eslint-disable svelte/no-navigation-without-resolve -- links to Google Maps -->
	<ul class="st-menu">
		<li>
			<a
				class="st-menu__item"
				href={googleSatelliteUrl(at)}
				target="_blank"
				rel="noopener noreferrer"
				onclick={() => (open = false)}>{m.google_maps_satellite()}</a
			>
		</li>
		<li>
			<a
				class="st-menu__item"
				href={googleStreetViewUrl(at)}
				target="_blank"
				rel="noopener noreferrer"
				onclick={() => (open = false)}>{m.google_maps_street_view()}</a
			>
		</li>
	</ul>
	<!-- eslint-enable svelte/no-navigation-without-resolve -->
</details>

<style>
	.menu {
		position: relative;
		display: inline-block;
	}
	summary {
		list-style: none;
	}
	summary::-webkit-details-marker {
		display: none;
	}
	ul {
		position: absolute;
		top: calc(100% + 4px);
		right: 0;
		z-index: 10;
		margin: 0;
		list-style: none;
		white-space: nowrap;
		animation: menu-in var(--motion-fast) var(--ease-out);
	}
	li a {
		display: flex;
		width: 100%;
	}
	@keyframes menu-in {
		from {
			opacity: 0;
			transform: translateY(-4px);
		}
	}
</style>
