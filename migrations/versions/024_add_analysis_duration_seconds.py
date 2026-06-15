"""Add analysis duration metric to reports.

Revision ID: 024_add_analysis_duration_seconds
Revises: 023_add_incident_ingestion_sources
Create Date: 2026-06-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "024_add_analysis_duration_seconds"
down_revision = "023_add_incident_ingestion_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_reports",
        sa.Column("analysis_duration_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_reports", "analysis_duration_seconds")
