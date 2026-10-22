# SPDX-License-Identifier: AGPL-3.0-or-later
"""Library overview and synchronization with Immich."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from steward import embeddings, worker_queue
from steward.deps import CurrentAccount, DbDep, SettingsDep
from steward.errors import ApiError
from steward.jobs import SYNC, enqueue
from steward.models import Job, Worker
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
    sync_job: JobOut | None


class WorkerOut(BaseModel):
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


class Pause(BaseModel):
    """Paused background runs: of every module, or of some."""

    all: bool
    modules: list[str]

    @classmethod
    def of(cls, paused: set[str]) -> "Pause":
        return cls(
            all=worker_queue.ALL_MODULES in paused,
            modules=sorted(paused - {worker_queue.ALL_MODULES}),
        )


class PauseRequest(BaseModel):
    # None: every module.
    module: str | None = None
    paused: bool


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


class RerunRequest(BaseModel):
    # Failure code (`worker_queue.FAILURE_CODES`); None: every failed photo.
    code: str | None = None


class RerunResult(BaseModel):
    queued: int


class SyncRequest(BaseModel):
    # None: decided automatically (full once a day, otherwise incremental).
    full: bool | None = None


@router.get("")
async def get_library(account: CurrentAccount, db: DbDep) -> Library:
    job = await db.scalar(
        select(Job)
        .where(Job.account_id == account.id, Job.kind == SYNC)
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    return Library(
        **await library_counts(db, account),
        synced_at=account.synced_at,
        full_synced_at=account.full_synced_at,
        sync_job=JobOut.of(job) if job else None,
    )


@router.post("/sync", status_code=202)
async def start_sync(body: SyncRequest, account: CurrentAccount, db: DbDep) -> JobOut:
    job = await enqueue(db, SYNC, account.id, {"full": body.full})
    return JobOut.of(job)


@router.get("/workers")
async def get_workers(account: CurrentAccount, db: DbDep, settings: SettingsDep) -> Workers:
    """Workers known to this installation and the progress of module runs on this library."""
    since = datetime.now(UTC) - timedelta(minutes=settings.worker_active_minutes)
    workers = await db.scalars(select(Worker).order_by(Worker.last_seen_at.desc()))
    return Workers(
        workers=[
            WorkerOut(
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
    )


@router.get("/pause")
async def get_pause(account: CurrentAccount, db: DbDep) -> Pause:
    """Paused modules; the pause is for the whole installation, as the workers are."""
    return Pause.of(await worker_queue.paused_modules(db))


@router.put("/pause")
async def set_pause(body: PauseRequest, account: CurrentAccount, db: DbDep) -> Pause:
    """Pauses or resumes the background runs of a worker module, or of all of them."""
    if body.module is not None and body.module not in REMOTE_MODULES:
        raise ApiError(404, "module_not_found")
    await worker_queue.set_paused(db, body.module or worker_queue.ALL_MODULES, body.paused)
    return Pause.of(await worker_queue.paused_modules(db))


@router.delete("/pause")
async def resume_all(account: CurrentAccount, db: DbDep) -> Pause:
    """Resumes every module, whether paused one by one or all together."""
    await worker_queue.resume_all(db)
    return Pause.of(set())


@router.post("/modules/{module_id}/rerun-failed")
async def rerun_failed(
    module_id: str, body: RerunRequest, account: CurrentAccount, db: DbDep
) -> RerunResult:
    """Runs the module again on this library's photos whose latest run of it failed."""
    if module_id not in REMOTE_MODULES:
        raise ApiError(404, "module_not_found")
    return RerunResult(queued=await worker_queue.rerun_failed(db, account, module_id, body.code))
