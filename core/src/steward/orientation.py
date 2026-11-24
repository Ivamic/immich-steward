# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turned photos (D-237): the photos the `orientation` module of a worker finds turned, for the
user to turn back in Immich or keep as they are. Nothing is written to Immich here."""

from uuid import UUID

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from steward import locked, rotation, worker_queue
from steward.config import Settings
from steward.models import Asset, AssetOrientation, ModuleRun

MODULE_ID = "orientation"

# Quarter turns counter-clockwise the photo has now -> degrees clockwise that make it right
# (as `steward.rotation` and the selection rotate take them).
FIX: dict[int, int] = {1: 90, 2: 180, 3: 270}


def offered(settings: Settings) -> list[int]:
    """The turns the list offers: the quarter turns, and upside down when turned on."""
    return [1, 3, 2] if settings.orientation_upside_down else [1, 3]


def _turned(account_id: UUID, settings: Settings) -> ColumnElement[bool]:
    return and_(
        AssetOrientation.asset_id == Asset.id,
        Asset.account_id == account_id,
        AssetOrientation.turn.in_(offered(settings)),
        AssetOrientation.score >= settings.orientation_min_confidence,
        AssetOrientation.kept.is_(False),
        Asset.is_trashed.is_(False),
        Asset.type == "IMAGE",
        # Being turned now: offered again it could be turned twice.
        rotation.not_turning(),
        locked.shown(),
    )


async def counts(db: AsyncSession, account_id: UUID, settings: Settings) -> dict[int, int]:
    """Turn -> how many photos look turned so."""
    rows = await db.execute(
        select(AssetOrientation.turn, func.count())
        .select_from(AssetOrientation)
        .join(Asset, Asset.id == AssetOrientation.asset_id)
        .where(_turned(account_id, settings))
        .group_by(AssetOrientation.turn)
    )
    return {turn: count for turn, count in rows.all()}


async def photos(
    db: AsyncSession, account_id: UUID, settings: Settings, turn: int, offset: int, limit: int
) -> list[tuple[Asset, AssetOrientation]]:
    """Photos that look turned so, the surest first."""
    rows = await db.execute(
        select(Asset, AssetOrientation)
        .join(AssetOrientation, AssetOrientation.asset_id == Asset.id)
        .where(_turned(account_id, settings), AssetOrientation.turn == turn)
        .order_by(AssetOrientation.score.desc(), Asset.local_taken_at.desc(), Asset.id)
        .offset(offset)
        .limit(limit)
    )
    return [(asset, found) for asset, found in rows.all()]


def _kept(account_id: UUID) -> ColumnElement[bool]:
    return and_(
        AssetOrientation.asset_id == Asset.id,
        Asset.account_id == account_id,
        AssetOrientation.kept.is_(True),
        Asset.is_trashed.is_(False),
        locked.shown(),
    )


async def kept_count(db: AsyncSession, account_id: UUID) -> int:
    """Photos the user kept as they are."""
    count = await db.scalar(
        select(func.count())
        .select_from(AssetOrientation)
        .join(Asset, Asset.id == AssetOrientation.asset_id)
        .where(_kept(account_id))
    )
    return count or 0


async def kept_photos(
    db: AsyncSession, account_id: UUID, offset: int, limit: int
) -> list[tuple[Asset, AssetOrientation]]:
    """Photos the user kept as they are, newest first."""
    rows = await db.execute(
        select(Asset, AssetOrientation)
        .join(AssetOrientation, AssetOrientation.asset_id == Asset.id)
        .where(_kept(account_id))
        .order_by(Asset.local_taken_at.desc(), Asset.id)
        .offset(offset)
        .limit(limit)
    )
    return [(asset, found) for asset, found in rows.all()]


async def keep(db: AsyncSession, account_id: UUID, ids: list[UUID], kept: bool) -> int:
    """Marks the photos right as they are (or offers them again); returns how many changed."""
    own = select(Asset.id).where(Asset.account_id == account_id, Asset.id.in_(ids))
    result = await db.execute(
        update(AssetOrientation)
        .where(AssetOrientation.asset_id.in_(own), AssetOrientation.kept.is_not(kept))
        .values(kept=kept)
    )
    await db.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def _to_look_again(account_id: UUID, keep_kept: bool) -> list[ColumnElement[bool]]:
    """The finished runs of the module a reset drops: the photos the list can show (not those
    of the closed locked folder), not those being turned now, with `keep_kept` not those kept
    as they are. Runs still queued or running are left alone."""
    photos = select(Asset.id).where(
        Asset.account_id == account_id, rotation.not_turning(), locked.shown()
    )
    conditions = [
        ModuleRun.module_id == MODULE_ID,
        ModuleRun.status.not_in(worker_queue.ACTIVE),
        ModuleRun.asset_id.in_(photos),
    ]
    if keep_kept:
        kept = select(AssetOrientation.asset_id).where(AssetOrientation.kept.is_(True))
        conditions.append(ModuleRun.asset_id.not_in(kept))
    return conditions


async def reset_count(db: AsyncSession, account_id: UUID, keep_kept: bool) -> int:
    """How many photos a reset would have the module look at again."""
    count = await db.scalar(
        select(func.count(func.distinct(ModuleRun.asset_id))).where(
            *_to_look_again(account_id, keep_kept)
        )
    )
    return count or 0


async def reset(db: AsyncSession, account_id: UUID, keep_kept: bool) -> int:
    """Forgets what the module found, so that the automatic runs look at the photos again (the
    answers go with their runs); returns how many photos."""
    count = await reset_count(db, account_id, keep_kept)
    await db.execute(
        delete(ModuleRun)
        .where(*_to_look_again(account_id, keep_kept))
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return count
