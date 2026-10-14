"""Persist scoped drafts, immutable revisions, project policy and audit.

Revision ID: 031_add_infra_workflows
Revises: 030_add_project_memberships
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "031_add_infra_workflows"
down_revision = "030_add_project_memberships"
branch_labels = None
depends_on = None

TABLES = (
    "infra_workflows",
    "infra_workflow_revisions",
    "infra_automation_policies",
    "infra_automation_audit",
)
GUARDS = {
    "infra_workflow_no_replace": "BEFORE INSERT ON infra_workflows WHEN EXISTS (SELECT 1 FROM infra_workflows WHERE id=NEW.id OR sequence=NEW.sequence) BEGIN SELECT RAISE(ABORT, 'Immutable workflow identity'); END",
    "infra_revision_no_replace": "BEFORE INSERT ON infra_workflow_revisions WHEN EXISTS (SELECT 1 FROM infra_workflow_revisions WHERE id=NEW.id OR sequence=NEW.sequence OR (workflow_id=NEW.workflow_id AND revision_number=NEW.revision_number) OR (published_by=NEW.published_by AND idempotency_key_digest=NEW.idempotency_key_digest)) BEGIN SELECT RAISE(ABORT, 'Immutable workflow revision'); END",
    "infra_audit_no_replace": "BEFORE INSERT ON infra_automation_audit WHEN EXISTS (SELECT 1 FROM infra_automation_audit WHERE id=NEW.id OR sequence=NEW.sequence) BEGIN SELECT RAISE(ABORT, 'Immutable automation audit'); END",
    "infra_policy_no_replace": "BEFORE INSERT ON infra_automation_policies WHEN EXISTS (SELECT 1 FROM infra_automation_policies WHERE project_id=NEW.project_id) BEGIN SELECT RAISE(ABORT, 'Automation policy epochs cannot reset'); END",
    "infra_workflow_version": "BEFORE UPDATE ON infra_workflows WHEN NEW.draft_version <= OLD.draft_version BEGIN SELECT RAISE(ABORT, 'Workflow version must advance'); END",
    "infra_revision_no_update": "BEFORE UPDATE ON infra_workflow_revisions BEGIN SELECT RAISE(ABORT, 'Immutable workflow revision'); END",
    "infra_revision_no_delete": "BEFORE DELETE ON infra_workflow_revisions BEGIN SELECT RAISE(ABORT, 'Immutable workflow revision'); END",
    "infra_audit_no_update": "BEFORE UPDATE ON infra_automation_audit BEGIN SELECT RAISE(ABORT, 'Immutable automation audit'); END",
    "infra_audit_no_delete": "BEFORE DELETE ON infra_automation_audit BEGIN SELECT RAISE(ABORT, 'Immutable automation audit'); END",
    "infra_workflow_identity": "BEFORE UPDATE ON infra_workflows WHEN NEW.sequence IS NOT OLD.sequence OR NEW.id IS NOT OLD.id OR NEW.project_id IS NOT OLD.project_id OR NEW.workspace_id IS NOT OLD.workspace_id OR NEW.created_by IS NOT OLD.created_by OR NEW.created_at IS NOT OLD.created_at BEGIN SELECT RAISE(ABORT, 'Immutable workflow identity'); END",
    "infra_revision_scope": "BEFORE INSERT ON infra_workflow_revisions WHEN NOT EXISTS (SELECT 1 FROM infra_workflows WHERE id=NEW.workflow_id AND project_id=NEW.project_id AND workspace_id IS NEW.workspace_id) BEGIN SELECT RAISE(ABORT, 'Workflow revision scope mismatch'); END",
    "infra_policy_monotonic": "BEFORE UPDATE ON infra_automation_policies WHEN NEW.project_id IS NOT OLD.project_id OR NEW.version <= OLD.version OR NEW.authorization_epoch <= OLD.authorization_epoch OR NEW.restore_epoch < OLD.restore_epoch BEGIN SELECT RAISE(ABORT, 'Automation policy epochs cannot reset'); END",
    "infra_policy_no_delete": "BEFORE DELETE ON infra_automation_policies BEGIN SELECT RAISE(ABORT, 'Automation policy epochs cannot reset'); END",
}


def upgrade() -> None:
    op.create_table(
        "infra_workflows",
        sa.Column(
            "sequence",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("id", sa.String(64), unique=True, nullable=False),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("draft_definition", sa.LargeBinary(), nullable=False),
        sa.Column("draft_digest", sa.String(71), nullable=False),
        sa.Column("draft_version", sa.Integer(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column(
            "created_by",
            sa.String(64),
            sa.ForeignKey("identity_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("id", "project_id", name="uq_infra_workflows_id_project"),
        sa.CheckConstraint("draft_version > 0", name="ck_infra_workflow_version"),
        sa.CheckConstraint(
            "length(draft_definition) BETWEEN 1 AND 131072",
            name="ck_infra_workflow_bytes",
        ),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 120", name="ck_infra_workflow_name"
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["project_workspaces.project_id", "project_workspaces.id"],
            ondelete="RESTRICT",
            name="fk_infra_workflows_workspace",
        ),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_infra_workflows_project_id", "infra_workflows", ["project_id"])
    op.create_table(
        "infra_workflow_revisions",
        sa.Column(
            "sequence",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("id", sa.String(64), unique=True, nullable=False),
        sa.Column(
            "workflow_id",
            sa.String(64),
            sa.ForeignKey("infra_workflows.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("canonical_definition", sa.LargeBinary(), nullable=False),
        sa.Column("digest", sa.String(71), nullable=False),
        sa.Column(
            "published_by",
            sa.String(64),
            sa.ForeignKey("identity_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("idempotency_key_digest", sa.String(71), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workflow_id", "revision_number", name="uq_infra_workflow_revision_number"
        ),
        sa.UniqueConstraint(
            "published_by",
            "idempotency_key_digest",
            name="uq_infra_workflow_publication_key",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id", "project_id"],
            ["infra_workflows.id", "infra_workflows.project_id"],
            ondelete="RESTRICT",
            name="fk_infra_revision_workflow_project",
        ),
        sa.CheckConstraint("revision_number > 0", name="ck_infra_revision_number"),
        sa.CheckConstraint(
            "length(canonical_definition) BETWEEN 1 AND 131072",
            name="ck_infra_revision_bytes",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["project_workspaces.project_id", "project_workspaces.id"],
            ondelete="RESTRICT",
            name="fk_infra_workflow_revisions_workspace",
        ),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "ix_infra_workflow_revisions_workflow_id",
        "infra_workflow_revisions",
        ["workflow_id"],
    )
    op.create_index(
        "ix_infra_workflow_revisions_project_id",
        "infra_workflow_revisions",
        ["project_id"],
    )
    op.create_table(
        "infra_automation_policies",
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("authorization_epoch", sa.Integer(), nullable=False),
        sa.Column("restore_epoch", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version > 0 AND authorization_epoch > 0 AND restore_epoch > 0",
            name="ck_infra_policy_versions",
        ),
    )
    op.create_table(
        "infra_automation_audit",
        sa.Column(
            "sequence",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("id", sa.String(64), unique=True, nullable=False),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column(
            "actor_principal_id",
            sa.String(64),
            sa.ForeignKey("identity_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_role", sa.String(20), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(256), nullable=False),
        sa.Column("before_digest", sa.String(71), nullable=True),
        sa.Column("after_digest", sa.String(71), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(reason) BETWEEN 1 AND 256", name="ck_infra_audit_reason"
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["project_workspaces.project_id", "project_workspaces.id"],
            ondelete="RESTRICT",
            name="fk_infra_automation_audit_workspace",
        ),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "ix_infra_automation_audit_project_id", "infra_automation_audit", ["project_id"]
    )
    for name, body in GUARDS.items():
        op.execute(f"CREATE TRIGGER {name} {body}")


def downgrade() -> None:
    for name in GUARDS:
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
    for name in reversed(TABLES):
        op.drop_table(name)
