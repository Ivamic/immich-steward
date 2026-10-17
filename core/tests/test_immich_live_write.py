# SPDX-License-Identifier: AGPL-3.0-or-later
"""Checks against a real Immich server that WRITE to it. Run them by hand after an Immich update.

Undo of a location written over an empty one relies on undocumented behaviour: Immich turns
exactly (0, 0) into "no location". If this test fails, that undo no longer works.

Needs STEWARD_TEST_IMMICH_URL, STEWARD_TEST_IMMICH_API_KEY and, as an explicit consent,
STEWARD_TEST_IMMICH_WRITE_ASSET_ID: the id of a photo of a test account that may be changed.
The photo's coordinates are restored at the end.
"""

import asyncio
import os
from uuid import UUID

import pytest

from steward.immich import ImmichClient
from steward.locations import CLEAR_ATTEMPTS, CLEAR_POLL_S

URL = os.environ.get("STEWARD_TEST_IMMICH_URL")
API_KEY = os.environ.get("STEWARD_TEST_IMMICH_API_KEY")
ASSET_ID = os.environ.get("STEWARD_TEST_IMMICH_WRITE_ASSET_ID")

pytestmark = pytest.mark.skipif(
    not (URL and API_KEY and ASSET_ID),
    reason="STEWARD_TEST_IMMICH_URL / _API_KEY / _WRITE_ASSET_ID are not set",
)


async def _location(client: ImmichClient, asset_id: UUID) -> tuple[float | None, float | None]:
    exif = (await client.asset(asset_id)).exif_info
    return (exif.latitude, exif.longitude) if exif else (None, None)


def test_null_island_clears_location() -> None:
    async def run() -> None:
        assert URL and API_KEY and ASSET_ID
        asset_id = UUID(ASSET_ID)
        async with ImmichClient(URL, API_KEY) as client:
            original = await _location(client, asset_id)
            try:
                await client.set_location(asset_id, 42.4247, 18.7712)
                assert await _location(client, asset_id) == (42.4247, 18.7712)

                await client.set_location(asset_id, 0.0, 0.0)
                for _ in range(CLEAR_ATTEMPTS):
                    await asyncio.sleep(CLEAR_POLL_S)
                    if await _location(client, asset_id) == (None, None):
                        break
                assert await _location(client, asset_id) == (None, None), (
                    "Immich kept (0, 0): undo over an empty location no longer works"
                )
            finally:
                latitude, longitude = original
                if latitude is not None and longitude is not None:
                    await client.set_location(asset_id, latitude, longitude)
                elif await _location(client, asset_id) != (None, None):
                    await client.set_location(asset_id, 0.0, 0.0)

    asyncio.run(run())
