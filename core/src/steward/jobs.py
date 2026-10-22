# SPDX-License-Identifier: AGPL-3.0-or-later
"""Background jobs stored in PostgreSQL and executed inside the core process.

Jobs of workers (ML modules) live in the same table but are leased through the worker API
(steward.worker_queue); the runner here only takes the kinds it has handlers for.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from steward import worker_queue
from steward.config import Settings
from steward.crypto import SecretBox
from steward.deps import ImmichClientFactory
from steward.immich import ImmichAuthError, ImmichPermissionError, ImmichUnreachableError
from steward.models import Account, Job
from steward.sync import sync_account

log = logging.getLogger(__name__)

SYNC = "sync"
ACTIVE_STATUSES = ("queued", "running")
IDLE_POLL_S = 2.0
SCHEDULE_EVERY_S = 60.0


async def enqueue(
    db: AsyncSession, kind: str, account_id: UUID | None, payload: dict[str, Any] | None = None
) -> Job:
    """Adds a job unless one of the same kind is already queued or running for the account."""
    existing = await db.scalar(
        select(Job).where(
            Job.kind == kind, Job.account_id == account_id, Job.status.in_(ACTIVE_STATUSES)
        )
    )
    if existing is not None:
        return existing
    job = Job(kind=kind, account_id=account_id, payload=payload or {})
    db.add(job)
    await db.commit()
    return job


@dataclass
class JobContext:
    job: Job
    db: AsyncSession
    settings: Settings
    immich_factory: ImmichClientFactory
    report: Callable[[dict[str, Any]], Awaitable[None]]


JobHandler = Callable[[JobContext], Awaitable[dict[str, Any]]]


async def run_sync(ctx: JobContext) -> dict[str, Any]:
    settings = ctx.settings
    if settings.immich_url is None or settings.secret_key is None:
        raise JobError("server_not_configured")
    account = await ctx.db.get(Account, ctx.job.account_id)
    if account is None:
        raise JobError("account_not_found")
    full = ctx.job.payload.get("full")
    if full is None:  # automatic: a full sync once per `full_sync_interval_hours`
        due = datetime.now(UTC) - timedelta(hours=settings.full_sync_interval_hours)
        full = account.full_synced_at is None or account.full_synced_at < due
    api_key = SecretBox(settings.secret_key.get_secret_value()).decrypt(account.api_key_encrypted)
    try:
        async with ctx.immich_factory(settings.immich_url, api_key) as client:
            stats = await sync_account(
                ctx.db, client, account, full=bool(full), on_progress=ctx.report
            )
    except ImmichAuthError as exc:
        raise JobError("immich_invalid_api_key") from exc
    except ImmichPermissionError as exc:
        raise JobError("immich_missing_permissions") from exc
    except ImmichUnreachableError as exc:
        raise JobError("immich_unreachable") from exc
    return stats.as_dict()


class JobError(Exception):
    """Expected failure; the message is an error code shown (translated) in the UI."""


HANDLERS: dict[str, JobHandler] = {SYNC: run_sync}


class JobRunner:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        settings: Settings,
        immich_factory: ImmichClientFactory,
        handlers: dict[str, JobHandler] | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._settings = settings
        self._immich_factory = immich_factory
        self._handlers = handlers or HANDLERS

    async def recover(self) -> None:
        """Jobs left running by a crashed or restarted process are queued again."""
        async with self._sessionmaker() as db:
            await db.execute(
                update(Job)
                .where(Job.status == "running", Job.kind.in_(self._handlers))
                .values(status="queued", started_at=None)
            )
            await db.commit()

    async def schedule_syncs(self) -> None:
        """Queues an automatic sync for every account whose last sync is older than the interval."""
        interval = self._settings.sync_interval_minutes
        if interval <= 0:
            return
        due = datetime.now(UTC) - timedelta(minutes=interval)
        async with self._sessionmaker() as db:
            accounts = await db.scalars(
                select(Account.id).where(or_(Account.synced_at.is_(None), Account.synced_at < due))
            )
            for account_id in list(accounts):
                await enqueue(db, SYNC, account_id, {"full": None})

    async def schedule_modules(self) -> None:
        """Feeds photos without a location to worker modules that run automatically.

        Only while a worker of the module is active (without one the queue would just grow) and
        the module is not paused.
        """
        modules = self._settings.auto_module_ids
        if not modules:
            return
        within = timedelta(minutes=self._settings.worker_active_minutes)
        async with self._sessionmaker() as db:
            workers = await worker_queue.active_workers(db, within)
            active = {module for worker in workers for module in worker.modules}
            paused = await worker_queue.paused_modules(db)
            for module_id in modules:
                if module_id in active and not worker_queue.is_paused(paused, module_id):
                    added = await worker_queue.auto_enqueue(db, module_id)
                    if added:
                        log.info("queued %d photos for %s", added, module_id)

    async def forget_old_workers(self) -> None:
        async with self._sessionmaker() as db:
            if forgotten := await worker_queue.forget_old_workers(db):
                log.info("forgot %d workers not seen for 30 days", forgotten)

    async def run_once(self) -> bool:
        """Claims and runs the oldest queued job. Returns False when the queue is empty."""
        async with self._sessionmaker() as db:
            job = await db.scalar(
                select(Job)
                .where(Job.status == "queued", Job.kind.in_(self._handlers))
                .order_by(Job.priority.desc(), Job.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return False
            job.status = "running"
            job.started_at = datetime.now(UTC)
            await db.commit()
            await self._execute(db, job)
        return True

    async def _execute(self, db: AsyncSession, job: Job) -> None:
        async def report(progress: dict[str, Any]) -> None:
            async with self._sessionmaker() as progress_db:
                await progress_db.execute(
                    update(Job).where(Job.id == job.id).values(progress=progress)
                )
                await progress_db.commit()

        job_id, kind = job.id, job.kind
        handler = self._handlers.get(kind)
        result: dict[str, Any] = {"status": "done"}
        try:
            if handler is None:
                raise JobError("unknown_job_kind")
            ctx = JobContext(job, db, self._settings, self._immich_factory, report)
            result["progress"] = await handler(ctx)
        except JobError as exc:
            await db.rollback()
            result = {"status": "failed", "error": str(exc)}
        except Exception as exc:
            log.exception("job %s (%s) failed", job_id, kind)
            await db.rollback()
            result = {"status": "failed", "error": f"internal_error: {type(exc).__name__}"}
        # An explicit UPDATE: after a rollback the ORM object is expired.
        await db.execute(
            update(Job).where(Job.id == job_id).values(finished_at=datetime.now(UTC), **result)
        )
        await db.commit()

    async def run_forever(self, stop: asyncio.Event) -> None:
        recovered = False
        next_schedule = 0.0
        loop = asyncio.get_running_loop()
        while not stop.is_set():
            try:
                if not recovered:
                    await self.recover()
                    recovered = True
                if loop.time() >= next_schedule:
                    await self.schedule_syncs()
                    await self.schedule_modules()
                    await self.forget_old_workers()
                    next_schedule = loop.time() + SCHEDULE_EVERY_S
                if await self.run_once():
                    continue
            except Exception:
                log.exception("job runner iteration failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=IDLE_POLL_S)
