# SPDX-License-Identifier: AGPL-3.0-or-later
"""The page "Groups": the groups of photos of one view (`steward.view_groups`)."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steward import view_groups
from steward.api.assets import AssetItem
from steward.api.library import JobOut
from steward.deps import CurrentAccount, DbDep
from steward.errors import ApiError
from steward.jobs import enqueue
from steward.models import Account, Job, ViewGroup
from steward.view_groups import Summary

router = APIRouter(prefix="/groups")

GroupView = Literal["all", "no_location", "spread", "trash"]
VIEWS: tuple[GroupView, ...] = ("all", "no_location", "spread", "trash")


class Cover(BaseModel):
    id: UUID
    version: str | None


class GroupOut(BaseModel):
    id: UUID
    name: str | None
    trash: bool
    photos: int
    without_location: int
    spread: bool
    cover: Cover | None = None

    @classmethod
    def of(cls, summary: Summary, cover: tuple[UUID, str | None] | None) -> "GroupOut":
        return cls(
            id=summary.id,
            name=summary.name,
            trash=summary.trash,
            photos=summary.photos,
            without_location=summary.without_location,
            spread=summary.spread,
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


class GroupDetail(BaseModel):
    group: GroupOut
    photos: list[AssetItem]


class GroupUpdate(BaseModel):
    # Empty: no name.
    name: str = Field(max_length=200)


def _in_view(summary: Summary, view: GroupView) -> bool:
    if view == "trash":
        return summary.trash
    if summary.trash:
        return False
    if view == "no_location":
        return summary.without_location > 0
    return view == "all" or summary.spread


async def _own_group(db: AsyncSession, account: Account, group_id: UUID) -> ViewGroup:
    group = await db.get(ViewGroup, group_id)
    if group is None or group.account_id != account.id:
        raise ApiError(404, "group_not_found")
    return group


async def _detail(db: AsyncSession, account: Account, group: ViewGroup) -> GroupDetail:
    summaries = await view_groups.summaries(db, account.id)
    summary = next((s for s in summaries if s.id == group.id), None)
    if summary is None:  # all its photos left: moved to the trash of Immich, or taken out
        summary = Summary(group.id, group.name, group.trash, 0, 0, False)
    covers = await view_groups.covers(db, [group.id])
    return GroupDetail(
        group=GroupOut.of(summary, covers.get(group.id)),
        photos=[AssetItem.of(asset) for asset in await view_groups.photos_of(db, group.id)],
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
    page = [s for s in summaries if _in_view(s, view)][offset : offset + limit]
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
        counts={v: sum(_in_view(s, v) for s in summaries) for v in VIEWS},
        groups=[GroupOut.of(s, covers.get(s.id)) for s in page],
    )


@router.post("/refresh", status_code=202)
async def refresh_groups(account: CurrentAccount, db: DbDep) -> JobOut:
    """Searches the neighbors of all the photos again and rebuilds the groups."""
    payload = {"since": datetime.now(UTC).isoformat(), "rebuild": True}
    return JobOut.of(await enqueue(db, view_groups.JOB_KIND, account.id, payload))


@router.get("/{group_id}")
async def get_group(group_id: UUID, account: CurrentAccount, db: DbDep) -> GroupDetail:
    return await _detail(db, account, await _own_group(db, account, group_id))


@router.patch("/{group_id}")
async def update_group(
    group_id: UUID, body: GroupUpdate, account: CurrentAccount, db: DbDep
) -> GroupDetail:
    group = await _own_group(db, account, group_id)
    group.name = body.name.strip() or None
    await db.commit()
    return await _detail(db, account, group)
