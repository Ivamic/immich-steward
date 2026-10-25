<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Satellite imagery sources of the map for this account (D-140...D-147): short terms with a
     link to the full ones, the key, switching on (= accepting the terms), the state, the tiles we
     counted and, where the provider tells it, its own usage; then the switching by zoom. Keys come
     back masked only. -->
<script lang="ts">
	import {
		checkMapKey,
		getMapSources,
		refreshMapUsage,
		resetMapCount,
		setMapAuto,
		updateMapSource,
		type MapAuto,
		type MapSourceItem,
		type MapSourceUpdate
	} from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import { m } from '#lib/paraglide/messages.js';

	let sources = $state<MapSourceItem[]>([]);
	let auto = $state<MapAuto | null>(null);
	let busy = $state<string | null>(null);
	let error = $state<string | null>(null);
	// Typed keys and tokens, by source; cleared once saved.
	let keys = $state<Record<string, string>>({});
	let tokens = $state<Record<string, string>>({});
	const DAYS = Array.from({ length: 31 }, (_, i) => i + 1);

	$effect(() => {
		getMapSources()
			.then((result) => {
				sources = result.sources;
				auto = result.auto;
			})
			.catch((e) => (error = errorMessage(e)));
	});

	const number = (n: number) => n.toLocaleString(getLocale());
	const day = (iso: string) =>
		new Date(iso).toLocaleDateString(getLocale(), {
			day: 'numeric',
			month: 'long',
			year: 'numeric'
		});

	async function act(id: string, work: () => Promise<MapSourceItem>) {
		busy = id;
		try {
			const item = await work();
			sources = sources.map((s) => (s.id === id ? item : s));
			error = null;
			// Switching a source off may take it out of the switching by zoom.
			if (auto) auto = (await getMapSources()).auto;
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = null;
		}
	}

	const update = (id: string, change: MapSourceUpdate) =>
		act(id, () => updateMapSource(id, change));

	async function saveKey(id: string) {
		await update(id, { api_key: keys[id] ?? '' });
		keys = { ...keys, [id]: '' };
	}

	async function saveToken(id: string) {
		await update(id, { usage_token: tokens[id] ?? '' });
		tokens = { ...tokens, [id]: '' };
	}

	async function saveAuto(change: Partial<MapAuto>) {
		if (!auto) return;
		const before = auto;
		auto = { ...auto, ...change };
		busy = 'auto';
		try {
			auto = await setMapAuto(auto);
			error = null;
		} catch (e) {
			auto = before;
			error = errorMessage(e);
		} finally {
			busy = null;
		}
	}

	function statusText(source: MapSourceItem): string {
		switch (source.status) {
			case 'no_key':
				return m.mapsrc_status_no_key();
			case 'invalid':
				return m.mapsrc_status_invalid();
			case 'exhausted':
				return m.mapsrc_status_exhausted();
			default:
				return source.enabled ? m.mapsrc_status_ok() : m.mapsrc_status_off();
		}
	}

	function statusClass(source: MapSourceItem): string {
		if (source.status === 'invalid' || source.status === 'exhausted') return 'st-badge--danger';
		if (source.status === 'no_key') return 'st-badge--warning';
		return source.enabled ? 'st-badge--success' : 'st-badge--outline';
	}

	function terms(id: string): string {
		if (id === 'eox') return m.mapsrc_terms_eox();
		if (id === 'esri') return m.mapsrc_terms_esri();
		if (id === 'maptiler') return m.mapsrc_terms_maptiler();
		return '';
	}

	function quality(id: string): string {
		if (id === 'eox') return m.mapsrc_quality_eox();
		if (id === 'esri') return m.mapsrc_quality_esri();
		if (id === 'maptiler') return m.mapsrc_quality_maptiler();
		return '';
	}

	function periodRule(id: string): string | null {
		if (id === 'esri') return m.mapsrc_period_esri();
		if (id === 'maptiler') return m.mapsrc_period_maptiler();
		return null;
	}

	const enabledSources = $derived(sources.filter((s) => s.enabled));
	const percent = (used: number, quota: number) => Math.min(100, Math.round((used / quota) * 100));
</script>

