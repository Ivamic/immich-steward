# SPDX-License-Identifier: AGPL-3.0-or-later
"""Queries behind the gallery: filters, month buckets, assets of a month, filter options."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Numeric,
    Select,
    and_,
    exists,
    func,
    literal,
    or_,
    select,
    tuple_,
)
from sqlalchemy.dialects.postgresql import JSONPATH
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from steward.embeddings import located
from steward.models import Account, Album, Asset, AssetAlbum, ModuleRun, SimilarHint
from steward.worker_queue import latest_run_failed, whole_photo

# Disjoint groups the gallery can show in any combination. with: has a location (whatever its
# review status); todo: no location and not marked; skipped / not_applicable: no location and
# marked so by the user.
ShowCategory = Literal["todo", "with", "skipped", "not_applicable"]
TypeFilter = Literal["all", "image", "video"]

# Separates make and model in the camera filter value.
CAMERA_SEPARATOR = "\x1f"
# Scanned photos carry the scan date, not the capture date (matched against "make model").
SCANNER = re.compile(r"scan|epson|perfection|coolscan|plustek|fujitsu fi-", re.IGNORECASE)
# Which located photo close in time makes a photo without a location "nearby": one by the
# same camera, or only by another one.
NearbyLevel = Literal["same_camera", "other_camera"]
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
    # Only photos without a location with a located photo this confidently similar (the badge
    # of `similar_hints`).
    similar_confidence: float | None = None
    # Only photos without a location with a located one this many minutes before or after.
    nearby_minutes: float | None = None
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
        if self.similar_confidence is not None:
            result.append(~located())
            result.append(similar_confident(self.similar_confidence))
        if self.nearby_minutes is not None:
            result.append(located_nearby(self.nearby_minutes))
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


def similar_confident(min_score: float) -> ColumnElement[bool]:
    """A photo with a location is at least this confidently similar (`steward.similar_hints`)."""
    return exists().where(SimilarHint.asset_id == Asset.id, SimilarHint.score >= min_score)


def is_scan(asset: Any = Asset) -> ColumnElement[bool]:
    """SQL twin of `time_neighbors.is_scanner`."""
    camera = func.concat_ws(
        " ", func.coalesce(asset.camera_make, ""), func.coalesce(asset.camera_model, "")
    )
    result: ColumnElement[bool] = camera.op("~*")(SCANNER.pattern)
    return result


def located_nearby(minutes: float, same_camera: bool = False) -> ColumnElement[bool]:
    """The asset has no location, and another photo of the account taken at most this many
    minutes before or after (by the camera clock) has one; with `same_camera`, by the same
    camera. As for time neighbors: archived photos count, trashed ones and scans do not."""
    neighbor = aliased(Asset)
    window = timedelta(minutes=minutes)
    conditions = [
        neighbor.account_id == Asset.account_id,
        neighbor.is_trashed.is_(False),
        neighbor.latitude.is_not(None),
        neighbor.id != Asset.id,
        neighbor.local_taken_at.between(
            Asset.local_taken_at - window, Asset.local_taken_at + window
        ),
        ~is_scan(neighbor),
    ]
    if same_camera:
        conditions += [
            neighbor.camera_make.is_not_distinct_from(Asset.camera_make),
            neighbor.camera_model.is_not_distinct_from(Asset.camera_model),
            or_(Asset.camera_make.is_not(None), Asset.camera_model.is_not(None)),
        ]
    return and_(Asset.latitude.is_(None), ~is_scan(), exists().where(*conditions))


async def nearby_levels(
    db: AsyncSession, asset_ids: list[UUID], minutes: float
) -> dict[UUID, NearbyLevel]:
    """Of the given assets, those with a located photo nearby in time, and by which camera."""
    if not asset_ids:
        return {}
    same = located_nearby(minutes, same_camera=True).label("same")
    rows = await db.execute(
        select(Asset.id, same).where(Asset.id.in_(asset_ids), located_nearby(minutes))
    )
    return {row.id: "same_camera" if row.same else "other_camera" for row in rows}


# Heat map cells by level: coordinates rounded to this many decimals. The coarse cells of about
# 100 m are for an overview; close up their grid shows, so there the map takes the fine ones of
# about 11 m.
HEATMAP_DECIMALS = {"coarse": 3, "fine": 4}
# A cell is drawn where its photos are on average, rounded to about 1 m.
HEATMAP_POINT_DECIMALS = 5


def _located(account: Account) -> list[ColumnElement[bool]]:
    return [
        Asset.account_id == account.id,
        Asset.is_trashed.is_(False),
        Asset.latitude.is_not(None),
        Asset.longitude.is_not(None),
    ]


async def heatmap_version(db: AsyncSession, account: Account) -> str:
    """Changes whenever a photo gets, loses or changes its location: for the ETag."""
    row = (
        await db.execute(
            select(func.count(), func.sum(Asset.latitude), func.sum(Asset.longitude)).where(
                *_located(account)
            )
        )
    ).one()
    return f"{row[0]}-{row[1] or 0:.6f}-{row[2] or 0:.6f}"


async def heatmap_cells(db: AsyncSession, account: Account, level: str = "coarse") -> list[float]:
    """Where the located photos of the account are, as cells of the level: a flat list of
    latitude, longitude and number of photos, cell after cell. The point of a cell is the average
    of its photos, not a corner of the grid: the grid would show as rows of spots close up.
    Archived photos count, trashed ones do not; the gallery filter does not apply."""
    decimals = HEATMAP_DECIMALS[level]
    lat = func.round(func.cast(Asset.latitude, Numeric), decimals)
    lon = func.round(func.cast(Asset.longitude, Numeric), decimals)
    rows = await db.execute(
        select(func.avg(Asset.latitude), func.avg(Asset.longitude), func.count())
        .where(*_located(account))
        .group_by(lat, lon)
    )
    cells: list[float] = []
    for cell_lat, cell_lon, count in rows:
        cells += [
            round(float(cell_lat), HEATMAP_POINT_DECIMALS),
            round(float(cell_lon), HEATMAP_POINT_DECIMALS),
            count,
        ]
    return cells


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


async def similar_confident_ids(
    db: AsyncSession, asset_ids: list[UUID], min_score: float
) -> set[UUID]:
    """Of the given assets, those without a location with a confidently similar located photo."""
    if not asset_ids:
        return set()
    rows = await db.scalars(
        select(Asset.id).where(Asset.id.in_(asset_ids), ~located(), similar_confident(min_score))
    )
    return set(rows)


def _month_start(month: date) -> datetime:
    return datetime(month.year, month.month, 1)


def _next_month(month: date) -> datetime:
    return datetime(month.year + month.month // 12, month.month % 12 + 1, 1)


async def month_buckets(
    db: AsyncSession, account: Account, gallery_filter: GalleryFilter
) -> list[tuple[date, list[int]]]:
    """The months with photos, newest first, each with the number of photos of each of its days
    that has any (newest first too): the gallery shows the days as groups and sizes a month
    before its photos are loaded."""
    day = func.date_trunc("day", Asset.local_taken_at).label("day")
    rows = await db.execute(
        select(day, func.count())
        .where(*gallery_filter.conditions(account))
        .group_by(day)
        .order_by(day.desc())
    )
    months: list[tuple[date, list[int]]] = []
    for taken, count in rows:
        first = taken.date().replace(day=1)
        if not months or months[-1][0] != first:
            months.append((first, []))
        months[-1][1].append(count)
    return months


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
