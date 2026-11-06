# SPDX-License-Identifier: AGPL-3.0-or-later
"""The page "Groups": the groups of photos of one view (`steward.view_groups`)."""

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from steward import view_groups
from steward.api.assets import AssetItem, _immich
from steward.api.library import JobOut
from steward.deps import CurrentAccount, DbDep, ImmichFactoryDep, SecretBoxDep, SettingsDep
from steward.embeddings import is_located
from steward.errors import ApiError
from steward.immich import ImmichError
from steward.jobs import ACTIVE_STATUSES, enqueue
from steward.models import Account, Job, ViewFolder, ViewGroup
from steward.modules.time_neighbors import distance_m
from steward.view_groups import Summary

router = APIRouter(prefix="/groups")

# Far more than anyone chooses by hand; keeps a request bounded.
MAX_ASSETS = 2000
# Photos of the trash given at a time.
TRASHED_PAGE = 120
TRASHED_MOST = 500
# The most Immich gives for a smart search at a time.
SMART_SEARCH_MOST = 1000
# Who set a mark "no sign of a place".
MarkSource = Literal["user", "auto"]
# Groups shown as lying in the same spot as a group.
SAME_SPOT_SHOWN = 12
# Covers on the tile of a folder.
FOLDER_COVERS = 4

GroupView = Literal["all", "ready", "no_location", "with_location", "spread", "trash", "dissolved"]
VIEWS: tuple[GroupView, ...] = ("all", "ready", "no_location", "with_location", "spread", "trash")


class Cover(BaseModel):
    id: UUID
    version: str | None


class GroupSpot(BaseModel):
    latitude: float
    longitude: float
    photos: int


class FolderRef(BaseModel):
    id: UUID
    name: str


class GroupOut(BaseModel):
    id: UUID
    name: str | None
    trash: bool
    photos: int
    without_location: int
    with_location: int
    spread: bool
    # How close the photos are to each other; None until the next rebuild.
    similarity: float | None
    # Where most of the photos with a location lie.
    spot: GroupSpot | None = None
    # Photos with it, marked as showing nothing of the place.
    marked: int = 0
    # Most of the photos with a location lie in the spot.
    main_spot: bool = False
    # The photos without a location can get the place of the spot.
    ready: bool = False
    cover: Cover | None = None
    # The folder it is in (D-201).
    folder: FolderRef | None = None

    @classmethod
    def of(cls, summary: Summary, cover: tuple[UUID, str | None] | None) -> "GroupOut":
        return cls(
            id=summary.id,
            name=summary.name,
            trash=summary.trash,
            photos=summary.photos,
            without_location=summary.without_location,
            with_location=summary.with_location,
            spread=summary.spread,
            similarity=summary.similarity,
            spot=GroupSpot(**asdict(summary.spot)) if summary.spot else None,
            marked=summary.marked,
            main_spot=summary.main_spot,
            ready=summary.ready,
            cover=Cover(id=cover[0], version=cover[1]) if cover else None,
        )


class GroupsStatus(BaseModel):
    vectors: int
    searched: int
    rebuilt_at: datetime | None
    job: JobOut | None


class FolderOut(BaseModel):
    """A folder in the list: of the groups of the view in it."""

    id: UUID
    name: str
    groups: int
    photos: int
    without_location: int
    with_location: int
    # Its groups marked as showing no sign of a place.
    trash: int
    covers: list[Cover]


class GroupList(BaseModel):
    status: GroupsStatus
    # Groups in each view, for the filters.
    counts: dict[GroupView, int]
    groups: list[GroupOut]
    # The groups of this list (out of the folders unless flat), for the pages.
    total: int = 0
    # The folders with groups of the view (on the first page only; none when flat).
    folders: list[FolderOut] = []


class GroupPoint(BaseModel):
    id: UUID
    latitude: float
    longitude: float
    # The number of its spot in the group: 0 for the largest.
    spot: int
    # The location was written by this app; where it came from before, nobody knows here.
    set_in_app: bool


