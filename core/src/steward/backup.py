# SPDX-License-Identifier: AGPL-3.0-or-later
"""Backups of what the users decided (D-249, D-252).

The database of the app is more and more the only place some data lives in: the history of the
locations written (behind undo), the directions, the marks, the groups and folders, the settings.
A backup keeps only that; what the modules compute (vectors, answers, comparisons) is computed
again after a restore, which takes hours but loses nothing.

One format for both: a gzipped JSON file. The photos in it are named by their Immich id, not by
the ids of this database, so that a backup goes into a new installation too. Secrets (API keys of
map and street sources) stay encrypted as they are in the database: they open only with the same
`STEWARD_SECRET_KEY`.

- Every night the core writes one into `STEWARD_BACKUP_DIR` (`/backups`, a folder of the host
  mounted into the container), when that folder is there; it keeps the last days and weeks.
- A user downloads one at any time from Settings.
- A restore is a command (`python -m steward.backup restore FILE`), run after the first sync of
  the accounts. It adds what is missing and leaves what is there: running it again is harmless,
  and is how the marks waiting for the modules (a photo kept as it is turned) get in later.
"""

import argparse
import asyncio
import gzip
import json
import logging
import os
import re
import sys
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from steward import __version__
from steward.models import (
    Account,
    AccountSetting,
    AppSetting,
    Asset,
    AssetDirection,
    AssetOrientation,
    LocationChange,
    MapAuto,
    MapSourceSetting,
    MapTileUsage,
    ModuleDisplay,
    ModulePause,
    StreetSourceSetting,
    ViewFolder,
    ViewGroup,
    ViewGroupMember,
    ViewPhotoKeep,
    ViewPhotoTrash,
    Worker,
)
from steward.schedule import server_zone
from steward.view_groups import ADDED, EXCLUDED

log = logging.getLogger(__name__)

FORMAT = "immich-steward-backup"
FORMAT_VERSION = 1
KEY = "backups"
# backup-2026-11-28-0300.json.gz: the time of the server's clock it was made at.
FILE_PATTERN = re.compile(r"^steward-backup-(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})\.json\.gz$")
RETRY_AFTER_ERROR = timedelta(hours=1)
# Settings of the installation that are no decision: state of the app itself.
APP_KEYS_LEFT_OUT = {KEY}


# --- Settings and state --------------------------------------------------------------------------


@dataclass
class BackupState:
    """The nightly backup: its settings and how the last one went. For the whole installation."""

    enabled: bool = True
    # Hour of the server's clock it is made at, or the first check after it.
    hour: int = 3
    # Backups kept: the newest of each of the last days, and of each of the last weeks.
    keep_daily: int = 7
    keep_weekly: int = 4
    last_at: datetime | None = None
    last_file: str | None = None
    last_size: int | None = None
    # When the last attempt failed and why; None after a good one.
    error: str | None = None
    error_at: datetime | None = None


SETTING_FIELDS = ("enabled", "hour", "keep_daily", "keep_weekly")


async def load(db: AsyncSession) -> BackupState:
    row = await db.get(AppSetting, KEY)
    if row is None:
        return BackupState()
    value = dict(row.value)
    for name in ("last_at", "error_at"):
        if value.get(name):
            value[name] = datetime.fromisoformat(value[name])
    known = {f for f in BackupState.__dataclass_fields__}
    return BackupState(**{k: v for k, v in value.items() if k in known})


async def save(db: AsyncSession, state: BackupState) -> None:
    value = {k: v.isoformat() if isinstance(v, datetime) else v for k, v in asdict(state).items()}
    row = await db.get(AppSetting, KEY)
    if row is None:
        db.add(AppSetting(key=KEY, value=value))
    else:
        row.value = value
    await db.commit()


def folder_problem(backup_dir: Path | None) -> str | None:
    """Why there are no nightly backups: "missing" (no folder mounted) or "not_writable" (mounted,
    but the app may not write there: a folder Docker made for the mount belongs to root, while
    the app runs as uid 1000); None when the folder is ready."""
    if backup_dir is None or not Path(backup_dir).is_dir():
        return "missing"
    return None if os.access(backup_dir, os.W_OK) else "not_writable"


