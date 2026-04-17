"""Add provenance columns to analysis_reports.

Revision ID: 0005_add_analysis_provenance_columns
Revises: 0004_add_dashboard_display_duration_to_analysis_reports
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_add_analysis_provenance_columns"
down_revision = "0004_add_dashboard_display_duration_to_analysis_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.add_column(sa.Column("assessment_source", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("narrative_source", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("narrative_skills_json", sa.Text(), nullable=True, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.drop_column("narrative_skills_json")
        batch_op.drop_column("narrative_source")
        batch_op.drop_column("assessment_source")
