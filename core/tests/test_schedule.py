# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hours a worker gets background jobs (D-238)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from steward import schedule
from steward.schedule import FULL_DAY

NIGHTS = [(1 << 23) | 0b1111111] * 7  # 23:00-06:59 every day


def at(day: int, hour: int, minute: int = 0) -> datetime:
    # 2026-11-23 is a Monday.
    return datetime(2026, 11, 23 + day, hour, minute, tzinfo=UTC)


def test_always_and_never() -> None:
    assert schedule.is_open(None, at(0, 12))
    assert schedule.next_change(None, at(0, 12)) is None
    assert not schedule.is_open([0] * 7, at(3, 3))
    assert schedule.next_change([0] * 7, at(3, 3)) is None


def test_every_hour_on_is_stored_as_always() -> None:
    assert schedule.normalized([FULL_DAY] * 7) is None
    assert schedule.normalized(NIGHTS) == NIGHTS
    assert schedule.normalized(None) is None


@pytest.mark.parametrize(
    ("day", "hour", "open_", "change"),
    [
        (0, 3, True, at(0, 7)),
        (0, 6, True, at(0, 7)),
        (0, 7, False, at(0, 23)),
        (0, 22, False, at(0, 23)),
        (0, 23, True, at(1, 7)),
    ],
)
def test_nights(day: int, hour: int, open_: bool, change: datetime) -> None:
    now = at(day, hour, 30)
    assert schedule.is_open(NIGHTS, now) is open_
    assert schedule.next_change(NIGHTS, now) == change


def test_days_of_the_week_start_on_monday() -> None:
    weekends = [0] * 5 + [FULL_DAY] * 2
    assert not schedule.is_open(weekends, at(4, 23))  # Friday
    assert schedule.is_open(weekends, at(5, 0))  # Saturday
    assert schedule.next_change(weekends, at(4, 23, 59)) == at(5, 0)
    assert schedule.next_change(weekends, at(6, 10)) == at(7, 0)  # next Monday


def test_hours_go_by_the_clock_given() -> None:
    berlin_winter = timezone(timedelta(hours=1))
    # 22:30 UTC is 23:30 in UTC+1: inside the night.
    now = datetime(2026, 11, 23, 22, 30, tzinfo=UTC)
    assert not schedule.is_open(NIGHTS, now)
    assert schedule.is_open(NIGHTS, now.astimezone(berlin_winter))


def test_server_zone_from_tz(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "No/Such_Zone")
    _, name = schedule.server_zone()
    assert name is None  # an unknown name: the system's clock
    monkeypatch.delenv("TZ")
    assert schedule.server_zone()[1] is None