def folder(backup_dir: Path | None) -> Path | None:
    """The folder for the nightly backups, when it is there and writable: in a container, a
    folder of the host mounted at `STEWARD_BACKUP_DIR`."""
    if backup_dir is None:
        return None
    path = Path(backup_dir)
    return path if path.is_dir() and os.access(path, os.W_OK) else None


# --- Export --------------------------------------------------------------------------------------


def _iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None


async def _schema(db: AsyncSession) -> str | None:
    try:
        value = await db.scalar(text("SELECT version_num FROM alembic_version"))
        return str(value) if value else None
    except Exception:  # a database made without migrations (tests)
        await db.rollback()
        return None


async def export(db: AsyncSession) -> dict[str, Any]:
    """What the users decided, as JSON-ready data (see the module)."""
    app_settings = {
        row.key: row.value
        for row in await db.scalars(select(AppSetting))
        if row.key not in APP_KEYS_LEFT_OUT
    }
    state = await load(db)
    app_settings[KEY] = {name: getattr(state, name) for name in SETTING_FIELDS}
    data: dict[str, Any] = {
        "format": FORMAT,
        "version": FORMAT_VERSION,
        "steward": __version__,
        "schema": await _schema(db),
        "created_at": datetime.now(UTC).isoformat(),
        "app_settings": app_settings,
        "module_pauses": [
            {"module_id": p.module_id, "paused_at": _iso(p.paused_at), "until": _iso(p.until)}
            for p in await db.scalars(select(ModulePause))
        ],
        "workers": [
            {"name": w.name, "disabled_modules": w.disabled_modules or [], "schedule": w.schedule}
            for w in await db.scalars(select(Worker))
            if w.disabled_modules or w.schedule is not None
        ],
        "accounts": [],
    }
    for account in await db.scalars(select(Account).order_by(Account.created_at)):
        data["accounts"].append(await _export_account(db, account))
    return data


