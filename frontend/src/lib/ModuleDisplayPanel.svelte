<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Order of the modules in the photo card of this account and which of them are shown; each
     change is saved at once. Reordered by dragging the handle (mouse only: touch screens
     scroll instead) or with the arrows. -->
<script lang="ts">
	import { getModuleDisplay, setModuleDisplay, type ModuleDisplay } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { moduleName } from '#lib/suggestions/format.js';
	import Icon from '#lib/ui/Icon.svelte';

	let displays = $state<ModuleDisplay[]>([]);
	let saving = $state(false);
	let error = $state<string | null>(null);
	// Dragging: the row taken and where it would go (index of the row it would stand before).
	let dragged = $state<number | null>(null);
	let target = $state<number | null>(null);

	$effect(() => {
		getModuleDisplay()
			.then((result) => (displays = result))
			.catch((e) => (error = errorMessage(e)));
	});

	async function save(next: ModuleDisplay[]) {
		const before = displays;
		displays = next;
		saving = true;
		try {
			displays = await setModuleDisplay(next);
			error = null;
		} catch (e) {
			displays = before;
			error = errorMessage(e);
		} finally {
			saving = false;
		}
	}

	function move(index: number, by: -1 | 1) {
		const next = [...displays];
		[next[index], next[index + by]] = [next[index + by], next[index]];
		save(next);
	}

	function dragOver(event: DragEvent, index: number) {
		if (dragged === null) return;
		event.preventDefault();
		const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
		target = event.clientY < box.top + box.height / 2 ? index : index + 1;
	}

	function drop(event: DragEvent) {
		// Firefox would otherwise open the dragged text as an address.
		event.preventDefault();
		if (dragged !== null && target !== null && target !== dragged && target !== dragged + 1) {
			const next = [...displays];
			const [moved] = next.splice(dragged, 1);
			next.splice(target > dragged ? target - 1 : target, 0, moved);
			save(next);
		}
		dragEnd();
	}

	function dragEnd() {
		dragged = null;
		target = null;
	}

	function toggle(index: number) {
		save(displays.map((d, i) => (i === index ? { ...d, hidden: !d.hidden } : d)));
	}
</script>

<section>
	<h2>{m.display_heading()}</h2>
	<p class="hint">{m.display_hint()}</p>
	{#if displays.length}
		<ol>
			{#each displays as display, index (display.module)}
				<li
					class:hidden={display.hidden}
					class:dragged={dragged === index}
					class:drop-before={target === index}
					class:drop-after={target === index + 1 && index === displays.length - 1}
					ondragover={(e) => dragOver(e, index)}
					ondrop={drop}
				>
					<span
						class="handle"
						draggable={!saving}
						role="presentation"
						ondragstart={(e) => {
							dragged = index;
							const row = (e.currentTarget as HTMLElement).closest('li');
							if (row && e.dataTransfer) {
								// Firefox starts no drag without data.
								e.dataTransfer.setData('text/plain', display.module);
								e.dataTransfer.effectAllowed = 'move';
								e.dataTransfer.setDragImage(row, 12, 12);
							}
						}}
						ondragend={dragEnd}><Icon name="grip-vertical" /></span
					>
					<span class="arrows">
						<button
							type="button"
							title={m.display_up()}
							aria-label={m.display_up()}
							disabled={saving || index === 0}
							class="st-iconbtn st-iconbtn--sm"
							onclick={() => move(index, -1)}><Icon name="chevron-up" /></button
						>
						<button
							type="button"
							title={m.display_down()}
							aria-label={m.display_down()}
							disabled={saving || index === displays.length - 1}
							class="st-iconbtn st-iconbtn--sm"
							onclick={() => move(index, 1)}><Icon name="chevron-down" /></button
						>
					</span>
					<span class="name">{moduleName(display.module)}</span>
					<label class="st-check st-check--sm">
						<input
							type="checkbox"
							checked={!display.hidden}
							disabled={saving}
							onchange={() => toggle(index)}
						/>
						{m.display_show()}
					</label>
				</li>
			{/each}
		</ol>
	{/if}
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
	.hint {
		margin: 0;
	}
	.hint {
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	ol {
		max-width: 32rem;
		margin: 0;
		padding: 0;
		list-style: none;
		border: var(--border-width) solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface);
	}
	li {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-1-5) var(--space-3) var(--space-1-5) var(--space-1-5);
	}
	li + li {
		border-top: var(--border-width) solid var(--color-border);
	}
	li.hidden .name {
		color: var(--color-text-subtle);
	}
	li.dragged {
		opacity: 0.4;
	}
	li.drop-before {
		box-shadow: inset 0 2px 0 var(--color-accent);
	}
	li.drop-after {
		box-shadow: inset 0 -2px 0 var(--color-accent);
	}
	.handle {
		display: inline-flex;
		padding: var(--space-1) 0;
		color: var(--color-text-subtle);
		cursor: grab;
		user-select: none;
	}
	/* Touch screens: dragging would fight scrolling; the arrows stay. */
	@media (pointer: coarse) {
		.handle {
			display: none;
		}
	}
	.arrows {
		display: inline-flex;
		gap: 2px;
	}
	.name {
		flex: 1;
		font-weight: var(--weight-medium);
	}
	.error {
		margin: 0;
		color: var(--color-danger-text);
	}
</style>
