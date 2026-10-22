# SPDX-License-Identifier: AGPL-3.0-or-later
"""When a sync first saw a photo, so that new photos are run before the rest of the library.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("asset", sa.Column("added_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("asset", "added_at")
