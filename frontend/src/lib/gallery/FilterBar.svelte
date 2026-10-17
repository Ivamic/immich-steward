<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
	import { getFilterOptions, type FilterOptions, type GalleryFilter } from '#lib/api.js';
	import { m } from '#lib/paraglide/messages.js';
	import { defaultFilter } from './filter.js';

	let { filter, onchange }: { filter: GalleryFilter; onchange: (f: GalleryFilter) => void } =
		$props();

	let options = $state<FilterOptions>({ cameras: [], albums: [] });

	$effect(() => {
		getFilterOptions()
			.then((result) => (options = result))
			.catch(() => {});
	});

	const set = (patch: Partial<GalleryFilter>) => onchange({ ...filter, ...patch });
	const cameraLabel = (make: string, model: string) =>
		[make, model].filter(Boolean).join(' ') || m.filter_camera_unknown();
</script>

<form class="filters" onsubmit={(e) => e.preventDefault()}>
	<label>
		{m.filter_location()}
		<select
			value={filter.location}
			onchange={(e) => set({ location: e.currentTarget.value as GalleryFilter['location'] })}
		>
			<option value="without">{m.filter_location_without()}</option>
			<option value="with">{m.filter_location_with()}</option>
			<option value="all">{m.filter_location_all()}</option>
		</select>
	</label>

	<label>
		{m.filter_type()}
		<select
			value={filter.type}
			onchange={(e) => set({ type: e.currentTarget.value as GalleryFilter['type'] })}
		>
			<option value="all">{m.filter_type_all()}</option>
			<option value="image">{m.filter_type_image()}</option>
			<option value="video">{m.filter_type_video()}</option>
		</select>
	</label>

	<label>
		{m.filter_camera()}
		<select
			value={filter.camera ?? ''}
			onchange={(e) => {
				const index = e.currentTarget.selectedIndex - 1;
				set({ camera: index < 0 ? null : options.cameras[index].value });
			}}
		>
			<option value="">{m.filter_any()}</option>
			{#each options.cameras as camera (camera.value)}
				<option value={camera.value}
					>{cameraLabel(camera.make, camera.model)} ({camera.count})</option
				>
			{/each}
		</select>
	</label>

	<label>
		{m.filter_album()}
		<select
			value={filter.album ?? ''}
			onchange={(e) => set({ album: e.currentTarget.value || null })}
		>
			<option value="">{m.filter_any()}</option>
			{#each options.albums as album (album.id)}
				<option value={album.id}>{album.name} ({album.count})</option>
			{/each}
		</select>
	</label>

	<label>
		{m.filter_date_from()}
		<input
			type="date"
			value={filter.date_from ?? ''}
			onchange={(e) => set({ date_from: e.currentTarget.value || null })}
		/>
	</label>

	<label>
		{m.filter_date_to()}
		<input
			type="date"
			value={filter.date_to ?? ''}
			onchange={(e) => set({ date_to: e.currentTarget.value || null })}
		/>
	</label>

	<label class="checkbox">
		<input
			type="checkbox"
			checked={filter.archived}
			onchange={(e) => set({ archived: e.currentTarget.checked })}
		/>
		{m.filter_archived()}
	</label>

	<button type="button" onclick={() => onchange(defaultFilter)}>{m.filter_reset()}</button>
</form>

<style>
	.filters {
		display: flex;
		flex-wrap: wrap;
		align-items: end;
		gap: 0.75rem 1rem;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		font-size: 0.85rem;
	}
	label.checkbox {
		flex-direction: row;
		align-items: center;
	}
	select {
		max-width: 16rem;
	}
</style>
