"""Permit one-way screened payload removal while retaining immutable identity.

Revision ID: 040_add_manifest_retention
Revises: 039_add_signed_trigger_intake
"""

from __future__ import annotations

from importlib import import_module

from alembic import op
import sqlalchemy as sa

revision = "040_add_manifest_retention"
down_revision = "039_add_signed_trigger_intake"
branch_labels = None
depends_on = None
TABLES = ("infra_automation_retention_tombstones",)
_COLUMNS = (
    "id",
    "run_id",
    "step_id",
    "project_id",
    "workspace_id",
    "requested_by",
    "digest",
    "created_at",
    "collection_bytes",
    "collection_digest",
)
_CHANGED = " OR ".join(f"NEW.{name} IS NOT OLD.{name}" for name in _COLUMNS)
OVERRIDES = {
    "infra_preflight_infra_automation_artifact_manifests_no_update": "".join(
        (
            "BEFORE UPDATE ON infra_automation_artifact_manifests WHEN ",
            _CHANGED,
            " OR NOT (NEW.artifacts_bytes=X'5b5d' AND OLD.artifacts_bytes!=X'5b5d' AND EXISTS (SELECT 1 FROM infra_automation_retention_tombstones t WHERE t.manifest_id=OLD.id AND t.original_digest=OLD.digest AND t.original_size=length(OLD.artifacts_bytes) AND t.run_id=OLD.run_id AND t.project_id=OLD.project_id AND t.workspace_id=OLD.workspace_id)) BEGIN SELECT RAISE(ABORT, 'Immutable preflight evidence'); END",
        )
    ),
}
# Retain every original engine-identity/version/clock clause. Only its monotonic
# byte-counter clause gains this one-use, exact tombstone-backed debit exception.
_ORIGINAL_RUN_GUARD = import_module(
    "migrations.versions.032_add_infra_automation_engine"
).GUARDS["infra_automation_runs_immutable"]
_DEBIT_PROOF = "".join(
    (
        "EXISTS (SELECT 1 FROM infra_automation_retention_tombstones t JOIN infra_automation_artifact_manifests m ON m.id=t.manifest_id WHERE t.run_id=OLD.id AND t.project_id=OLD.project_id AND t.workspace_id=OLD.workspace_id AND t.expected_run_version=OLD.version AND NEW.version=OLD.version+1 AND NEW.retained_bytes=OLD.retained_bytes-t.reclaimed_bytes AND NEW.retained_bytes>=length(OLD.snapshot_bytes) AND NEW.state=OLD.state AND OLD.state IN ('succeeded','failed','stopped_by_gate','rejected','expired','timed_out','cancelled') AND OLD.external_possible=0 AND NEW.external_possible=OLD.external_possible AND NEW.cancel_requested=OLD.cancel_requested AND NEW.cancellation_requested_at IS OLD.cancellation_requested_at AND NEW.updated_at=t.deleted_at AND NEW.last_observed_at=t.deleted_at AND m.run_id=OLD.id AND m.project_id=OLD.project_id AND m.workspace_id=OLD.workspace_id AND m.digest=t.original_digest AND m.artifacts_bytes=X'5b5d' AND NOT EXISTS (SELECT 1 FROM infra_automation_decisions d WHERE d.run_id=OLD.id AND d.status IN ('pending','approved')) AND NOT EXISTS (SELECT 1 FROM infra_automation_handoffs h WHERE h.run_id=OLD.id) AND NOT EXISTS (SELECT 1 FROM infra_automation_target_locks l WHERE l.run_id=OLD.id AND l.status!='resolved'))",
    )
)
OVERRIDES["infra_automation_runs_immutable"] = _ORIGINAL_RUN_GUARD.replace(
    "NEW.retained_bytes < OLD.retained_bytes",
    "".join(("(NEW.retained_bytes < OLD.retained_bytes AND NOT (", _DEBIT_PROOF, "))")),
)

