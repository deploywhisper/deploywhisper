"""Persist explicit narrative degraded state.

Revision ID: 020_add_narrative_state_fields
Revises: 019_add_finding_context_fields
Create Date: 2026-05-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "020_add_narrative_state_fields"
down_revision = "019_add_finding_context_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_reports",
        sa.Column("narrative_degraded", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "analysis_reports",
        sa.Column("narrative_failure_notice", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_reports", "narrative_failure_notice")
    op.drop_column("analysis_reports", "narrative_degraded")
