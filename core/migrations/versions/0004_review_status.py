# SPDX-License-Identifier: AGPL-3.0-or-later
"""Review status of assets.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "asset",
        sa.Column("review_status", sa.String(16), nullable=False, server_default="new"),
    )


def downgrade() -> None:
    op.drop_column("asset", "review_status")
