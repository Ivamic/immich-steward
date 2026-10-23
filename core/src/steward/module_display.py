# SPDX-License-Identifier: AGPL-3.0-or-later
"""Order of the modules in the photo card and which of them are hidden, per account.

Only the display: a hidden module still runs (pausing is `worker_queue`), so that showing it
again needs no new runs.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from steward.errors import ApiError
from steward.models import ModuleDisplay
from steward.modules import MODULES, REMOTE_MODULES

# Neighbors in time first: they are the most precise when there are any.
DEFAULT_ORDER = ("time_neighbors", "similar", "geoclip")


@dataclass(frozen=True)
class Display:
    module: str
    hidden: bool


def known_modules() -> list[str]:
    """Every module that shows suggestions, in the default order."""
    ids = [module.id for module in MODULES] + list(REMOTE_MODULES)
    return sorted(ids, key=lambda i: DEFAULT_ORDER.index(i) if i in DEFAULT_ORDER else len(ids))


async def get(db: AsyncSession, account_id: UUID) -> list[Display]:
    """All the modules, in the order of the account; modules it has not placed yet (none saved,
    or a module added by a newer version) follow, in the default order, and are shown."""
    rows = await db.scalars(select(ModuleDisplay).where(ModuleDisplay.account_id == account_id))
    stored = {row.module_id: row for row in rows}
    known = known_modules()

    def place(module_id: str) -> tuple[int, int]:
        row = stored.get(module_id)
        return (row.position if row else len(known), known.index(module_id))

    return [
        Display(module_id, hidden=module_id in stored and stored[module_id].hidden)
        for module_id in sorted(known, key=place)
    ]


async def save(db: AsyncSession, account_id: UUID, displays: list[Display]) -> list[Display]:
    """Stores the order and the hidden modules as given; every known module once."""
    ids = [d.module for d in displays]
    if sorted(ids) != sorted(known_modules()):
        raise ApiError(422, "module_display_invalid")
    await db.execute(delete(ModuleDisplay).where(ModuleDisplay.account_id == account_id))
    db.add_all(
        ModuleDisplay(account_id=account_id, module_id=d.module, position=i, hidden=d.hidden)
        for i, d in enumerate(displays)
    )
    await db.commit()
    return await get(db, account_id)
