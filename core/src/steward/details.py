# SPDX-License-Identifier: AGPL-3.0-or-later
"""Matching details: which photos a photo is compared with (D-225).

"Similar photos" finds the photos that look like the photo; the `details` module of a worker then
compares the photo with the most similar of them point by point. The answers are kept per pair
(`DetailMatch`) and confirm the suggestions when they are shown (`modules.similar.candidates`).
"""

from datetime import UTC, datetime, timedelta
from typing import Any
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
# A photo not confirmed is looked at again this long after its last comparison: photos that got
# a location since may be similar to it now.
RECHECK_EVERY = timedelta(days=1)


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


async def rerun_failed(
    db: AsyncSession, account_id: UUID, settings: Settings, code: str | None
) -> int:
    """Queues again the comparisons of the account's photos whose latest one failed, each with
    the photos it is to be compared with now."""
    assets = list(
        await db.scalars(
            select(Asset)
            .where(Asset.account_id == account_id, worker_queue.latest_run_failed(MODULE_ID, code))
            .order_by(Asset.local_taken_at.desc())
        )
    )
    personal = await account_settings.get_all(db, account_id)
    count = 0
    for asset in assets:
        if await enqueue(db, asset, settings, personal["details_candidates_auto"]) is not None:
            count += 1
    return count


async def auto_enqueue(db: AsyncSession, settings: Settings) -> int:
    """Tops up the background queue with photos without a location that have their similar
    photos found: first those never compared, newest first; then those compared more than
    `RECHECK_EVERY` ago and not confirmed, the longest ago first.

    The second look is for what changed since: photos that got a location and are now similar to
    the photo, and the rest of the most similar ones after a comparison started by hand, which
    takes fewer. A photo with nothing left to compare with is noted as looked at now (an empty
    finished run when it has none), so that it is not looked at again at every pass.
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

    def has_run(module_id: str, *conditions: Any) -> Any:
        return exists().where(
            ModuleRun.asset_id == Asset.id,
            ModuleRun.module_id == module_id,
            worker_queue.whole_photo(),
            *conditions,
        )

    waiting = (
        Asset.latitude.is_(None),
        Asset.review_status == "new",
        Asset.visibility.in_(("timeline", "locked")),
        Asset.type == "IMAGE",
        Asset.is_trashed.is_(False),
        has_run(similar.MODULE_ID, ModuleRun.status == "done"),
    )
    never = list(
        await db.scalars(
            select(Asset)
            .where(*waiting, ~has_run(MODULE_ID))
            .order_by(Asset.local_taken_at.desc())
            .limit(room)
        )
    )
    again: list[Asset] = []
    if len(never) < room:
        cutoff = datetime.now(UTC) - RECHECK_EVERY
        # Looked at last: the latest run of the module, finished or (for one that never
        # finished) made.
        looked_at = (
            select(func.max(func.coalesce(ModuleRun.finished_at, ModuleRun.created_at)))
            .where(
                ModuleRun.asset_id == Asset.id,
                ModuleRun.module_id == MODULE_ID,
                worker_queue.whole_photo(),
            )
            .correlate(Asset)
            .scalar_subquery()
        )
        again = list(
            await db.scalars(
                select(Asset)
                .where(
                    *waiting,
                    ~has_run(MODULE_ID, ModuleRun.status.in_(worker_queue.ACTIVE)),
                    looked_at < cutoff,
                )
                .order_by(looked_at)
                .limit(room - len(never))
            )
        )

    personal: dict[UUID, dict[str, Any]] = {}
    count = 0
    for asset in [*never, *again]:
        if asset.account_id not in personal:
            personal[asset.account_id] = await account_settings.get_all(db, asset.account_id)
        mine = personal[asset.account_id]
        confirmed = await is_confirmed(db, asset, settings, mine["details_confirmed_from"])
        queued_run = (
            None
            if confirmed
            else await enqueue(db, asset, settings, mine["details_candidates_auto"])
        )
        if queued_run is not None:
            count += 1
            continue
        # Nothing to do for it now: noted, so that it waits a day for the next look.
        now = datetime.now(UTC)
        latest = (await worker_queue.latest_runs(db, asset.id)).get(MODULE_ID)
        if latest is None:
            db.add(
                ModuleRun(asset_id=asset.id, module_id=MODULE_ID, status="done", finished_at=now)
            )
        else:
            latest.finished_at = now
        await db.commit()
    return count


async def is_confirmed(
    db: AsyncSession, asset: Asset, settings: Settings, confirmed_from: int
) -> bool:
    """One of the photos similar to the photo shares enough details with it already: comparing
    it with more of them would change nothing."""
    run = (await worker_queue.latest_runs(db, asset.id)).get(similar.MODULE_ID)
    if run is None or run.status != "done":
        return False
    found = await similar.neighbors(db, run, asset.account_id, settings.similar_include_estimated)
    shared = await similar.detail_inliers(db, asset.id, [n.asset_id for n in found])
    return any(count >= confirmed_from for count in shared.values())
