# SPDX-License-Identifier: AGPL-3.0-or-later
"""Whether a photo has edits in Immich, to ask for its edited images.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "asset", sa.Column("is_edited", sa.Boolean(), nullable=False, server_default="false")
    )


def downgrade() -> None:
    op.drop_column("asset", "is_edited")
