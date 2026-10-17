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
    # Encrypts stored Immich API keys. Changing it invalidates all stored keys.
    secret_key: SecretStr | None = Field(default=None, min_length=MIN_SECRET_KEY_LENGTH)

    session_ttl_days: int = 30

    # Background jobs run inside the core process; tests switch this off.
    run_jobs: bool = True
    # Automatic incremental sync with Immich; 0 disables it.
    sync_interval_minutes: int = 15
    # Automatic syncs become full (also detecting deleted assets) this often.
    full_sync_interval_hours: int = 24
    # Set to true when the UI is served over HTTPS (e.g. behind a reverse proxy).
    cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
