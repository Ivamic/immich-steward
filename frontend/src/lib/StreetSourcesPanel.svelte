<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Sources of street-level images for this account (D-244): what goes to each provider,
     switching on (= agreeing that the point looked at goes there), the access token where one is
     needed. Looks as the satellite sources above it. Tokens never come back to the browser. -->
<script lang="ts">
	import { getStreetSources, updateStreetSource, type StreetSource } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';

	let sources = $state<StreetSource[]>([]);
	let busy = $state<string | null>(null);
	let error = $state<string | null>(null);
	// Typed tokens, by source; cleared once saved.
	let keys = $state<Record<string, string>>({});

	$effect(() => {
		getStreetSources()
			.then((found) => (sources = found))
			.catch((e) => (error = errorMessage(e)));
	});

	async function update(id: string, change: { enabled?: boolean; api_key?: string }) {
		busy = id;
		try {
			const item = await updateStreetSource(id, change);
			sources = sources.map((s) => (s.id === id ? item : s));
			error = null;
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = null;
		}
	}

	async function saveKey(id: string) {
		await update(id, { api_key: keys[id] ?? '' });
		keys = { ...keys, [id]: '' };
	}

	function statusText(source: StreetSource): string {
		if (source.needs_key && !source.has_key) return m.street_status_no_key();
		if (source.key_problem === 'invalid') return m.street_status_invalid();
		return source.enabled ? m.street_status_on() : m.street_status_off();
	}

	function statusClass(source: StreetSource): string {
		if (source.key_problem === 'invalid') return 'st-badge--danger';
		if (source.needs_key && !source.has_key) return 'st-badge--warning';
		return source.enabled ? 'st-badge--success' : 'st-badge--outline';
	}

	const about = (id: string) =>
		id === 'mapillary' ? m.street_about_mapillary() : m.street_about_panoramax();
</script>

<!-- eslint-disable svelte/no-navigation-without-resolve -- links to the providers -->
<section>
	<h2>{m.street_heading()}</h2>
	<p class="hint">{m.street_hint()}</p>
	{#each sources as source (source.id)}
		<article class="source" aria-busy={busy === source.id}>
			<header>
				<h3>{source.name}</h3>
				<span class="st-badge {statusClass(source)}">{statusText(source)}</span>
				<label class="st-check st-check--sm">
					<input
						type="checkbox"
						checked={source.enabled}
						disabled={busy !== null}
						onchange={(e) =>
							update(source.id, { enabled: (e.currentTarget as HTMLInputElement).checked })}
					/>
					{m.street_enable()}
				</label>
			</header>
			<p class="terms">
				{about(source.id)}
				<a href={source.terms_url} target="_blank" rel="noopener">{m.mapsrc_terms_link()}</a>
				· <a href={source.site_url} target="_blank" rel="noopener">{m.mapsrc_site_link()}</a>
			</p>
			{#if source.needs_key}
				<div class="row">
					<span class="what">{m.street_key()}</span>
					{#if source.has_key}<span class="note">{m.street_key_saved()}</span>{/if}
					<input
						class="st-input"
						type="password"
						autocomplete="off"
						spellcheck="false"
						placeholder={source.has_key ? m.mapsrc_key_replace() : m.street_key_placeholder()}
						value={keys[source.id] ?? ''}
						oninput={(e) =>
							(keys = { ...keys, [source.id]: (e.currentTarget as HTMLInputElement).value })}
					/>
					<button
						type="button"
						class="st-btn st-btn--secondary st-btn--sm"
						disabled={busy !== null || !(keys[source.id] ?? '').trim()}
						onclick={() => saveKey(source.id)}>{m.mapsrc_save()}</button
					>
					{#if source.has_key}
						<button
							type="button"
							class="st-btn st-btn--ghost st-btn--sm"
							disabled={busy !== null}
							onclick={() => update(source.id, { api_key: '' })}>{m.mapsrc_key_delete()}</button
						>
					{/if}
				</div>
				{#if source.key_url && !source.has_key}
					<p class="note">
						<a href={source.key_url} target="_blank" rel="noopener">{m.street_get_key()}</a>
						— {m.street_key_which()}
					</p>
				{/if}
			{/if}
		</article>
	{/each}
	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
</section>

<style>
	section {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		max-width: 44rem;
		margin-bottom: var(--space-10);
	}
	h2,
	h3,
	p {
		margin: 0;
	}
	h3 {
		font-size: var(--text-base);
	}
	.hint,
	.note,
	.terms {
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	.source {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding: var(--space-3);
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface);
	}
	.source[aria-busy='true'] {
		opacity: 0.7;
	}
	header {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-2);
	}
	header h3 {
		flex: 1;
	}
	.row {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-2);
	}
	.row .st-input {
		flex: 1;
		min-width: 10rem;
	}
	.what {
		font-weight: var(--weight-medium);
	}
	.error {
		color: var(--color-danger-text);
	}
</style>
