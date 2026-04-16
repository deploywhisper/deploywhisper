"""Add audit metadata columns to analysis_reports.

Revision ID: 0003_add_analysis_report_audit_columns
Revises: 0002_create_app_settings
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_add_analysis_report_audit_columns"
down_revision = "0002_create_app_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.add_column(sa.Column("analyzed_files_json", sa.Text(), nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("llm_provider", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("llm_model", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("llm_local_mode", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("source_interface", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("trigger_type", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("trigger_id", sa.String(length=120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.drop_column("trigger_id")
        batch_op.drop_column("trigger_type")
        batch_op.drop_column("source_interface")
        batch_op.drop_column("llm_local_mode")
        batch_op.drop_column("llm_model")
        batch_op.drop_column("llm_provider")
        batch_op.drop_column("analyzed_files_json")
