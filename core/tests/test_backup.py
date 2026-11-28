# SPDX-License-Identifier: AGPL-3.0-or-later
"""Backups of what the users decided (D-252): what goes in, the restore, the nightly folder."""

import gzip
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import FAKE_IMMICH_URL, FakeImmich, make_settings, sync
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update

from steward import backup
from steward.app import create_app
from steward.models import (
    Account,
    AccountSetting,
    Asset,
    AssetDirection,
    AssetOrientation,
    LocationChange,
    ModuleRun,
    ViewFolder,
    ViewGroup,
    ViewGroupMember,
    ViewPhotoKeep,
    ViewPhotoTrash,
)


def db_call(client: TestClient, work: Any) -> Any:
    async def go() -> Any:
        async with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            return await work(db)

    return client.portal.call(go)  # type: ignore[union-attr]


@pytest.fixture
def backups_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "backups"
    folder.mkdir()
    return folder


@pytest.fixture
def app_client(database: str, fake_immich: FakeImmich, backups_dir: Path) -> Iterator[TestClient]:
    settings = make_settings(
        database_url=database,
        immich_url=FAKE_IMMICH_URL,
        secret_key="s" * 32,
        backup_dir=backups_dir,
    )
    app = create_app(settings, fake_immich.factory, fake_immich.transport)
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"api_key": "valid-key"}).status_code == 200
        yield client


@pytest.fixture
def photos(app_client: TestClient, fake_immich: FakeImmich) -> dict[str, uuid.UUID]:
    for hour, name in enumerate(("a.jpg", "b.jpg", "c.jpg", "d.jpg")):
        fake_immich.add_asset(taken=f"2024-05-01T{10 + hour}:00:00", originalFileName=name)
    sync(app_client)

    async def ids(db: Any) -> dict[str, uuid.UUID]:
        rows = await db.execute(select(Asset.original_file_name, Asset.id))
        return {name: asset_id for name, asset_id in rows}

    result: dict[str, uuid.UUID] = db_call(app_client, ids)
    return result


def decide(client: TestClient, photos: dict[str, uuid.UUID]) -> None:
    """What a user does: a place written and undone, a direction, marks, a folder, a named group."""

    async def work(db: Any) -> None:
        account = await db.scalar(select(Account))
        a, b, c, d = (photos[n] for n in ("a.jpg", "b.jpg", "c.jpg", "d.jpg"))
        (await db.get(Asset, d)).review_status = "not_applicable"
        batch = uuid.uuid4()
        db.add(LocationChange(asset_id=a, latitude=1.0, longitude=2.0, source="manual"))
        db.add(
            LocationChange(
                asset_id=b,
                latitude=3.0,
                longitude=4.0,
                source="similar",
                status="undone",
                undone_at=datetime.now(UTC),
                batch_id=batch,
            )
        )
        db.add(AssetDirection(asset_id=a, heading=90.0, accuracy=30.0, source="manual"))
        db.add(ViewPhotoTrash(asset_id=c, account_id=account.id))
        db.add(ViewPhotoKeep(asset_id=b, account_id=account.id))
        db.add(AccountSetting(account_id=account.id, key="details_first", value={"value": False}))
        folder = ViewFolder(account_id=account.id, name="Home")
        db.add(folder)
        await db.flush()
        group = ViewGroup(
            account_id=account.id, kind="environment", name="Garden", folder_id=folder.id
        )
        db.add(group)
        await db.flush()
        for asset_id, role in ((a, "core"), (b, "attached"), (d, "excluded")):
            db.add(
                ViewGroupMember(
                    group_id=group.id, asset_id=asset_id, account_id=account.id, role=role
                )
            )
        await db.commit()

    db_call(client, work)


def forget(client: TestClient) -> None:
    """The decisions lost (a new database, the photos synced again)."""

    async def work(db: Any) -> None:
        for model in (
            LocationChange,
            AssetDirection,
            ViewPhotoTrash,
            ViewPhotoKeep,
            AccountSetting,
            ViewGroupMember,
            ViewGroup,
            ViewFolder,
        ):
            await db.execute(delete(model))
        await db.execute(update(Asset).values(review_status="new"))
        await db.commit()

    db_call(client, work)


