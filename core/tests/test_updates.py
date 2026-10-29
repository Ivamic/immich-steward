# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from fastapi.testclient import TestClient

from steward import __version__, updates
from steward.updates import is_newer, version_key


def release(tag: str) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url == updates.LATEST_RELEASE_URL
        assert request.headers["User-Agent"] == f"immich-steward/{__version__}"
        url = f"https://github.com/Ivamic/immich-steward/releases/tag/{tag}"
        return httpx2.Response(200, json={"tag_name": tag, "html_url": url})

    return httpx2.MockTransport(handler)


def answer(status: int) -> httpx2.MockTransport:
    return httpx2.MockTransport(lambda _: httpx2.Response(status, json={}))


def unreachable(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ConnectError("no network", request=request)


def test_versions_compare_as_numbers() -> None:
    assert version_key("v0.10.2") == (0, 10, 2, 1, 0, 0)
    assert version_key("0.6.0-rc.1") == version_key("0.6.0rc1")
    assert is_newer("0.10.0", "0.9.9")
    assert is_newer("v1.0.0", "0.6.3")
    assert is_newer("0.6", "0.5.9")
    assert not is_newer("0.6.0", "0.6.0")
    assert not is_newer("0.6", "0.6.0")
    assert not is_newer("0.5.1", "0.6.0")


def test_a_pre_release_is_older_than_its_release() -> None:
    # A server on 0.6.0rc2 did not see 0.6.0 as newer.
    assert is_newer("0.6.0", "0.6.0rc2")
    assert is_newer("0.6.0rc2", "0.6.0rc1")
    assert is_newer("0.6.0rc1", "0.6.0b3")
    assert is_newer("0.6.0rc1", "0.5.9")
    assert is_newer("0.6.0.post1", "0.6.0")
    assert not is_newer("0.6.0rc2", "0.6.0")


def test_a_newer_release_is_found_and_kept(signed_in: TestClient) -> None:
    assert signed_in.get("/api/updates").json() == {
        "enabled": True,
        "current": __version__,
        "latest": None,
        "newer": False,
        "url": None,
        "checked_at": None,
        "error": None,
    }
    signed_in.app.state.update_transport = release("v99.0.0")  # type: ignore[attr-defined]

    checked = signed_in.post("/api/updates/check").json()

    assert checked["latest"] == "99.0.0"
    assert checked["newer"] is True
    assert checked["url"].endswith("/releases/tag/v99.0.0")
    assert checked["checked_at"]
    assert signed_in.get("/api/updates").json() == checked


def test_the_same_version_is_not_newer(signed_in: TestClient) -> None:
    signed_in.app.state.update_transport = release(f"v{__version__}")  # type: ignore[attr-defined]
    checked = signed_in.post("/api/updates/check").json()
    assert checked["latest"] == __version__
    assert checked["newer"] is False


@pytest.mark.parametrize(
    ("transport", "error"),
    [
        (httpx2.MockTransport(unreachable), "unreachable"),
        (answer(403), "http_403"),
        (answer(200), "bad_answer"),
        # No release yet that is not a pre-release: nothing to offer, and no error.
        (answer(404), None),
    ],
)
def test_failed_checks_are_recorded(
    signed_in: TestClient, transport: httpx2.MockTransport, error: str | None
) -> None:
    signed_in.app.state.update_transport = transport  # type: ignore[attr-defined]
    checked = signed_in.post("/api/updates/check").json()
    assert checked["error"] == error
    assert checked["newer"] is False


def test_turned_off_it_asks_nobody(signed_in: TestClient) -> None:
    def fail(_: httpx2.Request) -> httpx2.Response:
        raise AssertionError("GitHub must not be asked")

    signed_in.app.state.update_transport = httpx2.MockTransport(fail)  # type: ignore[attr-defined]
    off = signed_in.put("/api/updates", json={"enabled": False}).json()
    assert off["enabled"] is False

    async def due() -> updates.UpdateState:
        async with signed_in.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            return await updates.check_if_due(db, httpx2.MockTransport(fail))

    assert signed_in.portal.call(due).checked_at is None  # type: ignore[union-attr]

    # Turned on again, it checks at once.
    signed_in.app.state.update_transport = release("v99.0.0")  # type: ignore[attr-defined]
    on = signed_in.put("/api/updates", json={"enabled": True}).json()
    assert on["enabled"] is True
    assert on["latest"] == "99.0.0"


def test_checks_wait_twelve_hours_and_one_after_an_error(signed_in: TestClient) -> None:
    calls = []

    def counting(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(500)

    async def due_after(hours: float) -> None:
        async with signed_in.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            state = await updates.load(db)
            if state.checked_at:
                state.checked_at = datetime.now(UTC) - timedelta(hours=hours)
                await updates.save(db, state)
            await updates.check_if_due(db, httpx2.MockTransport(counting))

    portal = signed_in.portal
    assert portal is not None
    portal.call(due_after, 0)
    assert len(calls) == 1  # never checked: at once
    portal.call(due_after, 0.5)
    assert len(calls) == 1  # failed half an hour ago: not yet
    portal.call(due_after, 1.5)
    assert len(calls) == 2  # failed over an hour ago: again
    signed_in.app.state.update_transport = release("v0.0.1")  # type: ignore[attr-defined]
    signed_in.post("/api/updates/check")
    portal.call(due_after, 11)
    assert len(calls) == 2  # succeeded 11 hours ago: not yet
    portal.call(due_after, 13)
    assert len(calls) == 3


def test_signed_out_gets_nothing(client: TestClient) -> None:
    assert client.get("/api/updates").status_code == 401
