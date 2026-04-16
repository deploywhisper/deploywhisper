"""Create app_settings table.

Revision ID: 0002_create_app_settings
Revises: 0001_create_analysis_reports
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_create_app_settings"
down_revision = "0001_create_analysis_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
