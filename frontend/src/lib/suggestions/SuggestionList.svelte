<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  Suggestions under the map, grouped by module. The number in the colored circle is the rank
  within the module (as on the map); the key 1–9 picks one of the first nine. Cameras that a
  module looked at can be excluded (e.g. someone else's phone with a wrong clock). Modules run by
  workers show the state of their latest run and can be started from here.
-->
<script lang="ts">
	import { isPending, thumbnailUrl, type Candidate, type ModuleSuggestions } from '#lib/api.js';
	import { m } from '#lib/paraglide/messages.js';
	import { resolve } from '$app/paths';
	import { setCameraExcluded } from './cameraFilter.svelte.js';
	import {
		candidateDetails,
		candidateLabel,
		candidateRemarks,
		formatDelta,
		formatDistance,
		moduleName,
		moduleNote,
		numberCandidates,
		visibleSuggestions
	} from './format.js';

	let {
		modules,
		loading,
		onchoose,
		onrun,
		unfolded,
		ontoggle
	}: {
		modules: ModuleSuggestions[];
		loading: boolean;
		onchoose: (candidate: Candidate) => void;
		onrun: (module: string) => void;
		/** Modules whose weak suggestions are shown. */
		unfolded: string[];
		ontoggle: (module: string) => void;
	} = $props();

	const weakCount = (module: ModuleSuggestions) =>
		module.candidates.filter((c) => c.tier === 'weak').length;

	function status(module: ModuleSuggestions): string | null {
		switch (module.status) {
			case 'not_run':
				return m.module_status_not_run();
			case 'queued':
				return module.queue_position
					? m.module_status_queued_behind({ count: String(module.queue_position) })
					: m.module_status_queued();
			case 'running':
				return m.module_status_running();
			case 'failed':
				return m.module_status_failed({ error: module.error ?? '' });
			case 'done':
				return module.candidates.length ? null : m.module_no_candidates();
			default:
				return null;
		}
	}

	const shown = $derived(visibleSuggestions(modules, unfolded));
	const keys = $derived(new Map(numberCandidates(shown).map((item) => [item.candidate, item.key])));
</script>

<section class="suggestions" aria-busy={loading}>
	<h2>{m.suggestions_heading()}</h2>
	{#if loading && !modules.length}
		<p class="muted">{m.suggestions_loading()}</p>
	{/if}
	{#each shown as module, index (module.module)}
		{@const weak = weakCount(modules[index])}
		<div class="module">
			<h3>
				<span class="swatch shape-{module.shape}" style:background={module.color}></span>
				{moduleName(module.module)}
				{#if module.runnable}
					<button
						type="button"
						class="run"
						disabled={isPending(module)}
						onclick={() => onrun(module.module)}
					>
						{module.status === 'not_run' ? m.module_run() : m.module_rerun()}
					</button>
				{/if}
			</h3>
			{#if status(module)}
				<p class="muted" class:pending={isPending(module)}>{status(module)}</p>
			{/if}
			{#if module.runnable && !module.worker_available && module.status !== 'done'}
				<p class="warning">{m.module_no_worker()}</p>
			{/if}
			{#if module.cameras.length}
				<fieldset class="devices">
					<legend>{m.suggestions_devices()}</legend>
					{#each module.cameras as camera (camera.value)}
						<label>
							<input
								type="checkbox"
								checked={!camera.excluded}
								onchange={(e) => setCameraExcluded(camera.value, !e.currentTarget.checked)}
							/>
							{camera.label || m.device_unknown()}
							<span class="muted">
								({camera.count}{camera.same_camera ? `, ${m.device_this()}` : ''})
							</span>
						</label>
					{/each}
				</fieldset>
			{/if}
			{#if module.note && !module.candidates.length}
				<p class="muted">{moduleNote(module.note)}</p>
			{/if}
			<ol>
				{#each module.candidates as candidate (candidate.rank)}
					{@const key = keys.get(candidate)}
					<li class:weak={candidate.tier === 'weak'}>
						<span class="rank shape-{module.shape}" style:background={module.color}
							>{candidate.rank}</span
						>
						<div class="body">
							<div class="label" title={candidateDetails(candidate)}>
								{candidateLabel(candidate)}
							</div>
							<div class="meta">
								<span
									class="score"
									title={m.candidate_score({ percent: String(Math.round(candidate.score * 100)) })}
								>
									<span style:width="{Math.round(candidate.score * 100)}%"></span>
								</span>
								<span class="percent">{Math.round(candidate.score * 100)}%</span>
								{#if candidate.tier === 'confident'}
									<span class="confident">{m.candidate_confident()}</span>
								{/if}
								{#if candidate.radius_m}
									<span>±{formatDistance(candidate.radius_m)}</span>
								{/if}
								{#each candidateRemarks(candidate) as remark (remark)}
									<span class="remark">{remark}</span>
								{/each}
							</div>
							<div class="neighbors">
								{#each candidate.evidence.neighbors ?? [] as neighbor (neighbor.asset_id)}
									<a
										href={resolve('/photo/[id]', { id: neighbor.asset_id })}
										target="_blank"
										rel="noopener"
										title="{neighbor.file_name} — {m.photo_open_new_tab()}"
									>
										<figure>
											<img
												src={thumbnailUrl(neighbor.asset_id)}
												alt={neighbor.file_name}
												loading="lazy"
											/>
											<figcaption>{formatDelta(neighbor.delta_s)}</figcaption>
										</figure>
									</a>
								{/each}
							</div>
						</div>
						<button type="button" onclick={() => onchoose(candidate)}>
							{m.candidate_choose()}
							{#if key}<kbd>{key}</kbd>{/if}
						</button>
					</li>
				{/each}
			</ol>
			{#if weak}
				<button type="button" class="fold" onclick={() => ontoggle(module.module)}>
					{unfolded.includes(module.module)
						? m.suggestions_weak_hide()
						: m.suggestions_weak_more({ count: String(weak) })}
				</button>
			{/if}
		</div>
	{/each}
</section>

<style>
	h2 {
		font-size: 1rem;
		margin: 0.25rem 0;
	}
	h3 {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		font-size: 0.9rem;
		margin: 0.5rem 0 0.25rem;
	}
	.swatch {
		width: 0.75rem;
		height: 0.75rem;
		border-radius: 50%;
	}
	.swatch.shape-square {
		border-radius: 0.15rem;
	}
	.run {
		margin-left: 0.5rem;
		font-size: 0.8rem;
	}
	.pending::before {
		content: '⏳ ';
	}
	.warning {
		color: #9a6700;
		font-size: 0.85rem;
		margin: 0 0 0.4rem;
	}
	ol {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	li {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr) auto;
		gap: 0.6rem;
		align-items: start;
		padding: 0.4rem 0.5rem;
		border: 1px solid rgb(127 127 127 / 0.25);
		border-radius: 0.4rem;
	}
	.rank.shape-square {
		border-radius: 0.3rem;
	}
	.rank {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.5rem;
		height: 1.5rem;
		border-radius: 50%;
		color: #fff;
		font-weight: 700;
		font-size: 0.85rem;
	}
	.label {
		word-break: break-word;
	}
	.meta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.3rem 0.75rem;
		font-size: 0.85rem;
		opacity: 0.8;
	}
	.score {
		display: inline-block;
		width: 4rem;
		height: 0.4rem;
		border-radius: 0.2rem;
		background: rgb(127 127 127 / 0.25);
		overflow: hidden;
	}
	.score span {
		display: block;
		height: 100%;
		background: #1a7f37;
	}
	li.weak {
		opacity: 0.65;
	}
	.percent {
		margin-left: -0.4rem;
		font-variant-numeric: tabular-nums;
	}
	.confident {
		color: #1a7f37;
		font-weight: 600;
	}
	.fold {
		margin-top: 0.4rem;
		border: none;
		background: none;
		padding: 0;
		color: #0969da;
		cursor: pointer;
		text-decoration: underline;
		font-size: 0.85rem;
	}
	.remark {
		color: #9a6700;
	}
	.neighbors {
		display: flex;
		gap: 0.4rem;
		margin-top: 0.3rem;
	}
	.devices {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 1rem;
		margin: 0 0 0.5rem;
		padding: 0;
		border: none;
		font-size: 0.85rem;
	}
	.devices legend {
		float: left;
		margin-right: 0.5rem;
		font-weight: 600;
	}
	.neighbors a {
		color: inherit;
		text-decoration: none;
	}
	figure {
		margin: 0;
		font-size: 0.75rem;
		text-align: center;
	}
	figure img {
		display: block;
		width: 4rem;
		height: 4rem;
		object-fit: cover;
		border-radius: 0.25rem;
	}
	.muted {
		opacity: 0.65;
		margin: 0;
	}
	kbd {
		font-size: 0.75em;
		opacity: 0.7;
	}
</style>
