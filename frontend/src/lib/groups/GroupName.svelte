<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- The name of a group on a tile, a link to it, renamed in place with the pencil: Enter or leaving
     the field saves, Esc cancels; an empty name takes the name away. -->
<script lang="ts">
	import { updateGroup } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import Icon from '#lib/ui/Icon.svelte';

	let {
		id,
		name,
		href,
		onclick,
		onrenamed
	}: {
		id: string;
		name: string | null;
		href: string;
		/** A click on the name (a page may take it to choose the group instead). */
		onclick?: (event: MouseEvent) => void;
		/** Saved: the new name, null when taken away. */
		onrenamed: (name: string | null) => void;
	} = $props();

	let editing = $state(false);
	let value = $state('');
	let saving = $state(false);
	let error = $state<string | null>(null);

	function start() {
		value = name ?? '';
		error = null;
		editing = true;
	}

	async function save() {
		if (!editing || saving) return;
		const wanted = value.trim();
		if (wanted === (name ?? '')) {
			editing = false;
			return;
		}
		saving = true;
		try {
			const answer = await updateGroup(id, { name: wanted });
			onrenamed(answer.group.name);
			editing = false;
		} catch (e) {
			error = errorMessage(e);
		} finally {
			saving = false;
		}
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'Enter') (event.currentTarget as HTMLInputElement).blur();
		if (event.key === 'Escape') {
			event.stopPropagation();
			editing = false;
		}
	}

	/** Focus once the field is there. */
	function focus(node: HTMLInputElement) {
		node.focus();
		node.select();
	}
</script>

{#if editing}
	<span class="st-input st-input--sm field">
		<input
			aria-label={m.groups_name()}
			placeholder={m.groups_unnamed()}
			maxlength="200"
			disabled={saving}
			bind:value
			onblur={save}
			{onkeydown}
			use:focus
		/>
	</span>
	{#if error}<span class="error" role="alert">{error}</span>{/if}
{:else}
	<span class="row">
		<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- resolved by the page -->
		<a class="name" class:unnamed={!name} {href} {onclick}>{name ?? m.groups_unnamed()}</a>
		<button
			type="button"
			class="st-iconbtn st-iconbtn--sm edit"
			aria-label={m.groups_rename()}
			title={m.groups_rename()}
			onclick={start}
		>
			<Icon name="pencil" size={13} />
		</button>
	</span>
{/if}

<style>
	.row {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		min-width: 0;
		max-width: 100%;
	}
	.name {
		overflow: hidden;
		color: inherit;
		font-weight: var(--weight-medium);
		text-decoration: none;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.name.unnamed {
		color: var(--color-text-muted);
		font-weight: normal;
	}
	/* The pencil on hover, as the check of a photo; always on a touch screen. */
	.edit {
		flex-shrink: 0;
		opacity: 0;
		transition: opacity var(--motion-fast) var(--ease-out);
	}
	.row:hover .edit,
	.edit:focus-visible {
		opacity: 1;
	}
	@media (hover: none) {
		.edit {
			opacity: 1;
		}
	}
	.field {
		width: 100%;
	}
	.error {
		color: var(--color-danger-text);
		font-size: var(--text-xs);
	}
</style>
