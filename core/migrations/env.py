# SPDX-License-Identifier: AGPL-3.0-or-later
"""Alembic environment (async engine)."""

import asyncio
from logging.config import fileConfig

from alembic import context
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection

from steward import __version__
from steward.config import get_settings
from steward.db import create_engine
from steward.models import Base

config = context.config
if config.config_file_name is not None:
    # Keep the loggers of the app: the tests run the migrations inside their own process.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def database_url() -> str:
    # Tests pass the URL explicitly; otherwise it comes from STEWARD_DATABASE_URL.
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def check_known_revision() -> None:
    """Stops with a clear message when a newer version of the app has migrated the database:
    an older image started on it (e.g. STEWARD_VERSION pinned in .env) cannot work with it."""
    current = context.get_context().get_current_heads()
    known = {script.revision for script in ScriptDirectory.from_config(config).walk_revisions()}
    unknown = [revision for revision in current if revision not in known]
    if unknown:
        raise SystemExit(
            f"The database was updated by a newer version of Steward (revision "
            f"{', '.join(unknown)}); this is version {__version__}. Start that version or a newer "
            f"one: remove STEWARD_VERSION from .env or set it to a newer version, then run "
            f"docker compose pull && docker compose up -d."
        )


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        check_known_revision()
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_engine(database_url())
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
