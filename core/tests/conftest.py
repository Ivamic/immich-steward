# SPDX-License-Identifier: AGPL-3.0-or-later
import asyncio
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
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


def make_settings(**overrides: Any) -> Settings:
    """Settings isolated from the developer's .env file."""
    values: dict[str, Any] = {"database_url": UNREACHABLE_DATABASE_URL} | overrides
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@dataclass
class FakeImmich:
    """In-memory stand-in for the few Immich endpoints the app calls."""

    version: tuple[int, int, int] = (3, 3, 3)
    valid_key: str = "valid-key"
    permissions: list[str] = field(default_factory=lambda: sorted(REQUIRED_PERMISSIONS))
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    user_name: str = "Test User"

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
        return _json({"message": "Not found"}, 404)

    def factory(self, base_url: str, api_key: str | None) -> ImmichClient:
        return ImmichClient(base_url, api_key, transport=httpx2.MockTransport(self.handler))


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
            await conn.execute(text("TRUNCATE account, auth_session CASCADE"))
        await engine.dispose()

    asyncio.run(truncate())
    return migrated_database


@pytest.fixture
def client(database: str, fake_immich: FakeImmich) -> Iterator[TestClient]:
    settings = make_settings(database_url=database, immich_url=FAKE_IMMICH_URL, secret_key="s" * 32)
    with TestClient(create_app(settings, fake_immich.factory)) as test_client:
        yield test_client
