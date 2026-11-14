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
    # The app marks a photo as showing no sign of a place when at least this many photos the user
    # marked are among its neighbors, at least this alike (`steward.view_groups.auto_mark`, D-200).
    "trash_auto": True,
    "trash_auto_marks": 3,
    "trash_auto_similarity": 0.5,
    # Matching details (the `details` module of workers, D-225): a suggestion of similar photos is
    # confirmed when the photo and a photo behind it share at least this many points that fit one
    # geometry. Measured on a family library (2026-11-14, 300 photos with camera GPS against
    # their 20 most similar): from 100 points the place is right within 1 km 95 % of the time,
    # with 50-99 about half the time. Applies when the suggestions are shown.
    "details_confirmed_from": 100,
    # Similar photos with a confirmed suggestion go before every other module in the card; off:
    # the block stays where the account put it. Within the block the confirmed suggestion is
    # always first.
    "details_first": True,
    # How many of the most similar photos a photo is compared with: when the comparison runs by
    # itself (workers with a GPU only) and when it is started by hand (any worker; on a CPU a
    # comparison takes a couple of seconds).
    "details_candidates_auto": 20,
    "details_candidates_manual": 5,
}
# Settings whose change rebuilds the groups.
GROUP_RULE = (
    "groups_similarity",
    "groups_core_neighbors",
    "groups_mutual",
    "trash_auto",
    "trash_auto_marks",
    "trash_auto_similarity",
)


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
