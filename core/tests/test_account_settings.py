# SPDX-License-Identifier: AGPL-3.0-or-later
from fastapi.testclient import TestClient


def test_defaults_then_changed(signed_in: TestClient) -> None:
    assert signed_in.get("/api/settings").json() == {"gallery_tooltip": True}

    changed = signed_in.put("/api/settings", json={"gallery_tooltip": False})
    assert changed.json() == {"gallery_tooltip": False}
    assert signed_in.get("/api/settings").json() == {"gallery_tooltip": False}

    # A setting not given stays as it is.
    assert signed_in.put("/api/settings", json={}).json() == {"gallery_tooltip": False}
    assert signed_in.put("/api/settings", json={"gallery_tooltip": True}).json() == {
        "gallery_tooltip": True
    }


def test_signed_out_gets_nothing(client: TestClient) -> None:
    assert client.get("/api/settings").status_code == 401
