<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- One group: its name and all its photos. -->
<script lang="ts">
	import { getGroup, renameGroup, thumbnailUrl, type GroupDetail } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import Icon from '#lib/ui/Icon.svelte';
	import Skeleton from '#lib/ui/Skeleton.svelte';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';

	let detail = $state<GroupDetail | null>(null);
	let error = $state<string | null>(null);
	let name = $state('');

	const numbers = new Intl.NumberFormat(getLocale());
	const count = (n: number) => numbers.format(n);

	async function load(id: string) {
		try {
			detail = await getGroup(id);
			name = detail.group.name ?? '';
			error = null;
		} catch (e) {
			error = errorMessage(e);
		}
	}

	async function saveName() {
		if (!detail || name.trim() === (detail.group.name ?? '')) return;
		try {
			detail = await renameGroup(detail.group.id, name);
			name = detail.group.name ?? '';
			error = null;
		} catch (e) {
			error = errorMessage(e);
		}
	}

	$effect(() => {
		load(page.params.id ?? '');
	});
</script>

<a class="back" href={resolve('/groups')}>
	<Icon name="arrow-left" size={14} />
	{m.groups_back()}
</a>

{#if error}
	<p class="bad" role="alert">{error}</p>
{/if}

{#if detail}
	<div class="title">
		<span class="st-input">
			<input
				aria-label={m.groups_name()}
				placeholder={m.groups_unnamed()}
				maxlength="200"
				bind:value={name}
				onblur={saveName}
				onkeydown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
			/>
		</span>
	</div>
	<p class="numbers">
		<span>{m.groups_photos({ count: count(detail.group.photos) })}</span>
		{#if detail.group.without_location > 0}
			<span class="st-badge st-badge--info">
				<Icon name="map-pin-off" size={11} />
				<span>{m.groups_without_location({ count: count(detail.group.without_location) })}</span>
			</span>
		{/if}
		{#if detail.group.spread}
			<span class="st-badge st-badge--warning" title={m.groups_spread_hint()}>
				<Icon name="route" size={11} />
				<span>{m.groups_spread()}</span>
			</span>
		{/if}
	</p>

	{#if detail.photos.length > 0}
		<div class="grid">
			{#each detail.photos as photo (photo.id)}
				<a class="tile" href={resolve('/photo/[id]', { id: photo.id })} title={photo.file_name}>
					<img
						src={thumbnailUrl(photo.id, 'thumbnail', 0, photo.version)}
						alt={photo.file_name}
						loading="lazy"
						decoding="async"
					/>
					{#if photo.has_location}
						<span class="pin" role="img" aria-label={m.asset_has_location()}>
							<Icon name="map-pin" size={13} strokeWidth={2.25} />
						</span>
					{/if}
				</a>
			{/each}
		</div>
	{:else}
		<p class="numbers">{m.groups_no_photos()}</p>
	{/if}
{:else if !error}
	<Skeleton />
{/if}

<style>
	.back {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1);
		margin-bottom: var(--space-3);
		font-size: var(--text-sm);
	}
	.title {
		max-width: 32rem;
		margin-bottom: var(--space-2);
	}
	.numbers {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2);
		margin: 0 0 var(--space-4);
		color: var(--color-text-muted);
		font-size: var(--text-sm);
	}
	.bad {
		color: var(--color-danger-text);
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(8rem, 1fr));
		gap: var(--space-1);
	}
	.tile {
		position: relative;
		display: block;
		aspect-ratio: 1;
		overflow: hidden;
		background: var(--color-surface-sunken);
	}
	.tile img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}
	.pin {
		position: absolute;
		right: var(--space-1);
		bottom: var(--space-1);
		display: flex;
		color: white;
		filter: drop-shadow(0 0 2px rgb(0 0 0 / 0.7));
	}
</style>
