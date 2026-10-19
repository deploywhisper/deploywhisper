"""Persist bounded engine state without seeding authority.

Revision ID: 032_add_infra_automation_engine
Revises: 031_add_infra_workflows
"""

from __future__ import annotations
from alembic import op
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Column,
)

revision = "032_add_infra_automation_engine"
down_revision = "031_add_infra_workflows"
branch_labels = None
depends_on = None
TABLES = (
    "infra_automation_runs",
    "infra_automation_attempts",
    "infra_automation_coordinator_lease",
    "infra_automation_run_requests",
)
GUARDS = {
    "infra_automation_runs_no_replace": "BEFORE INSERT ON infra_automation_runs WHEN EXISTS (SELECT 1 FROM infra_automation_runs WHERE sequence=NEW.sequence OR id=NEW.id) BEGIN SELECT RAISE(ABORT, 'Immutable engine identity'); END",
    "infra_automation_runs_no_delete": "BEFORE DELETE ON infra_automation_runs BEGIN SELECT RAISE(ABORT, 'Immutable engine evidence'); END",
    "infra_automation_runs_immutable": "BEFORE UPDATE ON infra_automation_runs WHEN NEW.sequence IS NOT OLD.sequence OR NEW.id IS NOT OLD.id OR NEW.project_id IS NOT OLD.project_id OR NEW.workspace_id IS NOT OLD.workspace_id OR NEW.requested_by IS NOT OLD.requested_by OR NEW.workflow_id IS NOT OLD.workflow_id OR NEW.revision_id IS NOT OLD.revision_id OR NEW.snapshot_bytes IS NOT OLD.snapshot_bytes OR NEW.snapshot_digest IS NOT OLD.snapshot_digest OR NEW.definition_digest IS NOT OLD.definition_digest OR NEW.input_digest IS NOT OLD.input_digest OR NEW.request_digest IS NOT OLD.request_digest OR NEW.created_at IS NOT OLD.created_at OR NEW.deadline_at IS NOT OLD.deadline_at OR NEW.retained_bytes < OLD.retained_bytes OR NEW.external_possible < OLD.external_possible OR NEW.cancel_requested < OLD.cancel_requested OR (OLD.cancellation_requested_at IS NOT NULL AND NEW.cancellation_requested_at IS NOT OLD.cancellation_requested_at) OR NEW.version <= OLD.version OR NEW.last_observed_at < OLD.last_observed_at BEGIN SELECT RAISE(ABORT, 'Immutable engine binding or stale version'); END",
    "infra_automation_attempts_no_replace": "BEFORE INSERT ON infra_automation_attempts WHEN EXISTS (SELECT 1 FROM infra_automation_attempts WHERE sequence=NEW.sequence OR id=NEW.id OR (run_id=NEW.run_id AND step_id=NEW.step_id AND (attempt_number=NEW.attempt_number OR fence=NEW.fence))) BEGIN SELECT RAISE(ABORT, 'Immutable engine identity'); END",
    "infra_automation_attempts_no_delete": "BEFORE DELETE ON infra_automation_attempts BEGIN SELECT RAISE(ABORT, 'Immutable engine evidence'); END",
    "infra_automation_attempts_immutable": "BEFORE UPDATE ON infra_automation_attempts WHEN NEW.sequence IS NOT OLD.sequence OR NEW.id IS NOT OLD.id OR NEW.project_id IS NOT OLD.project_id OR NEW.workspace_id IS NOT OLD.workspace_id OR NEW.requested_by IS NOT OLD.requested_by OR NEW.run_id IS NOT OLD.run_id OR NEW.step_id IS NOT OLD.step_id OR NEW.step_kind IS NOT OLD.step_kind OR NEW.attempt_number IS NOT OLD.attempt_number OR NEW.fence IS NOT OLD.fence OR NEW.handler_id IS NOT OLD.handler_id OR NEW.handler_version IS NOT OLD.handler_version OR NEW.retry_safe IS NOT OLD.retry_safe OR NEW.input_digest IS NOT OLD.input_digest OR NEW.created_at IS NOT OLD.created_at OR NEW.deadline_at IS NOT OLD.deadline_at OR (OLD.coordinator_generation > 0 AND NEW.coordinator_generation IS NOT OLD.coordinator_generation) OR NEW.version <= OLD.version OR NEW.last_observed_at < OLD.last_observed_at BEGIN SELECT RAISE(ABORT, 'Immutable engine binding or stale version'); END",
    "infra_automation_coordinator_lease_no_replace": "BEFORE INSERT ON infra_automation_coordinator_lease WHEN EXISTS (SELECT 1 FROM infra_automation_coordinator_lease WHERE id=NEW.id) BEGIN SELECT RAISE(ABORT, 'Immutable engine identity'); END",
    "infra_automation_coordinator_lease_no_delete": "BEFORE DELETE ON infra_automation_coordinator_lease BEGIN SELECT RAISE(ABORT, 'Immutable engine evidence'); END",
    "infra_automation_coordinator_lease_immutable": "BEFORE UPDATE ON infra_automation_coordinator_lease WHEN NEW.id IS NOT OLD.id OR NEW.generation < OLD.generation OR NEW.version <= OLD.version OR NEW.last_observed_at < OLD.last_observed_at BEGIN SELECT RAISE(ABORT, 'Immutable engine binding or stale version'); END",
    "infra_automation_run_requests_no_replace": "BEFORE INSERT ON infra_automation_run_requests WHEN EXISTS (SELECT 1 FROM infra_automation_run_requests WHERE sequence=NEW.sequence OR id=NEW.id OR (project_id=NEW.project_id AND workspace_id=NEW.workspace_id AND requested_by=NEW.requested_by AND operation=NEW.operation AND key_digest=NEW.key_digest)) BEGIN SELECT RAISE(ABORT, 'Immutable engine identity'); END",
    "infra_automation_run_requests_no_delete": "BEFORE DELETE ON infra_automation_run_requests BEGIN SELECT RAISE(ABORT, 'Immutable engine evidence'); END",
    "infra_automation_run_requests_immutable": "BEFORE UPDATE ON infra_automation_run_requests WHEN 1 BEGIN SELECT RAISE(ABORT, 'Immutable engine binding or stale version'); END",
    "infra_engine_output_immutable": "BEFORE UPDATE ON infra_automation_attempts WHEN OLD.output_json IS NOT NULL AND (NEW.output_json IS NOT OLD.output_json OR NEW.output_digest IS NOT OLD.output_digest) BEGIN SELECT RAISE(ABORT, 'Immutable committed output'); END",
    "infra_engine_run_revision_scope": "BEFORE INSERT ON infra_automation_runs WHEN NOT EXISTS (SELECT 1 FROM infra_workflow_revisions r JOIN infra_workflows w ON w.id=r.workflow_id WHERE r.id=NEW.revision_id AND r.workflow_id=NEW.workflow_id AND r.project_id=NEW.project_id AND (r.workspace_id IS NULL OR r.workspace_id=NEW.workspace_id) AND (w.workspace_id IS NULL OR w.workspace_id=NEW.workspace_id)) BEGIN SELECT RAISE(ABORT, 'Engine revision scope mismatch'); END",
}