async def _export_account(db: AsyncSession, account: Account) -> dict[str, Any]:
    aid = account.id
    immich_of: dict[uuid.UUID, str] = {
        row.id: str(row.immich_id)
        for row in await db.execute(
            select(Asset.id, Asset.immich_id).where(Asset.account_id == aid)
        )
    }

    def photo(asset_id: uuid.UUID) -> str | None:
        return immich_of.get(asset_id)

    mine = select(Asset.id).where(Asset.account_id == aid)
    result: dict[str, Any] = {
        "immich_user_id": str(account.immich_user_id),
        "name": account.name,
        "email": account.email,
        "settings": {
            row.key: row.value
            for row in await db.scalars(
                select(AccountSetting).where(AccountSetting.account_id == aid)
            )
        },
        "module_display": [
            {"module_id": r.module_id, "position": r.position, "hidden": r.hidden}
            for r in await db.scalars(select(ModuleDisplay).where(ModuleDisplay.account_id == aid))
        ],
        "map_sources": [
            {
                "source_id": r.source_id,
                "enabled": r.enabled,
                "api_key_encrypted": r.api_key_encrypted,
                "usage_token_encrypted": r.usage_token_encrypted,
                "counted_since": _iso(r.counted_since),
                "reset_day": r.reset_day,
            }
            for r in await db.scalars(
                select(MapSourceSetting).where(MapSourceSetting.account_id == aid)
            )
        ],
        "map_tile_usage": [
            {"source_id": r.source_id, "day": _iso(r.day), "tiles": r.tiles}
            for r in await db.scalars(select(MapTileUsage).where(MapTileUsage.account_id == aid))
        ],
        "map_auto": None,
        "street_sources": [
            {
                "source_id": r.source_id,
                "enabled": r.enabled,
                "api_key_encrypted": r.api_key_encrypted,
            }
            for r in await db.scalars(
                select(StreetSourceSetting).where(StreetSourceSetting.account_id == aid)
            )
        ],
        "reviews": [
            {"photo": str(immich_id), "status": status}
            for immich_id, status in await db.execute(
                select(Asset.immich_id, Asset.review_status).where(
                    Asset.account_id == aid, Asset.review_status != "new"
                )
            )
        ],
        "location_changes": [
            {
                "id": str(c.id),
                "photo": photo(c.asset_id),
                "prev_latitude": c.prev_latitude,
                "prev_longitude": c.prev_longitude,
                "latitude": c.latitude,
                "longitude": c.longitude,
                "source": c.source,
                "tag_added": c.tag_added,
                "status": c.status,
                "created_at": _iso(c.created_at),
                "undone_at": _iso(c.undone_at),
                "batch_id": str(c.batch_id) if c.batch_id else None,
            }
            for c in await db.scalars(
                select(LocationChange)
                .where(LocationChange.asset_id.in_(mine))
                .order_by(LocationChange.created_at)
            )
        ],
        "directions": [
            {
                "photo": photo(d.asset_id),
                "heading": d.heading,
                "accuracy": d.accuracy,
                "source": d.source,
                "source_ref": d.source_ref,
                "created_at": _iso(d.created_at),
            }
            for d in await db.scalars(
                select(AssetDirection).where(AssetDirection.asset_id.in_(mine))
            )
        ],
        "trash": [
            {"photo": photo(t.asset_id), "source": t.source, "created_at": _iso(t.created_at)}
            for t in await db.scalars(
                select(ViewPhotoTrash).where(ViewPhotoTrash.account_id == aid)
            )
        ],
        "keep": [
            {"photo": photo(k.asset_id), "created_at": _iso(k.created_at)}
            for k in await db.scalars(select(ViewPhotoKeep).where(ViewPhotoKeep.account_id == aid))
        ],
        "kept_turns": [
            photo(asset_id)
            for asset_id in await db.scalars(
                select(AssetOrientation.asset_id).where(
                    AssetOrientation.asset_id.in_(mine), AssetOrientation.kept.is_(True)
                )
            )
        ],
        "folders": [
            {"id": str(f.id), "name": f.name, "created_at": _iso(f.created_at)}
            for f in await db.scalars(select(ViewFolder).where(ViewFolder.account_id == aid))
        ],
        "groups": await _export_groups(db, aid, photo),
    }
    auto = await db.get(MapAuto, aid)
    if auto is not None:
        result["map_auto"] = {
            "far_source": auto.far_source,
            "near_source": auto.near_source,
            "switch_zoom": auto.switch_zoom,
        }
    return result


async def _export_groups(
    db: AsyncSession, account_id: uuid.UUID, photo: Any
) -> list[dict[str, Any]]:
    """The groups the user did something with: named, marked, taken apart, put in a folder, or
    with photos added or taken out. With all their photos: a rebuild after the restore continues
    the group that shares the most photos with the one it finds, and so keeps what the user did."""
    members: dict[uuid.UUID, list[dict[str, Any]]] = {}
    touched: set[uuid.UUID] = set()
    for group_id, asset_id, role in await db.execute(
        select(ViewGroupMember.group_id, ViewGroupMember.asset_id, ViewGroupMember.role).where(
            ViewGroupMember.account_id == account_id
        )
    ):
        members.setdefault(group_id, []).append({"photo": photo(asset_id), "role": role})
        if role in (ADDED, EXCLUDED):
            touched.add(group_id)
    groups = []
    for group in await db.scalars(select(ViewGroup).where(ViewGroup.account_id == account_id)):
        if not (group.name or group.trash or group.dissolved or group.folder_id) and (
            group.id not in touched
        ):
            continue
        groups.append(
            {
                "id": str(group.id),
                "kind": group.kind,
                "name": group.name,
                "trash": group.trash,
                "dissolved": group.dissolved,
                "folder_id": str(group.folder_id) if group.folder_id else None,
                "created_at": _iso(group.created_at),
                "members": members.get(group.id, []),
            }
        )
    return groups


def encode(data: dict[str, Any]) -> bytes:
    return gzip.compress(json.dumps(data, ensure_ascii=False, default=str).encode(), mtime=0)


