<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Backups of what the users decided (D-252): the nightly one into a folder of the server, when
     that folder is mounted (otherwise how to mount it), and a download at any time. For the whole
     installation. -->
<script lang="ts">
	import {
		BACKUP_DOWNLOAD_URL,
		getBackups,
		runBackup,
		setBackups,
		type BackupSettings,
		type Backups
	} from '#lib/api.js';
	import { errorMessage } from '#lib/errors.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale } from '#lib/paraglide/runtime.js';
	import CopyButton from '#lib/ui/CopyButton.svelte';
	import Icon from '#lib/ui/Icon.svelte';

	const MOUNT = 'services:\n  core:\n    volumes:\n      - ./backups:/backups';
	// The app runs as uid 1000; a folder Docker made for the mount belongs to root.
	const OWN = 'sudo chown 1000:1000 backups';

	let info = $state<Backups | null>(null);
	let busy = $state(false);
	let error = $state<string | null>(null);

	const when = new Intl.DateTimeFormat(getLocale(), { dateStyle: 'medium', timeStyle: 'short' });
	const hours = Array.from({ length: 24 }, (_, hour) => hour);

	$effect(() => {
		getBackups()
			.then((loaded) => (info = loaded))
			.catch((e) => (error = errorMessage(e)));
	});

	async function run(action: () => Promise<Backups>) {
		busy = true;
		try {
			info = await action();
			error = null;
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = false;
		}
	}

	const save = (values: Partial<BackupSettings>) => run(() => setBackups(values));

	function saveNumber(key: 'keep_daily' | 'keep_weekly', event: Event) {
		const value = (event.currentTarget as HTMLInputElement).valueAsNumber;
		if (!Number.isNaN(value)) save({ [key]: Math.round(value) });
	}

	function size(bytes: number): string {
		const [value, unit] =
			bytes >= 1024 * 1024 ? [bytes / 1024 / 1024, 'megabyte'] : [bytes / 1024, 'kilobyte'];
		return new Intl.NumberFormat(getLocale(), {
			style: 'unit',
			unit,
			maximumFractionDigits: 1
		}).format(value);
	}

	const restoreCommand = $derived(
		info?.folder_ready
			? `docker compose exec core python -m steward.backup restore /backups/${info.last_file ?? 'steward-backup-….json.gz'}`
			: 'docker compose cp steward-backup-….json.gz core:/tmp/\n' +
					'docker compose exec core python -m steward.backup restore /tmp/steward-backup-….json.gz'
	);
</script>

<section aria-busy={busy}>
	<h2>{m.backups_heading()}</h2>
	<p class="hint">{m.backups_hint()}</p>
	{#if info}
		{#if info.folder_ready}
			<label class="st-check">
				<input
					type="checkbox"
					checked={info.enabled}
					disabled={busy}
					onchange={(e) => save({ enabled: e.currentTarget.checked })}
				/>
				{m.backups_enable()}
			</label>
			<label class="field">
				<span>
					{m.backups_hour()}
					<span class="hint"
						>{info.time_zone
							? m.backups_hour_hint_zone({ zone: info.time_zone })
							: m.backups_hour_hint()}</span
					>
				</span>
				<span class="st-input st-input--sm st-input--select">
					<select
						value={info.hour}
						disabled={busy || !info.enabled}
						onchange={(e) => save({ hour: Number(e.currentTarget.value) })}
					>
						{#each hours as hour (hour)}
							<option value={hour}>{String(hour).padStart(2, '0')}:00</option>
						{/each}
					</select>
					<span class="st-select__chev"><Icon name="chevron-down" size={14} /></span>
				</span>
			</label>
			<label class="field">
				<span>
					{m.backups_keep_daily()}
					<span class="hint">{m.backups_keep_daily_hint()}</span>
				</span>
				<span class="st-input st-input--sm">
					<input
						type="number"
						min="1"
						max="60"
						step="1"
						value={info.keep_daily}
						disabled={busy}
						onchange={(e) => saveNumber('keep_daily', e)}
					/>
				</span>
			</label>
			<label class="field">
				<span>
					{m.backups_keep_weekly()}
					<span class="hint">{m.backups_keep_weekly_hint()}</span>
				</span>
				<span class="st-input st-input--sm">
					<input
						type="number"
						min="0"
						max="52"
						step="1"
						value={info.keep_weekly}
						disabled={busy}
						onchange={(e) => saveNumber('keep_weekly', e)}
					/>
				</span>
			</label>
			<div class="row">
				<span>
					{#if info.last_at && info.last_file}
						{m.backups_last({
							when: when.format(new Date(info.last_at)),
							file: info.last_file,
							size: size(info.last_size ?? 0)
						})}
					{:else}
						{m.backups_none_yet()}
					{/if}
				</span>
				<button
					type="button"
					class="st-btn st-btn--sm"
					disabled={busy}
					onclick={() => run(runBackup)}
				>
					{m.backups_run_now()}
				</button>
			</div>
			{#if info.error && info.error !== 'no_folder'}
				<p class="error" role="alert">{m.backups_failed({ code: info.error })}</p>
			{/if}
		{:else if info.folder_problem === 'not_writable'}
			<div class="note">
				<p>{m.backups_not_writable({ folder: info.folder ?? '/backups' })}</p>
				<div class="step-head">
					<span class="hint">{m.backups_not_writable_command()}</span>
					<CopyButton text={OWN} />
				</div>
				<pre>{OWN}</pre>
			</div>
		{:else}
			<div class="note">
				<p>{m.backups_no_folder({ folder: info.folder ?? '/backups' })}</p>
				<div class="step-head">
					<span class="hint">compose.yaml / compose.override.yaml</span>
					<CopyButton text={MOUNT} />
				</div>
				<pre>{MOUNT}</pre>
				<p class="hint">{m.backups_no_folder_then()}</p>
			</div>
		{/if}

		<div class="row">
			<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- a file from the API, not a page -->
			<a class="st-btn st-btn--sm" href={BACKUP_DOWNLOAD_URL} download>{m.backups_download()}</a>
			<span class="hint">{m.backups_download_hint()}</span>
		</div>
		<p class="hint">{m.backups_secret()}</p>
		<div>
			<div class="step-head">
				<span class="hint">{m.backups_restore()}</span>
				<CopyButton text={restoreCommand} />
			</div>
			<pre>{restoreCommand}</pre>
		</div>
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
	p {
		margin: 0;
	}
	.hint {
		font-size: var(--text-sm);
		color: var(--color-text-muted);
	}
	.field {
		display: grid;
		grid-template-columns: 1fr 6rem;
		gap: var(--space-3);
		align-items: start;
	}
	.field .hint {
		display: block;
	}
	.row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-2) var(--space-4);
	}
	.note {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}
	.step-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-2);
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
	.error {
		color: var(--color-danger-text);
	}
</style>
