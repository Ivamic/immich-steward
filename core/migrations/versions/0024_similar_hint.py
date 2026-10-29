# SPDX-License-Identifier: AGPL-3.0-or-later
"""The most similar photo with a location, per photo without one (badge in the gallery).

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "similar_hint",
        sa.Column(
            "asset_id",
            sa.Uuid(),
            sa.ForeignKey("asset.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("neighbor_id", sa.Uuid(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_similar_hint_account_id", "similar_hint", ["account_id"])


def downgrade() -> None:
    op.drop_table("similar_hint")