class GroupDetail(BaseModel):
    group: GroupOut
    photos: list[AssetItem]
    # The photos with a location, for the map.
    points: list[GroupPoint]
    # Taken out by the user.
    excluded: list[AssetItem]
    # Showing nothing of the place: out of the photos of the group, but with it.
    marked: list[AssetItem]
    # Per photo: how close it is to the others of the group.
    closeness: dict[UUID, float]
    # The photos closest to the rest of the group: what it holds on to.
    center: list[UUID]


class FolderPoint(GroupPoint):
    group_id: UUID


class FolderDetail(BaseModel):
    folder: FolderRef
    groups: list[GroupOut]
    photos: list[AssetItem]
    # Photo -> its group.
    group_of: dict[UUID, UUID]
    # The photos with a location, for the map; `spot` numbers the spots of the whole folder.
    points: list[FolderPoint]
    # Where most of the photos with a location lie; `main_spot` when they share it as a group's.
    spot: GroupSpot | None
    main_spot: bool
    ready: bool


class FolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class FolderUpdate(BaseModel):
    """Only what is given changes."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    # All the groups of the folder marked as showing no sign of a place, or none.
    trash: bool | None = None


class GroupFolder(BaseModel):
    """Into a folder (`folder_id`), into a new one (`name`), or out of any (neither)."""

    folder_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)


class CloseGroup(BaseModel):
    group: GroupOut
    # How alike the mean vectors of the two groups are.
    similarity: float
    # Between their main spots, when both have one.
    distance_km: float | None


class PhotoGroup(BaseModel):
    id: UUID
    name: str | None


class PhotoGroups(BaseModel):
    group: PhotoGroup | None
    # Other photos do not get their place from this one.
    no_sign: bool
    # Marked by the app, not by the user (D-200).
    no_sign_auto: bool = False
    # Marked by itself, not only with its whole group: the mark can be taken off here.
    no_sign_self: bool = False


class GroupParts(BaseModel):
    similarity: float
    # Scenes of the group, the largest first; photos in none of them are not listed.
    parts: list[list[UUID]]


class GroupUpdate(BaseModel):
    """Only what is given changes."""

    # Empty: no name.
    name: str | None = Field(default=None, max_length=200)
    trash: bool | None = None


class GroupPhotos(BaseModel):
    ids: Annotated[list[UUID], Field(min_length=1, max_length=MAX_ASSETS)]


class TrashedPhotos(BaseModel):
    # Marked by themselves: all, by the user, by the app (D-200).
    total: int
    user: int = 0
    auto: int = 0
    # A page of them (of one source when asked), those marked last first.
    photos: list[AssetItem]
    # Those of the page the app marked.
    auto_ids: list[UUID] = []
    # Photos marked with their whole group, not counted above.
    in_groups: int = 0


def _in_view(summary: Summary, view: GroupView) -> bool:
    # Only marked photos left, the group is one of those marked.
    if view == "trash":
        return summary.trash or summary.photos == 0
    if summary.trash or summary.photos == 0:
        return False
    if view == "ready":
        return summary.ready
    if view == "no_location":
        return summary.without_location > 0
    if view == "with_location":
        return summary.with_location > 0
    return view == "all" or summary.spread


async def _own_group(db: AsyncSession, account: Account, group_id: UUID) -> ViewGroup:
    group = await db.get(ViewGroup, group_id)
    if group is None or group.account_id != account.id:
        raise ApiError(404, "group_not_found")
    return group


async def _rebuild_soon(db: AsyncSession, account: Account) -> None:
    """The groups are built again without what the user just took out."""
    await enqueue(db, view_groups.JOB_KIND, account.id, {"rebuild": True})


async def _detail(db: AsyncSession, account: Account, group: ViewGroup) -> GroupDetail:
    summaries = await view_groups.summaries(db, account.id, group.id)
    summary = summaries[0] if summaries else None
    if summary is None:  # all its photos left: moved to the trash of Immich, or taken out
        summary = Summary(group.id, group.name, group.trash, 0, 0, 0, False, None)
    covers = await view_groups.covers(db, [group.id])
    photos = await view_groups.photos_of(db, group.id)
    closeness = await view_groups.photo_closeness(db, group.id)
    points = [a for a in photos if is_located(a)]
    spots = view_groups.spots_of({a.id: (a.latitude or 0.0, a.longitude or 0.0) for a in points})
    in_app = await view_groups.set_in_app(db, [a.id for a in points])
    excluded, marked = await view_groups.excluded_of(db, group.id)
    folder = await db.get(ViewFolder, group.folder_id) if group.folder_id else None
    out = GroupOut.of(summary, covers.get(group.id))
    if folder is not None:
        out.folder = FolderRef(id=folder.id, name=folder.name)
    return GroupDetail(
        group=out,
        photos=[AssetItem.of(asset) for asset in photos],
        points=[
            GroupPoint(
                id=a.id,
                latitude=a.latitude,
                longitude=a.longitude,
                spot=spots[a.id],
                set_in_app=a.id in in_app,
            )
            for a in points
        ],
        excluded=[AssetItem.of(a) for a in excluded],
        marked=[AssetItem.of(a) for a in marked],
        closeness=closeness,
        center=view_groups.center_of(closeness),
    )


@router.get("")
async def list_groups(
    account: CurrentAccount,
    db: DbDep,
    view: GroupView = "all",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=60, ge=1, le=200),
    flat: bool = False,
) -> GroupList:
    """The groups of the view. Those in a folder are in its tile, unless `flat` (D-201)."""
    summaries = await view_groups.summaries(db, account.id)
    dissolved = await view_groups.dissolved_summaries(db, account.id)
    folder_of = await view_groups.folder_of_groups(db, account.id)
    all_folders = await view_groups.folders(db, account.id)
    names = {f.id: f.name for f in all_folders}
    folders: list[FolderOut] = []
    if view == "dissolved":
        listed = dissolved
        page = dissolved[offset : offset + limit]
        covers = await view_groups.excluded_cover(db, [s.id for s in page])
    else:
        listed = [s for s in summaries if _in_view(s, view)]
        if view == "ready":  # the most to gain first
            listed.sort(key=lambda s: -s.without_location)
        if not flat:
            if offset == 0:
                folders = await _folders_out(db, all_folders, listed, folder_of, view)
            listed = [s for s in listed if s.id not in folder_of]
        page = listed[offset : offset + limit]
        covers = await view_groups.covers(db, [s.id for s in page if s.photos])
        empty = [s.id for s in page if not s.photos]
        covers |= await view_groups.excluded_cover(db, empty)
    job = await db.scalar(
        select(Job)
        .where(Job.account_id == account.id, Job.kind == view_groups.JOB_KIND)
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    return GroupList(
        status=GroupsStatus(
            **await view_groups.progress_counts(db, account.id),
            rebuilt_at=await view_groups.last_rebuild(db, account.id),
            job=JobOut.of(job) if job else None,
        ),
        counts={v: sum(_in_view(s, v) for s in summaries) for v in VIEWS}
        | {"dissolved": len(dissolved)},
        groups=[_with_folder(GroupOut.of(s, covers.get(s.id)), folder_of, names) for s in page],
        total=len(listed),
        folders=folders,
    )


def _with_folder(out: GroupOut, folder_of: dict[UUID, UUID], names: dict[UUID, str]) -> GroupOut:
    folder_id = folder_of.get(out.id)
    if folder_id is not None and folder_id in names:
        out.folder = FolderRef(id=folder_id, name=names[folder_id])
    return out


async def _folders_out(
    db: AsyncSession,
    all_folders: list[ViewFolder],
    listed: list[Summary],
    folder_of: dict[UUID, UUID],
    view: GroupView,
) -> list[FolderOut]:
    """The folders with groups of the view, by name; those with no group at all too, in the view
    of all, where they are made and can be dropped."""
    found = []
    for folder in all_folders:
        members = [s for s in listed if folder_of.get(s.id) == folder.id]
        empty = folder.id not in folder_of.values()
        if not members and not (empty and view == "all"):
            continue
        covers = await view_groups.covers(db, [s.id for s in members[:FOLDER_COVERS]])
        found.append(
            FolderOut(
                id=folder.id,
                name=folder.name,
                groups=len(members),
                photos=sum(s.photos for s in members),
                without_location=sum(s.without_location for s in members),
                with_location=sum(s.with_location for s in members),
                trash=sum(s.trash for s in members),
                covers=[
                    Cover(id=covers[s.id][0], version=covers[s.id][1])
                    for s in members[:FOLDER_COVERS]
                    if s.id in covers
                ],
            )
        )
    return found


async def _own_folder(db: AsyncSession, account: Account, folder_id: UUID) -> ViewFolder:
    folder = await db.get(ViewFolder, folder_id)
    if folder is None or folder.account_id != account.id:
        raise ApiError(404, "folder_not_found")
    return folder


async def _folder_detail(db: AsyncSession, account: Account, folder: ViewFolder) -> FolderDetail:
    in_folder = [
        s
        for s in await view_groups.summaries(db, account.id)
        if s.id in set(await _groups_of_folder(db, folder.id))
    ]
    covers = await view_groups.covers(db, [s.id for s in in_folder])
    found = await view_groups.folder_photos(db, folder.id)
    located = [(a, g) for a, g in found if is_located(a)]
    places = {a.id: (a.latitude or 0.0, a.longitude or 0.0) for a, _ in located}
    spots = view_groups.spots_of(places)
    spot, main = view_groups.main_spot_of(places)
    in_app = await view_groups.set_in_app(db, list(places))
    ref = FolderRef(id=folder.id, name=folder.name)
    return FolderDetail(
        folder=ref,
        groups=[
            GroupOut.of(s, covers.get(s.id)).model_copy(update={"folder": ref}) for s in in_folder
        ],
        photos=[AssetItem.of(a) for a, _ in found],
        group_of={a.id: g for a, g in found},
        points=[
            FolderPoint(
                id=a.id,
                latitude=a.latitude,
                longitude=a.longitude,
                spot=spots[a.id],
                set_in_app=a.id in in_app,
                group_id=g,
            )
            for a, g in located
        ],
        spot=GroupSpot(**asdict(spot)) if spot else None,
        main_spot=main,
        ready=main and len(located) < len(found),
    )


async def _groups_of_folder(db: AsyncSession, folder_id: UUID) -> list[UUID]:
    return list(await db.scalars(select(ViewGroup.id).where(ViewGroup.folder_id == folder_id)))


@router.get("/folders")
async def list_folders(account: CurrentAccount, db: DbDep) -> list[FolderRef]:
    """The folders, by name: where a group can go."""
    return [FolderRef(id=f.id, name=f.name) for f in await view_groups.folders(db, account.id)]


@router.post("/folders", status_code=201)
async def create_folder(body: FolderIn, account: CurrentAccount, db: DbDep) -> FolderRef:
    folder = ViewFolder(account_id=account.id, name=body.name.strip())
    db.add(folder)
    await db.commit()
    return FolderRef(id=folder.id, name=folder.name)


@router.get("/folders/{folder_id}")
async def get_folder(folder_id: UUID, account: CurrentAccount, db: DbDep) -> FolderDetail:
    return await _folder_detail(db, account, await _own_folder(db, account, folder_id))


@router.patch("/folders/{folder_id}")
async def update_folder(
    folder_id: UUID, body: FolderUpdate, account: CurrentAccount, db: DbDep
) -> FolderDetail:
    folder = await _own_folder(db, account, folder_id)
    if body.name is not None:
        folder.name = body.name.strip()
    if body.trash is not None:
        await db.execute(
            update(ViewGroup).where(ViewGroup.folder_id == folder.id).values(trash=body.trash)
        )
    await db.commit()
    if body.trash is not None:
        await _rebuild_soon(db, account)
    return await _folder_detail(db, account, folder)


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(folder_id: UUID, account: CurrentAccount, db: DbDep) -> None:
    """The folder goes; its groups stay, out of any folder."""
    folder = await _own_folder(db, account, folder_id)
    await db.execute(delete(ViewFolder).where(ViewFolder.id == folder.id))
    await db.commit()


@router.post("/refresh", status_code=202)
async def refresh_groups(account: CurrentAccount, db: DbDep) -> JobOut:
    """Searches the neighbors of all the photos again and rebuilds the groups."""
    payload = {"since": datetime.now(UTC).isoformat(), "rebuild": True}
    return JobOut.of(await enqueue(db, view_groups.JOB_KIND, account.id, payload))


@router.post("/reset", status_code=202)
async def reset_groups(account: CurrentAccount, db: DbDep) -> JobOut:
    """Drops the groups, with their names and all that was done to them, and builds them anew.
    The neighbors stay, and so do the photos in the trash."""
    active = await db.scalar(
        select(Job).where(
            Job.account_id == account.id,
            Job.kind == view_groups.JOB_KIND,
            Job.status.in_(ACTIVE_STATUSES),
        )
    )
    if active is not None:
        raise ApiError(409, "groups_busy")
    payload = {"rebuild": True, "reset": True}
    return JobOut.of(await enqueue(db, view_groups.JOB_KIND, account.id, payload))


@router.get("/of-photo/{asset_id}")
async def groups_of_photo(asset_id: UUID, account: CurrentAccount, db: DbDep) -> PhotoGroups:
    """What the groups say about a photo, for its card."""
    group, no_sign, source = await view_groups.mark_of_photo(db, account.id, asset_id)
    found = PhotoGroup(id=group.id, name=group.name) if group else None
    return PhotoGroups(
        group=found,
        no_sign=no_sign,
        no_sign_auto=source == view_groups.AUTO_MARK,
        no_sign_self=source is not None,
    )


async def _trashed(
    db: AsyncSession,
    account: Account,
    offset: int = 0,
    limit: int = TRASHED_PAGE,
    source: MarkSource | None = None,
) -> TrashedPhotos:
    totals, found = await view_groups.trashed_photos(db, account.id, offset, limit, source)
    return TrashedPhotos(
        **totals,
        in_groups=await view_groups.in_marked_groups(db, account.id),
        photos=[AssetItem.of(asset) for asset, _ in found],
        auto_ids=[asset.id for asset, mark in found if mark == view_groups.AUTO_MARK],
    )


@router.get("/trash-photos")
async def trash_photos(
    account: CurrentAccount,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=TRASHED_PAGE, ge=1, le=TRASHED_MOST),
    source: MarkSource | None = None,
) -> TrashedPhotos:
    return await _trashed(db, account, offset, limit, source)


@router.post("/trash-photos/confirm")
async def confirm_trash_photos(
    body: GroupPhotos, account: CurrentAccount, db: DbDep
) -> TrashedPhotos:
    """Marks the app set become the user's own (and mark others in turn)."""
    await view_groups.confirm_photos(db, account.id, body.ids)
    await _rebuild_soon(db, account)
    return await _trashed(db, account)


