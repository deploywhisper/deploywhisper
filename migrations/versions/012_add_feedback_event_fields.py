"""Add finding-level reviewer feedback fields.

Revision ID: 012_add_feedback_event_fields
Revises: 011_add_deployment_outcome_fields
Create Date: 2026-04-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "012_add_feedback_event_fields"
down_revision = "011_add_deployment_outcome_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "feedback_events",
        sa.Column("finding_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "feedback_events",
        sa.Column("false_positive_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("feedback_events") as batch_op:
        batch_op.drop_column("false_positive_reason")
        batch_op.drop_column("finding_id")