def upgrade():
    op.create_table(
        "infra_automation_runs",
        Column(
            "sequence", Integer(), nullable=False, primary_key=True, autoincrement=True
        ),
        Column("id", String(64), nullable=False),
        Column("project_id", Integer(), nullable=False),
        Column("workspace_id", Integer(), nullable=False),
        Column("requested_by", String(64), nullable=False),
        Column("workflow_id", String(64), nullable=False),
        Column("revision_id", String(64), nullable=False),
        Column("snapshot_bytes", LargeBinary(), nullable=False),
        Column("snapshot_digest", String(71), nullable=False),
        Column("definition_digest", String(71), nullable=False),
        Column("input_digest", String(71), nullable=False),
        Column("request_digest", String(71), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("deadline_at", DateTime(timezone=True), nullable=False),
        Column("state", String(24), nullable=False),
        Column("version", Integer(), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        Column("last_observed_at", DateTime(timezone=True), nullable=False),
        Column("cancel_requested", Boolean(), nullable=False),
        Column("cancellation_requested_at", DateTime(timezone=True), nullable=True),
        Column("retained_bytes", Integer(), nullable=False),
        Column("external_possible", Boolean(), nullable=False),
        ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["project_workspaces.project_id", "project_workspaces.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["requested_by"], ["identity_accounts.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("id"),
        UniqueConstraint("id", "project_id", "workspace_id", "requested_by"),
        ForeignKeyConstraint(
            ["workflow_id", "project_id"],
            ["infra_workflows.id", "infra_workflows.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["revision_id"], ["infra_workflow_revisions.id"], ondelete="RESTRICT"
        ),
        CheckConstraint(
            "state IN ('queued','running','waiting_approval','ready_handoff','handing_off','external_running','succeeded','failed','stopped_by_gate','rejected','expired','timed_out','cancelled','delivery_unknown')",
            name="ck_engine_run_state",
        ),
        CheckConstraint(
            "version BETWEEN 1 AND 9007199254740991 AND retained_bytes >= length(snapshot_bytes) AND length(snapshot_bytes) BETWEEN 1 AND 524288",
            name="ck_engine_run_bounds",
        ),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "infra_automation_attempts",
        Column(
            "sequence", Integer(), nullable=False, primary_key=True, autoincrement=True
        ),
        Column("id", String(64), nullable=False),
        Column("project_id", Integer(), nullable=False),
        Column("workspace_id", Integer(), nullable=False),
        Column("requested_by", String(64), nullable=False),
        Column("run_id", String(64), nullable=False),
        Column("step_id", String(128), nullable=False),
        Column("step_kind", String(40), nullable=False),
        Column("attempt_number", Integer(), nullable=False),
        Column("fence", Integer(), nullable=False),
        Column("handler_id", String(128), nullable=False),
        Column("handler_version", String(128), nullable=False),
        Column("retry_safe", Boolean(), nullable=False),
        Column("input_digest", String(71), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("deadline_at", DateTime(timezone=True), nullable=False),
        Column("state", String(24), nullable=False),
        Column("version", Integer(), nullable=False),
        Column("owner_id", String(128), nullable=True),
        Column("owner_hash", String(64), nullable=True),
        Column("coordinator_generation", Integer(), nullable=False),
        Column("lease_until", DateTime(timezone=True), nullable=True),
        Column("last_observed_at", DateTime(timezone=True), nullable=False),
        Column("logs_json", Text(), nullable=False),
        Column("uploads_json", Text(), nullable=False),
        Column("output_json", Text(), nullable=True),
        Column("output_digest", String(71), nullable=True),
        Column("log_bytes", Integer(), nullable=False),
        Column("last_log_sequence", Integer(), nullable=False),
        ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["project_workspaces.project_id", "project_workspaces.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["requested_by"], ["identity_accounts.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("id"),
        UniqueConstraint("run_id", "step_id", "attempt_number"),
        UniqueConstraint("run_id", "step_id", "fence"),
        ForeignKeyConstraint(
            ["run_id", "project_id", "workspace_id", "requested_by"],
            [
                "infra_automation_runs.id",
                "infra_automation_runs.project_id",
                "infra_automation_runs.workspace_id",
                "infra_automation_runs.requested_by",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state IN ('pending','claimed','running','succeeded','failed','timed_out','cancelled')",
            name="ck_engine_attempt_state",
        ),
        CheckConstraint(
            "version BETWEEN 1 AND 9007199254740991 AND attempt_number BETWEEN 1 AND 3 AND fence BETWEEN 1 AND 9007199254740991 AND coordinator_generation BETWEEN 0 AND 9007199254740991 AND log_bytes BETWEEN 0 AND 1048576 AND last_log_sequence >= 0",
            name="ck_engine_attempt_bounds",
        ),
        CheckConstraint(
            "(output_json IS NULL) = (output_digest IS NULL)",
            name="ck_engine_attempt_output",
        ),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "infra_automation_coordinator_lease",
        Column("id", Integer(), nullable=False, primary_key=True, autoincrement=True),
        Column("generation", Integer(), nullable=False),
        Column("version", Integer(), nullable=False),
        Column("owner_id", String(128), nullable=True),
        Column("owner_hash", String(64), nullable=True),
        Column("lease_until", DateTime(timezone=True), nullable=True),
        Column("last_observed_at", DateTime(timezone=True), nullable=False),
        CheckConstraint(
            "id = 1 AND generation BETWEEN 1 AND 9007199254740991 AND version BETWEEN 1 AND 9007199254740991",
            name="ck_engine_lease_bounds",
        ),
    )
    op.create_table(
        "infra_automation_run_requests",
        Column(
            "sequence", Integer(), nullable=False, primary_key=True, autoincrement=True
        ),
        Column("id", String(64), nullable=False),
        Column("project_id", Integer(), nullable=False),
        Column("workspace_id", Integer(), nullable=False),
        Column("requested_by", String(64), nullable=False),
        Column("operation", String(32), nullable=False),
        Column("key_digest", String(71), nullable=False),
        Column("request_digest", String(71), nullable=False),
        Column("run_id", String(64), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["project_workspaces.project_id", "project_workspaces.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["requested_by"], ["identity_accounts.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("id"),
        UniqueConstraint(
            "project_id", "workspace_id", "requested_by", "operation", "key_digest"
        ),
        ForeignKeyConstraint(
            ["run_id", "project_id", "workspace_id", "requested_by"],
            [
                "infra_automation_runs.id",
                "infra_automation_runs.project_id",
                "infra_automation_runs.workspace_id",
                "infra_automation_runs.requested_by",
            ],
            ondelete="RESTRICT",
        ),
        sqlite_autoincrement=True,
    )
    for name, body in GUARDS.items():
        op.execute(f"CREATE TRIGGER {name} {body}")


def downgrade():
    for name in GUARDS:
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
    for name in reversed(TABLES):
        op.drop_table(name)