GUARDS = {
    "infra_retention_no_update": "BEFORE UPDATE ON infra_automation_retention_tombstones BEGIN SELECT RAISE(ABORT, 'Immutable retention receipt'); END",
    "infra_retention_no_delete": "BEFORE DELETE ON infra_automation_retention_tombstones BEGIN SELECT RAISE(ABORT, 'Immutable retention receipt'); END",
    "infra_retention_no_replace": "BEFORE INSERT ON infra_automation_retention_tombstones WHEN EXISTS (SELECT 1 FROM infra_automation_retention_tombstones WHERE manifest_id=NEW.manifest_id) BEGIN SELECT RAISE(ABORT, 'Immutable retention identity'); END",
    "infra_retention_scope": "BEFORE INSERT ON infra_automation_retention_tombstones WHEN NOT EXISTS (SELECT 1 FROM infra_automation_artifact_manifests m JOIN infra_automation_runs r ON r.id=m.run_id WHERE m.id=NEW.manifest_id AND m.run_id=NEW.run_id AND m.project_id=NEW.project_id AND m.workspace_id=NEW.workspace_id AND m.digest=NEW.original_digest AND length(m.artifacts_bytes)=NEW.original_size AND m.artifacts_bytes!=X'5b5d' AND r.version=NEW.expected_run_version AND r.external_possible=0 AND r.state IN ('succeeded','failed','stopped_by_gate','rejected','expired','timed_out','cancelled')) OR EXISTS (SELECT 1 FROM infra_automation_decisions WHERE run_id=NEW.run_id AND status IN ('pending','approved')) OR EXISTS (SELECT 1 FROM infra_automation_handoffs WHERE run_id=NEW.run_id) OR EXISTS (SELECT 1 FROM infra_automation_target_locks WHERE run_id=NEW.run_id AND status!='resolved') BEGIN SELECT RAISE(ABORT, 'Protected retention evidence'); END",
}


def upgrade():
    op.create_table(
        TABLES[0],
        sa.Column(
            "manifest_id",
            sa.String(64),
            sa.ForeignKey(
                "infra_automation_artifact_manifests.id", ondelete="RESTRICT"
            ),
            primary_key=True,
        ),
        sa.Column(
            "run_id",
            sa.String(64),
            sa.ForeignKey("infra_automation_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("original_digest", sa.String(71), nullable=False),
        sa.Column("original_size", sa.Integer(), nullable=False),
        sa.Column("reclaimed_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "actor_id",
            sa.String(64),
            sa.ForeignKey("identity_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(256), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_run_version", sa.Integer(), nullable=False),
        sa.Column("request_digest", sa.String(71), nullable=False),
        sa.Column("receipt_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("receipt_digest", sa.String(71), nullable=False),
        sa.CheckConstraint(
            "typeof(original_size)='integer' AND typeof(reclaimed_bytes)='integer' AND original_size BETWEEN 1 AND 50331648 AND reclaimed_bytes BETWEEN 1 AND original_size-1 AND length(original_digest)=71 AND length(receipt_digest)=71 AND length(request_digest)=71 AND length(receipt_bytes) BETWEEN 1 AND 4096 AND expected_run_version > 0 AND length(reason) BETWEEN 1 AND 256",
            name="ck_retention_receipt_bounds",
        ),
    )
    for name, body in {**GUARDS, **OVERRIDES}.items():
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
        op.execute(f"CREATE TRIGGER {name} {body}")


def downgrade():
    # A marker cannot be converted back into the removed original bytes.
    if (
        op.get_bind()
        .exec_driver_sql("SELECT 1 FROM infra_automation_retention_tombstones LIMIT 1")
        .first()
    ):
        raise RuntimeError("Retained removals prevent a lossless downgrade.")
    from importlib import import_module

    original = import_module("migrations.versions.033_add_infra_preflight")
    for name in GUARDS:
        op.execute(f"DROP TRIGGER {name}")
    for name in OVERRIDES:
        op.execute(f"DROP TRIGGER {name}")
        op.execute(
            f"CREATE TRIGGER {name} {(original.GUARDS[name] if name in original.GUARDS else _ORIGINAL_RUN_GUARD)}"
        )
    op.drop_table(TABLES[0])
