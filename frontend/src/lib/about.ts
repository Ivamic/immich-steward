// SPDX-License-Identifier: AGPL-3.0-or-later
// Links of the About page: the source code of the running version (AGPL §13) and its files.

import { displayVersion } from './versions.js';

export const REPOSITORY = 'https://github.com/Ivamic/immich-steward';

/** The tag of a release or pre-release ("v0.10.0", "v0.10.0-rc.1"); null for any other build
 * (a development one, or 0.0.0 when the package is not installed), whose code is on the main
 * branch. */
export function releaseTag(version: string): string | null {
	const shown = displayVersion(version);
	if (shown === '0.0.0') return null;
	return /^\d+\.\d+\.\d+(-(alpha|beta|rc)\.\d+)?$/.test(shown) ? `v${shown}` : null;
}

/** The source code of this version: its tag, or the main branch for a development build. */
export function sourceUrl(version: string): string {
	return `${REPOSITORY}/tree/${releaseTag(version) ?? 'main'}`;
}

/** A file of the repository as it is in this version. */
export function fileUrl(version: string, path: string): string {
	return `${REPOSITORY}/blob/${releaseTag(version) ?? 'main'}/${path}`;
}
