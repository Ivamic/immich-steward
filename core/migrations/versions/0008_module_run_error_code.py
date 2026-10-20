# SPDX-License-Identifier: AGPL-3.0-or-later
"""Failed module runs keep a code of why they failed.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("module_run", sa.Column("error_code", sa.String(32), nullable=True))
    # Before, a failure had only a text: a run out lease, or what the worker reported.
    op.execute(
        "UPDATE module_run SET error_code = CASE WHEN error = 'lease_expired' "
        "THEN 'lease_expired' ELSE 'module_error' END WHERE status = 'failed'"
    )


def downgrade() -> None:
    op.drop_column("module_run", "error_code")
