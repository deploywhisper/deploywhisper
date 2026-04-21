"""Add persisted rollback plan payload to analysis reports.

Revision ID: 008_add_rollback_plan_payload
Revises: 007_add_blast_radius_payload
Create Date: 2026-04-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "008_add_rollback_plan_payload"
down_revision = "007_add_blast_radius_payload"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_reports",
        sa.Column(
            "rollback_plan_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.execute(
        "UPDATE analysis_reports SET rollback_plan_json = '{}' "
        "WHERE rollback_plan_json IS NULL OR rollback_plan_json = ''"
    )
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.alter_column(
            "rollback_plan_json",
            existing_type=sa.Text(),
            server_default=None,
        )


def downgrade() -> None:
    op.drop_column("analysis_reports", "rollback_plan_json")
