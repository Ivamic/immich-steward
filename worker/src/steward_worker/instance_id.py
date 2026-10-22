# SPDX-License-Identifier: AGPL-3.0-or-later
"""An id of this worker that outlives restarts.

The core refuses a worker name while another running worker holds it, and a worker that was
killed without saying goodbye holds its name for a few minutes. With the same id, a restarted
worker (a recreated Docker container, say) is known at once to be the same one.
"""

import logging
import re
from pathlib import Path
from uuid import UUID, uuid4

log = logging.getLogger(__name__)


def default_path(name: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name) or "worker"
    return Path.home() / ".cache" / "steward-worker" / f"{safe}.id"


def load_instance_id(path: Path) -> UUID:
    """The id stored in the file; a new one, stored there, the first time. If the file cannot
    be written, the id lasts as long as the process (as before)."""
    try:
        return UUID(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        pass
    new = uuid4()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{new}\n", encoding="ascii")
    except OSError as exc:
        log.warning(
            "cannot keep the worker id in %s (%s): a restart may wait for its name", path, exc
        )
    return new
