# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application settings, read from environment variables with the ``STEWARD_`` prefix."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STEWARD_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://steward:steward@localhost:5432/steward"
    # Directory with the built web UI. When unset or missing, only the API is served.
    static_dir: Path | None = None
    log_level: str = "info"


@lru_cache
def get_settings() -> Settings:
    return Settings()
