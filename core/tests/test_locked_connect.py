# SPDX-License-Identifier: AGPL-3.0-or-later
"""Connecting the Immich locked folder with the password once (D-216, D-220)."""

import uuid

from conftest import FakeImmich
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_password_login import run_db

from steward.models import LockedFolder


def test_connect_keeps_the_session_not_the_password(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    assert signed_in.get("/api/locked").json()["connected"] is False

    response = signed_in.post("/api/locked/connect", json={"password": fake_immich.password})
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] and body["has_pin"] and not body["open"]
    assert body["idle_minutes"] == 15

    [token] = fake_immich.sessions
    stored = run_db(signed_in, select(LockedFolder.session_encrypted)).scalar_one()
    assert token not in stored and fake_immich.password not in stored
    assert token not in response.text
    # Connecting does not open the folder.
    assert fake_immich.elevated == set()
    assert signed_in.get("/api/locked").json()["connected"] is True


def test_a_user_without_a_pin_is_told(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    fake_immich.pin_code = None
    response = signed_in.post("/api/locked/connect", json={"password": fake_immich.password})
    assert response.status_code == 200
    assert response.json()["has_pin"] is False


def test_a_wrong_password_connects_nothing(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    response = signed_in.post("/api/locked/connect", json={"password": "wrong"})
    assert response.status_code == 401
    assert response.json()["code"] == "locked_wrong_password"
    assert signed_in.get("/api/locked").json()["connected"] is False


def test_the_password_of_another_user_is_refused(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    fake_immich.user_id = uuid.uuid4()  # the same email now belongs to another Immich user
    response = signed_in.post("/api/locked/connect", json={"password": fake_immich.password})
    assert response.status_code == 400
    assert response.json()["code"] == "locked_other_user"
    assert fake_immich.sessions == set()


def test_password_sign_in_off_in_immich(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    fake_immich.password_login_enabled = False
    response = signed_in.post("/api/locked/connect", json={"password": fake_immich.password})
    assert response.status_code == 400
    assert response.json()["code"] == "locked_password_login_failed"


def test_disconnect_ends_the_session_in_immich(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    signed_in.post("/api/locked/connect", json={"password": fake_immich.password})
    response = signed_in.delete("/api/locked")
    assert response.status_code == 200
    assert response.json()["connected"] is False
    assert fake_immich.sessions == set()
    assert run_db(signed_in, select(LockedFolder)).first() is None


def test_disconnect_works_when_immich_already_ended_the_session(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    signed_in.post("/api/locked/connect", json={"password": fake_immich.password})
    fake_immich.sessions.clear()  # the password changed in Immich
    assert signed_in.delete("/api/locked").json()["connected"] is False


def test_connecting_again_replaces_the_session(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    signed_in.post("/api/locked/connect", json={"password": fake_immich.password})
    [first] = fake_immich.sessions
    signed_in.post("/api/locked/connect", json={"password": fake_immich.password})
    assert len(fake_immich.sessions) == 1
    assert first not in fake_immich.sessions


def test_only_the_session_is_used_for_the_folder(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    signed_in.post("/api/locked/connect", json={"password": fake_immich.password})
    signed_in.get("/api/locked")
    # Connecting asks who the user is and whether they have a PIN; showing the state asks nothing.
    assert fake_immich.session_requests == ["/api/users/me", "/api/auth/status"]
