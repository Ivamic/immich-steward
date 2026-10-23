# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Any

from conftest import FakeImmich, sync
from fastapi.testclient import TestClient

DEFAULT = [
    {"module": "time_neighbors", "hidden": False},
    {"module": "similar", "hidden": False},
    {"module": "geoclip", "hidden": False},
]


def suggestion_blocks(client: TestClient, fake: FakeImmich) -> list[dict[str, Any]]:
    fake.add_asset()
    sync(client)
    [item] = client.get("/api/assets", params={"month": "2024-05"}).json()
    response = client.get(f"/api/assets/{item['id']}/suggestions")
    assert response.status_code == 200
    return list(response.json())


def test_default_order(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    assert signed_in.get("/api/library/module-display").json() == DEFAULT
    blocks = suggestion_blocks(signed_in, fake_immich)
    assert [b["module"] for b in blocks] == ["time_neighbors", "similar", "geoclip"]
    assert not any(b["hidden"] for b in blocks)


def test_order_and_hidden_modules_are_kept(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    wanted = [
        {"module": "geoclip", "hidden": False},
        {"module": "time_neighbors", "hidden": False},
        {"module": "similar", "hidden": True},
    ]
    response = signed_in.put("/api/library/module-display", json=wanted)
    assert response.status_code == 200
    assert response.json() == wanted
    assert signed_in.get("/api/library/module-display").json() == wanted

    blocks = suggestion_blocks(signed_in, fake_immich)
    # Hidden modules still come, marked: the card can show them on request.
    assert [(b["module"], b["hidden"]) for b in blocks] == [
        ("geoclip", False),
        ("time_neighbors", False),
        ("similar", True),
    ]


def test_every_module_once(signed_in: TestClient) -> None:
    missing = DEFAULT[:2]
    twice = [*DEFAULT, DEFAULT[0]]
    unknown = [*DEFAULT[:2], {"module": "nope", "hidden": False}]
    for body in (missing, twice, unknown):
        response = signed_in.put("/api/library/module-display", json=body)
        assert response.status_code == 422
        assert response.json()["code"] == "module_display_invalid"


def test_each_account_has_its_own(signed_in: TestClient, fake_immich: FakeImmich) -> None:
    hidden = [{**d, "hidden": True} for d in DEFAULT]
    assert signed_in.put("/api/library/module-display", json=hidden).status_code == 200
    signed_in.post("/api/auth/logout")
    fake_immich.user_id = FakeImmich().user_id  # the same key now belongs to another user
    assert signed_in.post("/api/auth/login", json={"api_key": "valid-key"}).status_code == 200
    assert signed_in.get("/api/library/module-display").json() == DEFAULT
