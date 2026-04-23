"""Add persisted share settings to analysis reports.

Revision ID: 009_add_report_share_settings
Revises: 008_add_rollback_plan_payload
Create Date: 2026-04-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "009_add_report_share_settings"
down_revision = "008_add_rollback_plan_payload"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_reports",
        sa.Column("share_password_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "analysis_reports",
        sa.Column("share_password_salt", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "analysis_reports",
        sa.Column(
            "share_redact_filenames",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.alter_column(
            "share_redact_filenames",
            existing_type=sa.Boolean(),
            server_default=None,
        )


def downgrade() -> None:
    op.drop_column("analysis_reports", "share_redact_filenames")
    op.drop_column("analysis_reports", "share_password_salt")
    op.drop_column("analysis_reports", "share_password_hash")
