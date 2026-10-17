# SPDX-License-Identifier: AGPL-3.0-or-later
"""Jobs for workers: running a location module on one asset.

A worker leases a job for a while (`Settings.worker_lease_seconds`) and must report the result
or extend the lease before it ends. A job whose lease ran out goes back to the queue, so a worker
that disappears (laptop closed) delays the job but never loses it.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from steward.errors import ApiError
from steward.models import Account, Asset, Job, ModuleRun, Worker

MODULE_JOB = "module"
ACTIVE = ("queued", "running")

# Priorities: the user waits for a run started from the photo card.
PRIORITY_BACKGROUND = 0
PRIORITY_USER = 100

# Automatic runs keep at most this many background jobs per module queued: enough for a GPU
# worker (~5 photos/s) between two scheduler ticks (1 min), without queuing the whole library.
# Runs started by hand have a higher priority and never wait behind them.
AUTO_QUEUE_SIZE = 500


@dataclass(frozen=True)
class Lease:
    job: Job
    run: ModuleRun


async def enqueue_module(
    db: AsyncSession, asset: Asset, module_id: str, priority: int = PRIORITY_BACKGROUND
) -> ModuleRun:
    """Queues a module run unless one is already queued or running; raises its priority."""
    active = await db.scalar(
        select(ModuleRun).where(
            ModuleRun.asset_id == asset.id,
            ModuleRun.module_id == module_id,
            ModuleRun.status.in_(ACTIVE),
        )
    )
    if active is not None:
        job = await db.get(Job, active.job_id) if active.job_id else None
        if job is not None and job.priority < priority:
            job.priority = priority
            await db.commit()
        return active
    job = Job(
        kind=MODULE_JOB,
        account_id=asset.account_id,
        module_id=module_id,
        priority=priority,
        payload={"asset_id": str(asset.id)},
    )
    db.add(job)
    await db.flush()
    run = ModuleRun(asset_id=asset.id, module_id=module_id, job_id=job.id, status="queued")
    db.add(run)
    await db.commit()
    return run


async def latest_runs(db: AsyncSession, asset_id: UUID) -> dict[str, ModuleRun]:
    """The newest run of every module for the asset."""
    runs = await db.scalars(
        select(ModuleRun)
        .where(ModuleRun.asset_id == asset_id)
        .order_by(ModuleRun.created_at.desc())
    )
    latest: dict[str, ModuleRun] = {}
    for run in runs:
        latest.setdefault(run.module_id, run)
    return latest


async def active_workers(db: AsyncSession, within: timedelta) -> list[Worker]:
    since = datetime.now(UTC) - within
    return list(
        await db.scalars(
            select(Worker)
            .where(Worker.online.is_(True), Worker.last_seen_at >= since)
            .order_by(Worker.name)
        )
    )


async def queue_position(db: AsyncSession, run: ModuleRun) -> int | None:
    """How many jobs of the module a worker takes before this queued run (None if not queued)."""
    if run.status != "queued" or run.job_id is None:
        return None
    job = await db.get(Job, run.job_id)
    if job is None:
        return None
    ahead = await db.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.kind == MODULE_JOB,
            Job.module_id == job.module_id,
            Job.status.in_(ACTIVE),
            or_(
                Job.priority > job.priority,
                and_(Job.priority == job.priority, Job.created_at < job.created_at),
            ),
        )
    )
    return int(ahead or 0)


async def say_goodbye(db: AsyncSession, worker: Worker) -> None:
    """The worker stops: it is no longer counted as available, and a job it was running goes
    back to the queue at once (stopping is not a failure of the job)."""
    worker.online = False
    jobs = await db.scalars(
        select(Job).where(Job.worker_id == worker.id, Job.status == "running").with_for_update()
    )
    for job in jobs:
        job.status = "queued"
        job.worker_id = None
        job.lease_until = None
        job.attempts = max(job.attempts - 1, 0)
        run = await _run_of(db, job)
        run.status = "queued"
    await db.commit()


async def auto_enqueue(db: AsyncSession, module_id: str) -> int:
    """Tops up the background queue of the module with photos that still need a location.

    Photos only (videos later, D-040), newest first, never twice: a photo that already has a run
    of the module (whatever its result) is not queued again automatically.
    """
    queued = await db.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.kind == MODULE_JOB,
            Job.module_id == module_id,
            Job.status == "queued",
            Job.priority == PRIORITY_BACKGROUND,
        )
    )
    room = AUTO_QUEUE_SIZE - (queued or 0)
    if room <= 0:
        return 0
    assets = await db.scalars(
        select(Asset)
        .where(
            Asset.latitude.is_(None),
            Asset.review_status == "new",
            Asset.type == "IMAGE",
            Asset.is_trashed.is_(False),
            Asset.visibility == "timeline",
            ~exists().where(ModuleRun.asset_id == Asset.id, ModuleRun.module_id == module_id),
        )
        .order_by(Asset.local_taken_at.desc())
        .limit(room)
    )
    count = 0
    for asset in assets:
        job = Job(
            kind=MODULE_JOB,
            account_id=asset.account_id,
            module_id=module_id,
            priority=PRIORITY_BACKGROUND,
            payload={"asset_id": str(asset.id)},
        )
        db.add(job)
        await db.flush()
        db.add(ModuleRun(asset_id=asset.id, module_id=module_id, job_id=job.id, status="queued"))
        count += 1
    await db.commit()
    return count


async def run_counts(db: AsyncSession, account: Account) -> dict[str, dict[str, int]]:
    """Module -> status -> number of photos of the account, by their latest run."""
    latest = (
        select(ModuleRun.module_id, ModuleRun.status)
        .join(Asset, Asset.id == ModuleRun.asset_id)
        .where(Asset.account_id == account.id)
        .ext(distinct_on(ModuleRun.asset_id, ModuleRun.module_id))
        .order_by(ModuleRun.asset_id, ModuleRun.module_id, ModuleRun.created_at.desc())
        .subquery()
    )
    rows = await db.execute(
        select(latest.c.module_id, latest.c.status, func.count()).group_by(
            latest.c.module_id, latest.c.status
        )
    )
    counts: dict[str, dict[str, int]] = {}
    for module_id, status, count in rows:
        counts.setdefault(module_id, {})[status] = count
    return counts


async def register(
    db: AsyncSession, name: str, modules: list[str], device: str, version: str
) -> Worker:
    worker = await db.scalar(select(Worker).where(Worker.name == name))
    now = datetime.now(UTC)
    if worker is None:
        worker = Worker(name=name, registered_at=now)
        db.add(worker)
    worker.modules = modules
    worker.device = device
    worker.version = version
    worker.last_seen_at = now
    worker.online = True
    await db.commit()
    return worker


async def lease(db: AsyncSession, worker: Worker, modules: list[str], lease_s: int) -> Lease | None:
    """Takes the most urgent job of the given modules, including ones whose lease ran out."""
    now = datetime.now(UTC)
    worker.last_seen_at = now
    worker.online = True
    while True:
        job = await db.scalar(
            select(Job)
            .where(
                Job.kind == MODULE_JOB,
                Job.module_id.in_(modules),
                or_(
                    Job.status == "queued",
                    and_(Job.status == "running", Job.lease_until < now),
                ),
            )
            .order_by(Job.priority.desc(), Job.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            await db.commit()
            return None
        run = await _run_of(db, job)
        if job.attempts >= job.max_attempts:
            # Lease ran out on the last attempt: the job keeps crashing or hanging its workers.
            _finish(job, run, "failed", error="lease_expired")
            continue
        job.status = "running"
        job.attempts += 1
        job.worker_id = worker.id
        job.lease_until = now + timedelta(seconds=lease_s)
        job.started_at = job.started_at or now
        run.status = "running"
        run.worker_id = worker.id
        await db.commit()
        return Lease(job, run)


async def leased_job(db: AsyncSession, worker: Worker, job_id: UUID) -> Lease:
    """The job, if this worker still holds it; otherwise the worker must drop it."""
    job = await db.get(Job, job_id, with_for_update=True)
    if job is None or job.kind != MODULE_JOB:
        raise ApiError(404, "job_not_found")
    if job.worker_id != worker.id or job.status != "running":
        raise ApiError(409, "lease_lost")
    worker.last_seen_at = datetime.now(UTC)
    return Lease(job, await _run_of(db, job))


async def heartbeat(db: AsyncSession, leased: Lease, lease_s: int) -> None:
    leased.job.lease_until = datetime.now(UTC) + timedelta(seconds=lease_s)
    await db.commit()


async def complete(
    db: AsyncSession, leased: Lease, module_version: str, candidates: list[dict[str, Any]]
) -> None:
    leased.run.module_version = module_version
    leased.run.candidates = candidates
    _finish(leased.job, leased.run, "done")
    await db.commit()


async def fail(db: AsyncSession, leased: Lease, error: str, retry: bool) -> None:
    """Puts the job back in the queue if it may succeed later, otherwise fails it."""
    job, run = leased.job, leased.run
    if retry and job.attempts < job.max_attempts:
        job.status = "queued"
        job.worker_id = None
        job.lease_until = None
        job.error = error
        run.status = "queued"
    else:
        _finish(job, run, "failed", error=error)
    await db.commit()


async def _run_of(db: AsyncSession, job: Job) -> ModuleRun:
    run = await db.scalar(select(ModuleRun).where(ModuleRun.job_id == job.id))
    assert run is not None, f"module job {job.id} has no run"
    return run


def _finish(job: Job, run: ModuleRun, status: str, error: str | None = None) -> None:
    now = datetime.now(UTC)
    job.status = run.status = status
    job.error = run.error = error
    job.finished_at = run.finished_at = now
    job.lease_until = None
