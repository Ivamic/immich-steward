# SPDX-License-Identifier: AGPL-3.0-or-later
"""The badge "similar with a location" of the gallery (0.7.0): for each photo without a location
that has a vector, how similar the most similar photo with a location is.

The search is that of similar photos (`modules.similar.search`), but done ahead, in the
background: the gallery shows hundreds of photos at once and cannot search for each. A full pass
runs once a day and on request (new locations make other photos similar to a located one); in
between, photos whose vector is newer than their hint are done within a minute.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, delete, exists, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from steward.config import Settings
from steward.embeddings import located
from steward.models import Asset, Embedding, SimilarHint
from steward.modules import similar

# Photos per transaction: the progress shows, and a restart loses little.
BATCH = 100


def _due(account_id: UUID, full: bool) -> Select[UUID]:
    """Photos without a location with a vector of the whole photo; unless `full`, only those
    whose vector is newer than their hint (or that have none)."""
    query = (
        select(Embedding.asset_id)
        .join(Asset, Asset.id == Embedding.asset_id)
        .where(
            Embedding.account_id == account_id,
            Embedding.module_id == similar.MODULE_ID,
            Embedding.region.is_(False),
            ~located(),
        )
        .order_by(Embedding.asset_id)
    )
    if not full:
        query = query.outerjoin(SimilarHint, SimilarHint.asset_id == Embedding.asset_id).where(
            or_(SimilarHint.asset_id.is_(None), SimilarHint.computed_at < Embedding.created_at)
        )
    return query


async def any_due(db: AsyncSession, account_id: UUID) -> bool:
    """Whether some photo waits for its hint (new vectors since the last pass)."""
    return bool(await db.scalar(select(exists(_due(account_id, full=False).subquery()))))


async def refresh(
    db: AsyncSession,
    account_id: UUID,
    settings: Settings,
    *,
    full: bool,
    on_progress: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Computes the hints of the due photos (`_due`); a full pass also drops the hints of the
    photos that got a location since."""
    if full:
        await db.execute(
            delete(SimilarHint).where(
                SimilarHint.account_id == account_id,
                SimilarHint.asset_id.in_(select(Asset.id).where(located())),
            )
        )
        await db.commit()
    due = list(await db.scalars(_due(account_id, full)))
    total, confident_count = len(due), 0
    for start in range(0, total, BATCH):
        # Vectors are large (8448 numbers): a batch at a time, not the whole library.
        rows = await db.execute(
            select(Embedding.asset_id, Embedding.vector).where(
                Embedding.asset_id.in_(due[start : start + BATCH]),
                Embedding.module_id == similar.MODULE_ID,
                Embedding.region.is_(False),
            )
        )
        for asset_id, vector in rows:
            found = await similar.search(
                db, vector, account_id, asset_id, settings.similar_include_estimated, limit=1
            )
            if not found:
                await db.execute(delete(SimilarHint).where(SimilarHint.asset_id == asset_id))
                continue
            best = found[0]
            score = round(similar.calibrated(best.similarity), 4)
            confident_count += score >= settings.similar_confident_from
            values = {
                "similarity": best.similarity,
                "score": score,
                "neighbor_id": best.asset_id,
                "computed_at": datetime.now(UTC),
            }
            await db.execute(
                insert(SimilarHint)
                .values(asset_id=asset_id, account_id=account_id, **values)
                .on_conflict_do_update(index_elements=[SimilarHint.asset_id], set_=values)
            )
        await db.commit()
        if on_progress is not None:
            await on_progress({"done": min(start + BATCH, total), "total": total})
    return {"full": full, "photos": total, "confident": confident_count}
