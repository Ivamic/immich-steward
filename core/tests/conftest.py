# SPDX-License-Identifier: AGPL-3.0-or-later
import asyncio
import json
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx2
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from steward.app import create_app
from steward.config import Settings
from steward.db import create_engine
from steward.immich import ImmichClient
from steward.immich.compat import REQUIRED_PERMISSIONS

# Integration tests need a real PostgreSQL with pgvector (CI provides one).
TEST_DATABASE_URL = os.environ.get("STEWARD_TEST_DATABASE_URL")
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://nobody:x@127.0.0.1:1/none"
FAKE_IMMICH_URL = "http://immich.test"
ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"
TABLES = "account, auth_session, asset, album, asset_album, job, location_change"


def make_settings(**overrides: Any) -> Settings:
    """Settings isolated from the developer's .env file and STEWARD_* environment variables."""
    values: dict[str, Any] = {
        "database_url": UNREACHABLE_DATABASE_URL,
        "immich_url": None,
        "secret_key": None,
        "static_dir": None,
        "run_jobs": False,
    }
    values |= overrides
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@dataclass
class FakeImmich:
    """In-memory stand-in for the few Immich endpoints the app calls."""

    version: tuple[int, int, int] = (3, 3, 3)
    valid_key: str = "valid-key"
    permissions: list[str] = field(default_factory=lambda: sorted(REQUIRED_PERMISSIONS))
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    user_name: str = "Test User"
    assets: dict[str, dict[str, Any]] = field(default_factory=dict)
    albums: dict[str, dict[str, Any]] = field(default_factory=dict)
    album_assets: dict[str, list[str]] = field(default_factory=dict)
    search_requests: list[dict[str, Any]] = field(default_factory=list)
    thumbnail_requests: int = 0
    # Tag id -> full value, and asset id -> ids of its tags.
    tags: dict[str, str] = field(default_factory=dict)
    asset_tags: dict[str, set[str]] = field(default_factory=dict)
    location_writes: int = 0
    fail_tagging: bool = False
    # Immich's metadata job turns exactly (0, 0) into "no location".
    clears_null_island: bool = True

    def add_asset(self, **fields: Any) -> str:
        """Adds an asset in the Immich API shape; returns its id."""
        asset_id = str(uuid.uuid4())
        taken = fields.pop("taken", "2024-05-01T10:00:00")
        exif = {"dateTimeOriginal": taken + "+00:00", "make": "Canon", "model": "EOS 300D"}
        exif |= fields.pop("exif", {})
        self.assets[asset_id] = {
            "id": asset_id,
            "ownerId": str(self.user_id),
            "type": "IMAGE",
            "visibility": "timeline",
            "originalFileName": f"IMG_{len(self.assets):04}.JPG",
            "fileCreatedAt": taken + "Z",
            "localDateTime": taken + "Z",
            "updatedAt": "2026-01-01T00:00:00Z",
            "isTrashed": False,
            "exifInfo": exif,
        } | fields
        return asset_id

    def add_album(self, name: str, asset_ids: list[str], **fields: Any) -> str:
        album_id = str(uuid.uuid4())
        self.albums[album_id] = {
            "id": album_id,
            "albumName": name,
            "assetCount": len(asset_ids),
            "updatedAt": "2026-01-01T00:00:00Z",
            "shared": False,
        } | fields
        self.album_assets[album_id] = list(asset_ids)
        return album_id

    def _search(self, body: dict[str, Any]) -> httpx2.Response:
        self.search_requests.append(body)
        items = list(self.assets.values())
        if "albumIds" in body:
            members = set(self.album_assets.get(body["albumIds"][0], []))
            items = [a for a in items if a["id"] in members]
        items = [a for a in items if a["visibility"] == body.get("visibility", "timeline")]
        if not body.get("withDeleted"):
            items = [a for a in items if not a["isTrashed"]]
        if "updatedAfter" in body:
            after = datetime.fromisoformat(body["updatedAfter"])
            items = [a for a in items if datetime.fromisoformat(a["updatedAt"]) > after]
        if not body.get("withExif"):
            items = [{k: v for k, v in a.items() if k != "exifInfo"} for a in items]
        page, size = body.get("page", 1), body.get("size", 250)
        chunk = items[(page - 1) * size : page * size]
        next_page = str(page + 1) if page * size < len(items) else None
        return _json({"assets": {"items": chunk, "nextPage": next_page}})

    def tag_values(self, asset_id: str) -> set[str]:
        return {self.tags[tag_id] for tag_id in self.asset_tags.get(asset_id, set())}

    def _asset(self, request: httpx2.Request, asset_id: str) -> httpx2.Response:
        asset = self.assets.get(asset_id)
        if asset is None:
            return _json({"message": "Not found"}, 400)
        if request.method == "PUT":
            body = json.loads(request.content)
            if not all(isinstance(body.get(k), (int, float)) for k in ("latitude", "longitude")):
                return _json({"message": "Validation failed"}, 400)
            self.location_writes += 1
            point = {"latitude": body["latitude"], "longitude": body["longitude"]}
            if self.clears_null_island and point == {"latitude": 0, "longitude": 0}:
                point = {"latitude": None, "longitude": None}
            asset["exifInfo"] |= point
        return _json(asset)

    def _upsert_tags(self, values: list[str]) -> httpx2.Response:
        by_value = {value: tag_id for tag_id, value in self.tags.items()}
        for value in values:
            by_value.setdefault(value, str(uuid.uuid4()))
            self.tags[by_value[value]] = value
        return _json([{"id": by_value[value], "value": value} for value in values])

    def _tag_assets(self, request: httpx2.Request, tag_id: str) -> httpx2.Response:
        if self.fail_tagging:
            return _json({"message": "Missing required permission: tag.asset"}, 403)
        results = []
        for asset_id in json.loads(request.content)["ids"]:
            tags = self.asset_tags.setdefault(asset_id, set())
            present = tag_id in tags
            if request.method == "PUT":
                tags.add(tag_id)
                ok = not present
            else:
                tags.discard(tag_id)
                ok = present
            results.append({"id": asset_id, "success": ok} | ({} if ok else {"error": "duplicate"}))
        return _json(results)

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if path == "/api/server/version":
            major, minor, patch = self.version
            return _json({"major": major, "minor": minor, "patch": patch})
        if request.headers.get("x-api-key") != self.valid_key:
            return _json({"message": "Invalid API key"}, 401)
        if path == "/api/api-keys/me":
            return _json({"id": str(uuid.uuid4()), "name": "k", "permissions": self.permissions})
        if path == "/api/users/me":
            if "user.read" not in self.permissions and "all" not in self.permissions:
                return _json({"message": "Missing required permission: user.read"}, 403)
            return _json(
                {"id": str(self.user_id), "name": self.user_name, "email": "test@example.com"}
            )
        if path.startswith("/api/assets/") and path.endswith("/thumbnail"):
            asset_id = path.split("/")[3]
            if asset_id not in self.assets:
                return _json({"message": "Not found"}, 400)
            self.thumbnail_requests += 1
            size = request.url.params.get("size")
            if size == "fullsize":
                return httpx2.Response(302, headers={"location": "original?"})
            return httpx2.Response(
                200,
                content=f"image:{asset_id}:{size}".encode(),
                headers={"content-type": "image/webp"},
            )
        parts = path.split("/")
        if len(parts) == 4 and parts[2] == "assets" and request.method in ("GET", "PUT"):
            return self._asset(request, parts[3])
        if path == "/api/tags" and request.method == "PUT":
            return self._upsert_tags(json.loads(request.content)["tags"])
        if len(parts) == 5 and parts[2] == "tags" and parts[4] == "assets":
            return self._tag_assets(request, parts[3])
        if path.startswith("/api/assets/") and path.endswith("/original"):
            if "asset.download" not in self.permissions:
                return _json({"message": "Missing required permission: asset.download"}, 403)
            return httpx2.Response(200, content=b"original", headers={"content-type": "image/jpeg"})
        if path == "/api/search/metadata":
            return self._search(json.loads(request.content))
        if path == "/api/albums":
            shared = request.url.params.get("shared") == "true"
            return _json([a for a in self.albums.values() if a["shared"] == shared])
        return _json({"message": "Not found"}, 404)

    @property
    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self.handler)

    def factory(self, base_url: str, api_key: str | None) -> ImmichClient:
        return ImmichClient(base_url, api_key, transport=self.transport)


