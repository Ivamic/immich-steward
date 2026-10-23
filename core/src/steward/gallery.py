# SPDX-License-Identifier: AGPL-3.0-or-later
"""Queries behind the gallery: filters, month buckets, assets of a month, filter options."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, exists, func, literal, or_, select, tuple_
from sqlalchemy.dialects.postgresql import JSONPATH
from sqlalchemy.ext.asyncio import AsyncSession

from steward.models import Account, Album, Asset, AssetAlbum, ModuleRun
from steward.worker_queue import latest_run_failed, whole_photo

# Disjoint groups the gallery can show in any combination. with: has a location (whatever its
# review status); todo: no location and not marked; skipped / not_applicable: no location and
# marked so by the user.
ShowCategory = Literal["todo", "with", "skipped", "not_applicable"]
TypeFilter = Literal["all", "image", "video"]

# Separates make and model in the camera filter value.
CAMERA_SEPARATOR = "\x1f"
# `failed_module` value: the latest run of any module failed.
ANY_MODULE = "any"


@dataclass(frozen=True)
class GalleryFilter:
    # Empty means every group.
    show: frozenset[ShowCategory] = field(default_factory=frozenset)
    type: TypeFilter = "all"
    # make + CAMERA_SEPARATOR + model, as returned by camera_options(); "" means unknown camera.
    camera: str | None = None
    album_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    include_archived: bool = False
    # Only photos without a location that GeoCLIP places with at least this confidence.
    geoclip_confidence: float | None = None
    # Only photos whose latest run of this module (`ANY_MODULE`: of any module) failed (with
    # this failure code, if set).
    failed_module: str | None = None
    failure: str | None = None

    def conditions(self, account: Account) -> list[ColumnElement[bool]]:
        result: list[ColumnElement[bool]] = [
            Asset.account_id == account.id,
            Asset.is_trashed.is_(False),
        ]
        if not self.include_archived:
            result.append(Asset.visibility == "timeline")
        if self.show:
            result.append(or_(*(_show_condition(category) for category in sorted(self.show))))
        if self.type != "all":
            result.append(Asset.type == self.type.upper())
        if self.camera is not None:
            make, _, model = self.camera.partition(CAMERA_SEPARATOR)
            result.append(func.coalesce(Asset.camera_make, "") == make)
            result.append(func.coalesce(Asset.camera_model, "") == model)
        if self.album_id is not None:
            result.append(
                Asset.id.in_(
                    select(AssetAlbum.asset_id).where(AssetAlbum.album_id == self.album_id)
                )
            )
        if self.date_from is not None:
            result.append(
                Asset.local_taken_at >= datetime.combine(self.date_from, datetime.min.time())
            )
        if self.geoclip_confidence is not None:
            result.append(Asset.latitude.is_(None))
            result.append(geoclip_confident(self.geoclip_confidence))
        if self.date_to is not None:
            end = datetime.combine(self.date_to + timedelta(days=1), datetime.min.time())
            result.append(Asset.local_taken_at < end)
        if self.failed_module is not None:
            module = None if self.failed_module == ANY_MODULE else self.failed_module
            result.append(latest_run_failed(module, self.failure))
        return result


def _show_condition(category: ShowCategory) -> ColumnElement[bool]:
    if category == "with":
        return Asset.latitude.is_not(None)
    status = "new" if category == "todo" else category
    return and_(Asset.latitude.is_(None), Asset.review_status == status)


def geoclip_confident(min_score: float) -> ColumnElement[bool]:
    """The asset has a GeoCLIP result with a candidate at least this confident."""
    return exists().where(
        ModuleRun.asset_id == Asset.id,
        ModuleRun.module_id == "geoclip",
        ModuleRun.status == "done",
        whole_photo(),
        func.jsonb_path_exists(
            ModuleRun.candidates,
            literal("$[*] ? (@.score >= $min)", JSONPATH),
            func.jsonb_build_object("min", min_score),
        ),
    )


async def geoclip_confident_ids(
    db: AsyncSession, asset_ids: list[UUID], min_score: float
) -> set[UUID]:
    """Of the given assets, those without a location that GeoCLIP places confidently."""
    if not asset_ids:
        return set()
    rows = await db.scalars(
        select(Asset.id).where(
            Asset.id.in_(asset_ids), Asset.latitude.is_(None), geoclip_confident(min_score)
        )
    )
    return set(rows)


def _month_start(month: date) -> datetime:
    return datetime(month.year, month.month, 1)


def _next_month(month: date) -> datetime:
    return datetime(month.year + month.month // 12, month.month % 12 + 1, 1)


async def month_buckets(
    db: AsyncSession, account: Account, gallery_filter: GalleryFilter
) -> list[tuple[date, int]]:
    month = func.date_trunc("month", Asset.local_taken_at).label("month")
    rows = await db.execute(
        select(month, func.count())
        .where(*gallery_filter.conditions(account))
        .group_by(month)
        .order_by(month.desc())
    )
    return [(row[0].date(), row[1]) for row in rows]


def gallery_order() -> tuple[Any, ...]:
    """Newest first; the file name breaks ties between photos taken in the same second."""
    return (Asset.local_taken_at.desc(), Asset.original_file_name.desc(), Asset.id.desc())


def month_assets_query(
    account: Account, gallery_filter: GalleryFilter, month: date
) -> Select[Asset]:
    return (
        select(Asset)
        .where(
            *gallery_filter.conditions(account),
            and_(
                Asset.local_taken_at >= _month_start(month),
                Asset.local_taken_at < _next_month(month),
            ),
        )
        .order_by(*gallery_order())
    )


async def neighbors(
    db: AsyncSession, account: Account, gallery_filter: GalleryFilter, asset: Asset
) -> tuple[UUID | None, UUID | None]:
    """Previous (newer) and next (older) asset in the gallery order under the filter."""
    key = tuple_(Asset.local_taken_at, Asset.original_file_name, Asset.id)
    current = tuple_(
        literal(asset.local_taken_at), literal(asset.original_file_name), literal(asset.id)
    )
    conditions = gallery_filter.conditions(account)
    previous = await db.scalar(
        select(Asset.id)
        .where(*conditions, key > current)
        .order_by(Asset.local_taken_at, Asset.original_file_name, Asset.id)
        .limit(1)
    )
    following = await db.scalar(
        select(Asset.id).where(*conditions, key < current).order_by(*gallery_order()).limit(1)
    )
    return previous, following


async def camera_options(db: AsyncSession, account: Account) -> list[dict[str, Any]]:
    make = func.coalesce(Asset.camera_make, "")
    model = func.coalesce(Asset.camera_model, "")
    rows = await db.execute(
        select(make, model, func.count())
        .where(Asset.account_id == account.id, Asset.is_trashed.is_(False))
        .group_by(make, model)
        .order_by(func.count().desc())
    )
    return [
        {
            "value": f"{row[0]}{CAMERA_SEPARATOR}{row[1]}",
            "make": row[0],
            "model": row[1],
            "count": row[2],
        }
        for row in rows
    ]


async def album_options(db: AsyncSession, account: Account) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(Album.id, Album.name, func.count(AssetAlbum.asset_id))
        .outerjoin(AssetAlbum, AssetAlbum.album_id == Album.id)
        .where(Album.account_id == account.id)
        .group_by(Album.id, Album.name)
        .order_by(Album.name)
    )
    return [{"id": row[0], "name": row[1], "count": row[2]} for row in rows]
