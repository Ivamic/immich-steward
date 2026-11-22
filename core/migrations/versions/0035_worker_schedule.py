# SPDX-License-Identifier: AGPL-3.0-or-later
"""When a worker gets background jobs: a week of hours (D-238).

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # None: always, as before.
    op.add_column("worker", sa.Column("schedule", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("worker", "schedule")
