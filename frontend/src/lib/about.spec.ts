// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { fileUrl, releaseTag, sourceUrl } from './about';

describe('releaseTag', () => {
	it.each([
		['0.10.0', 'v0.10.0'],
		['0.10.0rc1', 'v0.10.0-rc.1'],
		['0.10.0-rc.2', 'v0.10.0-rc.2'],
		['1.2.3b1', 'v1.2.3-beta.1']
	])('%s is the release %s', (version, tag) => {
		expect(releaseTag(version)).toBe(tag);
	});

	it.each(['0.10.0.dev3', '0.10.0+g1a2b3c', '0.0.0', 'unknown'])(
		'%s is a development build',
		(version) => {
			// 0.0.0: the version when the package is not installed (see steward/__init__.py).
			expect(releaseTag(version)).toBeNull();
		}
	);
});

describe('links', () => {
	it('point to the tag of a release', () => {
		expect(sourceUrl('0.10.0')).toBe('https://github.com/Ivamic/immich-steward/tree/v0.10.0');
		expect(fileUrl('0.10.0rc1', 'LICENSE')).toBe(
			'https://github.com/Ivamic/immich-steward/blob/v0.10.0-rc.1/LICENSE'
		);
	});

	it('point to the main branch for a development build', () => {
		expect(sourceUrl('0.10.0.dev3')).toBe('https://github.com/Ivamic/immich-steward/tree/main');
	});
});
