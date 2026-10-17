# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only checks against a real Immich server.

Run only when STEWARD_TEST_IMMICH_URL and STEWARD_TEST_IMMICH_API_KEY point to a test account.
These tests never modify anything in Immich.
"""

import asyncio
import os

import pytest

from steward.auth import verify_api_key
from steward.immich import ImmichClient
from steward.immich.compat import is_supported

URL = os.environ.get("STEWARD_TEST_IMMICH_URL")
API_KEY = os.environ.get("STEWARD_TEST_IMMICH_API_KEY")

pytestmark = pytest.mark.skipif(
    not (URL and API_KEY), reason="STEWARD_TEST_IMMICH_URL / _API_KEY are not set"
)


def test_server_is_supported() -> None:
    async def run() -> None:
        assert URL
        async with ImmichClient(URL) as client:
            assert is_supported(await client.server_version())

    asyncio.run(run())


def test_api_key_is_accepted() -> None:
    async def run() -> None:
        assert URL and API_KEY
        async with ImmichClient(URL, API_KEY) as client:
            user = await verify_api_key(client)
        assert user.name

    asyncio.run(run())
