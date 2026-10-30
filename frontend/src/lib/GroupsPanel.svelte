<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Personal settings of the groups of photos: the thresholds, and comparing all photos again. -->
<script lang="ts">
	import { accountSettings } from '#lib/accountSettings.svelte.js';
	import { errorMessage } from '#lib/errors.js';
	import {
		getGroups,
		isActive,
		refreshGroups,
		resetGroups,
		type AccountSettings,
		type Job
	} from '#lib/api.js';
	import { m } from '#lib/paraglide/messages.js';
	import Dialog from '#lib/ui/Dialog.svelte';

	let error = $state<string | null>(null);
	let saving = $state(false);
	let job = $state<Job | null>(null);
	let confirmReset = $state(false);

	async function loadJob() {
		try {
			job = (await getGroups('all', 0, 1)).status.job;
		} catch (e) {
			error = errorMessage(e);
		}
	}

	$effect(() => {
		accountSettings.load();
		loadJob();
	});

	async function save(values: Partial<AccountSettings>) {
		saving = true;
		try {
			await accountSettings.set(values);
			error = null;
		} catch (e) {
			error = errorMessage(e);
		} finally {
			saving = false;
		}
		await loadJob();
	}

	async function reset() {
		confirmReset = false;
		try {
			job = await resetGroups();
			error = null;
		} catch (e) {
			error = errorMessage(e);
			await loadJob();
		}
	}

	async function searchAgain() {
		try {
			job = await refreshGroups();
			error = null;
		} catch (e) {
			error = errorMessage(e);
		}
	}

	function number(event: Event): number | null {
		const value = (event.currentTarget as HTMLInputElement).valueAsNumber;
		return Number.isNaN(value) ? null : value;
	}

	function saveSimilarity(event: Event) {
		const value = number(event);
		if (value !== null) save({ groups_similarity: value });
	}

	function saveCore(event: Event) {
		const value = number(event);
		if (value !== null) save({ groups_core_neighbors: value });
	}
</script>

<section>
	<h2>{m.groups_settings_heading()}</h2>
	<label class="field">
		<span>
			{m.groups_settings_similarity()}
			<span class="hint">{m.groups_settings_similarity_hint()}</span>
		</span>
		<span class="st-input st-input--sm">
			<input
				type="number"
				min="0.1"
				max="0.95"
				step="0.01"
				value={accountSettings.values.groups_similarity}
				disabled={saving}
				onchange={saveSimilarity}
			/>
		</span>
	</label>
	<label class="field">
		<span>
			{m.groups_settings_core()}
			<span class="hint">{m.groups_settings_core_hint()}</span>
		</span>
		<span class="st-input st-input--sm">
			<input
				type="number"
				min="1"
				max="30"
				step="1"
				value={accountSettings.values.groups_core_neighbors}
				disabled={saving}
				onchange={saveCore}
			/>
		</span>
	</label>
	<label class="st-check">
		<input
			type="checkbox"
			checked={accountSettings.values.groups_mutual}
			disabled={saving}
			onchange={(e) => save({ groups_mutual: (e.currentTarget as HTMLInputElement).checked })}
		/>
		<span>
			{m.groups_settings_mutual()}
			<span class="hint">{m.groups_settings_mutual_hint()}</span>
		</span>
	</label>
	<p class="hint">{m.groups_settings_split_hint()}</p>
	<p class="hint">{m.groups_settings_rebuild_hint()}</p>
	<div>
		<button
			type="button"
			class="st-btn st-btn--secondary st-btn--sm"
			disabled={isActive(job)}
			onclick={searchAgain}
		>
			{m.groups_settings_search_again()}
		</button>
		<p class="hint">{m.groups_settings_search_again_hint()}</p>
	</div>
	<div>
		<button
			type="button"
			class="st-btn st-btn--secondary st-btn--sm"
			disabled={isActive(job)}
			onclick={() => (confirmReset = true)}
		>
			{m.groups_settings_reset()}
		</button>
		<p class="hint">{m.groups_settings_reset_hint()}</p>
	</div>
	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
</section>

{#if confirmReset}
	<Dialog
		title={m.groups_settings_reset()}
		icon="triangle-alert"
		onclose={() => (confirmReset = false)}
	>
		<p>{m.groups_reset_warning()}</p>
		{#snippet footer()}
			<button type="button" class="st-btn st-btn--secondary" onclick={() => (confirmReset = false)}>
				{m.groups_reset_cancel()}
			</button>
			<button type="button" class="st-btn st-btn--danger" onclick={reset}>
				{m.groups_reset_confirm()}
			</button>
		{/snippet}
	</Dialog>
{/if}

<style>
	section {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		margin-bottom: var(--space-10);
	}
	h2,
	p {
		margin: 0;
	}
	.field {
		display: grid;
		grid-template-columns: 1fr 6rem;
		gap: var(--space-3);
		align-items: start;
	}
	.hint {
		display: block;
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	.error {
		color: var(--color-danger-text);
	}
</style>
