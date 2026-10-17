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

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from steward.errors import ApiError
from steward.models import Asset, Job, ModuleRun, Worker

MODULE_JOB = "module"
ACTIVE = ("queued", "running")

# Priorities: the user waits for a run started from the photo card.
PRIORITY_BACKGROUND = 0
PRIORITY_USER = 100


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
    await db.commit()
    return worker


async def lease(db: AsyncSession, worker: Worker, modules: list[str], lease_s: int) -> Lease | None:
    """Takes the most urgent job of the given modules, including ones whose lease ran out."""
    now = datetime.now(UTC)
    worker.last_seen_at = now
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
