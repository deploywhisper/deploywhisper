"""Add submission manifest payload to analysis reports.

Revision ID: 017_add_submission_manifest_payload
Revises: 016_scope_learning_context_records
Create Date: 2026-05-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "017_add_submission_manifest_payload"
down_revision = "016_scope_learning_context_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_reports",
        sa.Column(
            "submission_manifest_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "analysis_reports",
        sa.Column(
            "submission_manifest_fallback_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.alter_column(
            "submission_manifest_json",
            existing_type=sa.Text(),
            server_default=None,
        )
        batch_op.alter_column(
            "submission_manifest_fallback_json",
            existing_type=sa.Text(),
            server_default=None,
        )


def downgrade() -> None:
    op.drop_column("analysis_reports", "submission_manifest_fallback_json")
    op.drop_column("analysis_reports", "submission_manifest_json")
