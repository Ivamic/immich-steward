// SPDX-License-Identifier: AGPL-3.0-or-later
// The commands of "Add a device" (Processing page): the same as in docs/workers.md, with the
// address, the token and the name filled in.

export type SetupWay = 'docker-linux' | 'docker-windows' | 'gpu-windows' | 'gpu-linux';
export const SETUP_WAYS: readonly SetupWay[] = [
	'docker-linux',
	'docker-windows',
	'gpu-windows',
	'gpu-linux'
];

export const WORKER_IMAGE = 'ghcr.io/ivamic/immich-steward-worker:0';
const REPOSITORY = 'https://github.com/Ivamic/immich-steward.git';
const SYNC_GPU =
	'uv sync --frozen --no-dev --package steward-worker --extra geoclip --extra similar --extra cuda';
/** Shown in place of the token to whoever may not see it. */
export const TOKEN_PLACEHOLDER = 'your-token';

export interface SetupValues {
	/** Address of the app as the other computer reaches it, e.g. http://192.168.1.10:8780. */
	url: string;
	token: string | null;
	name: string;
	/** Version of the app on the server: the GPU worker is installed from its tag. */
	version: string;
}

/** A name the commands can take as it is: letters, digits, dot, dash and underscore. */
export function workerName(text: string): string {
	return (
		text
			.trim()
			.replace(/[^A-Za-z0-9._-]+/g, '-')
			.replace(/^-+|-+$/g, '') || 'desktop'
	);
}

/** The Git tag of a version: "0.7.0" -> "v0.7.0", "0.7.0rc1" (as Python spells it) -> "v0.7.0-rc.1". */
export function releaseTag(version: string): string {
	const match = /^v?(\d+(?:\.\d+)*)[-_.]?(a|b|rc)\.?(\d+)$/.exec(version.trim().toLowerCase());
	if (match) {
		const label = { a: 'alpha', b: 'beta' }[match[2]] ?? match[2];
		return `v${match[1]}-${label}.${match[3]}`;
	}
	return `v${version.trim().replace(/^v/, '')}`;
}

/** The blocks to copy, in order: what each is for and its text. */
export function setupSteps(way: SetupWay, values: SetupValues): { step: string; text: string }[] {
	const url = values.url.trim().replace(/\/+$/, '');
	const token = values.token ?? TOKEN_PLACEHOLDER;
	const name = workerName(values.name);
	const tag = releaseTag(values.version);
	switch (way) {
		case 'docker-linux':
		case 'docker-windows': {
			const cont = way === 'docker-linux' ? ' \\' : ' `';
			const lines = [
				'docker run -d --name steward-worker --restart unless-stopped',
				`  -e STEWARD_CORE_URL=${url}`,
				`  -e STEWARD_WORKER_TOKEN=${token}`,
				`  -e STEWARD_WORKER_NAME=${name}`,
				'  -e STEWARD_WORKER_THREADS=4',
				'  -v steward-models:/models',
				`  ${WORKER_IMAGE}`
			];
			return [
				{ step: 'run', text: lines.map((l, i) => (i < lines.length - 1 ? l + cont : l)).join('\n') }
			];
		}
		case 'gpu-windows':
			return [
				{
					step: 'tools',
					text: 'winget install --id Git.Git -e\nwinget install --id astral-sh.uv -e'
				},
				{
					step: 'install',
					text: [
						`git clone --branch ${tag} ${REPOSITORY} D:\\steward-worker`,
						'cd D:\\steward-worker',
						SYNC_GPU
					].join('\n')
				},
				{
					step: 'start-file-windows',
					text: [
						'@echo off',
						'cd /d D:\\steward-worker',
						`set STEWARD_WORKER_TOKEN=${token}`,
						`set STEWARD_CORE_URL=${url}`,
						'set STEWARD_WORKER_MODULES=similar,geoclip',
						`set STEWARD_WORKER_NAME=${name}`,
						'.venv\\Scripts\\steward-worker.exe',
						'pause'
					].join('\n')
				}
			];
		case 'gpu-linux':
			return [
				{
					step: 'install-linux',
					text: [
						'curl -LsSf https://astral.sh/uv/install.sh | sh',
						'source $HOME/.local/bin/env',
						`git clone --branch ${tag} ${REPOSITORY} ~/steward-worker`,
						'cd ~/steward-worker',
						SYNC_GPU
					].join('\n')
				},
				{
					step: 'start-file-linux',
					text: [
						'#!/bin/sh',
						'cd ~/steward-worker',
						`export STEWARD_WORKER_TOKEN=${token}`,
						`export STEWARD_CORE_URL=${url}`,
						'export STEWARD_WORKER_MODULES=similar,geoclip',
						`export STEWARD_WORKER_NAME=${name}`,
						'exec .venv/bin/steward-worker'
					].join('\n')
				},
				{
					step: 'start-linux',
					text: 'chmod 700 ~/steward-worker/start-worker.sh\n~/steward-worker/start-worker.sh'
				}
			];
	}
}