def decode(raw: bytes) -> dict[str, Any]:
    data = json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("not a backup of immich-steward")
    if int(data.get("version", 0)) > FORMAT_VERSION:
        raise ValueError(
            f"backup format {data.get('version')} is newer than this version of the app reads "
            f"({FORMAT_VERSION}): update the app first"
        )
    return data


def file_name(now: datetime) -> str:
    return f"steward-backup-{now:%Y-%m-%d-%H%M}.json.gz"


# --- The nightly backup --------------------------------------------------------------------------


def write(directory: Path, raw: bytes, now: datetime) -> Path:
    """Writes the backup into the folder, readable by the owner only (it holds the places of the
    photos), whole or not at all."""
    path = directory / file_name(now)
    partial = path.with_suffix(".part")
    with open(partial, "wb") as handle:
        handle.write(raw)
    os.chmod(partial, 0o600)
    os.replace(partial, path)
    return path


def backups_in(directory: Path) -> list[tuple[datetime, Path]]:
    found = []
    for path in directory.iterdir():
        match = FILE_PATTERN.match(path.name)
        if match:
            year, month, day, hour, minute = (int(part) for part in match.groups())
            found.append((datetime(year, month, day, hour, minute), path))
    return sorted(found, reverse=True)


def to_keep(made: Iterable[datetime], keep_daily: int, keep_weekly: int) -> set[datetime]:
    """Which backups stay: the newest of each of the `keep_daily` latest days that have one, and
    the newest of each of the `keep_weekly` latest weeks (Monday to Sunday) that have one."""
    newest_first = sorted(made, reverse=True)
    kept: set[datetime] = set()
    days: list[date] = []
    weeks: list[tuple[int, int]] = []
    for when in newest_first:
        day = when.date()
        if day not in days and len(days) < keep_daily:
            days.append(day)
            kept.add(when)
        calendar = when.isocalendar()
        week = (calendar.year, calendar.week)
        if week not in weeks and len(weeks) < keep_weekly:
            weeks.append(week)
            kept.add(when)
    return kept


def rotate(directory: Path, keep_daily: int, keep_weekly: int) -> list[Path]:
    """Removes the backups no longer kept (only files named as the app names them)."""
    found = backups_in(directory)
    kept = to_keep((when for when, _ in found), keep_daily, keep_weekly)
    removed = []
    for when, path in found:
        if when not in kept:
            path.unlink(missing_ok=True)
            removed.append(path)
    return removed


def local_now() -> datetime:
    zone, _ = server_zone()
    return datetime.now(zone).replace(tzinfo=None)


async def run_now(db: AsyncSession, backup_dir: Path | None) -> BackupState:
    """Writes a backup into the folder now (also while the nightly one is off) and removes the old
    ones. The state says how it went."""
    state = await load(db)
    directory = folder(backup_dir)
    now = datetime.now(UTC)
    if directory is None:
        state.error, state.error_at = "no_folder", now
        await save(db, state)
        return state
    try:
        raw = encode(await export(db))
        path = await asyncio.to_thread(write, directory, raw, local_now())
        await asyncio.to_thread(rotate, directory, state.keep_daily, state.keep_weekly)
    except Exception as exc:
        log.exception("Backup failed")
        await db.rollback()
        state.error, state.error_at = type(exc).__name__, now
        await save(db, state)
        return state
    state.last_at, state.last_file, state.last_size = now, path.name, len(raw)
    state.error = state.error_at = None
    await save(db, state)
    log.info("Backup written: %s (%d bytes)", path, len(raw))
    return state


def is_due(state: BackupState, now_local: datetime, now: datetime) -> bool:
    """Once a day, from the hour set on (by the server's clock); after a failure, an hour later."""
    if not state.enabled or now_local.hour < state.hour:
        return False
    if state.error_at is not None and now - state.error_at < RETRY_AFTER_ERROR:
        return False
    if state.last_at is None:
        return True
    zone, _ = server_zone()
    last_local = state.last_at.astimezone(zone).replace(tzinfo=None)
    # Made today after the hour: done for today.
    return not (last_local.date() == now_local.date() and last_local.hour >= state.hour)


