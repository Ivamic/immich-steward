# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from steward import config
from steward.config import Settings, apply_renamed, environment_warnings


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for name, value in env.items():
        monkeypatch.setenv(f"STEWARD_{name.upper()}", value)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_empty_value_means_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # A line `STEWARD_X=` in .env reaches the container as an empty value (env_file).
    settings = _settings(
        monkeypatch,
        session_ttl_days="",
        time_neighbors_window_hours="",
        similar_include_estimated="",
        map_style_url="",
        log_level="",
        secret_key="",
        immich_url="",
    )

    assert settings.session_ttl_days == 90
    assert settings.time_neighbors_window_hours == 3.0
    assert settings.similar_include_estimated is True
    assert settings.map_style_url == "https://tiles.openfreemap.org/styles/liberty"
    assert settings.log_level == "info"
    assert settings.secret_key is None
    assert settings.immich_url is None


def test_empty_value_turns_off_what_it_did_before(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(
        monkeypatch,
        geocoder_url="",
        estimated_tag="",
        auto_modules="",
        map_style_url_dark="",
        immich_public_url="",
        worker_token="",
    )

    assert settings.geocoder_url == ""
    assert settings.estimated_tag == ""
    assert settings.auto_module_ids == []
    assert settings.map_style_url_dark == ""
    assert settings.immich_browser_url is None
    assert settings.worker_token is not None
    assert settings.worker_token.get_secret_value() == ""


def test_unset_values_keep_their_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)

    assert settings.geocoder_url == "https://photon.komoot.io"
    assert settings.estimated_tag == "steward/estimated"
    assert settings.auto_module_ids == ["geoclip", "similar"]


def test_unknown_settings_are_reported_once() -> None:
    environ = {
        "STEWARD_IMMICH_URL": "http://immich",
        "STEWARD_WORKER_THREADS": "2",  # the worker's, from the same .env
        "STEWARD_VERSION": "0",  # compose.yaml's
        "STEWARD_IMMICH_ULR": "typo",
        "STEWARD_SOMETHING": "x",
        "PATH": "/usr/bin",
    }

    assert environment_warnings(environ) == [
        "Unknown settings, ignored: STEWARD_IMMICH_ULR, STEWARD_SOMETHING. Check them for "
        "typos; the settings are listed in docs/configuration.md"
    ]


def test_old_name_of_a_renamed_setting_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "RENAMED", {"STEWARD_GEOCODER": "STEWARD_GEOCODER_URL"})
    environ = {"STEWARD_GEOCODER": "http://photon.local"}

    apply_renamed(environ)

    assert environ["STEWARD_GEOCODER_URL"] == "http://photon.local"
    warnings = environment_warnings(environ)
    assert len(warnings) == 1
    assert warnings[0].startswith("STEWARD_GEOCODER is now called STEWARD_GEOCODER_URL")
    # The new name wins when both are set.
    both = {"STEWARD_GEOCODER": "old", "STEWARD_GEOCODER_URL": "new"}
    apply_renamed(both)
    assert both["STEWARD_GEOCODER_URL"] == "new"
