"""Add first-class project workspace records.

Revision ID: 014_add_project_workspace_records
Revises: 013_add_incident_analysis_reference
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "014_add_project_workspace_records"
down_revision = "013_add_incident_analysis_reference"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_workspaces",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("workspace_key", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("environment", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "project_id",
            "workspace_key",
            name="uq_project_workspaces_project_key",
        ),
    )
    op.create_index(
        "ix_project_workspaces_project_id",
        "project_workspaces",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_workspaces_workspace_key",
        "project_workspaces",
        ["workspace_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_workspaces_workspace_key",
        table_name="project_workspaces",
    )
    op.drop_index("ix_project_workspaces_project_id", table_name="project_workspaces")
    op.drop_table("project_workspaces")