def counts(client: TestClient) -> dict[str, int]:
    async def work(db: Any) -> dict[str, int]:
        result = {}
        for model in (
            LocationChange,
            AssetDirection,
            ViewPhotoTrash,
            ViewPhotoKeep,
            AccountSetting,
            ViewGroup,
            ViewGroupMember,
            ViewFolder,
        ):
            result[model.__tablename__] = await db.scalar(select(func.count()).select_from(model))
        result["reviewed"] = await db.scalar(
            select(func.count()).select_from(Asset).where(Asset.review_status != "new")
        )
        return result

    found: dict[str, int] = db_call(client, work)
    return found


def test_a_backup_brings_back_what_the_user_decided(
    app_client: TestClient, photos: dict[str, uuid.UUID]
) -> None:
    decide(app_client, photos)
    before = counts(app_client)
    raw = app_client.get("/api/backups/download")
    assert raw.status_code == 200
    assert raw.headers["content-disposition"].startswith('attachment; filename="steward-backup-')
    data = backup.decode(raw.content)
    # Photos by their Immich id; no vectors, no answers of modules.
    account = data["accounts"][0]
    assert {"embeddings", "module_runs", "detail_matches"}.isdisjoint(account)
    assert len(account["location_changes"]) == 2

    forget(app_client)
    assert counts(app_client)["location_change"] == 0

    async def restore(db: Any) -> backup.Report:
        report = await backup.restore(db, data)
        await db.commit()
        return report

    report = db_call(app_client, restore)
    assert counts(app_client) == before
    assert report.added["location history"] == 2
    assert report.added["groups"] == 1

    async def group_of(db: Any) -> tuple[str | None, str | None]:
        group = await db.scalar(select(ViewGroup))
        folder = await db.get(ViewFolder, group.folder_id)
        return group.name, folder.name

    assert db_call(app_client, group_of) == ("Garden", "Home")

    # Again: nothing added twice.
    report = db_call(app_client, restore)
    assert counts(app_client) == before
    assert not report.added
    assert report.present["location history"] == 2


def test_photos_and_accounts_not_there_are_reported(
    app_client: TestClient, photos: dict[str, uuid.UUID]
) -> None:
    decide(app_client, photos)
    data = backup.decode(app_client.get("/api/backups/download").content)
    data["accounts"][0]["location_changes"][0]["photo"] = str(uuid.uuid4())
    data["accounts"].append({"immich_user_id": str(uuid.uuid4()), "name": "Someone"})
    forget(app_client)

    async def restore(db: Any) -> backup.Report:
        report = await backup.restore(db, data)
        await db.rollback()
        return report

    report = db_call(app_client, restore)
    assert report.missing_photos["location history"] == 1
    assert report.accounts_missing == ["Someone"]
    assert any("Someone" in line for line in report.lines())


def test_a_kept_turn_waits_for_the_module(
    app_client: TestClient, photos: dict[str, uuid.UUID]
) -> None:
    async def keep(db: Any) -> None:
        run = ModuleRun(asset_id=photos["a.jpg"], module_id="orientation", status="done")
        db.add(run)
        await db.flush()
        db.add(
            AssetOrientation(
                asset_id=photos["a.jpg"],
                run_id=run.id,
                turn=1,
                score=0.95,
                probs=[0.0, 0.95, 0.0, 0.05],
                module_version="1",
                kept=True,
            )
        )
        await db.commit()

    db_call(app_client, keep)
    data = backup.decode(app_client.get("/api/backups/download").content)
    assert len(data["accounts"][0]["kept_turns"]) == 1

    async def drop_and_restore(db: Any) -> backup.Report:
        await db.execute(delete(AssetOrientation))
        report = await backup.restore(db, data)
        await db.rollback()
        return report

    report = db_call(app_client, drop_and_restore)
    assert report.waiting == {"kept as turned": 1}


def test_the_nightly_folder(app_client: TestClient, backups_dir: Path) -> None:
    state = app_client.get("/api/backups").json()
    assert state["folder_ready"] is True
    assert state["folder_problem"] is None
    assert state["enabled"] is True
    assert state["last_at"] is None

    done = app_client.post("/api/backups/run").json()
    assert done["error"] is None
    written = list(backups_dir.iterdir())
    assert [p.name for p in written] == [done["last_file"]]
    data = json.loads(gzip.decompress(written[0].read_bytes()))
    assert data["format"] == backup.FORMAT

    changed = app_client.put("/api/backups", json={"hour": 4, "keep_daily": 3}).json()
    assert (changed["hour"], changed["keep_daily"], changed["enabled"]) == (4, 3, True)
    assert app_client.put("/api/backups", json={"hour": 24}).status_code == 422


