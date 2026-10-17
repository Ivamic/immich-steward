# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

from conftest import FAKE_IMMICH_URL, FakeImmich, make_settings
from fastapi.testclient import TestClient

from steward import __version__
from steward.app import create_app


def test_health_reports_unreachable_database() -> None:
    with TestClient(create_app(make_settings())) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["version"] == __version__
    assert body["database"]["ok"] is False
    assert body["database"]["error"]
    assert body["immich"] == {
        "configured": False,
        "reachable": False,
        "version": None,
        "supported": None,
    }


def test_health_with_database(database: str, fake_immich: FakeImmich) -> None:
    settings = make_settings(database_url=database, immich_url=FAKE_IMMICH_URL)
    with TestClient(create_app(settings, fake_immich.factory)) as client:
        body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["database"]["ok"] is True
    assert body["database"]["pgvector_version"]
    assert body["immich"] == {
        "configured": True,
        "reachable": True,
        "version": "3.3.3",
        "supported": True,
    }


def test_health_flags_unsupported_immich(fake_immich: FakeImmich) -> None:
    fake_immich.version = (2, 5, 0)
    settings = make_settings(immich_url=FAKE_IMMICH_URL)
    with TestClient(create_app(settings, fake_immich.factory)) as client:
        immich = client.get("/api/health").json()["immich"]

    assert immich["version"] == "2.5.0"
    assert immich["supported"] is False


def test_serves_ui_with_spa_fallback(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>ui</title>")
    with TestClient(create_app(make_settings(static_dir=tmp_path))) as client:
        assert "ui" in client.get("/").text
        assert "ui" in client.get("/some/client/route").text
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/does-not-exist").status_code == 404
