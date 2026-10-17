<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Address search; results come from the geocoder configured on the server. -->
<script lang="ts">
	import { geocode, type Place } from '#lib/api.js';
	import type { LatLon } from '#lib/coords.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';

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
	<label>
		{m.photo_search_address()}
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
			placeholder={m.photo_search_placeholder()}
		/>
	</label>
	{#if results.length}
		<ul>
			{#each results as place, index (index)}
				<li>
					<button type="button" onclick={() => choose(place)}>
						<strong>{place.name}</strong>
						{#if place.label}<span>{place.label}</span>{/if}
					</button>
				</li>
			{/each}
		</ul>
	{/if}
	{#if error}<p class="error">{error}</p>{/if}
</div>

<style>
	label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}
	ul {
		list-style: none;
		margin: 0.25rem 0 0;
		padding: 0;
		border: 1px solid color-mix(in srgb, currentColor 20%, transparent);
		border-radius: 0.375rem;
	}
	li button {
		display: flex;
		flex-direction: column;
		align-items: start;
		width: 100%;
		padding: 0.4rem 0.6rem;
		border: 0;
		background: none;
		color: inherit;
		text-align: left;
		cursor: pointer;
	}
	li button:hover,
	li button:focus-visible {
		background: color-mix(in srgb, currentColor 10%, transparent);
	}
	li span {
		font-size: 0.85rem;
		opacity: 0.7;
	}
	.error {
		color: #cf222e;
	}
</style>