class Candidates(BaseModel):
    """Photos that may show no sign of a place, for the user to mark (A1.3)."""

    photos: list[AssetItem]


@router.get("/candidates/scattered")
async def scattered_candidates(
    account: CurrentAccount,
    db: DbDep,
    limit: int = Query(default=view_groups.CANDIDATES_MOST, ge=1, le=view_groups.CANDIDATES_MOST),
) -> Candidates:
    """Photos alike several photos with a location that lie far apart: a view seen in many
    places."""
    found = await view_groups.scattered(db, account.id, limit)
    return Candidates(photos=[AssetItem.of(asset) for asset in found])


@router.get("/candidates/described")
async def described_candidates(
    account: CurrentAccount,
    db: DbDep,
    settings: SettingsDep,
    factory: ImmichFactoryDep,
    box: SecretBoxDep,
    query: str = Query(min_length=1, max_length=200),
    language: str | None = Query(default=None, max_length=10),
    limit: int = Query(default=view_groups.CANDIDATES_MOST, ge=1, le=SMART_SEARCH_MOST),
) -> Candidates:
    """Photos that match a description by the smart search of Immich (CLIP): what Immich finds
    first, not those marked already. Only the text goes to Immich, nothing else leaves."""
    async with _immich(settings, factory, box, account) as client:
        try:
            immich_ids = await client.smart_search(query, size=limit, language=language)
        except ImmichError as exc:
            # Immich answers 400 when its smart search (machine learning) is off.
            if exc.status == 400:
                raise ApiError(409, "immich_smart_search_off") from exc
            raise
    found = await view_groups.unmarked(db, account.id, immich_ids)
    return Candidates(photos=[AssetItem.of(asset) for asset in found])


