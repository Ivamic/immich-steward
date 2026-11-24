# SPDX-License-Identifier: AGPL-3.0-or-later
"""Street-level images (0.14): the sources an account switched on, and its access token.

Revision ID: 0039
Revises: 0038
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "street_source_setting",
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("source_id", sa.String(32), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("key_problem", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("street_source_setting")
