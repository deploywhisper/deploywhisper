"""Add project-scoped external scanner imports.

Revision ID: 027_add_scanner_imports
Revises: 026_add_evidence_context_source
Create Date: 2026-06-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "027_add_scanner_imports"
down_revision = "026_add_evidence_context_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scanner_imports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("workspace_key", sa.String(length=120), nullable=True),
        sa.Column("source_file", sa.String(length=255), nullable=False),
        sa.Column("format", sa.String(length=40), nullable=False),
        sa.Column("tool_names_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("failure_summaries_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('imported', 'failed')",
            name="ck_scanner_imports_status",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_scanner_imports_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["project_workspaces.id"],
            name="fk_scanner_imports_workspace_id_project_workspaces",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["project_workspaces.project_id", "project_workspaces.id"],
            name="fk_scanner_imports_project_workspace_scope",
        ),
    )
    op.create_index(
        "ix_scanner_imports_project_id",
        "scanner_imports",
        ["project_id"],
    )
    op.create_index(
        "ix_scanner_imports_workspace_id",
        "scanner_imports",
        ["workspace_id"],
    )
    op.create_table(
        "external_scanner_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("import_id", sa.Integer(), nullable=False),
        sa.Column("evidence_id", sa.String(length=120), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("project_key", sa.String(length=120), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("workspace_key", sa.String(length=120), nullable=True),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_file", sa.String(length=255), nullable=False),
        sa.Column("source_ref", sa.String(length=512), nullable=False),
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("rule_id", sa.String(length=255), nullable=False),
        sa.Column("rule_name", sa.String(length=255), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("level", sa.String(length=40), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("artifact_uri", sa.Text(), nullable=False),
        sa.Column("region_json", sa.Text(), nullable=False),
        sa.Column("properties_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_type = 'external_scanner'",
            name="ck_external_scanner_evidence_source_type",
        ),
        sa.ForeignKeyConstraint(
            ["import_id"],
            ["scanner_imports.id"],
            name="fk_external_scanner_evidence_import_id_scanner_imports",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_external_scanner_evidence_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["project_workspaces.id"],
            name="fk_external_scanner_evidence_workspace_id_project_workspaces",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["project_workspaces.project_id", "project_workspaces.id"],
            name="fk_external_scanner_evidence_project_workspace_scope",
        ),
        sa.UniqueConstraint(
            "evidence_id",
            name="uq_external_scanner_evidence_evidence_id",
        ),
        sa.UniqueConstraint(
            "project_id",
            "workspace_id",
            "source_ref",
            name="uq_external_scanner_evidence_scope_source_ref",
        ),
    )
    op.create_index(
        "ix_external_scanner_evidence_import_id",
        "external_scanner_evidence",
        ["import_id"],
    )
    op.create_index(
        "ix_external_scanner_evidence_evidence_id",
        "external_scanner_evidence",
        ["evidence_id"],
    )
    op.create_index(
        "ix_external_scanner_evidence_project_id",
        "external_scanner_evidence",
        ["project_id"],
    )
    op.create_index(
        "ix_external_scanner_evidence_workspace_id",
        "external_scanner_evidence",
        ["workspace_id"],
    )
    op.create_index(
        "ix_external_scanner_evidence_project_rule",
        "external_scanner_evidence",
        ["project_id", "rule_id"],
    )
    op.create_index(
        "uq_external_scanner_evidence_project_source_ref",
        "external_scanner_evidence",
        ["project_id", "source_ref"],
        unique=True,
        sqlite_where=sa.text("workspace_id IS NULL AND workspace_key IS NULL"),
        postgresql_where=sa.text("workspace_id IS NULL AND workspace_key IS NULL"),
    )
    op.create_index(
        "uq_external_scanner_evidence_workspace_key_source_ref",
        "external_scanner_evidence",
        ["project_id", "workspace_key", "source_ref"],
        unique=True,
        sqlite_where=sa.text("workspace_id IS NULL AND workspace_key IS NOT NULL"),
        postgresql_where=sa.text("workspace_id IS NULL AND workspace_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_external_scanner_evidence_workspace_key_source_ref",
        table_name="external_scanner_evidence",
    )
    op.drop_index(
        "uq_external_scanner_evidence_project_source_ref",
        table_name="external_scanner_evidence",
    )
    op.drop_index(
        "ix_external_scanner_evidence_project_rule",
        table_name="external_scanner_evidence",
    )
    op.drop_index(
        "ix_external_scanner_evidence_workspace_id",
        table_name="external_scanner_evidence",
    )
    op.drop_index(
        "ix_external_scanner_evidence_project_id",
        table_name="external_scanner_evidence",
    )
    op.drop_index(
        "ix_external_scanner_evidence_evidence_id",
        table_name="external_scanner_evidence",
    )
    op.drop_index(
        "ix_external_scanner_evidence_import_id",
        table_name="external_scanner_evidence",
    )
    op.drop_table("external_scanner_evidence")
    op.drop_index("ix_scanner_imports_workspace_id", table_name="scanner_imports")
    op.drop_index("ix_scanner_imports_project_id", table_name="scanner_imports")
    op.drop_table("scanner_imports")
