# SPDX-License-Identifier: AGPL-3.0-or-later
"""The run of a job by an index: a worker asking for a job no longer waits seconds.

Leasing a job checks for every queued job whether its photo waits for the locked folder, through
`module_run.job_id`; without an index that was a scan of all runs, 7 s per lease on a library of
100 000 photos (2026-11-22).

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_module_run_job", "module_run", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_module_run_job", "module_run")
