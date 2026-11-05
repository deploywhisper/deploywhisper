"""Bind human-declared immutable unit maps to exact preflight runs."""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "038_add_declared_unit_maps"
down_revision = "037_add_runner_enrollment"
branch_labels = None
depends_on = None

TABLES = ("infra_automation_unit_revisions", "infra_automation_run_units")
GUARDS = {
    "infra_automation_unit_revisions_immutable": "BEFORE UPDATE ON infra_automation_unit_revisions BEGIN SELECT RAISE(ABORT, 'immutable unit snapshot'); END",
    "infra_automation_run_units_immutable": "BEFORE UPDATE OF run_id, revision_id, project_id, workspace_id, snapshot_bytes, snapshot_digest, request_digest ON infra_automation_run_units BEGIN SELECT RAISE(ABORT, 'immutable unit snapshot'); END",
    "infra_automation_run_units_evidence_immutable": "BEFORE UPDATE OF evidence_bytes, evidence_digest ON infra_automation_run_units WHEN OLD.evidence_bytes IS NOT NULL BEGIN SELECT RAISE(ABORT, 'immutable unit evidence'); END",
}

GUARDS.update(
    {
        "infra_automation_unit_revisions_no_delete": "BEFORE DELETE ON infra_automation_unit_revisions BEGIN SELECT RAISE(ABORT, 'immutable unit history'); END",
        "infra_automation_run_units_no_delete": "BEFORE DELETE ON infra_automation_run_units BEGIN SELECT RAISE(ABORT, 'immutable unit history'); END",
        "infra_automation_unit_revisions_no_replace": "BEFORE INSERT ON infra_automation_unit_revisions WHEN EXISTS (SELECT 1 FROM infra_automation_unit_revisions WHERE id=NEW.id OR (inventory_id=NEW.inventory_id AND revision_number=NEW.revision_number)) BEGIN SELECT RAISE(ABORT, 'immutable unit history'); END",
        "infra_automation_run_units_no_replace": "BEFORE INSERT ON infra_automation_run_units WHEN EXISTS (SELECT 1 FROM infra_automation_run_units WHERE run_id=NEW.run_id) BEGIN SELECT RAISE(ABORT, 'immutable unit history'); END",
    }
)


def upgrade():
    op.create_table(
        "infra_automation_unit_revisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("inventory_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("plan_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("plan_digest", sa.String(71), nullable=False),
        sa.Column(
            "created_by",
            sa.String(64),
            sa.ForeignKey("identity_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["project_workspaces.project_id", "project_workspaces.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("inventory_id", "revision_number"),
        sa.UniqueConstraint("id", "project_id", "workspace_id"),
        sa.CheckConstraint(
            "revision_number BETWEEN 1 AND 32 AND length(plan_bytes) BETWEEN 1 AND 131072",
            name="ck_unit_revision_bounds",
        ),
    )
    op.create_index(
        "ix_infra_automation_unit_revisions_inventory_id",
        "infra_automation_unit_revisions",
        ["inventory_id"],
    )
    op.create_table(
        "infra_automation_run_units",
        sa.Column(
            "run_id",
            sa.String(64),
            sa.ForeignKey("infra_automation_runs.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("revision_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("snapshot_digest", sa.String(71), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("evidence_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("evidence_digest", sa.String(71), nullable=True),
        sa.ForeignKeyConstraint(
            ["revision_id", "project_id", "workspace_id"],
            [
                "infra_automation_unit_revisions.id",
                "infra_automation_unit_revisions.project_id",
                "infra_automation_unit_revisions.workspace_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "length(snapshot_bytes) BETWEEN 1 AND 131072 AND (evidence_bytes IS NULL OR length(evidence_bytes) BETWEEN 1 AND 131072)",
            name="ck_run_units_bounds",
        ),
    )
    for name, body in GUARDS.items():
        op.execute(f"CREATE TRIGGER {name} {body}")


def downgrade():
    for table in reversed(TABLES):
        if (
            op.get_bind()
            .execute(sa.select(sa.literal(1)).select_from(sa.table(table)).limit(1))
            .first()
        ):
            raise RuntimeError("Cannot discard retained declared scope history")
    for trigger in reversed(GUARDS):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.drop_table("infra_automation_run_units")
    op.drop_table("infra_automation_unit_revisions")
