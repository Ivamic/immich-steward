<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!--
  Suggestions next to the map, grouped by module, one compact row each. The number in the colored circle is the rank
  within the module (as on the map); the key 1–9 picks one of the first nine. Cameras that a
  module looked at can be excluded (e.g. someone else's phone with a wrong clock). Modules run by
  workers show the state of their latest run and can be started from here. Hovering a row
  highlights its marker on the map, and the other way round. A click on a row shows the
  suggestion on the map without picking it; hovering a neighbor's thumbnail enlarges it.
-->
<script lang="ts">
	import {
		isPending,
		thumbnailUrl,
		type Candidate,
		type ModuleSuggestions,
		type NeighborEvidence,
		type Region
	} from '#lib/api.js';
	import { m } from '#lib/paraglide/messages.js';
	import { resolve } from '$app/paths';
	import { cameraFilter, setCameraExcluded } from './cameraFilter.svelte.js';
	import type { Highlight } from './highlight.js';
	import {
		candidateDetails,
		candidateLabel,
		candidateRemarks,
		failureReason,
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
		ontoggle,
		highlight,
		onhighlight,
		onlocate,
		onpart,
		onpartshow,
		parts = true
	}: {
		modules: ModuleSuggestions[];
		loading: boolean;
		onchoose: (candidate: Candidate) => void;
		onrun: (module: string) => void;
		/** Modules whose weak suggestions are shown. */
		unfolded: string[];
		ontoggle: (module: string) => void;
		highlight: Highlight | null;
		onhighlight: (highlight: Highlight | null) => void;
		/** Show the suggestion on the map (does not pick it). */
		onlocate: (candidate: Candidate) => void;
		/** Choose a part of the photo for the module (FR-35), starting from the last one. */
		onpart: (module: string, region: Region | null) => void;
		/** The part of the photo to outline while a block of a run on a part is hovered. */
		onpartshow: (region: Region | null) => void;
		/** Runs on a part are possible (photos, not videos). */
		parts?: boolean;
	} = $props();

	const lastPart = (module: string) =>
		modules.find((block) => block.module === module && block.region)?.region ?? null;

	// Enlarged thumbnail of a neighbor photo, next to the hovered one.
	let peek = $state<{
		id: string;
		name: string;
		meta: string;
		left: number;
		top: number;
	} | null>(null);
	const PEEK_WIDTH = 240;
	const PEEK_HEIGHT = 230;

	function showPeek(event: MouseEvent, module: ModuleSuggestions, neighbor: NeighborEvidence) {
		const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
		const camera = module.track.find((p) => p.asset_id === neighbor.asset_id)?.camera;
		// Below the thumbnail, or above it near the bottom of the window; never off screen.
		const below = box.bottom + 6 + PEEK_HEIGHT < innerHeight;
		peek = {
			id: neighbor.asset_id,
			name: neighbor.file_name,
			meta: [formatDelta(neighbor.delta_s), camera || m.device_unknown()].join(' · '),
			left: Math.max(8, Math.min(box.left, innerWidth - PEEK_WIDTH - 8)),
			top: below ? box.bottom + 6 : Math.max(8, box.top - PEEK_HEIGHT - 6)
		};
	}

	/** A click anywhere on a row, except on its controls, shows the suggestion on the map. */
	function rowClick(event: MouseEvent, candidate: Candidate) {
		if ((event.target as HTMLElement).closest('button, a')) return;
		onlocate(candidate);
	}

	let list = $state<HTMLElement>();

	// A marker hovered on the map brings its row into view.
	$effect(() => {
		if (highlight?.from !== 'map' || !list) return;
		list
			.querySelector(`[data-candidate="${highlight.module}:${highlight.rank}"]`)
			?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
	});

	const isHighlighted = (module: string, rank: number) =>
		highlight?.module === module && highlight.rank === rank;

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
				return m.module_status_failed({ error: failureReason(module.error_code) });
			case 'done':
				return module.candidates.length ? null : m.module_no_candidates();
			default:
				return null;
		}
	}

	const shown = $derived(visibleSuggestions(modules, unfolded));
	const keys = $derived(new Map(numberCandidates(shown).map((item) => [item.candidate, item.key])));
</script>

