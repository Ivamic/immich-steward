# SPDX-License-Identifier: AGPL-3.0-or-later
from fastapi.testclient import TestClient

from steward.api.maps import _place


def test_photon_feature_to_place() -> None:
    place = _place(
        {
            "geometry": {"coordinates": [18.7713, 42.4249]},
            "properties": {
                "name": "Kotor",
                "city": "Kotor",
                "state": "Opština Kotor",
                "country": "Crna Gora",
                "osm_value": "town",
            },
        }
    )
    assert (place.latitude, place.longitude) == (42.4249, 18.7713)
    assert place.label == "Opština Kotor, Crna Gora"  # the name is not repeated
    assert place.kind == "town"


def test_map_config_requires_sign_in(client: TestClient) -> None:
    assert client.get("/api/config/map").status_code == 401


def test_map_config(signed_in: TestClient) -> None:
    config = signed_in.get("/api/config/map").json()
    assert config["style_url"].startswith("https://")
    assert config["style_url_dark"].startswith("https://")
    assert config["geocoder_enabled"] is True


def test_map_config_without_dark_style(signed_in: TestClient) -> None:
    signed_in.app.state.settings.map_style_url_dark = ""  # type: ignore[attr-defined]
    assert signed_in.get("/api/config/map").json()["style_url_dark"] is None
