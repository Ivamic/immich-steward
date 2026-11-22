# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turned photos: the answer of the `orientation` module per photo (D-237).

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "asset_orientation",
        sa.Column(
            "asset_id", sa.Uuid(), sa.ForeignKey("asset.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("module_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("probs", postgresql.JSONB(), nullable=False),
        sa.Column("module_version", sa.String(32), nullable=False),
        sa.Column("kept", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_asset_orientation_run", "asset_orientation", ["run_id"])
    op.create_index("ix_asset_orientation_turn", "asset_orientation", ["turn", "score"])


def downgrade() -> None:
    op.drop_table("asset_orientation")
