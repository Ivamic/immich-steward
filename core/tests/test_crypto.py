# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from steward.crypto import SecretBox


def test_round_trip_and_no_plaintext() -> None:
    box = SecretBox("a" * 32)
    token = box.encrypt("my-api-key")
    assert "my-api-key" not in token
    assert box.decrypt(token) == "my-api-key"


def test_wrong_secret_key_fails() -> None:
    token = SecretBox("a" * 32).encrypt("my-api-key")
    with pytest.raises(ValueError):
        SecretBox("b" * 32).decrypt(token)
