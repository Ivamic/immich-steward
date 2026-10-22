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

from sqlalchemy import and_, case, delete, exists, func, literal, or_, select, true
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql import ColumnElement

from steward import embeddings
from steward.errors import ApiError
from steward.models import Account, Asset, Job, ModulePause, ModuleRun, Worker

MODULE_JOB = "module"
ACTIVE = ("queued", "running")

# Priorities: the user waits for a run started from the photo card.
PRIORITY_BACKGROUND = 0
PRIORITY_USER = 100

# Why a run failed (`ModuleRun.error_code`).
# The photo cannot be had from Immich: deleted, or Immich cannot make its preview.
IMAGE_UNAVAILABLE = "image_unavailable"
# Immich refused the API key of the photo's owner (revoked key, missing permission).
IMMICH_AUTH = "immich_auth"
# The worker got the photo but cannot read it.
IMAGE_INVALID = "image_invalid"
# The module failed on the photo.
MODULE_ERROR = "module_error"
# The worker failed to talk to the core about the job (e.g. the core refused its result).
WORKER_ERROR = "worker_error"
# The job never finished in time: its worker crashed, hung or went away, three times.
LEASE_EXPIRED = "lease_expired"
FAILURE_CODES = (
    IMAGE_UNAVAILABLE,
    IMMICH_AUTH,
    IMAGE_INVALID,
    MODULE_ERROR,
    WORKER_ERROR,
    LEASE_EXPIRED,
)

# Automatic runs keep at most this many background jobs per module queued: enough for a GPU
# worker (~5 photos/s) between two scheduler ticks (1 min), without queuing the whole library.
# Runs started by hand have a higher priority and never wait behind them.
AUTO_QUEUE_SIZE = 500

# `ModulePause.module_id` that pauses every module.
ALL_MODULES = "*"


@dataclass(frozen=True)
class Lease:
    job: Job
    run: ModuleRun


def whole_photo() -> ColumnElement[bool]:
    """Runs on the whole photo, as opposed to a part the user selected (FR-35).

    Only these count for the library: progress, failures, filters, automatic runs.
    """
    return ModuleRun.region.is_(None)


async def enqueue_module(
    db: AsyncSession,
    asset: Asset,
    module_id: str,
    priority: int = PRIORITY_BACKGROUND,
    region: dict[str, float] | None = None,
    turn: int = 0,
) -> ModuleRun:
    """Queues a module run unless one is already queued or running; raises its priority.

    A run on a part of the photo is separate from the runs on the whole photo; a part chosen
    anew replaces the part of a run still waiting in the queue.
    """
    active = await db.scalar(
        select(ModuleRun).where(
            ModuleRun.asset_id == asset.id,
            ModuleRun.module_id == module_id,
            ModuleRun.status.in_(ACTIVE),
            whole_photo() if region is None else ModuleRun.region.is_not(None),
        )
    )
    if active is not None and (region is None or active.status == "queued"):
        job = await db.get(Job, active.job_id) if active.job_id else None
        if job is not None and job.priority < priority:
            job.priority = priority
        active.region = region
        if active.status == "queued":
            active.turn = turn
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
    run = ModuleRun(
        asset_id=asset.id,
        module_id=module_id,
        job_id=job.id,
        status="queued",
        region=region,
        turn=turn,
    )
    db.add(run)
    await db.commit()
    return run