@router.post("/trash-photos")
async def mark_trash_photos(body: GroupPhotos, account: CurrentAccount, db: DbDep) -> TrashedPhotos:
    """Marks photos from anywhere, not only from their group: out of the suggestions and of the
    groups."""
    await view_groups.trash_photos(db, account.id, body.ids)
    await _rebuild_soon(db, account)
    return await _trashed(db, account)


@router.post("/trash-photos/restore")
async def restore_trash_photos(
    body: GroupPhotos, account: CurrentAccount, db: DbDep
) -> TrashedPhotos:
    await view_groups.restore_photos(db, account.id, body.ids)
    await _rebuild_soon(db, account)
    return await _trashed(db, account)


@router.post("/trash-photos/restore-all")
async def restore_all_trash_photos(account: CurrentAccount, db: DbDep) -> TrashedPhotos:
    """All of them, also those no page has shown."""
    await view_groups.restore_all_photos(db, account.id)
    await _rebuild_soon(db, account)
    return await _trashed(db, account)


@router.get("/{group_id}")
async def get_group(group_id: UUID, account: CurrentAccount, db: DbDep) -> GroupDetail:
    return await _detail(db, account, await _own_group(db, account, group_id))


@router.patch("/{group_id}")
async def update_group(
    group_id: UUID, body: GroupUpdate, account: CurrentAccount, db: DbDep
) -> GroupDetail:
    group = await _own_group(db, account, group_id)
    if body.name is not None:
        group.name = body.name.strip() or None
    trash_changed = body.trash is not None and body.trash != group.trash
    if body.trash is not None:
        group.trash = body.trash
    await db.commit()
    # Its photos teach the marks of the app, or no more.
    if trash_changed:
        await _rebuild_soon(db, account)
    return await _detail(db, account, group)


