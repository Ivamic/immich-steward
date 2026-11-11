# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Immich client with a session token: the locked folder (D-216, D-220)."""

import asyncio

import pytest
from conftest import FakeImmich

from steward.immich import ImmichAuthError, ImmichPinError

URL = "http://immich.test"


async def _session(fake: FakeImmich) -> str:
    async with fake.factory(URL) as client:
        return (await client.login(fake.email, fake.password)).access_token


def test_unlock_and_lock_the_folder(fake_immich: FakeImmich) -> None:
    async def run() -> None:
        token = await _session(fake_immich)
        async with fake_immich.factory(URL, session_token=token) as client:
            status = await client.auth_status()
            assert status.pin_code and not status.is_elevated
            await client.unlock_session("123456")
            assert (await client.auth_status()).is_elevated
            await client.lock_session()
            assert not (await client.auth_status()).is_elevated

    asyncio.run(run())


def test_a_wrong_pin_and_no_pin_are_told_apart(fake_immich: FakeImmich) -> None:
    async def run() -> None:
        token = await _session(fake_immich)
        async with fake_immich.factory(URL, session_token=token) as client:
            with pytest.raises(ImmichPinError) as wrong:
                await client.unlock_session("000000")
            assert not wrong.value.no_pin
            fake_immich.pin_code = None
            with pytest.raises(ImmichPinError) as missing:
                await client.unlock_session("123456")
            assert missing.value.no_pin
        assert not fake_immich.elevated

    asyncio.run(run())


def test_a_session_ended_in_immich_is_refused(fake_immich: FakeImmich) -> None:
    async def run() -> None:
        token = await _session(fake_immich)
        fake_immich.sessions.clear()  # the password changed, or "sign out everywhere"
        async with fake_immich.factory(URL, session_token=token) as client:
            with pytest.raises(ImmichAuthError):
                await client.auth_status()

    asyncio.run(run())


def test_the_session_goes_as_a_bearer_token_not_with_the_key(
    fake_immich: FakeImmich,
) -> None:
    async def run() -> None:
        token = await _session(fake_immich)
        async with fake_immich.factory(URL, "valid-key", session_token=token) as client:
            await client.auth_status()
        assert fake_immich.session_requests == ["/api/auth/status"]

    asyncio.run(run())
