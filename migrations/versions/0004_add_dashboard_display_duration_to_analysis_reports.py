"""Add dashboard display duration column to analysis_reports.

Revision ID: 0004_add_dashboard_display_duration_to_analysis_reports
Revises: 0003_add_analysis_report_audit_columns
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_dashboard_display_duration_to_analysis_reports"
down_revision = "0003_add_analysis_report_audit_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.add_column(sa.Column("dashboard_display_duration_seconds", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.drop_column("dashboard_display_duration_seconds")
