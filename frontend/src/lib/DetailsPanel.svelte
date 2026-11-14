<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Personal settings of matching details: when a suggestion counts as confirmed, where it is
     shown, and how many photos a photo is compared with. -->
<script lang="ts">
	import { accountSettings } from '#lib/accountSettings.svelte.js';
	import { errorMessage } from '#lib/errors.js';
	import type { AccountSettings } from '#lib/api.js';
	import { m } from '#lib/paraglide/messages.js';

	let error = $state<string | null>(null);
	let saving = $state(false);

	$effect(() => {
		accountSettings.load();
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
	}

	type NumberKey =
		'details_confirmed_from' | 'details_candidates_auto' | 'details_candidates_manual';

	function saveNumber(key: NumberKey, event: Event) {
		const value = (event.currentTarget as HTMLInputElement).valueAsNumber;
		if (!Number.isNaN(value)) save({ [key]: Math.round(value) });
	}
</script>

<section>
	<h2>{m.details_settings_heading()}</h2>
	<p class="intro">{m.details_settings_intro()}</p>
	<label class="field">
		<span>
			{m.details_settings_threshold()}
			<span class="hint">{m.details_settings_threshold_hint()}</span>
		</span>
		<span class="st-input st-input--sm">
			<input
				type="number"
				min="8"
				max="2000"
				step="1"
				value={accountSettings.values.details_confirmed_from}
				disabled={saving}
				onchange={(e) => saveNumber('details_confirmed_from', e)}
			/>
		</span>
	</label>
	<label class="st-check">
		<input
			type="checkbox"
			checked={accountSettings.values.details_first}
			disabled={saving}
			onchange={(e) => save({ details_first: e.currentTarget.checked })}
		/>
		<span>
			{m.details_settings_first()}
			<span class="hint">{m.details_settings_first_hint()}</span>
		</span>
	</label>
	<label class="field">
		<span>
			{m.details_settings_auto()}
			<span class="hint">{m.details_settings_auto_hint()}</span>
		</span>
		<span class="st-input st-input--sm">
			<input
				type="number"
				min="1"
				max="30"
				step="1"
				value={accountSettings.values.details_candidates_auto}
				disabled={saving}
				onchange={(e) => saveNumber('details_candidates_auto', e)}
			/>
		</span>
	</label>
	<label class="field">
		<span>
			{m.details_settings_manual()}
			<span class="hint">{m.details_settings_manual_hint()}</span>
		</span>
		<span class="st-input st-input--sm">
			<input
				type="number"
				min="1"
				max="30"
				step="1"
				value={accountSettings.values.details_candidates_manual}
				disabled={saving}
				onchange={(e) => saveNumber('details_candidates_manual', e)}
			/>
		</span>
	</label>
	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
</section>

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
	.intro {
		font-size: var(--text-sm);
		color: var(--color-text-muted);
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
