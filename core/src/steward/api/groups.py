# SPDX-License-Identifier: AGPL-3.0-or-later
"""The page "Groups": the groups of photos of one view (`steward.view_groups`)."""

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steward import view_groups
from steward.api.assets import AssetItem
from steward.api.library import JobOut
from steward.deps import CurrentAccount, DbDep
from steward.embeddings import is_located
from steward.errors import ApiError
from steward.jobs import ACTIVE_STATUSES, enqueue
from steward.models import Account, Job, ViewGroup
from steward.view_groups import Summary

router = APIRouter(prefix="/groups")

# Far more than anyone chooses by hand; keeps a request bounded.
MAX_ASSETS = 2000
# Photos of the trash shown at once.
TRASHED_SHOWN = 300
# Groups shown as lying in the same spot as a group.
SAME_SPOT_SHOWN = 12

GroupView = Literal["all", "ready", "no_location", "with_location", "spread", "trash", "dissolved"]
VIEWS: tuple[GroupView, ...] = ("all", "ready", "no_location", "with_location", "spread", "trash")


class Cover(BaseModel):
    id: UUID
    version: str | None


class GroupSpot(BaseModel):
    latitude: float
    longitude: float
    photos: int


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
    # Most of the photos with a location lie in the spot.
    main_spot: bool = False
    # The photos without a location can get the place of the spot.
    ready: bool = False
    cover: Cover | None = None

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
            main_spot=summary.main_spot,
            ready=summary.ready,
            cover=Cover(id=cover[0], version=cover[1]) if cover else None,
        )


class GroupsStatus(BaseModel):
    vectors: int
    searched: int
    rebuilt_at: datetime | None
    job: JobOut | None


class GroupList(BaseModel):
    status: GroupsStatus
    # Groups in each view, for the filters.
    counts: dict[GroupView, int]
    groups: list[GroupOut]


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
    # Per photo: how close it is to the others of the group.
    closeness: dict[UUID, float]
    # The photos closest to the rest of the group: what it holds on to.
    center: list[UUID]


class PhotoGroup(BaseModel):
    id: UUID
    name: str | None


class PhotoGroups(BaseModel):
    group: PhotoGroup | None
    # Other photos do not get their place from this one.
    no_sign: bool


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
    total: int
    # The ones put there last.
    photos: list[AssetItem]


def _in_view(summary: Summary, view: GroupView) -> bool:
    if view == "trash":
        return summary.trash
    if summary.trash:
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
    return GroupDetail(
        group=GroupOut.of(summary, covers.get(group.id)),
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
        excluded=[AssetItem.of(a) for a in await view_groups.excluded_of(db, group.id)],
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
) -> GroupList:
    summaries = await view_groups.summaries(db, account.id)
    dissolved = await view_groups.dissolved_summaries(db, account.id)
    if view == "dissolved":
        page = dissolved[offset : offset + limit]
        covers = await view_groups.excluded_cover(db, [s.id for s in page])
    else:
        listed = [s for s in summaries if _in_view(s, view)]
        if view == "ready":  # the most to gain first
            listed.sort(key=lambda s: -s.without_location)
        page = listed[offset : offset + limit]
        covers = await view_groups.covers(db, [s.id for s in page])
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
        groups=[GroupOut.of(s, covers.get(s.id)) for s in page],
    )


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
    group, no_sign = await view_groups.of_photo(db, account.id, asset_id)
    found = PhotoGroup(id=group.id, name=group.name) if group else None
    return PhotoGroups(group=found, no_sign=no_sign)


@router.get("/trash-photos")
async def trash_photos(account: CurrentAccount, db: DbDep) -> TrashedPhotos:
    total, photos = await view_groups.trashed_photos(db, account.id, TRASHED_SHOWN)
    return TrashedPhotos(total=total, photos=[AssetItem.of(asset) for asset in photos])


@router.post("/trash-photos/restore")
async def restore_trash_photos(
    body: GroupPhotos, account: CurrentAccount, db: DbDep
) -> TrashedPhotos:
    await view_groups.restore_photos(db, account.id, body.ids)
    await _rebuild_soon(db, account)
    return await trash_photos(account, db)


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
    if body.trash is not None:
        group.trash = body.trash
    await db.commit()
    return await _detail(db, account, group)


@router.get("/{group_id}/same-spot")
async def same_spot_groups(group_id: UUID, account: CurrentAccount, db: DbDep) -> list[GroupOut]:
    """Other groups in the main spot of this one: other sides of one place."""
    group = await _own_group(db, account, group_id)
    found = view_groups.same_spot(await view_groups.summaries(db, account.id), group.id)
    found = found[:SAME_SPOT_SHOWN]
    covers = await view_groups.covers(db, [s.id for s in found])
    return [GroupOut.of(s, covers.get(s.id)) for s in found]


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
