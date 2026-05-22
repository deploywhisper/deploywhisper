"""Add incident ingestion source status.

Revision ID: 023_add_incident_ingestion_sources
Revises: 022_add_deployment_outcome_notes
Create Date: 2026-05-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "023_add_incident_ingestion_sources"
down_revision = "022_add_deployment_outcome_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incident_ingestion_sources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("source_file", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("indexed_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("redaction_status", sa.String(length=40), nullable=False),
        sa.Column("failure_summaries_json", sa.Text(), nullable=False),
        sa.Column("index_version", sa.String(length=120), nullable=True),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('indexed', 'failed', 'removed')",
            name="ck_incident_ingestion_sources_status",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_incident_ingestion_sources_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["project_workspaces.id"],
            name="fk_incident_ingestion_sources_workspace_id_project_workspaces",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["project_workspaces.project_id", "project_workspaces.id"],
            name="fk_incident_ingestion_sources_project_workspace_scope",
        ),
        sa.UniqueConstraint(
            "project_id",
            "workspace_id",
            "source_file",
            name="uq_incident_ingestion_sources_scope_source",
        ),
    )
    op.create_index(
        "ix_incident_ingestion_sources_project_id",
        "incident_ingestion_sources",
        ["project_id"],
    )
    op.create_index(
        "ix_incident_ingestion_sources_workspace_id",
        "incident_ingestion_sources",
        ["workspace_id"],
    )
    op.create_index(
        "uq_incident_ingestion_sources_project_source",
        "incident_ingestion_sources",
        ["project_id", "source_file"],
        unique=True,
        sqlite_where=sa.text("workspace_id IS NULL"),
        postgresql_where=sa.text("workspace_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_incident_ingestion_sources_project_source",
        table_name="incident_ingestion_sources",
    )
    op.drop_index(
        "ix_incident_ingestion_sources_workspace_id",
        table_name="incident_ingestion_sources",
    )
    op.drop_index(
        "ix_incident_ingestion_sources_project_id",
        table_name="incident_ingestion_sources",
    )
    op.drop_table("incident_ingestion_sources")