async def run_if_due(db: AsyncSession, backup_dir: Path | None) -> BackupState | None:
    if folder(backup_dir) is None:
        return None
    state = await load(db)
    if not is_due(state, local_now(), datetime.now(UTC)):
        return None
    return await run_now(db, backup_dir)


# --- Restore -------------------------------------------------------------------------------------


@dataclass
class Report:
    """What a restore did, per kind of data: added, there already, photos not found."""

    added: dict[str, int] = field(default_factory=dict)
    present: dict[str, int] = field(default_factory=dict)
    missing_photos: dict[str, int] = field(default_factory=dict)
    # Marks waiting for the modules: run the restore again after they have looked at the photos.
    waiting: dict[str, int] = field(default_factory=dict)
    accounts_missing: list[str] = field(default_factory=list)
    workers_missing: list[str] = field(default_factory=list)

    def count(self, kind: str, what: str, n: int = 1) -> None:
        bucket = getattr(self, what)
        bucket[kind] = bucket.get(kind, 0) + n

    def lines(self) -> list[str]:
        out = []
        for kind in sorted(set(self.added) | set(self.present) | set(self.missing_photos)):
            line = (
                f"{kind}: added {self.added.get(kind, 0)}, there already "
                f"{self.present.get(kind, 0)}"
            )
            if self.missing_photos.get(kind):
                line += f", photos not found {self.missing_photos[kind]}"
            out.append(line)
        for kind, n in sorted(self.waiting.items()):
            out.append(f"{kind}: {n} wait for the modules — run the restore again later")
        if self.accounts_missing:
            out.append(
                "accounts not signed in yet (sign in, let the sync finish, run again): "
                + ", ".join(self.accounts_missing)
            )
        if self.workers_missing:
            out.append("workers not registered yet: " + ", ".join(self.workers_missing))
        return out


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


async def restore(db: AsyncSession, data: dict[str, Any]) -> Report:
    """Adds what the backup holds and the database lacks; what is there stays as it is (it may be
    newer than the backup). Does not commit: the caller does, or rolls back for a dry run."""
    report = Report()
    for key, value in data.get("app_settings", {}).items():
        if await db.get(AppSetting, key) is None:
            if key == KEY:
                value = {k: v for k, v in value.items() if k in SETTING_FIELDS}
            db.add(AppSetting(key=key, value=value))
            report.count("app settings", "added")
        else:
            report.count("app settings", "present")
    for pause in data.get("module_pauses", []):
        if await db.get(ModulePause, pause["module_id"]) is None:
            db.add(
                ModulePause(
                    module_id=pause["module_id"],
                    paused_at=_dt(pause["paused_at"]),
                    until=_dt(pause["until"]),
                )
            )
            report.count("module pauses", "added")
        else:
            report.count("module pauses", "present")
    for saved in data.get("workers", []):
        worker = await db.scalar(select(Worker).where(Worker.name == saved["name"]))
        if worker is None:
            report.workers_missing.append(saved["name"])
            continue
        if not worker.disabled_modules and worker.schedule is None:
            worker.disabled_modules = saved["disabled_modules"]
            worker.schedule = saved["schedule"]
            report.count("worker settings", "added")
        else:
            report.count("worker settings", "present")
    for saved in data.get("accounts", []):
        account = await db.scalar(
            select(Account).where(Account.immich_user_id == uuid.UUID(saved["immich_user_id"]))
        )
        if account is None:
            report.accounts_missing.append(saved.get("name") or saved["immich_user_id"])
            continue
        await _restore_account(db, account, saved, report)
    await db.flush()
    return report


