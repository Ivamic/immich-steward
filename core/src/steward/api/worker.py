# SPDX-License-Identifier: AGPL-3.0-or-later
"""API for workers: processes that run ML modules, here or on another machine (NFR-04).

A worker authenticates with the shared token (`STEWARD_WORKER_TOKEN`), registers, then pulls jobs:
it never needs incoming connections and never sees an Immich API key. The image of a job comes
from the core, which fetches it from Immich with the key of the photo's owner.
"""

import secrets
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field

from steward import worker_queue
from steward.deps import DbDep, SecretBoxDep, SettingsDep
from steward.errors import ApiError
from steward.immich import ImmichError
from steward.immich.thumbnails import ThumbnailFetcher
from steward.models import Account, Asset, Worker

router = APIRouter(prefix="/worker")

# Bumped on incompatible changes of this API; a worker with another version is refused.
PROTOCOL_VERSION = 1
# Workers may send at most this many candidates per run.
MAX_CANDIDATES = 50


def check_token(
    settings: SettingsDep, authorization: Annotated[str | None, Header()] = None
) -> None:
    if settings.worker_token is None or not settings.worker_token.get_secret_value():
        raise ApiError(503, "workers_disabled")
    expected = f"Bearer {settings.worker_token.get_secret_value()}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise ApiError(401, "worker_unauthorized")


async def current_worker(
    db: DbDep,
    _: Annotated[None, Depends(check_token)],
    x_worker_id: Annotated[UUID | None, Header()] = None,
) -> Worker:
    worker = await db.get(Worker, x_worker_id) if x_worker_id else None
    if worker is None:
        # E.g. the core database was reset: the worker registers again.
        raise ApiError(401, "worker_unknown")
    return worker


WorkerDep = Annotated[Worker, Depends(current_worker)]


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    modules: list[str] = Field(max_length=50)
    device: str = Field(default="cpu", max_length=100)
    version: str = Field(max_length=32)
    protocol_version: int


class RegisterResponse(BaseModel):
    worker_id: UUID
    lease_seconds: int


class LeaseRequest(BaseModel):
    modules: list[str] = Field(min_length=1, max_length=50)


class LeasedJob(BaseModel):
    job_id: UUID
    module: str
    asset_id: UUID
    attempt: int
    lease_seconds: int


class CandidateIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    score: float = Field(ge=0, le=1)
    radius_m: float | None = Field(default=None, ge=0)
    kind: str = Field(default="point", max_length=32)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ResultRequest(BaseModel):
    module_version: str = Field(min_length=1, max_length=32)
    candidates: list[CandidateIn] = Field(max_length=MAX_CANDIDATES)


class FailRequest(BaseModel):
    error: str = Field(max_length=2000)
    # False when running again cannot help (e.g. the image cannot be decoded).
    retry: bool = True


@router.post("/register", dependencies=[Depends(check_token)])
async def register(body: RegisterRequest, db: DbDep, settings: SettingsDep) -> RegisterResponse:
    if body.protocol_version != PROTOCOL_VERSION:
        raise ApiError(400, "protocol_version_unsupported", supported=PROTOCOL_VERSION)
    worker = await worker_queue.register(db, body.name, body.modules, body.device, body.version)
    return RegisterResponse(worker_id=worker.id, lease_seconds=settings.worker_lease_seconds)


@router.post("/bye", status_code=204)
async def bye(worker: WorkerDep, db: DbDep) -> None:
    """The worker stops; a job it was running goes back to the queue right away."""
    await worker_queue.say_goodbye(db, worker)


@router.post("/lease", response_model=None)
async def lease(
    body: LeaseRequest, worker: WorkerDep, db: DbDep, settings: SettingsDep
) -> LeasedJob | Response:
    """The next job for the worker's modules, or 204 when there is nothing to do."""
    leased = await worker_queue.lease(db, worker, body.modules, settings.worker_lease_seconds)
    if leased is None:
        return Response(status_code=204)
    assert leased.job.module_id is not None
    return LeasedJob(
        job_id=leased.job.id,
        module=leased.job.module_id,
        asset_id=leased.run.asset_id,
        attempt=leased.job.attempts,
        lease_seconds=settings.worker_lease_seconds,
    )


@router.post("/jobs/{job_id}/heartbeat", status_code=204)
async def heartbeat(job_id: UUID, worker: WorkerDep, db: DbDep, settings: SettingsDep) -> None:
    leased = await worker_queue.leased_job(db, worker, job_id)
    await worker_queue.heartbeat(db, leased, settings.worker_lease_seconds)


@router.get("/jobs/{job_id}/image")
async def image(
    job_id: UUID, request: Request, worker: WorkerDep, db: DbDep, box: SecretBoxDep
) -> Response:
    """The preview of the job's photo (JPEG or WebP, about 1440 px on the long side)."""
    leased = await worker_queue.leased_job(db, worker, job_id)
    await db.commit()  # releases the row lock while Immich is asked
    asset = await db.get(Asset, leased.run.asset_id)
    account = await db.get(Account, asset.account_id) if asset else None
    if asset is None or account is None:
        raise ApiError(404, "asset_not_found")
    fetcher: ThumbnailFetcher = request.app.state.thumbnails
    try:
        found = await fetcher.fetch(
            box.decrypt(account.api_key_encrypted), asset.immich_id, "preview"
        )
    except ImmichError as exc:
        raise ApiError(502, "immich_error") from exc
    return Response(content=found.content, media_type=found.media_type)


@router.post("/jobs/{job_id}/result", status_code=204)
async def result(job_id: UUID, body: ResultRequest, worker: WorkerDep, db: DbDep) -> None:
    leased = await worker_queue.leased_job(db, worker, job_id)
    candidates = [c.model_dump() for c in body.candidates]
    await worker_queue.complete(db, leased, body.module_version, candidates)


@router.post("/jobs/{job_id}/fail", status_code=204)
async def fail(job_id: UUID, body: FailRequest, worker: WorkerDep, db: DbDep) -> None:
    leased = await worker_queue.leased_job(db, worker, job_id)
    await worker_queue.fail(db, leased, body.error, body.retry)
