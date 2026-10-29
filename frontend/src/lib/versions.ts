// SPDX-License-Identifier: AGPL-3.0-or-later
// Versions compare as in the core (`steward.updates.version_key`): "0.5.1" < "0.6.0", and a
// pre-release is older than its release: "0.6.0rc2" < "0.6.0".

const PRE_RELEASE: Record<string, number> = {
	dev: 0,
	a: 1,
	alpha: 1,
	b: 2,
	beta: 2,
	c: 3,
	rc: 3,
	pre: 3
};

export function versionKey(text: string): number[] {
	const match = /^v?(\d+(?:\.\d+)*)[-_.]?([a-z]*)[-_.]?(\d*)/.exec(text.trim().toLowerCase());
	if (!match) return [];
	const numbers = match[1].split('.').map(Number);
	while (numbers.length < 3) numbers.push(0);
	const [label, number] = [match[2], Number(match[3] || 0)];
	const stage = !label
		? [1, 0, 0]
		: label === 'post'
			? [2, 0, number]
			: [0, PRE_RELEASE[label] ?? 0, number];
	return [...numbers, ...stage];
}

export function older(version: string, than: string): boolean {
	const [a, b] = [versionKey(version), versionKey(than)];
	for (let i = 0; i < Math.max(a.length, b.length); i++) {
		const diff = (a[i] ?? -1) - (b[i] ?? -1);
		if (diff !== 0) return diff < 0;
	}
	return false;
}
