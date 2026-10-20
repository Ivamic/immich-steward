// SPDX-License-Identifier: AGPL-3.0-or-later
// Cameras the user excluded from the time-neighbor suggestions. Kept while the tab is open, so
// that a camera excluded on one photo (e.g. someone else's phone) stays excluded on the next.
// "Only this device" works the same way: it holds on the next photos, whatever their cameras.
export const cameraFilter = $state<{ excluded: string[]; sameOnly: boolean }>({
	excluded: [],
	sameOnly: false
});

export function setCameraExcluded(value: string, excluded: boolean) {
	const others = cameraFilter.excluded.filter((v) => v !== value);
	cameraFilter.excluded = excluded ? [...others, value] : others;
}
