# SPDX-License-Identifier: AGPL-3.0-or-later
from fastapi.testclient import TestClient

DEFAULTS = {
    "gallery_tooltip": True,
    "video_sound": False,
    "groups_similarity": 0.4,
    "groups_core_neighbors": 3,
    "groups_mutual": True,
}


def test_defaults_then_changed(signed_in: TestClient) -> None:
    assert signed_in.get("/api/settings").json() == DEFAULTS

    changed = signed_in.put("/api/settings", json={"gallery_tooltip": False})
    assert changed.json() == DEFAULTS | {"gallery_tooltip": False}
    assert signed_in.get("/api/settings").json() == DEFAULTS | {"gallery_tooltip": False}

    # A setting not given stays as it is.
    assert signed_in.put("/api/settings", json={}).json() == DEFAULTS | {"gallery_tooltip": False}
    both = {"gallery_tooltip": True, "video_sound": True}
    assert signed_in.put("/api/settings", json=both).json() == DEFAULTS | both


def test_signed_out_gets_nothing(client: TestClient) -> None:
    assert client.get("/api/settings").status_code == 401
