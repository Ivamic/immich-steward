<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Personal settings of the gallery. -->
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
</script>

<section>
	<h2>{m.gallery_settings_heading()}</h2>
	<label class="st-check">
		<input
			type="checkbox"
			checked={accountSettings.values.gallery_tooltip}
			disabled={saving}
			onchange={(e) => save({ gallery_tooltip: (e.currentTarget as HTMLInputElement).checked })}
		/>
		<span>
			{m.gallery_settings_tooltip()}
			<span class="hint">{m.gallery_settings_tooltip_hint()}</span>
		</span>
	</label>
	<label class="st-check">
		<input
			type="checkbox"
			checked={accountSettings.values.video_sound}
			disabled={saving}
			onchange={(e) => save({ video_sound: (e.currentTarget as HTMLInputElement).checked })}
		/>
		<span>
			{m.gallery_settings_video_sound()}
			<span class="hint">{m.gallery_settings_video_sound_hint()}</span>
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
	.hint {
		display: block;
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	.error {
		color: var(--color-danger-text);
	}
</style>
