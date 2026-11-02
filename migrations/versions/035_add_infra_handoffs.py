"""Retain canonical target reservations and durable one-use handoff intent.

Revision ID: 035_add_infra_handoffs
Revises: 034_add_infra_decisions
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "035_add_infra_handoffs"
down_revision = "034_add_infra_decisions"
branch_labels = None
depends_on = None
TABLES = (
    "infra_automation_targets",
    "infra_automation_target_aliases",
    "infra_automation_target_scopes",
    "infra_automation_target_locks",
    "infra_automation_run_targets",
    "infra_automation_handoffs",
    "infra_automation_outbox",
    "infra_automation_grants",
)

GUARDS = {
    "infra_targets_no_delete": "BEFORE DELETE ON infra_automation_targets BEGIN SELECT RAISE(ABORT, 'Retained handoff authority'); END",
    "infra_targets_no_replace": "BEFORE INSERT ON infra_automation_targets WHEN EXISTS (SELECT 1 FROM infra_automation_targets WHERE id=NEW.id OR sequence=NEW.sequence) BEGIN SELECT RAISE(ABORT, 'Reserved handoff identity'); END",
    "infra_targets_immutable": "BEFORE UPDATE ON infra_automation_targets WHEN NEW.sequence IS NOT OLD.sequence OR NEW.id IS NOT OLD.id OR NEW.created_by IS NOT OLD.created_by OR NEW.created_at IS NOT OLD.created_at BEGIN SELECT RAISE(ABORT, 'Immutable handoff identity'); END",
    "infra_target_aliases_no_delete": "BEFORE DELETE ON infra_automation_target_aliases BEGIN SELECT RAISE(ABORT, 'Retained handoff authority'); END",
    "infra_target_aliases_no_replace": "BEFORE INSERT ON infra_automation_target_aliases WHEN EXISTS (SELECT 1 FROM infra_automation_target_aliases WHERE alias=NEW.alias) BEGIN SELECT RAISE(ABORT, 'Reserved handoff identity'); END",
    "infra_target_aliases_immutable": "BEFORE UPDATE ON infra_automation_target_aliases WHEN NEW.alias IS NOT OLD.alias OR NEW.target_id IS NOT OLD.target_id OR NEW.created_at IS NOT OLD.created_at BEGIN SELECT RAISE(ABORT, 'Immutable handoff identity'); END",
    "infra_target_locks_no_delete": "BEFORE DELETE ON infra_automation_target_locks BEGIN SELECT RAISE(ABORT, 'Retained handoff authority'); END",
    "infra_target_locks_no_replace": "BEFORE INSERT ON infra_automation_target_locks WHEN EXISTS (SELECT 1 FROM infra_automation_target_locks WHERE id=NEW.id) BEGIN SELECT RAISE(ABORT, 'Reserved handoff identity'); END",
    "infra_target_locks_immutable": "BEFORE UPDATE ON infra_automation_target_locks WHEN NEW.id IS NOT OLD.id OR NEW.target_id IS NOT OLD.target_id OR NEW.run_id IS NOT OLD.run_id OR NEW.project_id IS NOT OLD.project_id OR NEW.workspace_id IS NOT OLD.workspace_id OR NEW.created_at IS NOT OLD.created_at BEGIN SELECT RAISE(ABORT, 'Immutable handoff identity'); END",
    "infra_run_targets_no_delete": "BEFORE DELETE ON infra_automation_run_targets BEGIN SELECT RAISE(ABORT, 'Retained handoff authority'); END",
    "infra_run_targets_no_replace": "BEFORE INSERT ON infra_automation_run_targets WHEN EXISTS (SELECT 1 FROM infra_automation_run_targets WHERE run_id=NEW.run_id AND handoff_step_id=NEW.handoff_step_id) BEGIN SELECT RAISE(ABORT, 'Reserved handoff identity'); END",
    "infra_run_targets_immutable": "BEFORE UPDATE ON infra_automation_run_targets WHEN NEW.run_id IS NOT OLD.run_id OR NEW.handoff_step_id IS NOT OLD.handoff_step_id OR NEW.project_id IS NOT OLD.project_id OR NEW.workspace_id IS NOT OLD.workspace_id OR NEW.target_id IS NOT OLD.target_id OR NEW.target_epoch IS NOT OLD.target_epoch OR NEW.requested_alias IS NOT OLD.requested_alias OR NEW.lock_id IS NOT OLD.lock_id OR NEW.snapshot_bytes IS NOT OLD.snapshot_bytes OR NEW.snapshot_digest IS NOT OLD.snapshot_digest OR NEW.created_at IS NOT OLD.created_at BEGIN SELECT RAISE(ABORT, 'Immutable handoff identity'); END",
    "infra_handoffs_no_delete": "BEFORE DELETE ON infra_automation_handoffs BEGIN SELECT RAISE(ABORT, 'Retained handoff authority'); END",
    "infra_handoffs_no_replace": "BEFORE INSERT ON infra_automation_handoffs WHEN EXISTS (SELECT 1 FROM infra_automation_handoffs WHERE id=NEW.id OR approval_id=NEW.approval_id OR (run_id=NEW.run_id AND step_id=NEW.step_id) OR (project_id=NEW.project_id AND workspace_id=NEW.workspace_id AND prepared_by=NEW.prepared_by AND key_digest=NEW.key_digest)) BEGIN SELECT RAISE(ABORT, 'Reserved handoff identity'); END",
    "infra_handoffs_immutable": "BEFORE UPDATE ON infra_automation_handoffs WHEN NEW.id IS NOT OLD.id OR NEW.run_id IS NOT OLD.run_id OR NEW.step_id IS NOT OLD.step_id OR NEW.approval_id IS NOT OLD.approval_id OR NEW.project_id IS NOT OLD.project_id OR NEW.workspace_id IS NOT OLD.workspace_id OR NEW.target_id IS NOT OLD.target_id OR NEW.receiver_id IS NOT OLD.receiver_id OR NEW.receiver_principal_id IS NOT OLD.receiver_principal_id OR NEW.prepared_by IS NOT OLD.prepared_by OR NEW.key_digest IS NOT OLD.key_digest OR NEW.request_digest IS NOT OLD.request_digest OR NEW.decision_binding_bytes IS NOT OLD.decision_binding_bytes OR NEW.decision_binding_digest IS NOT OLD.decision_binding_digest OR NEW.receiver_binding_bytes IS NOT OLD.receiver_binding_bytes OR NEW.receiver_binding_digest IS NOT OLD.receiver_binding_digest OR NEW.payload_bytes IS NOT OLD.payload_bytes OR NEW.payload_digest IS NOT OLD.payload_digest OR NEW.target_snapshot_bytes IS NOT OLD.target_snapshot_bytes OR NEW.target_snapshot_digest IS NOT OLD.target_snapshot_digest OR NEW.target_epoch IS NOT OLD.target_epoch OR NEW.authorization_epoch IS NOT OLD.authorization_epoch OR NEW.restore_epoch IS NOT OLD.restore_epoch OR NEW.deadline_at IS NOT OLD.deadline_at OR NEW.created_at IS NOT OLD.created_at BEGIN SELECT RAISE(ABORT, 'Immutable handoff identity'); END",
    "infra_outbox_no_delete": "BEFORE DELETE ON infra_automation_outbox BEGIN SELECT RAISE(ABORT, 'Retained handoff authority'); END",
    "infra_outbox_no_replace": "BEFORE INSERT ON infra_automation_outbox WHEN EXISTS (SELECT 1 FROM infra_automation_outbox WHERE operation_id=NEW.operation_id) BEGIN SELECT RAISE(ABORT, 'Reserved handoff identity'); END",
    "infra_outbox_immutable": "BEFORE UPDATE ON infra_automation_outbox WHEN NEW.operation_id IS NOT OLD.operation_id BEGIN SELECT RAISE(ABORT, 'Immutable handoff identity'); END",
    "infra_grants_no_delete": "BEFORE DELETE ON infra_automation_grants BEGIN SELECT RAISE(ABORT, 'Retained handoff authority'); END",
    "infra_grants_no_replace": "BEFORE INSERT ON infra_automation_grants WHEN EXISTS (SELECT 1 FROM infra_automation_grants WHERE id=NEW.id OR operation_id=NEW.operation_id) BEGIN SELECT RAISE(ABORT, 'Reserved handoff identity'); END",
    "infra_grants_immutable": "BEFORE UPDATE ON infra_automation_grants WHEN NEW.id IS NOT OLD.id OR NEW.operation_id IS NOT OLD.operation_id OR NEW.verifier_digest IS NOT OLD.verifier_digest OR NEW.key_ref IS NOT OLD.key_ref OR NEW.receiver_id IS NOT OLD.receiver_id OR NEW.deadline_at IS NOT OLD.deadline_at OR NEW.created_at IS NOT OLD.created_at BEGIN SELECT RAISE(ABORT, 'Immutable handoff identity'); END",
    "infra_target_canonical_reserved": "BEFORE INSERT ON infra_automation_targets WHEN EXISTS (SELECT 1 FROM infra_automation_target_aliases WHERE alias=NEW.id) BEGIN SELECT RAISE(ABORT, 'Canonical target name reserved'); END",
    "infra_target_alias_canonical": "BEFORE INSERT ON infra_automation_target_aliases WHEN EXISTS (SELECT 1 FROM infra_automation_targets WHERE id=NEW.alias AND id!=NEW.target_id) BEGIN SELECT RAISE(ABORT, 'Canonical target alias collision'); END",
    "infra_target_transition": "BEFORE UPDATE ON infra_automation_targets WHEN NEW.version!=OLD.version+1 OR NEW.epoch!=OLD.epoch+1 OR NEW.updated_at<OLD.updated_at OR NEW.last_observed_at<OLD.last_observed_at BEGIN SELECT RAISE(ABORT, 'Invalid target transition'); END",
    "infra_target_alias_transition": "BEFORE UPDATE ON infra_automation_target_aliases WHEN NEW.version!=OLD.version+1 OR NEW.updated_at<OLD.updated_at OR (NEW.alias=OLD.target_id AND NEW.active!=1) BEGIN SELECT RAISE(ABORT, 'Invalid alias transition'); END",
    "infra_target_lock_transition": "BEFORE UPDATE ON infra_automation_target_locks WHEN OLD.status!='held' OR NEW.status NOT IN ('resolved','broken') OR NEW.version!=OLD.version+1 OR NEW.updated_at<OLD.updated_at BEGIN SELECT RAISE(ABORT, 'Invalid lock transition'); END",
    "infra_target_lock_scope": "BEFORE INSERT ON infra_automation_target_locks WHEN NEW.status!='held' OR NEW.version!=1 OR NOT EXISTS (SELECT 1 FROM infra_automation_runs r JOIN infra_automation_target_scopes s ON s.project_id=r.project_id AND s.workspace_id=r.workspace_id WHERE r.id=NEW.run_id AND r.project_id=NEW.project_id AND r.workspace_id=NEW.workspace_id AND s.target_id=NEW.target_id) OR EXISTS (SELECT 1 FROM infra_automation_target_locks WHERE target_id=NEW.target_id AND run_id=NEW.run_id) BEGIN SELECT RAISE(ABORT, 'Lock scope or retained claim mismatch'); END",
    # CASE guarantees lazy JSON parsing even when SQLite reorders AND terms.
    "infra_run_target_scope": "BEFORE INSERT ON infra_automation_run_targets WHEN CASE WHEN json_valid(CAST(NEW.snapshot_bytes AS TEXT)) THEN NOT EXISTS (SELECT 1 FROM infra_automation_target_locks l JOIN infra_automation_targets t ON t.id=l.target_id JOIN infra_automation_target_aliases a ON a.target_id=t.id WHERE l.id=NEW.lock_id AND l.run_id=NEW.run_id AND l.target_id=NEW.target_id AND l.project_id=NEW.project_id AND l.workspace_id=NEW.workspace_id AND l.status='held' AND t.enabled=1 AND t.epoch=NEW.target_epoch AND CAST(json_extract(CAST(NEW.snapshot_bytes AS TEXT), '$.definition') AS TEXT)=CAST(t.definition_bytes AS TEXT) AND json_extract(CAST(NEW.snapshot_bytes AS TEXT), '$.version')=1 AND json_extract(CAST(NEW.snapshot_bytes AS TEXT), '$.target_version')=t.version AND json_extract(CAST(NEW.snapshot_bytes AS TEXT), '$.target_epoch')=t.epoch AND json_extract(CAST(NEW.snapshot_bytes AS TEXT), '$.receiver_principal_id')=t.receiver_principal_id AND EXISTS (SELECT 1 FROM identity_accounts i WHERE i.id=t.receiver_principal_id AND i.enabled=1 AND i.principal_type!='human' AND i.authentication_version=json_extract(CAST(NEW.snapshot_bytes AS TEXT), '$.receiver_authentication_version')) AND a.alias=lower(NEW.requested_alias) AND a.active=1) ELSE 1 END BEGIN SELECT RAISE(ABORT, 'Run target scope mismatch'); END",
    "infra_handoff_scope": "BEFORE INSERT ON infra_automation_handoffs WHEN NEW.state!='prepared' OR NEW.version!=1 OR NEW.broken!=0 OR NOT EXISTS (SELECT 1 FROM infra_automation_decisions d JOIN infra_automation_runs r ON r.id=d.run_id JOIN infra_automation_run_targets s ON s.run_id=r.id JOIN infra_automation_target_locks l ON l.id=s.lock_id JOIN infra_automation_targets t ON t.id=s.target_id WHERE d.id=NEW.approval_id AND d.status='approved' AND d.run_id=NEW.run_id AND d.project_id=NEW.project_id AND d.workspace_id=NEW.workspace_id AND r.project_id=NEW.project_id AND r.workspace_id=NEW.workspace_id AND s.handoff_step_id=NEW.step_id AND s.target_id=NEW.target_id AND s.project_id=NEW.project_id AND s.workspace_id=NEW.workspace_id AND s.target_epoch=NEW.target_epoch AND s.snapshot_bytes=NEW.target_snapshot_bytes AND s.snapshot_digest=NEW.target_snapshot_digest AND d.binding_bytes=NEW.decision_binding_bytes AND d.binding_digest=NEW.decision_binding_digest AND l.status='held' AND t.enabled=1 AND t.epoch=NEW.target_epoch AND t.receiver_principal_id=NEW.receiver_principal_id) BEGIN SELECT RAISE(ABORT, 'Handoff approval or target scope mismatch'); END",
    "infra_handoff_transition": "BEFORE UPDATE ON infra_automation_handoffs WHEN NEW.version!=OLD.version+1 OR NEW.last_observed_at<OLD.last_observed_at OR NEW.broken<OLD.broken OR (OLD.broken=1 AND NEW.state!=OLD.state) OR NOT (NEW.state=OLD.state OR (OLD.state='prepared' AND NEW.state IN ('sending','cancelled')) OR (OLD.state='sending' AND NEW.state IN ('delivery_unknown','consumed','cancelled')) OR (OLD.state='delivery_unknown' AND NEW.state IN ('consumed','accepted','running','succeeded','failed','cancelled')) OR (OLD.state='consumed' AND NEW.state IN ('accepted','running','succeeded','failed','cancelled')) OR (OLD.state='accepted' AND NEW.state IN ('running','succeeded','failed','cancelled')) OR (OLD.state='running' AND NEW.state IN ('succeeded','failed','cancelled'))) BEGIN SELECT RAISE(ABORT, 'Invalid handoff transition'); END",
    "infra_outbox_initial": "BEFORE INSERT ON infra_automation_outbox WHEN NEW.state!='pending' OR NEW.version!=1 OR NEW.attempted_at IS NOT NULL BEGIN SELECT RAISE(ABORT, 'Invalid outbox initial state'); END",
    "infra_outbox_transition": "BEFORE UPDATE ON infra_automation_outbox WHEN NEW.version!=OLD.version+1 OR NEW.updated_at<OLD.updated_at OR (OLD.attempted_at IS NOT NULL AND NEW.attempted_at IS NOT OLD.attempted_at) OR NOT ((OLD.state='pending' AND NEW.state IN ('sending','cancelled')) OR (OLD.state='sending' AND NEW.state IN ('delivery_unknown','delivered','cancelled')) OR (OLD.state='delivery_unknown' AND NEW.state IN ('delivered','cancelled'))) OR (NEW.state IN ('sending','delivery_unknown','delivered') AND NEW.attempted_at IS NULL) BEGIN SELECT RAISE(ABORT, 'Invalid outbox transition'); END",
    "infra_grant_initial": "BEFORE INSERT ON infra_automation_grants WHEN NEW.status!='available' OR NEW.version!=1 OR NOT EXISTS (SELECT 1 FROM infra_automation_handoffs h WHERE h.id=NEW.operation_id AND h.receiver_id=NEW.receiver_id AND h.deadline_at=NEW.deadline_at AND h.state='prepared' AND h.broken=0) BEGIN SELECT RAISE(ABORT, 'Invalid grant operation binding'); END",
    "infra_grant_transition": "BEFORE UPDATE ON infra_automation_grants WHEN OLD.status!='available' OR NEW.status NOT IN ('consumed','invalidated') OR NEW.version!=OLD.version+1 BEGIN SELECT RAISE(ABORT, 'Invalid one-use grant transition'); END",
}


def upgrade():
    op.create_table(
        "infra_automation_targets",
        sa.Column("sequence", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(128), nullable=False, unique=True),
        sa.Column("definition_bytes", sa.LargeBinary, nullable=False),
        sa.Column("definition_digest", sa.String(71), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("epoch", sa.Integer, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("receiver_principal_id", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["receiver_principal_id"], ["identity_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["identity_accounts.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("version > 0 AND epoch > 0", name="ck_target_versions"),
        sa.CheckConstraint(
            "length(id) BETWEEN 1 AND 128 AND id=lower(id) AND length(definition_bytes) BETWEEN 1 AND 131072 AND length(definition_digest)=71",
            name="ck_target_bounds",
        ),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "infra_automation_target_aliases",
        sa.Column("alias", sa.String(128), nullable=False, primary_key=True),
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["target_id"], ["infra_automation_targets.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "version > 0 AND length(alias) BETWEEN 1 AND 128 AND alias=lower(alias)",
            name="ck_target_alias_bounds",
        ),
    )
    op.create_table(
        "infra_automation_target_scopes",
        sa.Column("target_id", sa.String(128), nullable=False, primary_key=True),
        sa.Column("project_id", sa.Integer, nullable=False, primary_key=True),
        sa.Column("workspace_id", sa.Integer, nullable=False, primary_key=True),
        sa.ForeignKeyConstraint(
            ["target_id"], ["infra_automation_targets.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["project_workspaces.project_id", "project_workspaces.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_table(
        "infra_automation_target_locks",
        sa.Column("id", sa.String(64), nullable=False, primary_key=True),
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.Integer, nullable=False),
        sa.Column("workspace_id", sa.Integer, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(256), nullable=False),
        sa.ForeignKeyConstraint(
            ["target_id"], ["infra_automation_targets.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["infra_automation_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["project_workspaces.project_id", "project_workspaces.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('held','resolved','broken') AND version > 0 AND length(reason) BETWEEN 1 AND 256",
            name="ck_target_lock_state",
        ),
    )
    op.create_table(
        "infra_automation_run_targets",
        sa.Column("run_id", sa.String(64), nullable=False, primary_key=True),
        sa.Column("handoff_step_id", sa.String(128), nullable=False, primary_key=True),
        sa.Column("project_id", sa.Integer, nullable=False),
        sa.Column("workspace_id", sa.Integer, nullable=False),
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("target_epoch", sa.Integer, nullable=False),
        sa.Column("requested_alias", sa.String(128), nullable=False),
        sa.Column("lock_id", sa.String(64), nullable=False),
        sa.Column("snapshot_bytes", sa.LargeBinary, nullable=False),
        sa.Column("snapshot_digest", sa.String(71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["infra_automation_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["target_id"], ["infra_automation_targets.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["lock_id"], ["infra_automation_target_locks.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["project_workspaces.project_id", "project_workspaces.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "target_epoch > 0 AND length(snapshot_bytes) BETWEEN 1 AND 131072 AND length(snapshot_digest)=71",
            name="ck_run_target_bounds",
        ),
    )
    op.create_table(
        "infra_automation_handoffs",
        sa.Column("id", sa.String(64), nullable=False, primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("step_id", sa.String(128), nullable=False),
        sa.Column("approval_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.Integer, nullable=False),
        sa.Column("workspace_id", sa.Integer, nullable=False),
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("receiver_id", sa.String(128), nullable=False),
        sa.Column("receiver_principal_id", sa.String(64), nullable=False),
        sa.Column("prepared_by", sa.String(64), nullable=False),
        sa.Column("key_digest", sa.String(71), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("decision_binding_bytes", sa.LargeBinary, nullable=False),
        sa.Column("decision_binding_digest", sa.String(71), nullable=False),
        sa.Column("receiver_binding_bytes", sa.LargeBinary, nullable=False),
        sa.Column("receiver_binding_digest", sa.String(71), nullable=False),
        sa.Column("payload_bytes", sa.LargeBinary, nullable=False),
        sa.Column("payload_digest", sa.String(71), nullable=False),
        sa.Column("target_snapshot_bytes", sa.LargeBinary, nullable=False),
        sa.Column("target_snapshot_digest", sa.String(71), nullable=False),
        sa.Column("target_epoch", sa.Integer, nullable=False),
        sa.Column("authorization_epoch", sa.Integer, nullable=False),
        sa.Column("restore_epoch", sa.Integer, nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("broken", sa.Boolean, nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["infra_automation_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["approval_id"], ["infra_automation_decisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["target_id"], ["infra_automation_targets.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["prepared_by"], ["identity_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["receiver_principal_id"], ["identity_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["project_workspaces.project_id", "project_workspaces.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("run_id", "step_id"),
        sa.UniqueConstraint("approval_id"),
        sa.UniqueConstraint("approval_id", "step_id"),
        sa.UniqueConstraint("project_id", "workspace_id", "prepared_by", "key_digest"),
        sa.CheckConstraint(
            "state IN ('prepared','sending','delivery_unknown','consumed','accepted','running','succeeded','failed','cancelled') AND version > 0 AND target_epoch > 0 AND authorization_epoch > 0 AND restore_epoch > 0",
            name="ck_handoff_state",
        ),
        sa.CheckConstraint(
            "length(decision_binding_bytes) BETWEEN 1 AND 131072 AND length(decision_binding_digest)=71 AND length(receiver_binding_bytes) BETWEEN 1 AND 131072 AND length(receiver_binding_digest)=71 AND length(payload_bytes) BETWEEN 1 AND 131072 AND length(payload_digest)=71 AND length(target_snapshot_bytes) BETWEEN 1 AND 131072 AND length(target_snapshot_digest)=71 AND length(key_digest)=71 AND length(request_digest)=71",
            name="ck_handoff_bounds",
        ),
    )
    op.create_table(
        "infra_automation_outbox",
        sa.Column("operation_id", sa.String(64), nullable=False, primary_key=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id"], ["infra_automation_handoffs.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "state IN ('pending','sending','delivery_unknown','delivered','cancelled') AND version > 0",
            name="ck_outbox_state",
        ),
    )
    op.create_table(
        "infra_automation_grants",
        sa.Column("id", sa.String(64), nullable=False, primary_key=True),
        sa.Column("operation_id", sa.String(64), nullable=False),
        sa.Column("verifier_digest", sa.String(71), nullable=False),
        sa.Column("key_ref", sa.String(128), nullable=False),
        sa.Column("receiver_id", sa.String(128), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("receipt_bytes", sa.LargeBinary, nullable=True),
        sa.Column("receipt_digest", sa.String(71), nullable=True),
        sa.ForeignKeyConstraint(
            ["operation_id"], ["infra_automation_handoffs.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("operation_id"),
        sa.CheckConstraint(
            "status IN ('available','consumed','invalidated') AND version > 0 AND length(verifier_digest)=71 AND length(key_ref) BETWEEN 1 AND 128",
            name="ck_grant_state",
        ),
        sa.CheckConstraint(
            "(status='consumed' AND consumed_at IS NOT NULL AND receipt_bytes IS NOT NULL AND length(receipt_bytes) BETWEEN 1 AND 131072 AND receipt_digest IS NOT NULL AND length(receipt_digest)=71) OR (status IN ('available','invalidated') AND consumed_at IS NULL AND receipt_bytes IS NULL AND receipt_digest IS NULL)",
            name="ck_grant_receipt",
        ),
    )
    op.create_index(
        "uq_infra_target_held",
        "infra_automation_target_locks",
        ["target_id"],
        unique=True,
        sqlite_where=sa.text("status = 'held'"),
    )
    for name, body in GUARDS.items():
        op.execute(f"CREATE TRIGGER {name} {body}")


def downgrade():
    connection = op.get_bind()
    for table in TABLES:
        if connection.exec_driver_sql(f"SELECT 1 FROM {table} LIMIT 1").first():
            raise RuntimeError(
                "Cannot downgrade retained target authority or handoff history"
            )
    for name in GUARDS:
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
    for table in reversed(TABLES):
        op.drop_table(table)
