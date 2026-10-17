<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Placeholder of the photo card: the map, candidates and actions come in the next step. -->
<script lang="ts">
	import { thumbnailUrl } from '#lib/api.js';
	import { m } from '#lib/paraglide/messages.js';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';

	const id = $derived(page.params.id ?? '');
</script>

<p><a href={resolve(`/?${page.url.searchParams}`)}>← {m.photo_back()}</a></p>
<img src={thumbnailUrl(id, 'preview')} alt="" />

<style>
	img {
		max-width: 100%;
		max-height: 80vh;
	}
</style>
