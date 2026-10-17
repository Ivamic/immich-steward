# SPDX-License-Identifier: AGPL-3.0-or-later
from conftest import FakeImmich
from fastapi.testclient import TestClient

from steward.deps import SESSION_COOKIE


def login(client: TestClient, api_key: str = "valid-key") -> dict[str, object]:
    response = client.post("/api/auth/login", json={"api_key": api_key})
    return {"status": response.status_code, "body": response.json()}


def test_login_me_logout(client: TestClient, fake_immich: FakeImmich) -> None:
    assert client.get("/api/auth/me").status_code == 401

    response = client.post("/api/auth/login", json={"api_key": " valid-key "})
    assert response.status_code == 200
    assert response.json()["name"] == "Test User"
    cookie = response.headers["set-cookie"].lower()
    assert SESSION_COOKIE in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    # The API key itself never goes back to the browser.
    assert "valid-key" not in response.text

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "test@example.com"

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_repeated_login_updates_the_same_account(
    client: TestClient, fake_immich: FakeImmich
) -> None:
    first = login(client)["body"]
    fake_immich.user_name = "Renamed"
    second = login(client)["body"]
    assert isinstance(first, dict) and isinstance(second, dict)
    assert first["id"] == second["id"]
    assert second["name"] == "Renamed"


def test_invalid_api_key(client: TestClient) -> None:
    result = login(client, "wrong")
    assert result["status"] == 401
    assert result["body"] == {"code": "immich_invalid_api_key", "params": {}}


def test_missing_permissions_are_listed(client: TestClient, fake_immich: FakeImmich) -> None:
    fake_immich.permissions = ["asset.read", "asset.view"]
    result = login(client)
    assert result["status"] == 403
    body = result["body"]
    assert isinstance(body, dict)
    assert body["code"] == "immich_missing_permissions"
    assert "user.read" in body["params"]["permissions"]
    assert "asset.read" not in body["params"]["permissions"]


def test_key_with_all_permissions(client: TestClient, fake_immich: FakeImmich) -> None:
    fake_immich.permissions = ["all"]
    assert login(client)["status"] == 200


def test_unsupported_immich_version(client: TestClient, fake_immich: FakeImmich) -> None:
    fake_immich.version = (2, 7, 5)
    result = login(client)
    assert result["status"] == 400
    assert result["body"] == {
        "code": "immich_unsupported_version",
        "params": {"version": "2.7.5", "supported": [3]},
    }


def test_invalid_session_cookie(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, "forged")
    assert client.get("/api/auth/me").json() == {"code": "not_authenticated", "params": {}}
