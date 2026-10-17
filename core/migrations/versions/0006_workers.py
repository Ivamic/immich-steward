# SPDX-License-Identifier: AGPL-3.0-or-later
"""Workers, worker jobs and module runs.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("modules", JSONB(), nullable=False),
        sa.Column("device", sa.String(100), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("job", sa.Column("priority", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("job", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "job", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3")
    )
    op.add_column("job", sa.Column("module_id", sa.String(32)))
    op.add_column(
        "job",
        sa.Column("worker_id", sa.Uuid(), sa.ForeignKey("worker.id", ondelete="SET NULL")),
    )
    op.add_column("job", sa.Column("lease_until", sa.DateTime(timezone=True)))
    # Workers look for the next job of their modules by priority.
    op.create_index(
        "ix_job_worker_queue",
        "job",
        ["module_id", "status", sa.text("priority DESC"), "created_at"],
        postgresql_where=sa.text("module_id IS NOT NULL"),
    )
    op.create_table(
        "module_run",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "asset_id", sa.Uuid(), sa.ForeignKey("asset.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("module_id", sa.String(32), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("job.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("module_version", sa.String(32)),
        sa.Column("candidates", JSONB(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("worker_id", sa.Uuid(), sa.ForeignKey("worker.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_module_run_asset_module", "module_run", ["asset_id", "module_id"])


def downgrade() -> None:
    op.drop_index("ix_module_run_asset_module", "module_run")
    op.drop_table("module_run")
    op.drop_index("ix_job_worker_queue", "job")
    for column in ("lease_until", "worker_id", "module_id", "max_attempts", "attempts", "priority"):
        op.drop_column("job", column)
    op.drop_table("worker")