async def _restore_account(
    db: AsyncSession, account: Account, saved: dict[str, Any], report: Report
) -> None:
    aid = account.id
    asset_of: dict[str, uuid.UUID] = {
        str(immich_id): asset_id
        for asset_id, immich_id in await db.execute(
            select(Asset.id, Asset.immich_id).where(Asset.account_id == aid)
        )
    }

    def find(kind: str, photo: str | None) -> uuid.UUID | None:
        asset_id = asset_of.get(photo) if photo else None
        if asset_id is None:
            report.count(kind, "missing_photos")
        return asset_id

    async def add_once(kind: str, model: Any, key: Any, row: Any) -> None:
        if await db.get(model, key) is None:
            db.add(row)
            report.count(kind, "added")
        else:
            report.count(kind, "present")

    for key, value in saved.get("settings", {}).items():
        await add_once(
            "settings",
            AccountSetting,
            (aid, key),
            AccountSetting(account_id=aid, key=key, value=value),
        )
    for r in saved.get("module_display", []):
        await add_once(
            "module order",
            ModuleDisplay,
            (aid, r["module_id"]),
            ModuleDisplay(account_id=aid, **r),
        )
    for r in saved.get("map_sources", []):
        await add_once(
            "map sources",
            MapSourceSetting,
            (aid, r["source_id"]),
            MapSourceSetting(
                account_id=aid,
                source_id=r["source_id"],
                enabled=r["enabled"],
                api_key_encrypted=r["api_key_encrypted"],
                usage_token_encrypted=r["usage_token_encrypted"],
                counted_since=_dt(r["counted_since"]),
                reset_day=r["reset_day"],
            ),
        )
    for r in saved.get("map_tile_usage", []):
        day = date.fromisoformat(r["day"])
        await add_once(
            "map tiles counted",
            MapTileUsage,
            (aid, r["source_id"], day),
            MapTileUsage(account_id=aid, source_id=r["source_id"], day=day, tiles=r["tiles"]),
        )
    if saved.get("map_auto"):
        await add_once("map switching", MapAuto, aid, MapAuto(account_id=aid, **saved["map_auto"]))
    for r in saved.get("street_sources", []):
        await add_once(
            "street sources",
            StreetSourceSetting,
            (aid, r["source_id"]),
            StreetSourceSetting(account_id=aid, **r),
        )

    for r in saved.get("reviews", []):
        asset_id = find("reviews", r["photo"])
        if asset_id is None:
            continue
        asset = await db.get(Asset, asset_id)
        assert asset is not None
        if asset.review_status == "new":
            asset.review_status = r["status"]
            report.count("reviews", "added")
        else:
            report.count("reviews", "present")

    for r in saved.get("location_changes", []):
        asset_id = find("location history", r["photo"])
        if asset_id is None:
            continue
        await add_once(
            "location history",
            LocationChange,
            uuid.UUID(r["id"]),
            LocationChange(
                id=uuid.UUID(r["id"]),
                asset_id=asset_id,
                prev_latitude=r["prev_latitude"],
                prev_longitude=r["prev_longitude"],
                latitude=r["latitude"],
                longitude=r["longitude"],
                source=r["source"],
                tag_added=r["tag_added"],
                status=r["status"],
                created_at=_dt(r["created_at"]),
                undone_at=_dt(r["undone_at"]),
                batch_id=uuid.UUID(r["batch_id"]) if r["batch_id"] else None,
            ),
        )

    for r in saved.get("directions", []):
        asset_id = find("directions", r["photo"])
        if asset_id is None:
            continue
        await add_once(
            "directions",
            AssetDirection,
            asset_id,
            AssetDirection(
                asset_id=asset_id,
                heading=r["heading"],
                accuracy=r["accuracy"],
                source=r["source"],
                source_ref=r["source_ref"],
                created_at=_dt(r["created_at"]),
            ),
        )

    keep_ids = set()
    for r in saved.get("keep", []):
        asset_id = find("shows the place", r["photo"])
        if asset_id is None:
            continue
        keep_ids.add(asset_id)
        await add_once(
            "shows the place",
            ViewPhotoKeep,
            asset_id,
            ViewPhotoKeep(asset_id=asset_id, account_id=aid, created_at=_dt(r["created_at"])),
        )
    for r in saved.get("trash", []):
        asset_id = find("no place marks", r["photo"])
        if asset_id is None or asset_id in keep_ids:
            continue
        await add_once(
            "no place marks",
            ViewPhotoTrash,
            asset_id,
            ViewPhotoTrash(
                asset_id=asset_id,
                account_id=aid,
                source=r["source"],
                created_at=_dt(r["created_at"]),
            ),
        )

    for photo in saved.get("kept_turns", []):
        asset_id = find("kept as turned", photo)
        if asset_id is None:
            continue
        orientation = await db.get(AssetOrientation, asset_id)
        if orientation is None:
            report.count("kept as turned", "waiting")
        elif orientation.kept:
            report.count("kept as turned", "present")
        else:
            orientation.kept = True
            report.count("kept as turned", "added")

    for r in saved.get("folders", []):
        folder_id = uuid.UUID(r["id"])
        await add_once(
            "folders",
            ViewFolder,
            folder_id,
            ViewFolder(
                id=folder_id, account_id=aid, name=r["name"], created_at=_dt(r["created_at"])
            ),
        )
    await db.flush()
    await _restore_groups(db, aid, saved.get("groups", []), find, report)


