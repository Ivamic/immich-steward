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
	import ConfidenceMeter from '#lib/ui/ConfidenceMeter.svelte';
	import Icon from '#lib/ui/Icon.svelte';
	import Kbd from '#lib/ui/Kbd.svelte';
	import Skeleton from '#lib/ui/Skeleton.svelte';
	import Tooltip from '#lib/ui/Tooltip.svelte';
	import { resolve } from '$app/paths';
	import { moduleColor, moduleOnColor } from '#lib/map/modulePalette.js';
	import { cameraFilter, setCameraExcluded } from './cameraFilter.svelte.js';
	import type { Highlight } from './highlight.js';
	import {
		candidateDetails,
		candidateLabel,
		candidateRemarks,
		failureReason,
		formatDistance,
		moduleName,
		moduleNote,
		neighborMeta,
		noCandidates,
		numberCandidates,
		PART_KEY_MODULE,
		visibleSuggestions
	} from './format.js';

	let {
		modules,
		hidden,
		onreveal,
		loading,
		onchoose,
		onrun,
		unfolded,
		ontoggle,
		highlight,
		onhighlight,
		onlocate,
		onpart,
		onpartshow
	}: {
		modules: ModuleSuggestions[];
		/** Modules hidden in the card (Settings page); a click shows one here. */
		hidden: string[];
		onreveal: (module: string) => void;
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
		/** The part of the photo to outline while a block of a run on a part is hovered, and how
		 * the photo was turned when the part was chosen. */
		onpartshow: (region: Region | null, turn: number) => void;
	} = $props();

	const partBlock = (module: string) =>
		modules.find((block) => block.module === module && block.region);
	const lastPart = (module: string) => partBlock(module)?.region ?? null;
	// One part at a time: a new one waits until the run on the last one is over.
	const partPending = (module: string) => {
		const block = partBlock(module);
		return block !== undefined && isPending(block);
	};

	// Enlarged thumbnail of a neighbor photo, next to the hovered one.
	let peek = $state<{
		id: string;
		version: string | null;
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
			version: neighbor.version ?? null,
			name: neighbor.file_name,
			meta: neighborMeta(neighbor, camera ?? ''),
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
				return module.candidates.length ? null : noCandidates(module.module);
			default:
				return null;
		}
	}

	const shown = $derived(visibleSuggestions(modules, unfolded));
	const numbered = $derived(new Map(numberCandidates(shown).map((item) => [item.candidate, item])));
</script>

