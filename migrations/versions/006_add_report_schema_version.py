"""Add report schema version to persisted reports.

Revision ID: 006_add_report_schema_version
Revises: 005_add_evidence_model
Create Date: 2026-04-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "006_add_report_schema_version"
down_revision = "005_add_evidence_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_reports",
        sa.Column(
            "report_schema_version",
            sa.String(length=16),
            nullable=False,
            server_default="v2",
        ),
    )
    op.execute(
        "UPDATE analysis_reports SET report_schema_version = 'v2' "
        "WHERE report_schema_version IS NULL OR report_schema_version = ''"
    )
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.alter_column(
            "report_schema_version",
            existing_type=sa.String(length=16),
            server_default=None,
        )


def downgrade() -> None:
    op.drop_column("analysis_reports", "report_schema_version")
