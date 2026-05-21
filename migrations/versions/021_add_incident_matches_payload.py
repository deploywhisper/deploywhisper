"""Persist incident and public risk pattern matches.

Revision ID: 021_add_incident_matches_payload
Revises: 020_add_narrative_state_fields
Create Date: 2026-05-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "021_add_incident_matches_payload"
down_revision = "020_add_narrative_state_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_reports",
        sa.Column(
            "incident_matches_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.execute(
        "UPDATE analysis_reports SET incident_matches_json = '[]' "
        "WHERE incident_matches_json IS NULL OR incident_matches_json = ''"
    )
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.alter_column(
            "incident_matches_json",
            existing_type=sa.Text(),
            server_default=None,
        )


def downgrade() -> None:
    op.drop_column("analysis_reports", "incident_matches_json")
