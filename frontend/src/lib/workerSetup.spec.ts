// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { releaseTag, setupSteps, TOKEN_PLACEHOLDER, workerName } from './workerSetup';

const values = {
	url: 'http://192.168.1.10:8780/',
	token: 'abc123',
	name: 'laptop',
	version: '0.7.0'
};

describe('setupSteps', () => {
	it('fills in the address, the token and the name', () => {
		const [run] = setupSteps('docker-linux', values);
		expect(run.text).toContain('-e STEWARD_CORE_URL=http://192.168.1.10:8780 \\');
		expect(run.text).toContain('-e STEWARD_WORKER_TOKEN=abc123 \\');
		expect(run.text).toContain('-e STEWARD_WORKER_NAME=laptop \\');
		expect(run.text.endsWith('ghcr.io/ivamic/immich-steward-worker:0')).toBe(true);
	});

	it('continues lines as each shell does', () => {
		const [run] = setupSteps('docker-windows', values);
		expect(run.text.split('\n')[0]).toMatch(/ `$/);
	});

	it('leaves a placeholder for whoever may not see the token', () => {
		const steps = setupSteps('gpu-windows', { ...values, token: null });
		expect(steps.at(-1)?.text).toContain(`set STEWARD_WORKER_TOKEN=${TOKEN_PLACEHOLDER}`);
	});

	it('installs the version of the server', () => {
		const install = setupSteps('gpu-linux', { ...values, version: '0.7.0rc1' })[0].text;
		expect(install).toContain('git clone --branch v0.7.0-rc.1 ');
	});
});

describe('names and tags', () => {
	it('makes a name the commands take as it is', () => {
		expect(workerName(' Ivan laptop ')).toBe('Ivan-laptop');
		expect(workerName('')).toBe('desktop');
	});

	it('spells tags as Git does', () => {
		expect(releaseTag('0.7.0')).toBe('v0.7.0');
		expect(releaseTag('0.7.0b2')).toBe('v0.7.0-beta.2');
	});
});
