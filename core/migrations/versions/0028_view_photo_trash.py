# SPDX-License-Identifier: AGPL-3.0-or-later
"""Single photos marked as trash: they show nothing of the place.

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "view_photo_trash",
        sa.Column(
            "asset_id", sa.Uuid(), sa.ForeignKey("asset.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_view_photo_trash_account_id", "view_photo_trash", ["account_id"])


def downgrade() -> None:
    op.drop_table("view_photo_trash")
