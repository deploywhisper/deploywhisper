"""Add independent deployment outcome notes.

Revision ID: 022_add_deployment_outcome_notes
Revises: 021_add_incident_matches_payload
Create Date: 2026-05-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "022_add_deployment_outcome_notes"
down_revision = "021_add_incident_matches_payload"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "deployment_outcomes",
        sa.Column("notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("deployment_outcomes", "notes")
