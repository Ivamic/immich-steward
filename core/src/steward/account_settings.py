# SPDX-License-Identifier: AGPL-3.0-or-later
"""Personal settings of an account: simple switches, each a row of `account_setting` holding
{"value": ...}; a setting without a row has its default."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steward.models import AccountSetting

# Every personal setting and its default.
DEFAULTS: dict[str, Any] = {
    # The gallery shows its own tooltip (name, time taken, camera, size) over a tile, instead of
    # the file name alone.
    "gallery_tooltip": True,
    # A video shown large on a long press plays with its sound; off: muted.
    "video_sound": False,
    # Groups of photos of one view (`steward.view_groups`), by the measure on a family library
    # (D-181, D-182): photos at least this similar are close; a photo with this many close
    # neighbors is a core; close only when each keeps the other among its own neighbors.
    "groups_similarity": 0.47,
    "groups_core_neighbors": 3,
    "groups_mutual": True,
}
# Settings whose change rebuilds the groups.
GROUP_RULE = ("groups_similarity", "groups_core_neighbors", "groups_mutual")


async def get_all(db: AsyncSession, account_id: UUID) -> dict[str, Any]:
    rows = await db.scalars(select(AccountSetting).where(AccountSetting.account_id == account_id))
    stored = {row.key: row.value.get("value") for row in rows if row.key in DEFAULTS}
    return DEFAULTS | stored


async def set_many(db: AsyncSession, account_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
    for key, value in values.items():
        row = await db.get(AccountSetting, (account_id, key))
        if row is None:
            db.add(AccountSetting(account_id=account_id, key=key, value={"value": value}))
        else:
            row.value = {"value": value}
    await db.commit()
    return await get_all(db, account_id)
