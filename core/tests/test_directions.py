# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which way the camera looked (D-245): kept in the app, never written to Immich."""

from conftest import FakeImmich
from fastapi.testclient import TestClient
from test_regions import photo

__all__ = ["photo"]

STREET = {"heading": 48.0, "accuracy": 30.0, "source": "street", "source_ref": "mapillary:123"}


def test_a_direction_kept_with_the_location(
    signed_in: TestClient, fake_immich: FakeImmich, photo: tuple[str, str]
) -> None:
    asset, immich_id = photo
    assert signed_in.get(f"/api/assets/{asset}").json()["direction"] is None

    body = {"latitude": 42.43, "longitude": 18.7, "direction": STREET}
    saved = signed_in.put(f"/api/assets/{asset}/location", json=body)
    assert saved.status_code == 200
    assert saved.json()["direction"] == STREET
    # Immich gets the location only.
    exif = fake_immich.assets[immich_id]["exifInfo"]
    assert (exif["latitude"], exif["longitude"]) == (42.43, 18.7)
    assert "direction" not in str(fake_immich.assets[immich_id])

    # Saved again without one: the direction stays.
    body = {"latitude": 42.44, "longitude": 18.7}
    assert signed_in.put(f"/api/assets/{asset}/location", json=body).json()["direction"] == STREET


def test_set_and_forget(signed_in: TestClient, photo: tuple[str, str]) -> None:
    asset, _ = photo
    response = signed_in.put(f"/api/assets/{asset}/direction", json=STREET | {"heading": 359.5})
    assert response.json()["direction"]["heading"] == 359.5
    for bad in ({"heading": 360}, {"accuracy": 0}, {"source": "exif"}):
        assert signed_in.put(f"/api/assets/{asset}/direction", json=STREET | bad).status_code == 422
    assert signed_in.delete(f"/api/assets/{asset}/direction").json()["direction"] is None
    assert signed_in.delete(f"/api/assets/{asset}/direction").status_code == 200
