<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- The mode of the app (D-253, D-254): looking at the library, or working on the places. In the
     header, since it changes more than the gallery; a personal setting of the account. -->
<script lang="ts">
	import type { UiMode } from '#lib/api.js';
	import { mode } from '#lib/mode.svelte.js';
	import { m } from '#lib/paraglide/messages.js';
	import Icon from '#lib/ui/Icon.svelte';
	import Tooltip from '#lib/ui/Tooltip.svelte';

	const choices: {
		value: UiMode;
		icon: 'eye' | 'pencil';
		label: () => string;
		hint: () => string;
	}[] = [
		{ value: 'view', icon: 'eye', label: m.mode_view, hint: m.mode_view_hint },
		{ value: 'work', icon: 'pencil', label: m.mode_work, hint: m.mode_work_hint }
	];
</script>

<div class="st-seg" role="radiogroup" aria-label={m.mode()}>
	{#each choices as choice (choice.value)}
		<Tooltip text={choice.hint()} below>
			<button
				type="button"
				role="radio"
				aria-checked={mode.current === choice.value}
				onclick={() => mode.set(choice.value).catch(() => {})}
			>
				<Icon name={choice.icon} size={14} />
				{choice.label()}
			</button>
		</Tooltip>
	{/each}
</div>
