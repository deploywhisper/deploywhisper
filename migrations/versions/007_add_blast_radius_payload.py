"""Add persisted blast radius payload to analysis reports.

Revision ID: 007_add_blast_radius_payload
Revises: 006_add_report_schema_version
Create Date: 2026-04-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "007_add_blast_radius_payload"
down_revision = "006_add_report_schema_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_reports",
        sa.Column(
            "blast_radius_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.execute(
        "UPDATE analysis_reports SET blast_radius_json = '{}' "
        "WHERE blast_radius_json IS NULL OR blast_radius_json = ''"
    )
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.alter_column(
            "blast_radius_json",
            existing_type=sa.Text(),
            server_default=None,
        )


def downgrade() -> None:
    op.drop_column("analysis_reports", "blast_radius_json")
