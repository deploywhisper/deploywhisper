"""Create initial application schema.

Revision ID: 0001_create_analysis_reports
Revises:
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_create_analysis_reports"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("recommendation", sa.String(length=20), nullable=False),
        sa.Column("top_risk", sa.Text(), nullable=False),
        sa.Column("parse_summary", sa.Text(), nullable=False),
        sa.Column("narrative_opening", sa.Text(), nullable=False),
        sa.Column("narrative_explanation", sa.Text(), nullable=False),
        sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("contributors_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "analyzed_files_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column("llm_provider", sa.String(length=50), nullable=True),
        sa.Column("llm_model", sa.String(length=120), nullable=True),
        sa.Column("llm_local_mode", sa.String(length=10), nullable=True),
        sa.Column("assessment_source", sa.String(length=30), nullable=True),
        sa.Column("narrative_source", sa.String(length=30), nullable=True),
        sa.Column(
            "narrative_skills_json", sa.Text(), nullable=True, server_default="[]"
        ),
        sa.Column("source_interface", sa.String(length=30), nullable=True),
        sa.Column("trigger_type", sa.String(length=30), nullable=True),
        sa.Column("trigger_id", sa.String(length=120), nullable=True),
        sa.Column("dashboard_display_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_table("analysis_reports")
