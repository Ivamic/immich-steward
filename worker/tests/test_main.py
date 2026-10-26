# SPDX-License-Identifier: AGPL-3.0-or-later
import socket

import pytest

from steward_worker import __main__
from steward_worker.__main__ import parse_args
from steward_worker.modules import AVAILABLE


def test_empty_environment_values_count_as_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    # A line `STEWARD_X=` in .env reaches the container as an empty value (env_file).
    for name in ("MODULES", "NAME", "THREADS", "UNLOAD_AFTER_MINUTES", "DEVICE", "MAX_LOAD"):
        monkeypatch.setenv(f"STEWARD_WORKER_{name}", "")
    monkeypatch.setenv("STEWARD_LOG_LEVEL", "")

    args = parse_args([])

    assert args.modules == ",".join(AVAILABLE)
    assert args.name == socket.gethostname()
    assert args.threads == 2
    assert args.unload_after == 10
    assert args.device == "auto"
    assert args.max_load is None
    assert args.log_level == "info"


def test_old_name_of_a_renamed_setting_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(__main__, "RENAMED", {"STEWARD_WORKER_THREADS": "STEWARD_OLD_THREADS"})
    monkeypatch.delenv("STEWARD_WORKER_THREADS", raising=False)
    monkeypatch.setenv("STEWARD_OLD_THREADS", "5")

    assert parse_args([]).threads == 5
