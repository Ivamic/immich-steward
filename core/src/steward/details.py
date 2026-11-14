# SPDX-License-Identifier: AGPL-3.0-or-later
"""Matching details: which photos a photo is compared with (D-225).

"Similar photos" finds the photos that look like the photo; the `details` module of a worker then
compares the photo with the most similar of them point by point. The answers are kept per pair
(`DetailMatch`) and confirm the suggestions when they are shown (`modules.similar.candidates`).
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from steward import account_settings, worker_queue
from steward.config import Settings
from steward.models import Asset, Job, ModuleRun
from steward.modules import similar

MODULE_ID = "details"
# Background comparisons waiting in the queue at most, and queued in one pass (each needs a search
# of the similar photos).
AUTO_QUEUE_SIZE = 100
AUTO_BATCH = 50


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


async def auto_enqueue(db: AsyncSession, settings: Settings) -> int:
    """Tops up the background queue with photos that still wait for their comparison: photos
    without a location that have their similar photos found, newest first, once each.

    A photo with nothing to compare with gets an empty finished run, so that it is not looked at
    again at every pass. Later it is compared only when asked by hand.
    """
    queued = await db.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.kind == worker_queue.MODULE_JOB,
            Job.module_id == MODULE_ID,
            Job.status == "queued",
            Job.priority == worker_queue.PRIORITY_BACKGROUND,
        )
    )
    room = min(AUTO_QUEUE_SIZE - (queued or 0), AUTO_BATCH)
    if room <= 0:
        return 0

    def has_run(module_id: str, *conditions: object) -> object:
        return exists().where(
            ModuleRun.asset_id == Asset.id,
            ModuleRun.module_id == module_id,
            worker_queue.whole_photo(),
            *conditions,  # type: ignore[arg-type]
        )

    assets = list(
        await db.scalars(
            select(Asset)
            .where(
                Asset.latitude.is_(None),
                Asset.review_status == "new",
                Asset.visibility.in_(("timeline", "locked")),
                Asset.type == "IMAGE",
                Asset.is_trashed.is_(False),
                has_run(similar.MODULE_ID, ModuleRun.status == "done"),  # type: ignore[arg-type]
                ~has_run(MODULE_ID),  # type: ignore[operator]
            )
            .order_by(Asset.local_taken_at.desc())
            .limit(room)
        )
    )
    limits: dict[UUID, int] = {}
    count = 0
    for asset in assets:
        if asset.account_id not in limits:
            personal = await account_settings.get_all(db, asset.account_id)
            limits[asset.account_id] = personal["details_candidates_auto"]
        if await enqueue(db, asset, settings, limits[asset.account_id]) is None:
            now = datetime.now(UTC)
            db.add(
                ModuleRun(asset_id=asset.id, module_id=MODULE_ID, status="done", finished_at=now)
            )
            await db.commit()
        else:
            count += 1
    return count
