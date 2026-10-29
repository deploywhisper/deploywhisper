"""Preserve exact evidence-bound decision generations and report exports.

Revision ID: 034_add_infra_decisions
Revises: 033_add_infra_preflight
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "034_add_infra_decisions"
down_revision = "033_add_infra_preflight"
branch_labels = None
depends_on = None
TABLES = ("infra_automation_decisions",)
_IMMUTABLE = (
    "id",
    "sequence",
    "run_id",
    "step_id",
    "project_id",
    "workspace_id",
    "requested_by",
    "report_id",
    "generation",
    "binding_bytes",
    "binding_digest",
    "report_bytes",
    "report_digest",
    "created_at",
    "deadline_at",
)
_CHANGED = " OR ".join(f"NEW.{column} IS NOT OLD.{column}" for column in _IMMUTABLE)
GUARDS = {
    "infra_decision_immutable": f"BEFORE UPDATE ON infra_automation_decisions WHEN {_CHANGED} BEGIN SELECT RAISE(ABORT, 'Immutable decision evidence'); END",
    "infra_decision_no_delete": "BEFORE DELETE ON infra_automation_decisions BEGIN SELECT RAISE(ABORT, 'Retained decision evidence'); END",
    "infra_decision_no_replace": "BEFORE INSERT ON infra_automation_decisions WHEN EXISTS (SELECT 1 FROM infra_automation_decisions WHERE id=NEW.id OR (run_id=NEW.run_id AND step_id=NEW.step_id AND generation=NEW.generation)) BEGIN SELECT RAISE(ABORT, 'Immutable decision identity'); END",
    "infra_decision_transition": "BEFORE UPDATE ON infra_automation_decisions WHEN OLD.status != 'pending' OR NEW.status NOT IN ('approved','rejected','expired','invalidated','superseded') OR NEW.version != OLD.version+1 BEGIN SELECT RAISE(ABORT, 'Invalid decision transition'); END",
    "infra_decision_scope": "BEFORE INSERT ON infra_automation_decisions WHEN NOT EXISTS (SELECT 1 FROM analysis_reports WHERE id=NEW.report_id AND project_id=NEW.project_id AND workspace_id=NEW.workspace_id) BEGIN SELECT RAISE(ABORT, 'Decision report scope mismatch'); END",
    "infra_decision_live_deadline": "BEFORE UPDATE ON infra_automation_decisions WHEN NEW.status IN ('approved','rejected') AND NEW.decided_at >= OLD.deadline_at BEGIN SELECT RAISE(ABORT, 'Decision expired'); END",
    "infra_decision_pending_unique": "BEFORE INSERT ON infra_automation_decisions WHEN NEW.status != 'pending' OR EXISTS (SELECT 1 FROM infra_automation_decisions WHERE run_id=NEW.run_id AND step_id=NEW.step_id AND status='pending') BEGIN SELECT RAISE(ABORT, 'Active decision exists'); END",
}


def upgrade():
    op.create_table(
        "infra_automation_decisions",
        sa.Column("sequence", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("step_id", sa.String(128), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.String(64), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("binding_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("binding_digest", sa.String(71), nullable=False),
        sa.Column("report_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("report_digest", sa.String(71), nullable=False),
        sa.Column("decision_kind", sa.String(32), nullable=True),
        sa.Column("reviewer_id", sa.String(64), nullable=True),
        sa.Column("reviewer_authentication_version", sa.Integer(), nullable=True),
        sa.Column("reviewer_authorization_version", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id", "project_id", "workspace_id", "requested_by"],
            [
                "infra_automation_runs.id",
                "infra_automation_runs.project_id",
                "infra_automation_runs.workspace_id",
                "infra_automation_runs.requested_by",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["report_id"], ["analysis_reports.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("id"),
        sa.UniqueConstraint("run_id", "step_id", "generation"),
        sa.CheckConstraint(
            "generation > 0 AND version > 0", name="ck_infra_decision_versions"
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','expired','invalidated','superseded')",
            name="ck_infra_decision_status",
        ),
        sa.CheckConstraint(
            "length(binding_bytes) BETWEEN 1 AND 131072 AND length(report_bytes) BETWEEN 1 AND 8388608 AND length(binding_digest)=71 AND length(report_digest)=71",
            name="ck_infra_decision_bounds",
        ),
        sa.CheckConstraint(
            "(status='pending' AND reviewer_id IS NULL AND reason IS NULL AND decided_at IS NULL) OR (status IN ('approved','rejected') AND reviewer_id IS NOT NULL AND length(reviewer_id)>0 AND reason IS NOT NULL AND length(reason) BETWEEN 1 AND 2048 AND decided_at IS NOT NULL) OR (status IN ('expired','invalidated','superseded') AND reviewer_id IS NULL AND reason IS NOT NULL AND length(reason) BETWEEN 1 AND 2048 AND decided_at IS NOT NULL)",
            name="ck_infra_decision_terminal",
        ),
        sa.CheckConstraint(
            "(status IN ('approved','rejected') AND reviewer_authentication_version > 0 AND reviewer_authorization_version > 0 AND reviewer_authentication_version IS NOT NULL AND reviewer_authorization_version IS NOT NULL) OR (status NOT IN ('approved','rejected') AND reviewer_authentication_version IS NULL AND reviewer_authorization_version IS NULL)",
            name="ck_infra_decision_reviewer_versions",
        ),
        sa.CheckConstraint(
            "(status IN ('approved','rejected') AND decision_kind IS NOT NULL AND decision_kind IN ('independent-approval','acknowledgement')) OR (status NOT IN ('approved','rejected') AND decision_kind IS NULL)",
            name="ck_infra_decision_kind",
        ),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "uq_infra_decision_active",
        "infra_automation_decisions",
        ["run_id", "step_id"],
        unique=True,
        sqlite_where=sa.text("status = 'pending'"),
    )
    for name, body in GUARDS.items():
        op.execute(f"CREATE TRIGGER {name} {body}")


def downgrade():
    for name in GUARDS:
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
    op.drop_table("infra_automation_decisions")
