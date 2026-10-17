# SPDX-License-Identifier: AGPL-3.0-or-later
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from steward import __version__
from steward.app import create_app
from steward.config import Settings

# Integration tests need a real PostgreSQL with pgvector (CI provides one).
TEST_DATABASE_URL = os.environ.get("STEWARD_TEST_DATABASE_URL")


def test_health_reports_unreachable_database() -> None:
    settings = Settings(database_url="postgresql+asyncpg://nobody:x@127.0.0.1:1/none")
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["version"] == __version__
    assert body["database"]["ok"] is False
    assert body["database"]["error"]


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="STEWARD_TEST_DATABASE_URL is not set")
def test_health_with_database() -> None:
    assert TEST_DATABASE_URL is not None
    with TestClient(create_app(Settings(database_url=TEST_DATABASE_URL))) as client:
        body = client.get("/api/health").json()

    assert body["database"]["ok"] is True
    assert body["database"]["server_version"]


def test_serves_ui_with_spa_fallback(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>ui</title>")
    settings = Settings(
        database_url="postgresql+asyncpg://nobody:x@127.0.0.1:1/none", static_dir=tmp_path
    )
    with TestClient(create_app(settings)) as client:
        assert "ui" in client.get("/").text
        assert "ui" in client.get("/some/client/route").text
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/does-not-exist").status_code == 404