<section class="suggestions" aria-busy={loading} bind:this={list}>
	<h2>{m.suggestions_heading()}</h2>
	{#if loading && !modules.length}
		<p class="muted">{m.suggestions_loading()}</p>
	{/if}
	{#each shown as module, index (module.key)}
		{@const weak = weakCount(modules[index])}
		<div
			class="module"
			role="group"
			onmouseenter={() => module.region && onpartshow(module.region)}
			onmouseleave={() => module.region && onpartshow(null)}
		>
			<h3>
				<span class="swatch shape-{module.shape}" style:background={module.color}></span>
				{module.region
					? m.module_part_title({ module: moduleName(module.module) })
					: moduleName(module.module)}
				{#if module.runnable}
					<button
						type="button"
						class="run"
						disabled={isPending(module)}
						onclick={() =>
							module.region ? onpart(module.module, module.region) : onrun(module.module)}
					>
						{module.region
							? m.module_part_change()
							: module.status === 'not_run'
								? m.module_run()
								: m.module_rerun()}
					</button>
					{#if parts && !module.region}
						<button
							type="button"
							class="run"
							title={m.module_part_hint()}
							onclick={() => onpart(module.module, lastPart(module.module))}
						>
							{m.module_part_run()} <kbd>R</kbd>
						</button>
					{/if}
				{/if}
			</h3>
			{#if status(module)}
				<p
					class="muted"
					class:pending={isPending(module)}
					title={module.status === 'failed' ? (module.error ?? undefined) : undefined}
				>
					{status(module)}
				</p>
				{#if module.status === 'failed' && module.error_code === 'lease_expired'}
					<p class="muted">{m.failure_lease_expired_hint()}</p>
				{/if}
			{/if}
			{#if module.runnable && !module.worker_available && module.status !== 'done'}
				<p class="warning">{m.module_no_worker()}</p>
			{/if}
			<!-- Shown in "only this device" mode even without neighbors, so that it can be undone. -->
			{#if module.cameras.length || (module.module === 'time_neighbors' && cameraFilter.sameOnly)}
				<fieldset class="devices">
					<legend>{m.suggestions_devices()}</legend>
					<label class="same-only" title={m.device_same_only_hint()}>
						<input
							type="checkbox"
							checked={cameraFilter.sameOnly}
							onchange={(e) => (cameraFilter.sameOnly = e.currentTarget.checked)}
						/>
						{m.device_same_only()}
					</label>
					{#each module.cameras as camera (camera.value)}
						<label>
							<input
								type="checkbox"
								checked={!camera.excluded}
								disabled={cameraFilter.sameOnly && !camera.same_camera}
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
					<!-- The row is a shortcut for the mouse; keyboard users have the label button. -->
					<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
					<li
						onclick={(e) => rowClick(e, candidate)}
						class:weak={candidate.tier === 'weak'}
						class:highlight={isHighlighted(module.key, candidate.rank)}
						data-candidate="{module.key}:{candidate.rank}"
						onmouseenter={() =>
							onhighlight({ module: module.key, rank: candidate.rank, from: 'list' })}
						onmouseleave={() => onhighlight(null)}
					>
						<span class="rank shape-{module.shape}" style:background={module.color}
							>{candidate.rank}</span
						>
						<div class="body">
							<button
								type="button"
								class="label"
								title={candidateDetails(candidate) ?? m.candidate_locate()}
								onclick={() => onlocate(candidate)}
							>
								{candidateLabel(candidate)}
							</button>
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
								{#each candidate.evidence.neighbors ?? [] as neighbor (neighbor.asset_id)}
									<a
										class="neighbor"
										href={resolve('/photo/[id]', { id: neighbor.asset_id })}
										target="_blank"
										rel="noopener"
										aria-label="{neighbor.file_name} — {m.photo_open_new_tab()}"
										onmouseenter={(e) => showPeek(e, module, neighbor)}
										onmouseleave={() => (peek = null)}
									>
										<img
											src={thumbnailUrl(neighbor.asset_id)}
											alt={neighbor.file_name}
											loading="lazy"
										/>
									</a>
								{/each}
							</div>
						</div>
						<button type="button" class="choose" onclick={() => onchoose(candidate)}>
							{m.candidate_choose()}
							{#if key}<kbd>{key}</kbd>{/if}
						</button>
					</li>
				{/each}
			</ol>
			{#if weak}
				<button type="button" class="fold" onclick={() => ontoggle(module.key)}>
					{unfolded.includes(module.key)
						? m.suggestions_weak_hide()
						: m.suggestions_weak_more({ count: String(weak) })}
				</button>
			{/if}
		</div>
	{/each}
</section>

{#if peek}
	<div class="peek" style:left="{peek.left}px" style:top="{peek.top}px" aria-hidden="true">
		<img src={thumbnailUrl(peek.id)} alt="" />
		<div class="name">{peek.name}</div>
		<div>{peek.meta}</div>
		<div class="muted">{m.photo_open_new_tab()}</div>
	</div>
{/if}

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
		gap: 0.3rem;
	}
	li {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr) auto;
		gap: 0.5rem;
		align-items: center;
		padding: 0.3rem 0.4rem;
		border: 1px solid rgb(127 127 127 / 0.25);
		border-radius: 0.4rem;
		font-size: 0.9rem;
	}
	li.highlight {
		border-color: #0969da;
		box-shadow: 0 0 0 2px rgb(9 105 218 / 0.25);
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
	li {
		cursor: pointer;
	}
	.label {
		padding: 0;
		border: none;
		background: none;
		color: inherit;
		font: inherit;
		text-align: left;
		cursor: pointer;
		word-break: break-word;
		/* Two lines at most; the full text is in the title. */
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.peek {
		position: fixed;
		z-index: 20;
		width: 240px;
		padding: 0.4rem;
		border-radius: 0.4rem;
		background: #fff;
		color: #24292f;
		box-shadow: 0 4px 16px rgb(0 0 0 / 0.3);
		font-size: 0.8rem;
		pointer-events: none;
	}
	.peek img {
		display: block;
		width: 100%;
		max-height: 160px;
		object-fit: cover;
		border-radius: 0.25rem;
		margin-bottom: 0.3rem;
	}
	.peek .name {
		font-weight: 600;
		word-break: break-all;
	}
	.choose {
		font-size: 0.8rem;
		white-space: nowrap;
	}
	.meta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.2rem 0.6rem;
		font-size: 0.8rem;
	}
	.score {
		display: inline-block;
		width: 3rem;
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
		display: block;
		text-align: left;
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
	.neighbor img {
		display: block;
		width: 1.75rem;
		height: 1.75rem;
		object-fit: cover;
		border-radius: 0.2rem;
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
