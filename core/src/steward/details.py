# SPDX-License-Identifier: AGPL-3.0-or-later
"""Matching details: which photos a photo is compared with (D-225).

"Similar photos" finds the photos that look like the photo; the `details` module of a worker then
compares the photo with the most similar of them point by point. The answers are kept per pair
(`DetailMatch`) and confirm the suggestions when they are shown (`modules.similar.candidates`).
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from steward import worker_queue
from steward.config import Settings
from steward.models import Asset, ModuleRun
from steward.modules import similar

MODULE_ID = "details"


async def targets(
    db: AsyncSession, run: ModuleRun, account_id: UUID, settings: Settings, limit: int
) -> list[UUID]:
    """The photos to compare the photo of a similar-photos run with: of its `limit` most similar
    photos with a location, those it was not compared with yet; most similar first."""
    found = await similar.neighbors(db, run, account_id, settings.similar_include_estimated)
    nearest = [n.asset_id for n in found[:limit]]
    compared = await similar.detail_inliers(db, run.asset_id, nearest)
    return [asset_id for asset_id in nearest if asset_id not in compared]


async def enqueue(
    db: AsyncSession,
    asset: Asset,
    settings: Settings,
    limit: int,
    priority: int = worker_queue.PRIORITY_BACKGROUND,
) -> ModuleRun | None:
    """Queues the comparison of the photo with its most similar photos; None when there is
    nothing to compare it with (no vector of the photo yet, no similar photos with a location,
    or all of them compared already)."""
    run = (await worker_queue.latest_runs(db, asset.id)).get(similar.MODULE_ID)
    if run is None or run.status != "done":
        return None
    others = await targets(db, run, asset.account_id, settings, limit)
    if not others:
        return None
    return await worker_queue.enqueue_pairs(db, asset, MODULE_ID, others, priority)
