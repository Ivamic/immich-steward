# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a worker is doing: waiting, downloading or loading a model, working.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("worker", sa.Column("state", sa.String(16)))
    op.add_column("worker", sa.Column("state_module", sa.String(32)))
    op.add_column("worker", sa.Column("state_since", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("worker", "state_since")
    op.drop_column("worker", "state_module")
    op.drop_column("worker", "state")
