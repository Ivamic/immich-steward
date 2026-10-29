# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application settings, read from environment variables with the ``STEWARD_`` prefix."""

import os
from collections.abc import Mapping, MutableMapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_KEY_LENGTH = 32
ENV_PREFIX = "STEWARD_"

# Renamed settings, old name -> new name. Within a major version the old name keeps working, with a
# warning in the log; drop an entry only in a new major version.
RENAMED: dict[str, str] = {}

# STEWARD_* names that are not settings of the core but share its .env: compose.yaml, the worker
# and the tests read them.
USED_ELSEWHERE = frozenset(
    {
        "STEWARD_VERSION",
        "STEWARD_PORT",
        "STEWARD_CORE_URL",
        "STEWARD_WORKER_NAME",
        "STEWARD_WORKER_MODULES",
        "STEWARD_WORKER_ONE_MODEL",
        "STEWARD_WORKER_THREADS",
        "STEWARD_WORKER_MAX_LOAD",
        "STEWARD_WORKER_UNLOAD_AFTER_MINUTES",
        "STEWARD_WORKER_DEVICE",
        "STEWARD_WORKER_ID_FILE",
        "STEWARD_WORKER_IMAGE",
        "STEWARD_WORKER_MEMORY_LIMIT",
        "STEWARD_TEST_DATABASE_URL",
    }
)

# Settings where an empty value turns something off; for every other one, an empty value (a line
# `STEWARD_X=` in .env) means "not set" and the default applies.
EMPTY_MEANS_OFF = frozenset(
    {
        "immich_public_url",
        "map_style_url_dark",
        "geocoder_url",
        "estimated_tag",
        "worker_token",
        "auto_modules",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://steward:steward@localhost:5432/steward"
    # Directory with the built web UI. When unset or missing, only the API is served.
    static_dir: Path | None = None
    log_level: str = "info"

    # Immich server shared by all users of this installation, e.g. http://192.168.1.10:2283
    immich_url: str | None = None
    # Address of Immich in the browsers of the users, for "Open in Immich" links, when it
    # differs from immich_url (e.g. that one is a Docker container name). Empty: immich_url.
    immich_public_url: str | None = None
    # Encrypts stored Immich API keys. Changing it invalidates all stored keys.
    secret_key: SecretStr | None = Field(default=None, min_length=MIN_SECRET_KEY_LENGTH)

    # Sessions are extended on use, so only this long without opening the app signs a user out.
    session_ttl_days: int = 90

    # Background jobs run inside the core process; tests switch this off.
    run_jobs: bool = True
    # Automatic incremental sync with Immich; 0 disables it.
    sync_interval_minutes: int = 15
    # Automatic syncs become full (also detecting deleted assets) this often.
    full_sync_interval_hours: int = 24

    # MapLibre style for the base map. OpenFreeMap needs no API key; data © OpenStreetMap.
    map_style_url: str = "https://tiles.openfreemap.org/styles/liberty"
    # The style for the dark theme of the web UI; empty: the style above, dimmed.
    map_style_url_dark: str = ""
    # Photon geocoder for address search (https://photon.komoot.io or a self-hosted one);
    # an empty value disables address search.
    geocoder_url: str = "https://photon.komoot.io"

    # M1 "time neighbors": located photos up to this many hours before or after count.
    time_neighbors_window_hours: float = Field(default=3.0, gt=0, le=48)
    # The gallery marks photos without a location that have a located one this close in time.
    time_neighbors_nearby_minutes: float = Field(default=15.0, gt=0, le=24 * 60)

    # Immich tag for coordinates written by the app (they are not from the camera GPS);
    # "a/b" is a nested tag. An empty value disables tagging.
    estimated_tag: str = "steward/estimated"

    # Shared secret of the workers that run ML modules (sent as a bearer token). Empty: the
    # worker API is off.
    worker_token: SecretStr | None = None
    # A leased job returns to the queue when its worker stays silent this long.
    worker_lease_seconds: int = Field(default=300, ge=30)
    # Worker modules run automatically on photos without a location (FR-10, FR-11) and, for
    # similar photos, on the photos with one too (its search index), comma-separated; empty turns
    # automatic runs off. Runs started by hand are always allowed.
    auto_modules: str = "geoclip,similar"
    # How GeoCLIP results are shown (they are stored in full, so changing these needs no rerun).
    # Measured on 506 photos with GPS: below 25 % a suggestion is rarely right (noise, hidden);
    # 25-50 % often hits the region only (weak, folded); from 75 % it is right about 95 % of the
    # time (marked as confident).
    geoclip_min_confidence: float = Field(default=0.25, ge=0, le=1)
    geoclip_weak_below: float = Field(default=0.5, ge=0, le=1)
    geoclip_confident_from: float = Field(default=0.75, ge=0, le=1)
    # How similar-photos (M3) suggestions are shown, on the calibrated scale of
    # `steward.modules.similar.CALIBRATION`: hidden below 20 % (similarity ~0.15), weak below
    # 50 % (~0.2), confident from 80 % (~0.35, right within 1 km about 85 % of the time).
    similar_min_confidence: float = Field(default=0.2, ge=0, le=1)
    similar_weak_below: float = Field(default=0.5, ge=0, le=1)
    similar_confident_from: float = Field(default=0.8, ge=0, le=1)
    # Photos whose location was set in this app are searched among too (D-106). The search runs
    # when the suggestions are shown, so a change applies at once, without running anything again.
    similar_include_estimated: bool = True

    # A worker counts as active this long after it last contacted the core. Idle workers ask for
    # jobs every 30 s at most, busy ones send a heartbeat every third of the lease.
    worker_active_minutes: int = Field(default=3, ge=1)

    @model_validator(mode="before")
    @classmethod
    def _empty_means_default(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        return {
            key: value
            for key, value in data.items()
            if not (value == "" and key not in EMPTY_MEANS_OFF)
        }

    @property
    def immich_browser_url(self) -> str | None:
        return (self.immich_public_url or self.immich_url or "").rstrip("/") or None

    @property
    def auto_module_ids(self) -> list[str]:
        return [m.strip() for m in self.auto_modules.split(",") if m.strip()]

    # Set to true when the UI is served over HTTPS (e.g. behind a reverse proxy).
    cookie_secure: bool = False


def apply_renamed(environ: MutableMapping[str, str]) -> None:
    """Lets an old name of a renamed setting stand for the new one, unless that is set too."""
    for old, new in RENAMED.items():
        if old in environ and new not in environ:
            environ[new] = environ[old]


def environment_warnings(environ: Mapping[str, str]) -> list[str]:
    """Warnings about the STEWARD_* variables: old names of renamed settings, and unknown names
    (a typo in .env has no effect otherwise)."""
    warnings = [
        f"{old} is now called {new}: rename it in .env (the old name works until the next "
        f"major version)"
        for old, new in RENAMED.items()
        if old in environ
    ]
    known = {ENV_PREFIX + name.upper() for name in Settings.model_fields} | USED_ELSEWHERE
    unknown = sorted(
        name
        for name in environ
        if name.startswith(ENV_PREFIX) and name not in known and name not in RENAMED
    )
    if unknown:
        warnings.append(
            f"Unknown settings, ignored: {', '.join(unknown)}. Check them for typos; the "
            f"settings are listed in docs/configuration.md"
        )
    return warnings


@lru_cache
def get_settings() -> Settings:
    apply_renamed(os.environ)
    return Settings()