async def latest_runs(
    db: AsyncSession, asset_id: UUID, region: bool = False
) -> dict[str, ModuleRun]:
    """The newest run of every module for the asset: on the whole photo, or on a part of it."""
    runs = await db.scalars(
        select(ModuleRun)
        .where(
            ModuleRun.asset_id == asset_id,
            ModuleRun.region.is_not(None) if region else whole_photo(),
        )
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
        _requeue(job, await _run_of(db, job), refund=True)
    await db.commit()


async def give_back(db: AsyncSession, leased: Lease, error: str) -> None:
    """The job could not be done for a reason outside it (Immich is down): it goes back to the
    queue without using up an attempt."""
    _requeue(leased.job, leased.run, refund=True)
    leased.job.error = error
    await db.commit()


# Modules that need every photo, not only the ones without a location: the vectors of the photos
# with a location are what similar photos (M3) are searched among.
INDEXING_MODULES = ("similar",)


def _auto_eligible(module_id: str) -> tuple[ColumnElement[bool], ColumnElement[int]]:
    """Photos the module runs on automatically, and which of them go first (lower first)."""
    needs_location = and_(
        Asset.latitude.is_(None), Asset.review_status == "new", Asset.visibility == "timeline"
    )
    if module_id not in INDEXING_MODULES:
        return needs_location, literal(0)
    # The search index first, so that suggestions have something to be found among.
    located = and_(embeddings.located(), Asset.visibility.in_(("timeline", "archive")))
    return or_(located, needs_location), case((located, 0), else_=1)


async def auto_enqueue(db: AsyncSession, module_id: str) -> int:
    """Tops up the background queue of the module with photos that still need it.

    Photos without a location; for indexing modules also the photos with one, first. Photos only
    (videos later, D-040), never twice: a photo that already has a run of the module (whatever
    its result) is not queued again automatically. Accounts take turns, newest photos first
    within each, so that every user sees progress on their own library.
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
    eligible, group = _auto_eligible(module_id)
    # 1st newest photo of every account, then the 2nd of every account, and so on.
    turn = (
        func.row_number()
        .over(partition_by=(Asset.account_id, group), order_by=Asset.local_taken_at.desc())
        .label("turn")
    )
    candidates = (
        select(Asset.id, Asset.local_taken_at, group.label("grp"), turn)
        .where(
            eligible,
            Asset.type == "IMAGE",
            Asset.is_trashed.is_(False),
            ~exists().where(
                ModuleRun.asset_id == Asset.id, ModuleRun.module_id == module_id, whole_photo()
            ),
        )
        .subquery()
    )
    ids = list(
        await db.scalars(
            select(candidates.c.id)
            .order_by(candidates.c.grp, candidates.c.turn, candidates.c.local_taken_at.desc())
            .limit(room)
        )
    )
    assets = {a.id: a for a in await db.scalars(select(Asset).where(Asset.id.in_(ids)))}
    # Workers take jobs of equal priority by creation time: keep the turns in that order.
    start = datetime.now(UTC)
    count = 0
    for asset in (assets[i] for i in ids):
        job = Job(
            kind=MODULE_JOB,
            account_id=asset.account_id,
            module_id=module_id,
            priority=PRIORITY_BACKGROUND,
            payload={"asset_id": str(asset.id)},
            created_at=start + timedelta(microseconds=count),
        )
        db.add(job)
        await db.flush()
        db.add(ModuleRun(asset_id=asset.id, module_id=module_id, job_id=job.id, status="queued"))
        count += 1
    await db.commit()
    return count


async def paused_modules(db: AsyncSession) -> set[str]:
    """Modules whose background runs are paused; `ALL_MODULES` among them pauses every one."""
    return set(await db.scalars(select(ModulePause.module_id)))


def is_paused(paused: set[str], module_id: str) -> bool:
    return ALL_MODULES in paused or module_id in paused


async def set_paused(db: AsyncSession, module_id: str, paused: bool) -> None:
    """Pauses or resumes the background runs of a module (or of all, `ALL_MODULES`)."""
    row = await db.get(ModulePause, module_id)
    if paused and row is None:
        db.add(ModulePause(module_id=module_id))
    elif not paused and row is not None:
        await db.delete(row)
    await db.commit()


async def resume_all(db: AsyncSession) -> None:
    await db.execute(delete(ModulePause))
    await db.commit()


def _not_paused(paused: set[str]) -> ColumnElement[bool]:
    """Jobs a worker may take: background jobs of a paused module wait, runs by hand go."""
    if ALL_MODULES in paused:
        return Job.priority > PRIORITY_BACKGROUND
    if paused:
        return or_(Job.priority > PRIORITY_BACKGROUND, Job.module_id.not_in(paused))
    return true()


async def forget_results(db: AsyncSession, asset_ids: list[UUID]) -> None:
    """The image of these photos changed (rotated or edited in Immich): the results and vectors
    of the worker modules no longer describe it, so the photos count as never run (automatic runs
    take them again). Runs still in the queue or running are left alone."""
    await db.execute(
        delete(ModuleRun).where(ModuleRun.asset_id.in_(asset_ids), ModuleRun.status.not_in(ACTIVE))
    )


async def run_counts(db: AsyncSession, account: Account) -> dict[str, dict[str, int]]:
    """Module -> status -> number of photos of the account, by their latest run."""
    latest = (
        select(ModuleRun.module_id, ModuleRun.status)
        .join(Asset, Asset.id == ModuleRun.asset_id)
        .where(Asset.account_id == account.id, whole_photo())
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


async def failure_counts(db: AsyncSession, account: Account) -> dict[str, dict[str, int]]:
    """Module -> failure code -> number of photos of the account whose latest run failed so."""
    rows = await db.execute(
        select(ModuleRun.module_id, ModuleRun.error_code, func.count())
        .join(Asset, Asset.id == ModuleRun.asset_id)
        .where(Asset.account_id == account.id, _latest_failed())
        .group_by(ModuleRun.module_id, ModuleRun.error_code)
    )
    counts: dict[str, dict[str, int]] = {}
    for module_id, code, count in rows:
        counts.setdefault(module_id, {})[code or MODULE_ERROR] = count
    return counts


def latest_run_failed(module_id: str, code: str | None = None) -> ColumnElement[bool]:
    """For a query over assets: the asset's latest run of the module failed (with this code)."""
    conditions = [ModuleRun.asset_id == Asset.id, ModuleRun.module_id == module_id]
    if code is not None:
        conditions.append(ModuleRun.error_code == code)
    return exists().where(*conditions, _latest_failed())


def _latest_failed() -> ColumnElement[bool]:
    newer = aliased(ModuleRun)
    return and_(
        ModuleRun.status == "failed",
        whole_photo(),
        ~exists().where(
            newer.asset_id == ModuleRun.asset_id,
            newer.module_id == ModuleRun.module_id,
            newer.region.is_(None),
            newer.created_at > ModuleRun.created_at,
        ),
    )


async def rerun_failed(db: AsyncSession, account: Account, module_id: str, code: str | None) -> int:
    """Queues the module again on the account's photos whose latest run of it failed."""
    assets = list(
        await db.scalars(
            select(Asset)
            .where(Asset.account_id == account.id, latest_run_failed(module_id, code))
            .order_by(Asset.local_taken_at.desc())
        )
    )
    for asset in assets:
        await enqueue_module(db, asset, module_id)
    return len(assets)


async def register(
    db: AsyncSession,
    name: str,
    modules: list[str],
    device: str,
    version: str,
    instance_id: UUID | None = None,
    active_within: timedelta = timedelta(minutes=3),
) -> Worker:
    """Registers the worker under its name, reusing the row of an earlier start.

    Refused while another running process (another computer, say) holds the name: both would
    share one row, and stopping one would show the other as gone.
    """
    worker = await db.scalar(select(Worker).where(Worker.name == name).with_for_update())
    now = datetime.now(UTC)
    if worker is None:
        worker = Worker(name=name, registered_at=now)
        db.add(worker)
    elif (
        instance_id is not None
        and worker.instance_id is not None
        and worker.instance_id != instance_id
        and worker.online
        and worker.last_seen_at >= now - active_within
    ):
        await db.rollback()
        raise ApiError(409, "worker_name_taken", name=name)
    worker.instance_id = instance_id
    worker.modules = modules
    worker.device = device
    worker.version = version
    worker.last_seen_at = now
    worker.online = True
    await db.commit()
    return worker


async def lease(db: AsyncSession, worker: Worker, modules: list[str], lease_s: int) -> Lease | None:
    """Takes the most urgent job of the given modules, including ones whose lease ran out.

    Runs started by hand come first; then the modules in the order the worker lists them (so a
    worker short of memory can finish one module's queue before it loads the next model).
    Background jobs of paused modules stay in the queue.
    """
    module_order = case({module: i for i, module in enumerate(modules)}, value=Job.module_id)
    paused = await paused_modules(db)
    now = datetime.now(UTC)
    worker.last_seen_at = now
    worker.online = True
    while True:
        job = await db.scalar(
            select(Job)
            .where(
                Job.kind == MODULE_JOB,
                Job.module_id.in_(modules),
                _not_paused(paused),
                or_(
                    Job.status == "queued",
                    and_(Job.status == "running", Job.lease_until < now),
                ),
            )
            .order_by(Job.priority.desc(), module_order, Job.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            await db.commit()
            return None
        run = await _run_of(db, job)
        if job.attempts >= job.max_attempts:
            # Lease ran out on the last attempt: the job keeps crashing or hanging its workers.
            _finish(job, run, "failed", error=LEASE_EXPIRED, code=LEASE_EXPIRED)
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
    db: AsyncSession,
    leased: Lease,
    module_version: str,
    candidates: list[dict[str, Any]],
    embedding: list[float] | None = None,
) -> None:
    leased.run.module_version = module_version
    leased.run.candidates = candidates
    if embedding is not None:
        asset = await db.get(Asset, leased.run.asset_id)
        if asset is not None:
            await embeddings.store(db, leased.run, asset, module_version, embedding)
    _finish(leased.job, leased.run, "done")
    await db.commit()


async def fail(db: AsyncSession, leased: Lease, error: str, retry: bool, code: str) -> None:
    """Puts the job back in the queue if it may succeed later, otherwise fails it."""
    job, run = leased.job, leased.run
    if retry and job.attempts < job.max_attempts:
        _requeue(job, run, refund=False)
        job.error = error
    else:
        _finish(job, run, "failed", error=error, code=code)
    await db.commit()


async def _run_of(db: AsyncSession, job: Job) -> ModuleRun:
    run = await db.scalar(select(ModuleRun).where(ModuleRun.job_id == job.id))
    assert run is not None, f"module job {job.id} has no run"
    return run


def _requeue(job: Job, run: ModuleRun, refund: bool) -> None:
    job.status = run.status = "queued"
    job.worker_id = None
    job.lease_until = None
    if refund:
        job.attempts = max(job.attempts - 1, 0)


def _finish(
    job: Job, run: ModuleRun, status: str, error: str | None = None, code: str | None = None
) -> None:
    now = datetime.now(UTC)
    job.status = run.status = status
    job.error = run.error = error
    run.error_code = code
    job.finished_at = run.finished_at = now
    job.lease_until = None
