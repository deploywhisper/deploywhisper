"""Create analysis_reports table.

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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("analysis_reports")