<section class="suggestions" aria-busy={loading} bind:this={list}>
	<h2>{m.suggestions_heading()}</h2>
	{#if loading && !modules.length}
		{#each { length: 2 }, i (i)}
			<div class="skeleton" role="status" aria-label={m.suggestions_loading()}>
				<Skeleton width="8rem" />
				<div class="skeleton-row">
					<Skeleton width="1.5rem" height="1.5rem" radius="50%" />
					<span class="skeleton-lines"
						><Skeleton width="75%" /><Skeleton width="45%" height="0.625rem" /></span
					>
					<Skeleton width="4.5rem" height="1.75rem" />
				</div>
			</div>
		{/each}
	{/if}
	{#each shown as module, index (module.key)}
		{@const weak = weakCount(modules[index])}
		<div
			class="st-sgroup"
			role="group"
			onmouseenter={() => module.region && onpartshow(module.region, module.turn)}
			onmouseleave={() => module.region && onpartshow(null, 0)}
		>
			<!-- A button that does not fit goes to the next line whole, so buttons keep one height. -->
			<h3 class="st-sgroup__head">
				<span
					class="swatch shape-{module.shape}"
					style:background={moduleColor(module.module, module.color)}
				></span>
				<span class="st-sgroup__name">
					{module.region
						? m.module_part_title({ module: moduleName(module.module) })
						: moduleName(module.module)}
				</span>
				{#if module.turn}
					<span class="st-sgroup__sub">· {m.module_turned({ degrees: String(module.turn) })}</span>
				{/if}
				{#if module.runnable}
					<span class="st-sgroup__actions">
						<button
							type="button"
							class="st-btn st-btn--ghost st-btn--sm"
							disabled={isPending(module)}
							onclick={() =>
								module.region ? onpart(module.module, module.region) : onrun(module.module)}
						>
							<Icon name={module.region ? 'square-dashed' : 'refresh-cw'} size={14} />
							{module.region
								? m.module_part_change()
								: module.status === 'not_run'
									? m.module_run()
									: m.module_rerun()}
						</button>
						{#if !module.region}
							<Tooltip text={m.module_part_hint()}>
								<button
									type="button"
									class="st-btn st-btn--ghost st-btn--sm"
									disabled={partPending(module.module)}
									onclick={() => onpart(module.module, lastPart(module.module))}
								>
									<Icon name="square-dashed" size={14} />
									{m.module_part_run()}
									{#if module.module === PART_KEY_MODULE}<Kbd>R</Kbd>{/if}
								</button>
							</Tooltip>
						{/if}
					</span>
				{/if}
			</h3>
			{#if status(module)}
				<p
					class="st-sgroup__note"
					class:failed={module.status === 'failed'}
					title={module.status === 'failed' ? (module.error ?? undefined) : undefined}
				>
					{#if isPending(module)}
						<span class="st-spin"><Icon name="loader-circle" size={14} /></span>
					{:else if module.status === 'failed'}
						<Icon name="circle-alert" size={14} />
					{:else}
						<Icon name="info" size={14} />
					{/if}
					<span>{status(module)}</span>
				</p>
				{#if module.status === 'failed' && module.error_code === 'lease_expired'}
					<p class="st-sgroup__note">{m.failure_lease_expired_hint()}</p>
				{/if}
			{/if}
			{#if module.worker_loading && isPending(module)}
				<p class="st-sgroup__note">
					<Icon name="hard-drive" size={14} />{m.module_worker_loading()}
				</p>
			{/if}
			{#if module.paused && (module.status === 'not_run' || module.status === 'queued')}
				<p class="st-sgroup__note"><Icon name="pause" size={14} />{m.module_paused()}</p>
			{/if}
			{#if module.runnable && !module.worker_available && module.status !== 'done'}
				<p class="st-sgroup__note warning">
					<Icon name="triangle-alert" size={14} />{m.module_no_worker()}
				</p>
			{/if}
			<!-- Shown in "only this device" mode even without neighbors, so that it can be undone. -->
			{#if module.cameras.length || (module.module === 'time_neighbors' && cameraFilter.sameOnly)}
				<fieldset class="devices">
					<legend>{m.suggestions_devices()}</legend>
					<label class="st-check st-check--sm" title={m.device_same_only_hint()}>
						<input
							type="checkbox"
							checked={cameraFilter.sameOnly}
							onchange={(e) => (cameraFilter.sameOnly = e.currentTarget.checked)}
						/>
						{m.device_same_only()}
					</label>
					{#each module.cameras as camera (camera.value)}
						<label class="st-check st-check--sm">
							<input
								type="checkbox"
								checked={!camera.excluded}
								disabled={cameraFilter.sameOnly && !camera.same_camera}
								onchange={(e) => setCameraExcluded(camera.value, !e.currentTarget.checked)}
							/>
							<span>
								{camera.label || m.device_unknown()}
								<span class="st-check__meta">
									({camera.count}{camera.same_camera ? `, ${m.device_this()}` : ''})
								</span>
							</span>
						</label>
					{/each}
				</fieldset>
			{/if}
			{#if module.note && !module.candidates.length}
				<p class="st-sgroup__note"><Icon name="info" size={14} />{moduleNote(module.note)}</p>
			{/if}
			<ol class="st-sgroup__list">
				{#each module.candidates as candidate (candidate.rank)}
					{@const key = numbered.get(candidate)?.key}
					{@const remarks = candidateRemarks(candidate)}
					<!-- The row is a shortcut for the mouse; keyboard users have the label button. -->
					<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
					<li
						class="st-cand"
						style:--_c={moduleColor(module.module, module.color)}
						data-state={isHighlighted(module.key, candidate.rank)
							? 'highlight'
							: candidate.tier === 'weak'
								? 'weak'
								: undefined}
						onclick={(e) => rowClick(e, candidate)}
						data-candidate="{module.key}:{candidate.rank}"
						onmouseenter={() =>
							onhighlight({ module: module.key, rank: candidate.rank, from: 'list' })}
						onmouseleave={() => onhighlight(null)}
					>
						<span
							class="rank shape-{module.shape}"
							style:background={moduleColor(module.module, module.color)}
							style:color={moduleOnColor(module.module)}
							>{numbered.get(candidate)?.number ?? candidate.rank}</span
						>
						<div class="st-cand__body">
							<button
								type="button"
								class="st-cand__label"
								title={candidateDetails(candidate) ?? m.candidate_locate()}
								onclick={() => onlocate(candidate)}
							>
								{candidateLabel(candidate)}
							</button>
							<div class="st-cand__meta">
								<ConfidenceMeter
									score={candidate.score}
									tier={candidate.tier}
									label={candidate.tier === 'confident' ? m.candidate_confident() : undefined}
									title={m.candidate_score({ percent: String(Math.round(candidate.score * 100)) })}
								/>
								{#if candidate.radius_m}
									<span class="st-cand__radius">±{formatDistance(candidate.radius_m)}</span>
								{/if}
								{#if candidate.evidence.neighbors?.length}
									<span class="st-cand__thumbs">
										{#each candidate.evidence.neighbors as neighbor (neighbor.asset_id)}
											<a
												href={resolve('/photo/[id]', { id: neighbor.asset_id })}
												target="_blank"
												rel="noopener"
												aria-label="{neighbor.file_name} — {m.photo_open_new_tab()}"
												onmouseenter={(e) => showPeek(e, module, neighbor)}
												onmouseleave={() => (peek = null)}
											>
												<img
													src={thumbnailUrl(neighbor.asset_id, 'thumbnail', 0, neighbor.version)}
													alt={neighbor.file_name}
													loading="lazy"
												/>
											</a>
										{/each}
									</span>
								{/if}
								{#if remarks.length}
									<!-- One line, cut short: the whole text on hover. -->
									<span class="st-cand__remark remarks" title={remarks.join(' · ')}
										>{remarks.join(' · ')}</span
									>
								{/if}
							</div>
						</div>
						<button
							type="button"
							class="st-btn st-btn--sm choose"
							onclick={() => onchoose(candidate)}
						>
							{m.candidate_choose()}
							{#if key}<Kbd>{key}</Kbd>{/if}
						</button>
					</li>
				{/each}
			</ol>
			{#if weak}
				<button type="button" class="st-sgroup__fold" onclick={() => ontoggle(module.key)}>
					<Icon name={unfolded.includes(module.key) ? 'chevron-up' : 'chevron-down'} size={14} />
					{unfolded.includes(module.key)
						? m.suggestions_weak_hide()
						: m.suggestions_weak_more({ count: String(weak) })}
				</button>
			{/if}
		</div>
	{/each}
	{#if hidden.length}
		<p class="hidden-modules">
			<span>{m.suggestions_hidden()}</span>
			{#each hidden as module (module)}
				<button
					type="button"
					class="st-chip"
					title={m.suggestions_reveal_title()}
					onclick={() => onreveal(module)}
				>
					<Icon name="eye" size={14} />
					{moduleName(module)}
				</button>
			{/each}
		</p>
	{/if}
</section>

{#if peek}
	<div class="peek" style:left="{peek.left}px" style:top="{peek.top}px" aria-hidden="true">
		<img src={thumbnailUrl(peek.id, 'thumbnail', 0, peek.version)} alt="" />
		<div class="name">{peek.name}</div>
		<div>{peek.meta}</div>
		<div class="muted">{m.photo_open_new_tab()}</div>
	</div>
{/if}

<style>
	/* The remarks take what is left of the line and are cut short there. */
	.remarks {
		flex: 1 1 0;
		min-width: 4rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.suggestions {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}
	h2 {
		margin: 0;
		font-size: var(--text-md);
	}
	.st-sgroup__head {
		margin: 0;
	}
	.st-sgroup__fold {
		text-align: start;
	}
	.swatch {
		width: 0.75rem;
		height: 0.75rem;
		border-radius: 50%;
	}
	.swatch.shape-square {
		border-radius: 0.15rem;
	}
	.swatch.shape-diamond,
	.rank.shape-diamond {
		border-radius: 0;
		clip-path: polygon(50% 0, 100% 50%, 50% 100%, 0 50%);
	}
	.rank.shape-diamond {
		width: 1.75rem;
		height: 1.75rem;
	}
	.rank.shape-square {
		border-radius: var(--radius-xs);
	}
	.rank {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.5rem;
		height: 1.5rem;
		border-radius: 50%;
		color: var(--gray-0);
		font-size: var(--text-sm);
		font-weight: var(--weight-bold);
		font-variant-numeric: tabular-nums;
	}
	.st-sgroup__note.failed {
		color: var(--color-danger-text);
	}
	.st-sgroup__note.warning {
		color: var(--color-warning-text);
	}
	.st-sgroup__note :global(svg) {
		margin-top: 0.125rem;
	}
	.st-spin {
		display: inline-flex;
	}
	.choose {
		white-space: nowrap;
	}
	.devices {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-1) var(--space-4);
		margin: 0 0 var(--space-1);
		padding: 0;
		border: none;
		font-size: var(--text-sm);
	}
	.devices legend {
		float: left;
		margin-inline-end: var(--space-2);
		font-weight: var(--weight-medium);
		color: var(--color-text-muted);
	}
	.st-cand__thumbs a {
		display: block;
	}
	.peek {
		position: fixed;
		z-index: var(--z-tooltip);
		width: 240px;
		padding: var(--space-1-5);
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface-raised);
		color: var(--color-text);
		box-shadow: var(--shadow-md);
		font-size: var(--text-xs);
		pointer-events: none;
	}
	.peek img {
		display: block;
		width: 100%;
		max-height: 160px;
		margin-bottom: var(--space-1);
		object-fit: cover;
		border-radius: var(--radius-xs);
	}
	.peek .name {
		font-weight: var(--weight-semibold);
		word-break: break-all;
	}
	.muted {
		color: var(--color-text-muted);
	}
	.hidden-modules {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2);
		margin: 0;
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	.skeleton {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}
	.skeleton-row {
		display: grid;
		grid-template-columns: 1.5rem minmax(0, 1fr) 4.5rem;
		gap: var(--space-3);
		align-items: center;
		padding: var(--space-3);
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-md);
	}
	.skeleton-lines {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
</style>
