# SPDX-License-Identifier: AGPL-3.0-or-later
"""Backups of what the users decided (`steward.backup`, D-252): the nightly one and its settings,
for the whole installation (until there are roles, any account may change them), and a download
at any time."""

from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from steward import backup
from steward.deps import CurrentAccount, DbDep, SettingsDep
from steward.schedule import server_zone

router = APIRouter(prefix="/backups")


class BackupsOut(BaseModel):
    enabled: bool
    hour: int
    keep_daily: int
    keep_weekly: int
    # The folder for the nightly backups is there (mounted) and writable; the path the app looks
    # at, to show in the instructions when it is not.
    folder_ready: bool
    folder: str | None
    # Why it is not ready: "missing" or "not_writable".
    folder_problem: str | None
    # The time zone of the server's clock the hour is in, when known.
    time_zone: str | None
    last_at: datetime | None
    last_file: str | None
    last_size: int | None
    # "no_folder", or the kind of error of the last attempt.
    error: str | None
    error_at: datetime | None


class BackupsIn(BaseModel):
    enabled: bool | None = None
    hour: int | None = Field(default=None, ge=0, le=23)
    keep_daily: int | None = Field(default=None, ge=1, le=60)
    keep_weekly: int | None = Field(default=None, ge=0, le=52)


def _out(state: backup.BackupState, settings: SettingsDep) -> BackupsOut:
    return BackupsOut(
        enabled=state.enabled,
        hour=state.hour,
        keep_daily=state.keep_daily,
        keep_weekly=state.keep_weekly,
        folder_ready=backup.folder(settings.backup_dir) is not None,
        folder_problem=backup.folder_problem(settings.backup_dir),
        folder=str(settings.backup_dir) if settings.backup_dir else None,
        time_zone=server_zone()[1],
        last_at=state.last_at,
        last_file=state.last_file,
        last_size=state.last_size,
        error=state.error,
        error_at=state.error_at,
    )


@router.get("")
async def get_backups(_: CurrentAccount, db: DbDep, settings: SettingsDep) -> BackupsOut:
    return _out(await backup.load(db), settings)


@router.put("")
async def set_backups(
    body: BackupsIn, _: CurrentAccount, db: DbDep, settings: SettingsDep
) -> BackupsOut:
    state = await backup.load(db)
    for name, value in body.model_dump(exclude_none=True).items():
        setattr(state, name, value)
    await backup.save(db, state)
    return _out(state, settings)


@router.post("/run")
async def run_now(_: CurrentAccount, db: DbDep, settings: SettingsDep) -> BackupsOut:
    """Writes a backup into the folder now, also while the nightly one is off."""
    return _out(await backup.run_now(db, settings.backup_dir), settings)


@router.get("/download")
async def download(_: CurrentAccount, db: DbDep) -> Response:
    """A backup made now, as a file to save (it holds the places of the photos of all accounts)."""
    raw = backup.encode(await backup.export(db))
    name = backup.file_name(backup.local_now())
    return Response(
        raw,
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )
