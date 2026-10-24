# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application settings, read from environment variables with the ``STEWARD_`` prefix."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STEWARD_", env_file=".env", extra="ignore")

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

    @property
    def immich_browser_url(self) -> str | None:
        return (self.immich_public_url or self.immich_url or "").rstrip("/") or None

    @property
    def auto_module_ids(self) -> list[str]:
        return [m.strip() for m in self.auto_modules.split(",") if m.strip()]

    # Set to true when the UI is served over HTTPS (e.g. behind a reverse proxy).
    cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
