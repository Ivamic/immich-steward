# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import UTC, datetime, timedelta
from typing import Any

from conftest import FakeImmich
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from steward.immich.compat import OPTIONAL_PERMISSIONS, REQUIRED_PERMISSIONS
from steward.models import Account, AuthSession


def password_login(client: TestClient, fake: FakeImmich, password: str | None = None) -> Any:
    body = {"email": f" {fake.email} ", "password": password or fake.password}
    return client.post("/api/auth/login/password", json=body)


def run_db(client: TestClient, query: Any) -> Any:
    async def go() -> Any:
        async with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            result = await db.execute(query)
            await db.commit()
            return result

    return client.portal.call(go)  # type: ignore[union-attr]


def test_first_login_creates_a_key_and_closes_the_session(
    client: TestClient, fake_immich: FakeImmich
) -> None:
    response = password_login(client, fake_immich)
    assert response.status_code == 200
    assert response.json()["name"] == "Test User"
    assert client.get("/api/auth/me").status_code == 200

    [key] = fake_immich.created_keys.values()
    assert key["name"].startswith("immich-steward ")
    assert set(key["permissions"]) == REQUIRED_PERMISSIONS | OPTIONAL_PERMISSIONS
    assert fake_immich.sessions == set()
    # Neither the password nor the key reach the browser or the database in clear text.
    assert fake_immich.password not in response.text
    stored = run_db(client, select(Account.api_key_encrypted)).scalar_one()
    assert fake_immich.password not in stored
    assert not any(secret in stored for secret in fake_immich.created_keys)


def test_next_login_reuses_the_stored_key(client: TestClient, fake_immich: FakeImmich) -> None:
    password_login(client, fake_immich)
    client.post("/api/auth/logout")
    assert password_login(client, fake_immich).status_code == 200
    assert len(fake_immich.created_keys) == 1
    assert fake_immich.sessions == set()


def test_key_deleted_in_immich_is_replaced(client: TestClient, fake_immich: FakeImmich) -> None:
    password_login(client, fake_immich)
    [(secret, key)] = fake_immich.created_keys.items()
    # The user deleted the key in Immich; a leftover key of ours with the same name stays.
    del fake_immich.created_keys[secret]
    fake_immich.created_keys["leftover"] = key | {"id": "00000000-0000-4000-8000-000000000001"}

    assert password_login(client, fake_immich).status_code == 200
    [(new_secret, new_key)] = fake_immich.created_keys.items()
    assert new_secret not in (secret, "leftover")
    assert new_key["name"] == key["name"]


def test_account_from_key_login_keeps_its_key(client: TestClient, fake_immich: FakeImmich) -> None:
    assert client.post("/api/auth/login", json={"api_key": "valid-key"}).status_code == 200
    client.post("/api/auth/logout")
    assert password_login(client, fake_immich).status_code == 200
    assert fake_immich.created_keys == {}


def test_wrong_password(client: TestClient, fake_immich: FakeImmich) -> None:
    response = password_login(client, fake_immich, password="wrong")
    assert response.status_code == 401
    assert response.json()["code"] == "immich_invalid_credentials"
    assert client.get("/api/auth/me").status_code == 401


def test_password_login_disabled_on_server(client: TestClient, fake_immich: FakeImmich) -> None:
    fake_immich.password_login_enabled = False
    response = password_login(client, fake_immich)
    assert response.status_code == 400
    assert response.json()["code"] == "immich_password_login_failed"


def test_session_is_extended_on_use(client: TestClient, fake_immich: FakeImmich) -> None:
    password_login(client, fake_immich)
    soon = datetime.now(UTC) + timedelta(days=3)
    run_db(client, update(AuthSession).values(expires_at=soon))

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert "max-age=7776000" in me.headers["set-cookie"].lower()  # 90 days
    expires = run_db(client, select(AuthSession.expires_at)).scalar_one()
    assert expires > datetime.now(UTC) + timedelta(days=89)

    # A fresh session is not rewritten on every request.
    assert "set-cookie" not in client.get("/api/auth/me").headers
