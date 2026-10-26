# SPDX-License-Identifier: AGPL-3.0-or-later
"""Workers the core refused to register because one side is too old for the other, so that the
Processing page can say which one to update. Kept in memory only: a refused worker tries again
every few seconds, so after a restart of the core it shows up again at once."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# The worker is older than the oldest protocol the core still speaks: update the worker.
WORKER_TOO_OLD = "worker_too_old"
# The worker needs a newer core: update the server.
CORE_TOO_OLD = "core_too_old"


@dataclass(frozen=True)
class Refusal:
    name: str
    version: str
    reason: str
    at: datetime


class WorkerRefusals:
    def __init__(self) -> None:
        self._by_name: dict[str, Refusal] = {}

    def note(self, name: str, version: str, reason: str) -> None:
        self._by_name[name] = Refusal(name, version, reason, datetime.now(UTC))

    def forget(self, name: str) -> None:
        self._by_name.pop(name, None)

    def recent(self, within: timedelta) -> list[Refusal]:
        since = datetime.now(UTC) - within
        return sorted(
            (r for r in self._by_name.values() if r.at >= since), key=lambda r: r.name.lower()
        )