<!-- eslint-disable svelte/no-navigation-without-resolve -- links to the providers -->
<section>
	<h2>{m.mapsrc_heading()}</h2>
	<p class="hint">{m.mapsrc_hint()}</p>
	<p class="hint">{m.mapsrc_own_count_hint()}</p>
	{#each sources as source (source.id)}
		{@const usage = source.provider_usage}
		<article class="source" aria-busy={busy === source.id}>
			<header>
				<h3>{source.name}</h3>
				<span class="st-badge {statusClass(source)}">{statusText(source)}</span>
				<label class="st-check st-check--sm on">
					<input
						type="checkbox"
						checked={source.enabled}
						disabled={busy !== null || (source.needs_key && !source.key)}
						title={source.needs_key && !source.key ? m.mapsrc_need_key() : undefined}
						onchange={(e) =>
							update(source.id, { enabled: (e.currentTarget as HTMLInputElement).checked })}
					/>
					{m.mapsrc_enable()}
				</label>
			</header>
			<p class="quality">{quality(source.id)}</p>
			<p class="terms">
				{terms(source.id)}
				<a href={source.terms_url} target="_blank" rel="noopener">{m.mapsrc_terms_link()}</a>
				· <a href={source.site_url} target="_blank" rel="noopener">{m.mapsrc_site_link()}</a>
			</p>

			{#if source.needs_key}
				<div class="row">
					<span class="what">{m.mapsrc_key()}</span>
					{#if source.key}<code>{source.key}</code>{/if}
					<input
						class="st-input"
						type="password"
						autocomplete="off"
						spellcheck="false"
						placeholder={source.key ? m.mapsrc_key_replace() : m.mapsrc_key_placeholder()}
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
					{#if source.key}
						<button
							type="button"
							class="st-btn st-btn--ghost st-btn--sm"
							disabled={busy !== null}
							onclick={() => act(source.id, () => checkMapKey(source.id))}
							>{m.mapsrc_check()}</button
						>
						<button
							type="button"
							class="st-btn st-btn--ghost st-btn--sm"
							disabled={busy !== null}
							onclick={() => update(source.id, { api_key: null })}>{m.mapsrc_key_delete()}</button
						>
					{/if}
				</div>
				{#if source.key_url && !source.key}
					<p class="note">
						<a href={source.key_url} target="_blank" rel="noopener">{m.mapsrc_get_key()}</a>
						— {m.mapsrc_key_restrict()}
					</p>
				{/if}
				{#if source.key_check === 'unreachable'}
					<p class="note warn">{m.mapsrc_check_unreachable()}</p>
				{/if}
			{/if}

			<div class="row count">
				<span>
					{m.mapsrc_own_count({ tiles: number(source.tiles), since: day(source.counted_since) })}
				</span>
				<button
					type="button"
					class="st-btn st-btn--ghost st-btn--sm"
					disabled={busy !== null}
					onclick={() => act(source.id, () => resetMapCount(source.id))}>{m.mapsrc_reset()}</button
				>
				{#if source.needs_key}
					<label class="reset-day">
						{m.mapsrc_reset_day()}
						<select
							class="st-select"
							value={source.reset_day === null ? '' : String(source.reset_day)}
							disabled={busy !== null}
							onchange={(e) => {
								const value = (e.currentTarget as HTMLSelectElement).value;
								update(source.id, { reset_day: value ? Number(value) : null });
							}}
						>
							<option value="">{m.mapsrc_reset_day_never()}</option>
							{#each DAYS as d (d)}<option value={String(d)}>{d}</option>{/each}
						</select>
					</label>
				{/if}
			</div>
			{#if periodRule(source.id) || source.usage_url}
				<p class="note">
					{periodRule(source.id) ?? ''}
					{#if source.usage_url}
						<a href={source.usage_url} target="_blank" rel="noopener">{m.mapsrc_usage_link()}</a>
					{/if}
				</p>
			{/if}

			{#if source.usage_token_supported}
				<details class="usage" open={Boolean(source.usage_token)}>
					<summary>{m.mapsrc_usage_heading()}</summary>
					<p class="note">{m.mapsrc_usage_hint()}</p>
					<div class="row">
						<span class="what">{m.mapsrc_usage_token()}</span>
						{#if source.usage_token}<code>{source.usage_token}</code>{/if}
						<input
							class="st-input"
							type="password"
							autocomplete="off"
							spellcheck="false"
							value={tokens[source.id] ?? ''}
							oninput={(e) =>
								(tokens = { ...tokens, [source.id]: (e.currentTarget as HTMLInputElement).value })}
						/>
						<button
							type="button"
							class="st-btn st-btn--secondary st-btn--sm"
							disabled={busy !== null || !(tokens[source.id] ?? '').trim()}
							onclick={() => saveToken(source.id)}>{m.mapsrc_save()}</button
						>
						{#if source.usage_token}
							<button
								type="button"
								class="st-btn st-btn--ghost st-btn--sm"
								disabled={busy !== null}
								onclick={() => act(source.id, () => refreshMapUsage(source.id))}
								>{m.mapsrc_usage_refresh()}</button
							>
							<button
								type="button"
								class="st-btn st-btn--ghost st-btn--sm"
								disabled={busy !== null}
								onclick={() => update(source.id, { usage_token: null })}
								>{m.mapsrc_key_delete()}</button
							>
						{/if}
					</div>
					{#if usage}
						{#if usage.error === 'token_invalid'}
							<p class="note warn">{m.mapsrc_usage_token_invalid()}</p>
						{:else if usage.error === 'unreachable'}
							<p class="note warn">{m.mapsrc_usage_unreachable()}</p>
						{/if}
						{#if usage.used !== null}
							<div class="st-progress">
								<div class="st-progress__row">
									<span>
										{m.mapsrc_usage_used({
											used: number(usage.used),
											since: usage.since ? day(usage.since) : '?'
										})}
									</span>
									{#if source.free_quota}
										<span class="st-progress__value">
											{m.mapsrc_usage_of_free({
												percent: percent(usage.used, source.free_quota),
												quota: number(source.free_quota)
											})}
										</span>
									{/if}
								</div>
								{#if source.free_quota}
									<div class="st-progress__track">
										<div
											class="st-progress__bar"
											style:transform={`scaleX(${percent(usage.used, source.free_quota) / 100})`}
										></div>
									</div>
								{/if}
							</div>
							<p class="note">
								{#if usage.estimated !== null}
									{m.mapsrc_usage_estimate({ n: number(usage.estimated) })}
								{/if}
								{m.mapsrc_usage_delay()}
							</p>
						{/if}
					{/if}
				</details>
			{/if}
		</article>
	{/each}

	{#if auto}
		<article class="source">
			<h3>{m.mapsrc_auto_heading()}</h3>
			<p class="note">{m.mapsrc_auto_settings_hint()}</p>
			<div class="row">
				<label class="field">
					{m.mapsrc_auto_far()}
					<select
						class="st-select"
						value={auto.far ?? ''}
						disabled={busy !== null}
						onchange={(e) =>
							saveAuto({ far: (e.currentTarget as HTMLSelectElement).value || null })}
					>
						<option value="">{m.mapsrc_scheme()}</option>
						{#each sources as s (s.id)}
							<option value={s.id} disabled={!s.enabled}
								>{s.name}{s.enabled ? '' : ` — ${m.mapsrc_option_off()}`}</option
							>
						{/each}
					</select>
				</label>
				<label class="field">
					{m.mapsrc_auto_near()}
					<select
						class="st-select"
						value={auto.near ?? ''}
						disabled={busy !== null}
						onchange={(e) =>
							saveAuto({ near: (e.currentTarget as HTMLSelectElement).value || null })}
					>
						<option value="">{m.mapsrc_scheme()}</option>
						{#each sources as s (s.id)}
							<option value={s.id} disabled={!s.enabled}
								>{s.name}{s.enabled ? '' : ` — ${m.mapsrc_option_off()}`}</option
							>
						{/each}
					</select>
				</label>
				<label class="field">
					{m.mapsrc_auto_zoom()}
					<input
						class="st-input zoom"
						type="number"
						min="1"
						max="22"
						value={auto.switch_zoom}
						disabled={busy !== null}
						onchange={(e) => {
							const value = Number((e.currentTarget as HTMLInputElement).value);
							if (value >= 1 && value <= 22) saveAuto({ switch_zoom: Math.round(value) });
						}}
					/>
				</label>
			</div>
			{#if !enabledSources.length}
				<p class="note">{m.mapsrc_auto_none()}</p>
			{/if}
		</article>
	{/if}
	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
</section>

<!-- eslint-enable svelte/no-navigation-without-resolve -->

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
	.quality,
	.terms {
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	.note.warn {
		color: var(--color-warning-text, var(--color-danger-text));
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
	code {
		font-size: var(--text-sm);
	}
	.count {
		font-size: var(--text-sm);
	}
	.reset-day,
	.field {
		display: inline-flex;
		align-items: center;
		gap: var(--space-1-5);
		font-size: var(--text-sm);
	}
	.row .zoom {
		width: 4.5rem;
		flex: none;
		min-width: 0;
	}
	.usage summary {
		cursor: pointer;
		font-size: var(--text-sm);
		font-weight: var(--weight-medium);
	}
	.usage[open] {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}
	.error {
		color: var(--color-danger-text);
	}
</style>