async def _restore_groups(
    db: AsyncSession, account_id: uuid.UUID, groups: list[dict[str, Any]], find: Any, report: Report
) -> None:
    # A photo is in one group at most (but may be taken out of several).
    grouped = set(
        await db.scalars(
            select(ViewGroupMember.asset_id).where(
                ViewGroupMember.account_id == account_id, ViewGroupMember.role != EXCLUDED
            )
        )
    )
    for r in groups:
        group_id = uuid.UUID(r["id"])
        if await db.get(ViewGroup, group_id) is not None:
            report.count("groups", "present")
            continue
        folder_id = uuid.UUID(r["folder_id"]) if r["folder_id"] else None
        if folder_id is not None and await db.get(ViewFolder, folder_id) is None:
            folder_id = None
        db.add(
            ViewGroup(
                id=group_id,
                account_id=account_id,
                kind=r["kind"],
                name=r["name"],
                trash=r["trash"],
                dissolved=r["dissolved"],
                folder_id=folder_id,
                created_at=_dt(r["created_at"]),
            )
        )
        await db.flush()
        report.count("groups", "added")
        for member in r["members"]:
            asset_id = find("group photos", member["photo"])
            if asset_id is None:
                continue
            if member["role"] != EXCLUDED:
                if asset_id in grouped:
                    report.count("group photos", "present")
                    continue
                grouped.add(asset_id)
            db.add(
                ViewGroupMember(
                    group_id=group_id,
                    asset_id=asset_id,
                    account_id=account_id,
                    role=member["role"],
                )
            )
            report.count("group photos", "added")
    await db.flush()


# --- Command -------------------------------------------------------------------------------------


async def _command(args: argparse.Namespace) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from steward.config import get_settings
    from steward.db import create_engine

    settings = get_settings()
    engine = create_engine(settings.database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as db:
            if args.action == "now":
                state = await run_now(db, settings.backup_dir)
                if state.error:
                    print(f"Backup failed: {state.error}", file=sys.stderr)
                    return 1
                print(f"Backup written: {state.last_file} ({state.last_size} bytes)")
                return 0
            data = decode(await asyncio.to_thread(Path(args.file).read_bytes))
            print(
                f"Backup of {data.get('created_at')}, app {data.get('steward')}, "
                f"{len(data.get('accounts', []))} account(s)"
            )
            report = await restore(db, data)
            if args.dry_run:
                await db.rollback()
                print("Dry run: nothing written.")
            else:
                await db.commit()
            for line in report.lines():
                print(line)
            return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m steward.backup", description="Backups of what the users decided."
    )
    sub = parser.add_subparsers(dest="action", required=True)
    restore_parser = sub.add_parser(
        "restore",
        help="add what a backup holds and the database lacks (run after the first sync)",
    )
    restore_parser.add_argument("file", help="a steward-backup-….json.gz file")
    restore_parser.add_argument(
        "--dry-run", action="store_true", help="say what would be added, write nothing"
    )
    sub.add_parser("now", help="write a backup into STEWARD_BACKUP_DIR now")
    return asyncio.run(_command(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
