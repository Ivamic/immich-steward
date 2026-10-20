# SPDX-License-Identifier: AGPL-3.0-or-later
"""Workers send the id of their running process, to detect two workers with one name.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("worker", sa.Column("instance_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("worker", "instance_id")
