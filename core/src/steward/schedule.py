# SPDX-License-Identifier: AGPL-3.0-or-later
"""When a worker gets background jobs (D-238): a week of hours, by the clock of the server.

A schedule is 7 numbers, Monday first (as `datetime.weekday`); bit `h` of a day is the hour
h:00-h:59. None: always, as before schedules existed. Outside its hours a worker gets only the
jobs started by hand; a job it already holds runs to the end.
"""

import os
from datetime import datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DAYS = 7
HOURS = 24
FULL_DAY = (1 << HOURS) - 1


def server_zone() -> tuple[tzinfo, str | None]:
    """The time zone of the server: `TZ` when it names one, else the system's (UTC in a
    container without `TZ`); with its name, if known."""
    name = os.environ.get("TZ", "").strip()
    if name:
        try:
            return ZoneInfo(name), name
        except (ZoneInfoNotFoundError, ValueError):
            pass
    local = datetime.now().astimezone().tzinfo
    assert local is not None
    return local, None


def normalized(schedule: list[int] | None) -> list[int] | None:
    """The schedule as stored: None for "always" (every hour on)."""
    if schedule is None or all(day == FULL_DAY for day in schedule):
        return None
    return schedule


def is_open(schedule: list[int] | None, now: datetime) -> bool:
    """Whether the hour of `now` (in the server's zone) is a working one."""
    if schedule is None:
        return True
    return bool(schedule[now.weekday()] >> now.hour & 1)


def next_change(schedule: list[int] | None, now: datetime) -> datetime | None:
    """The next hour at which the schedule turns from open to closed or back; None if it never
    does (always, or never)."""
    if schedule is None or not any(schedule) or all(day == FULL_DAY for day in schedule):
        return None
    current = is_open(schedule, now)
    hour = now.replace(minute=0, second=0, microsecond=0)
    for step in range(1, DAYS * HOURS + 1):
        at = hour + timedelta(hours=step)
        if is_open(schedule, at) != current:
            return at
    return None
