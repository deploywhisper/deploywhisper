"""Add incident-to-analysis linking for backtesting.

Revision ID: 013_add_incident_analysis_reference
Revises: 012_add_feedback_event_fields
Create Date: 2026-04-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "013_add_incident_analysis_reference"
down_revision = "012_add_feedback_event_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "incident_records",
        sa.Column("analysis_id", sa.Integer(), nullable=True),
    )
    with op.batch_alter_table("incident_records") as batch_op:
        batch_op.create_foreign_key(
            "fk_incident_records_analysis_id_analysis_reports",
            "analysis_reports",
            ["analysis_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_incident_records_analysis_id",
            ["analysis_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("incident_records") as batch_op:
        batch_op.drop_index("ix_incident_records_analysis_id")
        batch_op.drop_constraint(
            "fk_incident_records_analysis_id_analysis_reports",
            type_="foreignkey",
        )
        batch_op.drop_column("analysis_id")
