<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Order of the modules in the photo card of this account and which of them are shown; each
     change is saved at once. -->
<script lang="ts">
	import { getModuleDisplay, setModuleDisplay, type ModuleDisplay } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { moduleName } from '#lib/suggestions/format.js';

	let displays = $state<ModuleDisplay[]>([]);
	let saving = $state(false);
	let error = $state<string | null>(null);

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
				<li class:hidden={display.hidden}>
					<span class="arrows">
						<button
							type="button"
							title={m.display_up()}
							aria-label={m.display_up()}
							disabled={saving || index === 0}
							onclick={() => move(index, -1)}>↑</button
						>
						<button
							type="button"
							title={m.display_down()}
							aria-label={m.display_down()}
							disabled={saving || index === displays.length - 1}
							onclick={() => move(index, 1)}>↓</button
						>
					</span>
					<span class="name">{moduleName(display.module)}</span>
					<label>
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
		margin-bottom: 2.5rem;
	}
	.hint {
		margin-top: 0;
		opacity: 0.7;
		font-size: 0.9rem;
	}
	ol {
		margin: 0;
		padding: 0;
		list-style: none;
		display: grid;
		gap: 0.35rem;
		max-width: 28rem;
	}
	li {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}
	li.hidden .name {
		opacity: 0.5;
	}
	.arrows {
		display: inline-flex;
		gap: 0.2rem;
	}
	.arrows button {
		width: 1.8rem;
		padding: 0.1rem 0;
	}
	.name {
		flex: 1;
	}
	label {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		cursor: pointer;
	}
	.error {
		color: #cf222e;
	}
</style>
