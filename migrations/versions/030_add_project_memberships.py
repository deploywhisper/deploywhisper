"""Persist scoped project authority without granting existing users permissions.

Revision ID: 030_add_project_memberships
Revises: 029_add_identity_lifecycle
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "030_add_project_memberships"
down_revision = "029_add_identity_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("projects", "analysis_reports"):
        op.add_column(
            table,
            sa.Column(
                "authorization_required",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
    op.create_table(
        "project_memberships",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "principal_id",
            sa.String(64),
            sa.ForeignKey("identity_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("authorization_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "principal_id", "project_id", name="uq_project_membership_principal_project"
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["project_workspaces.project_id", "project_workspaces.id"],
            name="fk_project_memberships_project_workspace_scope",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "role IN ('admin', 'maintainer', 'reviewer', 'contributor', 'read-only')",
            name="ck_project_memberships_role",
        ),
        sa.CheckConstraint(
            "authorization_version > 0",
            name="ck_project_memberships_authorization_version",
        ),
    )
    op.create_index(
        "ix_project_memberships_principal_id", "project_memberships", ["principal_id"]
    )
    op.create_index(
        "ix_project_memberships_project_id", "project_memberships", ["project_id"]
    )
    op.create_table(
        "project_authorization_audit",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "actor_principal_id",
            sa.String(64),
            sa.ForeignKey("identity_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "target_principal_id",
            sa.String(64),
            sa.ForeignKey("identity_accounts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("object_id", sa.String(64), nullable=True),
        sa.Column("before_json", sa.Text(), nullable=False),
        sa.Column("after_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["project_workspaces.project_id", "project_workspaces.id"],
            name="fk_project_authorization_audit_project_workspace_scope",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_project_authorization_audit_project_id",
        "project_authorization_audit",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_table("project_authorization_audit")
    op.drop_table("project_memberships")
    for table in ("analysis_reports", "projects"):
        op.drop_column(table, "authorization_required")
