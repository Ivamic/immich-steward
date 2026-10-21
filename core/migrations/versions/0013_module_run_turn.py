# SPDX-License-Identifier: AGPL-3.0-or-later
"""Module runs on a photo the user turned in the app.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("module_run", sa.Column("turn", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("module_run", "turn")