@router.put("/{group_id}/folder")
async def set_group_folder(
    group_id: UUID, body: GroupFolder, account: CurrentAccount, db: DbDep
) -> GroupDetail:
    """Puts the group into a folder, a new one, or out of any."""
    group = await _own_group(db, account, group_id)
    if body.name is not None:
        folder = ViewFolder(account_id=account.id, name=body.name.strip())
        db.add(folder)
        await db.flush()
        group.folder_id = folder.id
    elif body.folder_id is not None:
        group.folder_id = (await _own_folder(db, account, body.folder_id)).id
    else:
        group.folder_id = None
    await db.commit()
    return await _detail(db, account, group)


@router.get("/{group_id}/close")
async def close_groups(group_id: UUID, account: CurrentAccount, db: DbDep) -> list[CloseGroup]:
    """Groups that may show the same scene: alike by their mean vectors, linked by neighbors."""
    group = await _own_group(db, account, group_id)
    found = await view_groups.close_groups(db, group.id)
    if not found:
        return []
    by_id = {s.id: s for s in await view_groups.summaries(db, account.id)}
    mine = by_id.get(group.id)
    covers = await view_groups.covers(db, [g for g, _ in found])
    folder_of = await view_groups.folder_of_groups(db, account.id)
    names = {f.id: f.name for f in await view_groups.folders(db, account.id)}
    result = []
    for other_id, similarity in found:
        other = by_id.get(other_id)
        if other is None or other.trash != (mine.trash if mine else False):
            continue
        apart = None
        if mine and mine.main_spot and other.main_spot and mine.spot and other.spot:
            apart = (
                distance_m(
                    mine.spot.latitude,
                    mine.spot.longitude,
                    other.spot.latitude,
                    other.spot.longitude,
                )
                / 1000
            )
        out = _with_folder(GroupOut.of(other, covers.get(other_id)), folder_of, names)
        result.append(CloseGroup(group=out, similarity=round(similarity, 3), distance_km=apart))
    return result


