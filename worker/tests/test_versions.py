# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from steward_worker import versions
from steward_worker.versions import is_newer, release_tag, update_hint


def test_versions_compare_as_in_the_core() -> None:
    assert is_newer("0.10.0", "0.9.9")
    assert is_newer("0.6.1", "0.6.0")
    assert is_newer("0.6.0", "0.6.0rc2")
    assert is_newer("0.6.0rc2", "0.6.0-rc.1")
    assert not is_newer("0.6.0", "0.6")
    assert not is_newer("0.6.0rc2", "0.6.0")


def test_the_git_tag_of_a_version() -> None:
    assert release_tag("0.6.1") == "v0.6.1"
    assert release_tag("0.6.0rc2") == "v0.6.0-rc.2"
    assert release_tag("0.6.0-rc.2") == "v0.6.0-rc.2"


def test_a_worker_from_source_is_told_the_git_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(versions.IN_IMAGE_ENV, raising=False)
    monkeypatch.setattr(versions, "find_spec", lambda package: package == "safetensors")
    monkeypatch.setattr(versions, "version", lambda _: "2.14.1+cu130")
    assert update_hint("0.6.1") == (
        "git fetch --tags && git checkout v0.6.1 && "
        "uv sync --frozen --no-dev --package steward-worker --extra similar --extra cuda"
    )


def test_a_worker_in_the_image_is_told_the_docker_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(versions.IN_IMAGE_ENV, "1")
    assert "docker compose pull" in update_hint("0.6.1")
    assert versions.IMAGE in update_hint("0.6.1")
