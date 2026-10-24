<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Address search; results come from the geocoder configured on the server. -->
<script lang="ts">
	import { geocode, type Place } from '#lib/api.js';
	import type { LatLon } from '#lib/coords.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import Icon from '#lib/ui/Icon.svelte';

	let { near, onselect }: { near: LatLon | null; onselect: (point: LatLon) => void } = $props();

	const DEBOUNCE_MS = 400;

	let text = $state('');
	let results = $state<Place[]>([]);
	let error = $state<string | null>(null);
	let timer: ReturnType<typeof setTimeout> | undefined;

	function search() {
		clearTimeout(timer);
		const q = text.trim();
		if (q.length < 2) {
			results = [];
			return;
		}
		timer = setTimeout(async () => {
			try {
				results = await geocode(q, getLocale(), near);
				error = null;
			} catch (e) {
				error = errorMessage(e);
			}
		}, DEBOUNCE_MS);
	}

	function choose(place: Place) {
		onselect({ lat: place.latitude, lon: place.longitude });
		results = [];
		text = place.name;
	}
</script>

<div class="geocoder">
	<label class="st-input">
		<Icon name="search" />
		<input
			type="search"
			bind:value={text}
			oninput={search}
			onkeydown={(e) => {
				if (e.key === 'Enter' && results.length) {
					e.preventDefault();
					choose(results[0]);
				}
			}}
			aria-label={m.photo_search_address()}
			placeholder={m.photo_search_placeholder()}
		/>
	</label>
	{#if results.length}
		<ul class="st-menu">
			{#each results as place, index (index)}
				<li>
					<button type="button" class="st-menu__item" onclick={() => choose(place)}>
						<Icon name="map-pin" />
						<span class="place">
							<strong>{place.name}</strong>
							{#if place.label}<span class="st-menu__hint">{place.label}</span>{/if}
						</span>
					</button>
				</li>
			{/each}
		</ul>
	{/if}
	{#if error}<p class="st-field__error">{error}</p>{/if}
</div>

<style>
	ul {
		max-width: none;
		margin: var(--space-1) 0 0;
		list-style: none;
		box-shadow: none;
	}
	.st-menu__item {
		width: 100%;
		min-height: var(--control-lg);
	}
	.place {
		display: flex;
		flex-direction: column;
		min-width: 0;
		line-height: var(--leading-snug);
	}
	strong {
		font-weight: var(--weight-medium);
	}
</style>
