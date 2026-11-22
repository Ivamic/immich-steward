# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turned photos (D-237): the photos the `orientation` module of a worker finds turned, for the
user to turn back in Immich or keep as they are. Nothing is written to Immich here."""

from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from steward import locked
from steward.config import Settings
from steward.models import Asset, AssetOrientation

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
