# SPDX-License-Identifier: AGPL-3.0-or-later
"""Whether this worker and the core run the same version, and how to bring them together.

The right version of a worker is the one of the core it works for, not the latest on GitHub: the
worker asks nobody but the core. Versions compare as in the core (`steward.updates`).
"""

import contextlib
import os
import re
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec

# Set in the worker image: a worker there is updated with Docker, not with Git.
IN_IMAGE_ENV = "STEWARD_WORKER_IMAGE"
IMAGE = "ghcr.io/ivamic/immich-steward-worker:0"

_PRE_RELEASE = {"dev": 0, "a": 1, "alpha": 1, "b": 2, "beta": 2, "c": 3, "rc": 3, "pre": 3}


def version_key(text: str) -> tuple[int, ...]:
    """ "v0.10.2" -> (0, 10, 2, 1, 0, 0); a pre-release ("0.6.0rc2", "0.6.0-rc.2") is older than
    its release, a post-release newer."""
    match = re.match(r"v?(\d+(?:\.\d+)*)[-_.]?([a-z]*)[-_.]?(\d*)", text.strip().lower())
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


def release_tag(version: str) -> str:
    """The Git tag of a version: "0.6.1" -> "v0.6.1", "0.6.0rc2" (as Python spells it) ->
    "v0.6.0-rc.2"."""
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)[-_.]?(a|b|rc)\.?(\d+)", version.strip().lower())
    if match:
        label = {"a": "alpha", "b": "beta"}.get(match[2], match[2])
        return f"v{match[1]}-{label}.{match[3]}"
    return "v" + version.strip().removeprefix("v")


def update_hint(core_version: str) -> str:
    """The commands that bring this worker to the version of the core."""
    if os.environ.get(IN_IMAGE_ENV):
        return (
            f"docker compose pull && docker compose --profile worker up -d (the worker on the "
            f"server), or docker pull {IMAGE} and start the container again (docker run)"
        )
    # The extras it was installed with, told by a package that only that extra brings.
    extras = [
        extra
        for extra, package in (("geoclip", "geoclip"), ("similar", "safetensors"))
        if find_spec(package)
    ]
    with contextlib.suppress(PackageNotFoundError):
        extras.append("cuda" if "+cu" in version("torch") else "cpu")
    sync = "uv sync --frozen --no-dev --package steward-worker" + "".join(
        f" --extra {extra}" for extra in extras
    )
    return f"git fetch --tags && git checkout {release_tag(core_version)} && {sync}"