def _json(body: Any, status: int = 200) -> httpx2.Response:
    return httpx2.Response(status, json=body)


@pytest.fixture
def fake_immich() -> FakeImmich:
    return FakeImmich()


@pytest.fixture(scope="session")
def migrated_database() -> str:
    if not TEST_DATABASE_URL:
        pytest.skip("STEWARD_TEST_DATABASE_URL is not set")
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return TEST_DATABASE_URL


@pytest.fixture
def database(migrated_database: str) -> str:
    """A migrated test database with all tables emptied."""

    async def truncate() -> None:
        engine = create_engine(migrated_database)
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {TABLES} CASCADE"))
        await engine.dispose()

    asyncio.run(truncate())
    return migrated_database


@pytest.fixture
def client(database: str, fake_immich: FakeImmich) -> Iterator[TestClient]:
    settings = make_settings(database_url=database, immich_url=FAKE_IMMICH_URL, secret_key="s" * 32)
    app = create_app(settings, fake_immich.factory, fake_immich.transport)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def signed_in(client: TestClient) -> TestClient:
    assert client.post("/api/auth/login", json={"api_key": "valid-key"}).status_code == 200
    return client


def run_jobs(client: TestClient) -> None:
    runner = client.app.state.job_runner  # type: ignore[attr-defined]
    while client.portal.call(runner.run_once):  # type: ignore[union-attr]
        pass


def sync(client: TestClient, full: bool | None = None) -> dict[str, Any]:
    job = client.post("/api/library/sync", json={"full": full})
    assert job.status_code == 202
    run_jobs(client)
    library: dict[str, Any] = client.get("/api/library").json()
    return library
