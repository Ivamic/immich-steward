# SPDX-License-Identifier: AGPL-3.0-or-later
"""Order of the modules in the photo card and hiding them, per account.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "module_display",
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("module_id", sa.String(32), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("module_display")
