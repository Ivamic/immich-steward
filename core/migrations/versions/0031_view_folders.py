# SPDX-License-Identifier: AGPL-3.0-or-later
"""Folders of groups: groups the user keeps together (one place seen from many sides, the
documents), shown together; the groups themselves do not change (D-201).

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "view_folder",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id", sa.Uuid(), sa.ForeignKey("account.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_view_folder_account_id", "view_folder", ["account_id"])
    op.add_column(
        "view_group",
        sa.Column(
            "folder_id",
            sa.Uuid(),
            sa.ForeignKey("view_folder.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_view_group_folder_id", "view_group", ["folder_id"])


def downgrade() -> None:
    op.drop_index("ix_view_group_folder_id", table_name="view_group")
    op.drop_column("view_group", "folder_id")
    op.drop_index("ix_view_folder_account_id", table_name="view_folder")
    op.drop_table("view_folder")
