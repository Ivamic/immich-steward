<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Puts groups into a folder (D-201): one of the folders, a new one, or out of any. Several
     groups go together ("into one folder" from a group close to another). -->
<script lang="ts">
	import { getFolders, setGroupFolder, type FolderRef } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import Dialog from '#lib/ui/Dialog.svelte';
	import Icon from '#lib/ui/Icon.svelte';

	let {
		groupIds,
		current = null,
		ondone,
		onclose
	}: {
		/** The groups to put; the first one first (a new folder is made with it). */
		groupIds: string[];
		/** The folder the first group is in now. */
		current?: FolderRef | null;
		/** Done: the folder they are in now, or null when taken out. */
		ondone: (folder: FolderRef | null) => void;
		onclose: () => void;
	} = $props();

	let folders = $state<FolderRef[] | null>(null);
	let name = $state('');
	let busy = $state(false);
	let error = $state<string | null>(null);

	$effect(() => {
		getFolders()
			.then((found) => (folders = found))
			.catch((e) => (error = errorMessage(e)));
	});

	async function put(work: () => Promise<FolderRef | null>) {
		busy = true;
		try {
			ondone(await work());
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	/** Into a folder there is. */
	function into(folder: FolderRef) {
		put(async () => {
			for (const id of groupIds) await setGroupFolder(id, { folder_id: folder.id });
			return folder;
		});
	}

	/** Into a new folder: made with the first group, the others follow. */
	function intoNew(event: SubmitEvent) {
		event.preventDefault();
		const wanted = name.trim();
		if (!wanted) return;
		put(async () => {
			const [first, ...others] = groupIds;
			const folder = (await setGroupFolder(first, { name: wanted })).group.folder;
			if (!folder) return null;
			for (const id of others) await setGroupFolder(id, { folder_id: folder.id });
			return folder;
		});
	}

	function takeOut() {
		put(async () => {
			for (const id of groupIds) await setGroupFolder(id, {});
			return null;
		});
	}
</script>

<Dialog title={m.folder_dialog_title()} icon="folder" {onclose}>
	<p class="hint">{m.folder_dialog_hint()}</p>
	{#if folders === null && !error}
		<p class="hint" role="status">
			<span class="st-spin"><Icon name="loader-circle" size={14} /></span>
		</p>
	{:else if folders && folders.length > 0}
		<ul class="folders">
			{#each folders as folder (folder.id)}
				<li>
					<button
						type="button"
						class="st-btn st-btn--sm"
						class:st-btn--secondary={folder.id === current?.id}
						class:st-btn--ghost={folder.id !== current?.id}
						aria-pressed={folder.id === current?.id}
						disabled={busy || folder.id === current?.id}
						onclick={() => into(folder)}
					>
						<Icon name="folder" size={14} />
						{folder.name}
					</button>
				</li>
			{/each}
		</ul>
	{/if}
	<form class="new" onsubmit={intoNew}>
		<span class="st-input st-input--sm">
			<input
				maxlength="200"
				placeholder={m.folder_name()}
				aria-label={m.folder_name()}
				bind:value={name}
			/>
		</span>
		<button type="submit" class="st-btn st-btn--primary st-btn--sm" disabled={busy || !name.trim()}>
			<Icon name="plus" size={14} />
			{m.folder_create()}
		</button>
	</form>
	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}
	{#snippet footer()}
		{#if current}
			<button type="button" class="st-btn st-btn--ghost" disabled={busy} onclick={takeOut}>
				{m.folder_take_out()}
			</button>
		{/if}
		<button type="button" class="st-btn st-btn--secondary" onclick={onclose}>
			{m.groups_reset_cancel()}
		</button>
	{/snippet}
</Dialog>

<style>
	.hint {
		margin: 0 0 var(--space-3);
		color: var(--color-text-muted);
		font-size: var(--text-sm);
	}
	.folders {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		margin: 0 0 var(--space-3);
		padding: 0;
		list-style: none;
	}
	.new {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
	}
	.new .st-input {
		flex: 1 1 12rem;
	}
	.error {
		margin: var(--space-2) 0 0;
		color: var(--color-danger-text);
	}
</style>
