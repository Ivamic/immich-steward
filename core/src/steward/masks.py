# SPDX-License-Identifier: AGPL-3.0-or-later
"""Masks of people, animals and vehicles before matching details (D-248, D-256).

A worker's `details` leaves out the points on the groups the account chose before it matches two
photos: points on a person or a dog seen on both photos are no sign of one place (measured on a
family library: all 32 wrong "confirmed" of 486 lay on people and animals). A pair compared with
masks is confirmed from fewer points (`details_masked_from`, 80) than one without
(`details_confirmed_from`, 100).

Each comparison keeps with which masks it was made (`DetailMatch.mask_key`). When the account's
masks change (or after an update, for the pairs compared before masks existed), `requeue` has the
pairs compared again where it can change anything: where one of the photos has any of the groups
(`AssetObjects`, the module `objects`), or where masks were used and are off now. The other pairs
only take the new key: without those groups in them their answer is the same to the bit.
"""

import logging
from collections import defaultdict
from collections.abc import Mapping
from typing import Any, NamedTuple
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from steward import account_settings, worker_queue
from steward.models import Account, Asset, AssetObjects, DetailMatch, ModuleRun, Worker
from steward.updates import version_key

log = logging.getLogger(__name__)

GROUPS = ("person", "animal", "vehicle")
# Pixels the masks grow by, of the copy of 1024 px the details are matched at (measured: 6 and
# 12 differ by a couple of pairs, 6 loses fewer right ones).
GROW = 6
OFF = "off"
# Workers from this version mask; older ones get no comparisons while masks are on (D-256).
MASKING_WORKER = (0, 15, 0)
DETAILS = "details"
# Photos whose pairs are queued again in one pass, at most.
REQUEUE_BATCH = 50


class Shared(NamedTuple):
    """What a pair of photos shares: the points that fit one geometry, and whether people,
    animals or vehicles were left out first."""

    inliers: int
    masked: bool


def groups_of(personal: Mapping[str, Any]) -> list[str]:
    if not personal["masks_enabled"]:
        return []
    return [g for g in GROUPS if g in (personal["masks_groups"] or [])]


def key_of(personal: Mapping[str, Any]) -> str:
    """With which masks the account's comparisons are made now: "person+animal:6", or "off"."""
    groups = groups_of(personal)
    return f"{'+'.join(groups)}:{GROW}" if groups else OFF


def param_of(personal: Mapping[str, Any]) -> dict[str, Any] | None:
    """What a worker is asked to leave out, or None."""
    groups = groups_of(personal)
    return {"groups": groups, "grow": GROW} if groups else None


def is_confirmed(shared: Shared | None, personal: Mapping[str, Any]) -> bool:
    if shared is None:
        return False
    least = personal["details_masked_from"] if shared.masked else personal["details_confirmed_from"]
    return shared.inliers >= int(least)


def enough(personal: Mapping[str, Any]) -> ColumnElement[bool]:
    """SQL: the pair of a `DetailMatch` row shares enough points to confirm."""
    return or_(
        and_(DetailMatch.masked.is_(True), DetailMatch.inliers >= personal["details_masked_from"]),
        and_(
            DetailMatch.masked.is_not(True),
            DetailMatch.inliers >= personal["details_confirmed_from"],
        ),
    )


def masking_worker(worker: Worker) -> bool:
    return version_key(worker.version)[:3] >= MASKING_WORKER


async def any_on(db: AsyncSession) -> bool:
    """Whether some account has masks on (the default): then older workers compare nothing."""
    for account_id in await db.scalars(select(Account.id)):
        if groups_of(await account_settings.get_all(db, account_id)):
            return True
    return False


async def requeue(db: AsyncSession) -> int:
    """Brings the comparisons to the masks of their accounts (see the module): pairs where it
    changes nothing take the key, the others are compared again, the ones with the most points
    first. Leaves alone what still waits for the module `objects` and photos already queued.
    Returns how many photos were queued."""
    queued = 0
    for account_id in list(await db.scalars(select(Account.id))):
        personal = await account_settings.get_all(db, account_id)
        queued += await _requeue_account(db, account_id, personal)
    return queued


async def _requeue_account(db: AsyncSession, account_id: UUID, personal: dict[str, Any]) -> int:
    key = key_of(personal)
    groups = groups_of(personal)
    rows = list(
        (
            await db.execute(
                select(DetailMatch.asset_id, DetailMatch.other_id, DetailMatch.masked)
                .join(Asset, Asset.id == DetailMatch.asset_id)
                .where(
                    Asset.account_id == account_id,
                    or_(DetailMatch.mask_key.is_(None), DetailMatch.mask_key != key),
                )
                .order_by(DetailMatch.inliers.desc())
                .limit(2000)
            )
        ).all()
    )
    if not rows:
        return 0
    ids = {a for a, _, _ in rows} | {o for _, o, _ in rows}
    objects = {
        asset_id: found
        for asset_id, found in await db.execute(
            select(AssetObjects.asset_id, AssetObjects.groups).where(AssetObjects.asset_id.in_(ids))
        )
    }

    def has_groups(asset_id: UUID) -> bool | None:
        found = objects.get(asset_id)
        if found is None:
            return None  # not looked at yet
        return any(g in found for g in groups)

    settle: list[tuple[UUID, UUID]] = []
    again: dict[UUID, list[UUID]] = defaultdict(list)
    for asset_id, other_id, masked in rows:
        if key == OFF:
            # Masks off: only the pairs compared with masks change.
            (again[asset_id].append(other_id) if masked else settle.append((asset_id, other_id)))
            continue
        first, second = has_groups(asset_id), has_groups(other_id)
        if first or second:
            again[asset_id].append(other_id)
        elif first is False and second is False and not masked:
            settle.append((asset_id, other_id))
        # else: waits for the module `objects`
    for asset_id, other_id in settle:
        await db.execute(
            update(DetailMatch)
            .where(DetailMatch.asset_id == asset_id, DetailMatch.other_id == other_id)
            .values(mask_key=key, masked=None if key == OFF else False)
        )
    busy = set(
        await db.scalars(
            select(ModuleRun.asset_id).where(
                ModuleRun.asset_id.in_(list(again)),
                ModuleRun.module_id == DETAILS,
                ModuleRun.status.in_(worker_queue.ACTIVE),
            )
        )
    )
    queued = 0
    for asset_id, others in again.items():
        if asset_id in busy or queued >= REQUEUE_BATCH:
            continue
        asset = await db.get(Asset, asset_id)
        if asset is None:
            continue
        await worker_queue.enqueue_pairs(db, asset, DETAILS, others)
        queued += 1
    await db.commit()
    if queued or settle:
        log.info(
            "masks: %d pairs took the key %s, %d photos queued to compare again",
            len(settle),
            key,
            queued,
        )
    return queued


async def pending(db: AsyncSession, account_id: UUID) -> int:
    """Pairs of the account not compared with its masks yet (for "being compared again")."""
    key = key_of(await account_settings.get_all(db, account_id))
    count = await db.scalar(
        select(func.count())
        .select_from(DetailMatch)
        .join(Asset, Asset.id == DetailMatch.asset_id)
        .where(
            Asset.account_id == account_id,
            or_(DetailMatch.mask_key.is_(None), DetailMatch.mask_key != key),
        )
    )
    return int(count or 0)
