# SPDX-License-Identifier: AGPL-3.0-or-later
import asyncio

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from conftest import ALEMBIC_INI
from sqlalchemy import text

from steward.db import create_engine


def _set_revision(database: str, revision: str) -> None:
    async def update() -> None:
        engine = create_engine(database)
        async with engine.begin() as conn:
            await conn.execute(text("UPDATE alembic_version SET version_num = :r"), {"r": revision})
        await engine.dispose()

    asyncio.run(update())


def test_database_of_a_newer_version_stops_with_a_clear_message(migrated_database: str) -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", migrated_database)
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    _set_revision(migrated_database, "9999_from_the_future")
    try:
        with pytest.raises(SystemExit, match=r"newer version of Steward.*9999_from_the_future"):
            command.upgrade(config, "head")
    finally:
        _set_revision(migrated_database, head)
