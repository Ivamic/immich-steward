# SPDX-License-Identifier: AGPL-3.0-or-later
"""Library overview and synchronization with Immich."""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from steward.deps import CurrentAccount, DbDep
from steward.jobs import SYNC, enqueue
from steward.models import Job
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
