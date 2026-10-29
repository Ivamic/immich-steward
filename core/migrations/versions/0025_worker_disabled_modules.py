# SPDX-License-Identifier: AGPL-3.0-or-later
"""Modules turned off for a worker on the Processing page.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "worker",
        sa.Column("disabled_modules", postgresql.JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("worker", "disabled_modules")
