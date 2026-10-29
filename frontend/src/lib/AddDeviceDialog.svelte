<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- "Add a device": ready commands to start a worker on another computer, with the address, the
     name and (for an administrator of Immich) the token filled in. -->
<script lang="ts">
	import { getWorkerSetup, type WorkerSetup } from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import CopyButton from '#lib/ui/CopyButton.svelte';
	import Dialog from '#lib/ui/Dialog.svelte';
	import { SETUP_WAYS, setupSteps, type SetupWay } from '#lib/workerSetup.js';

	let { docs, onclose }: { docs: string; onclose: () => void } = $props();

	let setup = $state<WorkerSetup | null>(null);
	let error = $state<string | null>(null);
	let way = $state<SetupWay>('docker-linux');
	// The address the browser reached the app at: the other computer usually reaches it so too.
	let url = $state(location.origin);
	let name = $state('desktop');

	const wayLabels: Record<SetupWay, () => string> = {
		'docker-linux': m.add_device_docker_linux,
		'docker-windows': m.add_device_docker_windows,
		'gpu-windows': m.add_device_gpu_windows,
		'gpu-linux': m.add_device_gpu_linux
	};
	const stepLabels: Record<string, () => string> = {
		run: m.add_device_step_run,
		tools: m.add_device_step_tools,
		install: m.add_device_step_install,
		'install-linux': m.add_device_step_install,
		'start-file-windows': m.add_device_step_file_windows,
		'start-file-linux': m.add_device_step_file_linux,
		'start-linux': m.add_device_step_start_linux
	};

	$effect(() => {
		getWorkerSetup()
			.then((result) => (setup = result))
			.catch((e) => (error = errorMessage(e)));
	});

	const steps = $derived(
		setup ? setupSteps(way, { url, token: setup.token, name, version: setup.version }) : []
	);
</script>

<Dialog title={m.add_device_title()} icon="cpu" wide {onclose}>
	<p class="muted">{m.add_device_intro()}</p>
	{#if error}
		<p class="error" role="alert">{error}</p>
	{:else if setup}
		{#if !setup.token_set}
			<p class="st-banner st-banner--warning" role="status">{m.add_device_no_token()}</p>
		{:else if !setup.admin}
			<p class="st-banner st-banner--info" role="status">{m.add_device_token_hidden()}</p>
		{/if}

		<div class="fields">
			<label class="field">
				<span>{m.add_device_address()}</span>
				<span class="st-input st-input--mono"><input bind:value={url} spellcheck="false" /></span>
			</label>
			<label class="field">
				<span>{m.add_device_name()}</span>
				<span class="st-input st-input--mono"><input bind:value={name} spellcheck="false" /></span>
			</label>
		</div>
		<p class="hint">{m.add_device_address_hint()}</p>

		<div class="st-seg ways" role="radiogroup" aria-label={m.add_device_how()}>
			{#each SETUP_WAYS as option (option)}
				<button
					type="button"
					role="radio"
					aria-checked={way === option}
					onclick={() => (way = option)}
				>
					{wayLabels[option]()}
				</button>
			{/each}
		</div>
		{#if way.startsWith('gpu')}
			<p class="hint">{m.add_device_gpu_note()}</p>
		{/if}

		<ol class="steps">
			{#each steps as { step, text } (step)}
				<li>
					<div class="step-head">
						<span>{stepLabels[step]()}</span>
						<CopyButton {text} />
					</div>
					<pre>{text}</pre>
				</li>
			{/each}
		</ol>

		<p class="hint">
			<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- the documentation on GitHub -->
			<a href={docs} target="_blank" rel="noreferrer">{m.add_device_docs()}</a>
		</p>
	{/if}
</Dialog>

<style>
	p {
		margin: 0;
	}
	.muted,
	.hint {
		color: var(--color-text-muted);
	}
	.hint {
		font-size: var(--text-sm);
	}
	.error {
		color: var(--color-danger-text);
	}
	.fields {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
		gap: var(--space-3);
		margin-top: var(--space-3);
	}
	.field {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		font-size: var(--text-sm);
	}
	.ways {
		flex-wrap: wrap;
		margin-top: var(--space-3);
	}
	.steps {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		margin: var(--space-3) 0;
		padding-inline-start: var(--space-5);
	}
	.step-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-2);
		font-size: var(--text-sm);
	}
	pre {
		margin: var(--space-1) 0 0;
		padding: var(--space-2) var(--space-3);
		overflow-x: auto;
		border-radius: var(--radius-sm);
		background: var(--color-surface-sunken);
		font-family: var(--font-mono);
		font-size: var(--text-sm);
		line-height: var(--leading-snug);
	}
</style>
