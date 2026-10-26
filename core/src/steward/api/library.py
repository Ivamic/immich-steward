# SPDX-License-Identifier: AGPL-3.0-or-later
"""Library overview and synchronization with Immich."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from steward import __version__, embeddings, module_display, worker_queue, worker_refusals
from steward.config import Settings
from steward.deps import CurrentAccount, DbDep, SettingsDep
from steward.errors import ApiError
from steward.jobs import SYNC, enqueue
from steward.models import Account, Job, Worker
from steward.modules import REMOTE_MODULES
from steward.sync import library_counts

router = APIRouter(prefix="/library")


class JobOut(BaseModel):
    id: UUID
    kind: str
    status: str
    progress: dict[str, Any]
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def of(cls, job: Job) -> "JobOut":
        return cls(
            id=job.id,
            kind=job.kind,
            status=job.status,
            progress=job.progress,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class Library(BaseModel):
    assets: int
    videos: int
    with_gps: int
    without_gps: int
    albums: int
    synced_at: datetime | None
    full_synced_at: datetime | None
    # When the automatic syncs are due (the scheduler looks once a minute); None: they are off.
    next_sync_at: datetime | None = None
    next_full_sync_at: datetime | None = None
    sync_job: JobOut | None


class WorkerOut(BaseModel):
    id: UUID
    name: str
    device: str
    modules: list[str]
    version: str
    last_seen_at: datetime
    active: bool
    # What it says it is doing (`worker_queue.WORKER_STATES`); None for older workers.
    state: str | None
    state_module: str | None
    state_since: datetime | None


class RefusedWorkerOut(BaseModel):
    """A worker the core did not take: `worker_too_old` (update the worker) or `core_too_old`
    (update the server)."""

    name: str
    version: str
    reason: str
    at: datetime


class Pause(BaseModel):
    """Paused background runs: of every module, or of some."""

    all: bool
    modules: list[str]
    # When the pause of all modules, or of a module, ends by itself; absent: until resumed.
    all_until: datetime | None = None
    until: dict[str, datetime] = {}

    @classmethod
    def of(cls, paused: dict[str, datetime | None]) -> "Pause":
        modules = {m: until for m, until in paused.items() if m != worker_queue.ALL_MODULES}
        return cls(
            all=worker_queue.ALL_MODULES in paused,
            all_until=paused.get(worker_queue.ALL_MODULES),
            modules=sorted(modules),
            until={m: until for m, until in modules.items() if until is not None},
        )


class PauseRequest(BaseModel):
    # None: every module.
    module: str | None = None
    paused: bool
    # A pause for so many minutes (up to a week); None: until resumed.
    minutes: int | None = Field(default=None, ge=1, le=7 * 24 * 60)


class ModuleOut(BaseModel):
    id: str
    color: str
    shape: str


class Workers(BaseModel):
    workers: list[WorkerOut]
    # Every module workers can run, in the order they are shown.
    modules: list[ModuleOut]
    # Module -> status of the latest run -> number of photos of this account.
    runs: dict[str, dict[str, int]]
    # Module -> failure code -> photos whose latest run failed so.
    failures: dict[str, dict[str, int]]
    auto_modules: list[str]
    # Indexing module -> {"indexed", "located"}: photos with a location in its search index.
    index: dict[str, dict[str, int]]
    pause: Pause
    # Workers refused lately because one side is too old for the other.
    refused: list[RefusedWorkerOut]
    # Version of this core: an active worker with an older one can be updated.
    core_version: str


class RerunRequest(BaseModel):
    # Failure code (`worker_queue.FAILURE_CODES`); None: every failed photo.
    code: str | None = None


class RerunResult(BaseModel):
    queued: int


class SyncRequest(BaseModel):
    # None: decided automatically (full once a day, otherwise incremental).
    full: bool | None = None


def next_syncs(account: Account, settings: Settings) -> tuple[datetime | None, datetime | None]:
    """When the next automatic sync and the next full one are due (`JobRunner.schedule_syncs`).

    A due time in the past means the sync is waiting for the scheduler or already running.
    """
    if not settings.run_jobs or settings.sync_interval_minutes <= 0:
        return None, None
    now = datetime.now(UTC)
    if account.synced_at is None:
        return now, now
    next_sync = account.synced_at + timedelta(minutes=settings.sync_interval_minutes)
    if account.full_synced_at is None:
        return next_sync, next_sync
    # An automatic sync becomes full once the full one is old enough.
    full_due = account.full_synced_at + timedelta(hours=settings.full_sync_interval_hours)
    return next_sync, max(next_sync, full_due)


@router.get("")
async def get_library(account: CurrentAccount, db: DbDep, settings: SettingsDep) -> Library:
    job = await db.scalar(
        select(Job)
        .where(Job.account_id == account.id, Job.kind == SYNC)
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    next_sync_at, next_full_sync_at = next_syncs(account, settings)
    return Library(
        **await library_counts(db, account),
        synced_at=account.synced_at,
        full_synced_at=account.full_synced_at,
        next_sync_at=next_sync_at,
        next_full_sync_at=next_full_sync_at,
        sync_job=JobOut.of(job) if job else None,
    )


@router.post("/sync", status_code=202)
async def start_sync(body: SyncRequest, account: CurrentAccount, db: DbDep) -> JobOut:
    job = await enqueue(db, SYNC, account.id, {"full": body.full})
    return JobOut.of(job)


@router.get("/workers")
async def get_workers(
    account: CurrentAccount, db: DbDep, settings: SettingsDep, request: Request
) -> Workers:
    """Workers known to this installation and the progress of module runs on this library."""
    refusals: worker_refusals.WorkerRefusals = request.app.state.worker_refusals
    since = datetime.now(UTC) - timedelta(minutes=settings.worker_active_minutes)
    workers = await db.scalars(select(Worker).order_by(Worker.last_seen_at.desc()))
    return Workers(
        workers=[
            WorkerOut(
                id=w.id,
                name=w.name,
                device=w.device,
                modules=w.modules,
                version=w.version,
                last_seen_at=w.last_seen_at,
                active=(active := w.online and w.last_seen_at >= since),
                state=w.state if active else None,
                state_module=w.state_module if active else None,
                state_since=w.state_since if active else None,
            )
            for w in workers
        ],
        modules=[ModuleOut(id=m.id, color=m.color, shape=m.shape) for m in REMOTE_MODULES.values()],
        runs=await worker_queue.run_counts(db, account),
        failures=await worker_queue.failure_counts(db, account),
        auto_modules=settings.auto_module_ids,
        index={
            module_id: await embeddings.index_counts(db, account, module_id)
            for module_id in worker_queue.INDEXING_MODULES
        },
        pause=Pause.of(await worker_queue.paused_modules(db)),
        refused=[
            RefusedWorkerOut(name=r.name, version=r.version, reason=r.reason, at=r.at)
            for r in refusals.recent(timedelta(minutes=settings.worker_active_minutes))
        ],
        core_version=__version__,
    )


@router.delete("/workers/{worker_id}", status_code=204)
async def forget_worker(
    worker_id: UUID, account: CurrentAccount, db: DbDep, settings: SettingsDep
) -> None:
    """Removes a worker that is not connected from the list; if it comes back, it registers
    anew. Workers not seen for 30 days are removed by themselves."""
    worker = await db.get(Worker, worker_id)
    if worker is None:
        raise ApiError(404, "worker_not_found")
    since = datetime.now(UTC) - timedelta(minutes=settings.worker_active_minutes)
    if worker.online and worker.last_seen_at >= since:
        raise ApiError(409, "worker_active")
    await worker_queue.forget_worker(db, worker)


@router.get("/pause")
async def get_pause(account: CurrentAccount, db: DbDep) -> Pause:
    """Paused modules; the pause is for the whole installation, as the workers are."""
    return Pause.of(await worker_queue.paused_modules(db))


@router.put("/pause")
async def set_pause(body: PauseRequest, account: CurrentAccount, db: DbDep) -> Pause:
    """Pauses or resumes the background runs of a worker module, or of all of them."""
    if body.module is not None and body.module not in REMOTE_MODULES:
        raise ApiError(404, "module_not_found")
    await worker_queue.set_paused(
        db, body.module or worker_queue.ALL_MODULES, body.paused, body.minutes
    )
    return Pause.of(await worker_queue.paused_modules(db))


@router.delete("/pause")
async def resume_all(account: CurrentAccount, db: DbDep) -> Pause:
    """Resumes every module, whether paused one by one or all together."""
    await worker_queue.resume_all(db)
    return Pause.of({})


class ModuleDisplayItem(BaseModel):
    module: str
    hidden: bool = False


@router.get("/module-display")
async def get_module_display(account: CurrentAccount, db: DbDep) -> list[ModuleDisplayItem]:
    """The order of the modules in the photo card of this account and the hidden ones."""
    return [ModuleDisplayItem(**vars(d)) for d in await module_display.get(db, account.id)]


@router.put("/module-display")
async def set_module_display(
    body: list[ModuleDisplayItem], account: CurrentAccount, db: DbDep
) -> list[ModuleDisplayItem]:
    """Stores the order (every module once, first shown first) and which modules are hidden."""
    displays = [module_display.Display(item.module, item.hidden) for item in body]
    saved = await module_display.save(db, account.id, displays)
    return [ModuleDisplayItem(**vars(d)) for d in saved]


@router.post("/modules/{module_id}/rerun-failed")
async def rerun_failed(
    module_id: str, body: RerunRequest, account: CurrentAccount, db: DbDep
) -> RerunResult:
    """Runs the module again on this library's photos whose latest run of it failed."""
    if module_id not in REMOTE_MODULES:
        raise ApiError(404, "module_not_found")
    return RerunResult(queued=await worker_queue.rerun_failed(db, account, module_id, body.code))
