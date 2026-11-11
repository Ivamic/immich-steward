# SPDX-License-Identifier: AGPL-3.0-or-later
"""Opening and closing the Immich locked folder (D-216, D-220)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from conftest import FakeImmich
from fastapi.testclient import TestClient
from sqlalchemy import update
from test_password_login import run_db

from steward.models import LockedFolder


def connected(client: TestClient, fake: FakeImmich) -> TestClient:
    assert client.post("/api/locked/connect", json={"password": fake.password}).status_code == 200
    return client


def open_with(client: TestClient, pin: str) -> Any:
    return client.post("/api/locked/open", json={"pin_code": pin})


def close_idle(client: TestClient) -> None:
    runner = client.app.state.job_runner  # type: ignore[attr-defined]
    client.portal.call(runner.close_idle_locked)  # type: ignore[union-attr]


def idle_for(client: TestClient, minutes: float) -> None:
    then = datetime.now(UTC) - timedelta(minutes=minutes)
    run_db(client, update(LockedFolder).values(active_at=then))


def test_the_pin_opens_and_close_closes(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    client = connected(signed_in, fake_immich)
    response = open_with(client, "123456")
    assert response.status_code == 200
    assert response.json()["open"] is True
    [token] = fake_immich.sessions
    assert token in fake_immich.elevated

    response = client.post("/api/locked/close")
    assert response.json()["open"] is False
    assert fake_immich.elevated == set()


def test_wrong_pins_pause_the_tries(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    client = connected(signed_in, fake_immich)
    for left in (4, 3, 2, 1):
        response = open_with(client, "000000")
        assert response.status_code == 400
        assert response.json() == {"code": "locked_wrong_pin", "params": {"left": left}}
    paused = open_with(client, "000000")
    assert paused.status_code == 429
    assert paused.json()["code"] == "locked_pin_paused"
    # Even the right PIN waits: Immich is not asked during the pause.
    asked = len(fake_immich.session_requests)
    assert open_with(client, "123456").status_code == 429
    assert len(fake_immich.session_requests) == asked
    assert client.get("/api/locked").json()["blocked_until"] is not None


def test_the_right_pin_resets_the_count(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    client = connected(signed_in, fake_immich)
    for _ in range(3):
        open_with(client, "000000")
    assert open_with(client, "123456").status_code == 200
    client.post("/api/locked/close")
    for _ in range(4):
        assert open_with(client, "000000").status_code == 400


def test_no_pin_in_immich(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    client = connected(signed_in, fake_immich)
    fake_immich.pin_code = None
    response = open_with(client, "123456")
    assert response.status_code == 400
    assert response.json()["code"] == "locked_no_pin"


def test_a_session_ended_in_immich_asks_to_connect_again(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    client = connected(signed_in, fake_immich)
    fake_immich.sessions.clear()
    response = open_with(client, "123456")
    assert response.status_code == 409
    assert response.json()["code"] == "locked_session_lost"
    assert client.get("/api/locked").json()["connected"] is False


def test_opening_needs_a_connected_folder(signed_in: TestClient) -> None:
    assert open_with(signed_in, "123456").json()["code"] == "locked_not_connected"


def test_idle_closes_the_folder(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    client = connected(signed_in, fake_immich)
    open_with(client, "123456")
    idle_for(client, 14)
    close_idle(client)
    assert client.get("/api/locked").json()["open"] is True
    idle_for(client, 16)
    close_idle(client)
    assert client.get("/api/locked").json()["open"] is False
    assert fake_immich.elevated == set()


def test_a_user_action_keeps_it_open(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    client = connected(signed_in, fake_immich)
    open_with(client, "123456")
    idle_for(client, 16)
    assert client.post("/api/locked/activity").json()["open"] is True
    close_idle(client)
    assert client.get("/api/locked").json()["open"] is True


def test_an_action_does_not_open_a_closed_folder(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    client = connected(signed_in, fake_immich)
    assert client.post("/api/locked/activity").json()["open"] is False


def test_signing_out_closes_the_folder(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    client = connected(signed_in, fake_immich)
    open_with(client, "123456")
    client.post("/api/auth/logout")
    assert fake_immich.elevated == set()
    # The connection stays: the next sign-in only needs the PIN again.
    assert client.post("/api/auth/login", json={"api_key": "valid-key"}).status_code == 200
    state = client.get("/api/locked").json()
    assert state["connected"] is True and state["open"] is False


def test_closed_here_even_when_immich_is_down(
    signed_in: TestClient, fake_immich: FakeImmich
) -> None:
    client = connected(signed_in, fake_immich)
    open_with(client, "123456")
    fake_immich.sessions.clear()  # Immich answers 401 now
    assert client.post("/api/locked/close").json()["open"] is False
