# SPDX-License-Identifier: AGPL-3.0-or-later
"""The rotate job that turns a photo: no second turn while one is on its way (0.13.2).

A photo turned from the list of turned photos stayed in the list until Immich made its new
thumbnails; opened again meanwhile, the page offered it once more, and a second turn put it
upside down. The job is now kept with the photo for as long as it runs.

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "asset",
        sa.Column(
            "turning_job_id", sa.Uuid(), sa.ForeignKey("job.id", ondelete="SET NULL"), nullable=True
        ),
    )
    op.create_index("ix_asset_turning_job", "asset", ["turning_job_id"])


def downgrade() -> None:
    op.drop_index("ix_asset_turning_job", "asset")
    op.drop_column("asset", "turning_job_id")