def test_without_the_folder_it_says_so(
    database: str, fake_immich: FakeImmich, tmp_path: Path
) -> None:
    settings = make_settings(
        database_url=database,
        immich_url=FAKE_IMMICH_URL,
        secret_key="s" * 32,
        backup_dir=tmp_path / "not-mounted",
    )
    app = create_app(settings, fake_immich.factory, fake_immich.transport)
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"api_key": "valid-key"}).status_code == 200
        state = client.get("/api/backups").json()
        assert state["folder_ready"] is False
        assert state["folder_problem"] == "missing"
        assert state["folder"].endswith("not-mounted")
        assert client.post("/api/backups/run").json()["error"] == "no_folder"
        # The download works all the same.
        assert backup.decode(client.get("/api/backups/download").content)["accounts"]


def test_which_backups_are_kept() -> None:
    start = datetime(2026, 11, 30, 3, 0)  # a Monday
    made = [start - timedelta(days=n) for n in range(40)]
    # Two the same day: the newer stays.
    made.append(start - timedelta(hours=1))
    kept = backup.to_keep(made, keep_daily=7, keep_weekly=4)
    days = {when.date() for when in kept}
    assert {(start - timedelta(days=n)).date() for n in range(7)} <= days
    assert start - timedelta(hours=1) not in kept
    # And the newest of each of the 4 latest weeks: this week's and last week's are among the
    # days already; the two weeks before add their Sundays.
    assert datetime(2026, 11, 22, 3, 0) in kept
    assert datetime(2026, 11, 15, 3, 0) in kept
    assert len(kept) == 7 + 2
    assert len(backup.to_keep(made, keep_daily=1, keep_weekly=0)) == 1


def test_rotation_removes_only_its_own_files(backups_dir: Path) -> None:
    for day in range(1, 11):
        (backups_dir / f"steward-backup-2026-11-{day:02d}-0300.json.gz").write_bytes(b"x")
    (backups_dir / "notes.txt").write_text("mine")
    removed = backup.rotate(backups_dir, keep_daily=3, keep_weekly=0)
    assert len(removed) == 7
    assert sorted(p.name for p in backups_dir.iterdir()) == [
        "notes.txt",
        "steward-backup-2026-11-08-0300.json.gz",
        "steward-backup-2026-11-09-0300.json.gz",
        "steward-backup-2026-11-10-0300.json.gz",
    ]


def test_when_the_nightly_backup_is_due() -> None:
    now = datetime(2026, 11, 28, 5, 0, tzinfo=UTC)
    local = datetime(2026, 11, 28, 5, 0)
    state = backup.BackupState(hour=3)
    assert backup.is_due(state, local, now)
    assert not backup.is_due(backup.BackupState(hour=6), local, now)
    assert not backup.is_due(backup.BackupState(enabled=False), local, now)
    # Failed a moment ago: an hour later.
    failed = backup.BackupState(hour=3, error="OSError", error_at=now - timedelta(minutes=5))
    assert not backup.is_due(failed, local, now)


def test_a_newer_format_is_refused() -> None:
    raw = gzip.compress(json.dumps({"format": backup.FORMAT, "version": 99}).encode())
    with pytest.raises(ValueError, match="newer"):
        backup.decode(raw)
    with pytest.raises(ValueError, match="not a backup"):
        backup.decode(b"{}")


def test_the_restore_command(
    app_client: TestClient,
    photos: dict[str, uuid.UUID],
    database: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from steward.config import get_settings

    decide(app_client, photos)
    file = tmp_path / "steward-backup-2026-11-28-0300.json.gz"
    file.write_bytes(app_client.get("/api/backups/download").content)
    forget(app_client)
    monkeypatch.setenv("STEWARD_DATABASE_URL", database)
    get_settings.cache_clear()
    try:
        # A dry run writes nothing.
        assert backup.main(["restore", str(file), "--dry-run"]) == 0
        assert "Dry run" in capsys.readouterr().out
        assert counts(app_client)["location_change"] == 0
        assert backup.main(["restore", str(file)]) == 0
        assert "location history: added 2" in capsys.readouterr().out
        assert counts(app_client)["location_change"] == 2
    finally:
        get_settings.cache_clear()
