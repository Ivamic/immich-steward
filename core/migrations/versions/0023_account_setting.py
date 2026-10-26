# SPDX-License-Identifier: AGPL-3.0-or-later
"""Personal settings of an account (the tooltip of the gallery tiles, for a start).

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_setting",
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("account_setting")