@router.get("/{group_id}/same-spot")
async def same_spot_groups(group_id: UUID, account: CurrentAccount, db: DbDep) -> list[GroupOut]:
    """Other groups in the main spot of this one: other sides of one place."""
    group = await _own_group(db, account, group_id)
    found = view_groups.same_spot(await view_groups.summaries(db, account.id), group.id)
    found = found[:SAME_SPOT_SHOWN]
    covers = await view_groups.covers(db, [s.id for s in found])
    folder_of = await view_groups.folder_of_groups(db, account.id)
    names = {f.id: f.name for f in await view_groups.folders(db, account.id)}
    return [_with_folder(GroupOut.of(s, covers.get(s.id)), folder_of, names) for s in found]


@router.get("/{group_id}/parts")
async def group_parts(
    group_id: UUID,
    account: CurrentAccount,
    db: DbDep,
    level: int = Query(default=2, ge=1, le=3),
) -> GroupParts:
    """The scenes inside the group, by the rule of the groups made stricter."""
    group = await _own_group(db, account, group_id)
    rule = await view_groups.rule_of(db, account.id)
    similarity, parts = await view_groups.parts(db, group.id, rule, level)
    return GroupParts(similarity=similarity, parts=parts)


@router.get("/{group_id}/near")
async def near_photos(group_id: UUID, account: CurrentAccount, db: DbDep) -> list[AssetItem]:
    """Photos just short of the group: where its border runs."""
    group = await _own_group(db, account, group_id)
    rule = await view_groups.rule_of(db, account.id)
    return [AssetItem.of(asset) for asset in await view_groups.near(db, group.id, rule)]


