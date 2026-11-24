# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which way the camera looked (D-245): kept in the app, Immich has no field for it.

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "asset_direction",
        sa.Column(
            "asset_id", sa.Uuid(), sa.ForeignKey("asset.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("heading", sa.Float(), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("source_ref", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("asset_direction")
