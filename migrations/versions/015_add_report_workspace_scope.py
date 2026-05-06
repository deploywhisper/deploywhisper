"""Add optional workspace scope to analysis reports.

Revision ID: 015_add_report_workspace_scope
Revises: 014_add_project_workspace_records
Create Date: 2026-05-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "015_add_report_workspace_scope"
down_revision = "014_add_project_workspace_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_reports",
        sa.Column("workspace_id", sa.Integer(), nullable=True),
    )
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.create_foreign_key(
            "fk_analysis_reports_workspace_id_project_workspaces",
            "project_workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_analysis_reports_workspace_id",
            ["workspace_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.drop_index("ix_analysis_reports_workspace_id")
        batch_op.drop_constraint(
            "fk_analysis_reports_workspace_id_project_workspaces",
            type_="foreignkey",
        )
        batch_op.drop_column("workspace_id")