@router.post("/{group_id}/dissolve", status_code=202)
async def dissolve_group(group_id: UUID, account: CurrentAccount, db: DbDep) -> JobOut:
    """Takes the group apart: its photos may join other groups, and link nothing among them."""
    group = await _own_group(db, account, group_id)
    await view_groups.dissolve(db, group)
    return JobOut.of(await enqueue(db, view_groups.JOB_KIND, account.id, {"rebuild": True}))


@router.post("/{group_id}/bring-back", status_code=202)
async def bring_back_group(group_id: UUID, account: CurrentAccount, db: DbDep) -> JobOut:
    group = await _own_group(db, account, group_id)
    await view_groups.bring_back(db, group)
    return JobOut.of(await enqueue(db, view_groups.JOB_KIND, account.id, {"rebuild": True}))


@router.post("/{group_id}/exclude")
async def exclude_photos(
    group_id: UUID, body: GroupPhotos, account: CurrentAccount, db: DbDep
) -> GroupDetail:
    group = await _own_group(db, account, group_id)
    await view_groups.exclude(db, group.id, body.ids)
    await _rebuild_soon(db, account)
    return await _detail(db, account, group)


@router.post("/{group_id}/trash")
async def trash_group_photos(
    group_id: UUID, body: GroupPhotos, account: CurrentAccount, db: DbDep
) -> GroupDetail:
    """Photos that show nothing of the place: out of the suggestions and of the groups."""
    group = await _own_group(db, account, group_id)
    await view_groups.trash_photos(db, account.id, body.ids)
    await _rebuild_soon(db, account)
    return await _detail(db, account, group)


@router.post("/{group_id}/include")
async def include_photos(
    group_id: UUID, body: GroupPhotos, account: CurrentAccount, db: DbDep
) -> GroupDetail:
    """Adds photos by hand, or brings back those taken out."""
    group = await _own_group(db, account, group_id)
    await view_groups.include(db, group.id, account.id, body.ids)
    await _rebuild_soon(db, account)
    return await _detail(db, account, group)
