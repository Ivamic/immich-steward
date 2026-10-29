# SPDX-License-Identifier: AGPL-3.0-or-later
"""Checks whether a newer release of the app is out (D-159): twice a day the core asks GitHub for
the number of the latest release. GitHub sees the IP address of the server and the version in the
User-Agent; no photos and no data of the library leave the server. On by default, it can be turned
off in Settings for the whole installation."""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx2
from sqlalchemy.ext.asyncio import AsyncSession

from steward import __version__
from steward.models import AppSetting

log = logging.getLogger(__name__)

# The latest release that is neither a draft nor a pre-release (D-160).
LATEST_RELEASE_URL = "https://api.github.com/repos/Ivamic/immich-steward/releases/latest"
CHECK_EVERY = timedelta(hours=12)
RETRY_AFTER_ERROR = timedelta(hours=1)
TIMEOUT_S = 10.0
KEY = "update_check"


@dataclass
class UpdateState:
    enabled: bool = True
    # The latest release found, e.g. "0.6.1", and the page of its release notes.
    latest: str | None = None
    url: str | None = None
    checked_at: datetime | None = None
    # Why the last check failed: "unreachable", "http_<status>" or "bad_answer".
    error: str | None = None

    @property
    def newer(self) -> bool:
        return self.latest is not None and is_newer(self.latest, __version__)


_PRE_RELEASE = {"dev": 0, "a": 1, "alpha": 1, "b": 2, "beta": 2, "c": 3, "rc": 3, "pre": 3}


def version_key(version: str) -> tuple[int, ...]:
    """ "v0.10.2" -> (0, 10, 2, 1, 0, 0); a pre-release ("0.6.0rc2", "0.6.0-rc.2") is older than
    its release, a post-release newer. The worker compares the same way
    (`steward_worker.versions`)."""
    match = re.match(r"v?(\d+(?:\.\d+)*)[-_.]?([a-z]*)[-_.]?(\d*)", version.strip().lower())
    if not match:
        return ()
    numbers = tuple(int(part) for part in match[1].split("."))
    numbers += (0,) * (3 - len(numbers))
    label, number = match[2], int(match[3] or 0)
    if not label:
        stage = (1, 0, 0)
    elif label == "post":
        stage = (2, 0, number)
    else:
        stage = (0, _PRE_RELEASE.get(label, 0), number)
    return numbers + stage


def is_newer(version: str, than: str) -> bool:
    return version_key(version) > version_key(than)


async def load(db: AsyncSession) -> UpdateState:
    row = await db.get(AppSetting, KEY)
    if row is None:
        return UpdateState()
    value = row.value
    checked_at = value.get("checked_at")
    return UpdateState(
        enabled=bool(value.get("enabled", True)),
        latest=value.get("latest"),
        url=value.get("url"),
        checked_at=datetime.fromisoformat(checked_at) if checked_at else None,
        error=value.get("error"),
    )


async def save(db: AsyncSession, state: UpdateState) -> None:
    value = {
        "enabled": state.enabled,
        "latest": state.latest,
        "url": state.url,
        "checked_at": state.checked_at.isoformat() if state.checked_at else None,
        "error": state.error,
    }
    row = await db.get(AppSetting, KEY)
    if row is None:
        db.add(AppSetting(key=KEY, value=value))
    else:
        row.value = value
    await db.commit()


async def set_enabled(db: AsyncSession, enabled: bool) -> UpdateState:
    state = await load(db)
    state.enabled = enabled
    await save(db, state)
    return state


async def check(
    db: AsyncSession, transport: httpx2.AsyncBaseTransport | None = None
) -> UpdateState:
    """Asks GitHub for the latest release now, whether due or not, and keeps the answer."""
    state = await load(db)
    state.checked_at = datetime.now(UTC)
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"immich-steward/{__version__}",
    }
    try:
        async with httpx2.AsyncClient(
            timeout=TIMEOUT_S, headers=headers, transport=transport
        ) as http:
            response = await http.get(LATEST_RELEASE_URL)
    except httpx2.HTTPError as exc:
        log.info("update check: GitHub is not reachable (%s)", type(exc).__name__)
        state.error = "unreachable"
    else:
        if response.status_code == 404:
            # No release yet that is not a pre-release.
            state.latest, state.url, state.error = None, None, None
        elif not response.is_success:
            log.info("update check: GitHub answered HTTP %s", response.status_code)
            state.error = f"http_{response.status_code}"
        else:
            try:
                release = response.json()
                tag, url = str(release["tag_name"]), str(release["html_url"])
            except (ValueError, KeyError, TypeError):
                state.error = "bad_answer"
            else:
                state.latest, state.url, state.error = tag.removeprefix("v"), url, None
    await save(db, state)
    return state


async def check_if_due(
    db: AsyncSession, transport: httpx2.AsyncBaseTransport | None = None
) -> UpdateState:
    state = await load(db)
    if not state.enabled:
        return state
    wait = RETRY_AFTER_ERROR if state.error else CHECK_EVERY
    if state.checked_at is not None and datetime.now(UTC) - state.checked_at < wait:
        return state
    return await check(db, transport)
