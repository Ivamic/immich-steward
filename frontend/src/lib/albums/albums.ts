// SPDX-License-Identifier: AGPL-3.0-or-later
// Putting photos into an album of Immich and taking them out, with a notice that can undo it
// (D-233): the photos put in now are taken out again (an album made by this change is deleted),
// the ones taken out are put back.
import {
	addToAlbum,
	createAlbum,
	deleteAlbum,
	removeFromAlbum,
	SHOW_CATEGORIES,
	type Album,
	type AlbumAdded
} from '#lib/api.js';
import { bulkNotices } from '#lib/gallery/bulk.svelte.js';
import { defaultFilter, filterToUrl } from '#lib/gallery/filter.js';
import { galleryChanged } from '#lib/gallery/selection.svelte.js';
import { m } from '#lib/paraglide/messages.js';

/** The album in the gallery of the app: all its photos, the archived ones too (a query to put
 * after the gallery path). */
export function albumGalleryQuery(albumId: string) {
	return filterToUrl({
		...defaultFilter,
		show: [...SHOW_CATEGORIES],
		archived: 'with',
		album: albumId
	});
}

/** Where the photos go: an existing album, or a new one by name. */
export type AlbumTarget = { album: Album } | { name: string };

/** Puts the photos into the album; `canDelete`: the key may delete albums (for the undo of a
 * new one). Throws the API error when Immich refuses. */
export async function putIntoAlbum(
	target: AlbumTarget,
	ids: string[],
	canDelete: boolean
): Promise<AlbumAdded> {
	const result =
		'album' in target
			? await addToAlbum(target.album.id, ids)
			: await createAlbum(target.name, ids);
	galleryChanged();
	const name = result.album.name;
	const text = result.created
		? m.album_created({ album: name, count: result.added.length })
		: m.album_added({ album: name, count: result.added.length });
	const details = [
		...(result.already ? [m.album_already({ count: result.already })] : []),
		...(result.skipped_locked ? [m.album_skipped_locked({ count: result.skipped_locked })] : []),
		...(result.failed ? [m.album_failed_some({ count: result.failed })] : [])
	];
	if (result.created || result.added.length) {
		bulkNotices.undoable(text, details, () => undo(result, canDelete));
	} else {
		bulkNotices.done([text, ...details].join(' '));
	}
	return result;
}

async function undo(result: AlbumAdded, canDelete: boolean): Promise<string> {
	const name = result.album.name;
	if (result.created && canDelete) {
		await deleteAlbum(result.album.id);
		galleryChanged();
		return m.album_create_undone({ album: name });
	}
	const { removed } = result.added.length
		? await removeFromAlbum(result.album.id, result.added)
		: { removed: 0 };
	galleryChanged();
	return result.created
		? m.album_create_undone_kept({ album: name })
		: m.album_add_undone({ album: name, count: removed });
}

/** Takes the photos out of the album (they stay in the library); the notice can put them back.
 * Throws the API error when Immich refuses. */
export async function takeOutOfAlbum(
	album: { id: string; name: string },
	ids: string[]
): Promise<void> {
	const result = await removeFromAlbum(album.id, ids);
	galleryChanged();
	const text = m.album_removed({ album: album.name, count: result.removed });
	const details = result.failed ? [m.album_remove_failed_some({ count: result.failed })] : [];
	if (!result.removed) {
		bulkNotices.done([text, ...details].join(' '));
		return;
	}
	bulkNotices.undoable(text, details, async () => {
		const back = await addToAlbum(album.id, result.removed_ids);
		galleryChanged();
		return m.album_remove_undone({ album: album.name, count: back.added.length });
	});
}
