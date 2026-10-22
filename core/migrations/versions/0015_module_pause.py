# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pausing the background runs of worker modules.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "module_pause",
        sa.Column("module_id", sa.String(32), primary_key=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("module_pause")
