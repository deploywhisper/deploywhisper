"""Bind short-lived recovery credentials to retained consumed operations.

Revision ID: 042_add_receiver_recovery
Revises: 041_add_operator_recovery
"""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "042_add_receiver_recovery"
down_revision = "041_add_operator_recovery"
branch_labels = None
depends_on = None
TABLES = ("infra_automation_receiver_recovery_credentials",)
_FIXED = (
    "operation_id",
    "project_id",
    "workspace_id",
    "receiver_id",
    "receiver_principal_id",
    "installation_id",
    "binding_digest",
    "receipt_digest",
)
_ALL = (
    "operation_id",
    "project_id",
    "workspace_id",
    "receiver_id",
    "receiver_principal_id",
    "installation_id",
    "generation",
    "project_restore_epoch",
    "receiver_authentication_version",
    "issuer_id",
    "issuer_authentication_version",
    "issuer_membership_version",
    "version",
    "issue_count",
    "mode",
    "token_hash",
    "binding_digest",
    "receipt_digest",
    "credential_digest",
    "issued_at",
    "expires_at",
)
_FIXED_CHANGED = " OR ".join(f"NEW.{name} IS NOT OLD.{name}" for name in _FIXED)
_SAME = " AND ".join(f"NEW.{name} IS OLD.{name}" for name in _ALL)
GUARDS = {
    "infra_receiver_recovery_no_delete": "BEFORE DELETE ON infra_automation_receiver_recovery_credentials BEGIN SELECT RAISE(ABORT, 'Retained receiver recovery fence'); END",
    "infra_receiver_recovery_no_replace": "BEFORE INSERT ON infra_automation_receiver_recovery_credentials WHEN EXISTS(SELECT 1 FROM infra_automation_receiver_recovery_credentials WHERE operation_id=NEW.operation_id) BEGIN SELECT RAISE(ABORT, 'Retained receiver recovery fence'); END",
    "infra_receiver_recovery_immutable": "BEFORE UPDATE ON infra_automation_receiver_recovery_credentials WHEN "
    + _FIXED_CHANGED
    + " OR NEW.last_observed_at < OLD.last_observed_at OR NOT (("
    + _SAME
    + ") OR (NEW.version=OLD.version+1 AND NEW.generation>=OLD.generation AND NEW.project_restore_epoch>=OLD.project_restore_epoch AND NEW.receiver_authentication_version>=OLD.receiver_authentication_version AND NEW.issued_at>=OLD.last_observed_at AND NEW.last_observed_at=NEW.issued_at AND NEW.token_hash!=OLD.token_hash AND (OLD.mode!='status_only' OR NEW.mode='status_only') AND ((NEW.generation=OLD.generation AND NEW.issue_count=OLD.issue_count+1) OR (NEW.generation>OLD.generation AND NEW.issue_count=1)))) BEGIN SELECT RAISE(ABORT, 'Immutable receiver recovery binding'); END",
    "infra_receiver_recovery_scope": "BEFORE INSERT ON infra_automation_receiver_recovery_credentials WHEN NOT EXISTS (SELECT 1 FROM infra_automation_handoffs h JOIN infra_automation_grants g ON g.operation_id=h.id JOIN infra_automation_recovery_state s ON s.id=1 JOIN infra_automation_policies p ON p.project_id=h.project_id WHERE h.id=NEW.operation_id AND h.project_id=NEW.project_id AND h.workspace_id=NEW.workspace_id AND h.receiver_id=NEW.receiver_id AND h.receiver_principal_id=NEW.receiver_principal_id AND h.receiver_binding_digest=NEW.binding_digest AND g.status='consumed' AND g.receipt_digest=NEW.receipt_digest AND s.installation_id=NEW.installation_id AND s.generation=NEW.generation AND s.phase='reconciliation_required' AND p.restore_epoch=NEW.project_restore_epoch) BEGIN SELECT RAISE(ABORT, 'Receiver recovery scope mismatch'); END",
}


def upgrade():
    op.create_table(
        TABLES[0],
        sa.Column(
            "operation_id",
            sa.String(64),
            sa.ForeignKey("infra_automation_handoffs.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("receiver_id", sa.String(128), nullable=False),
        sa.Column(
            "receiver_principal_id",
            sa.String(64),
            sa.ForeignKey("identity_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("installation_id", sa.String(32), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("project_restore_epoch", sa.Integer(), nullable=False),
        sa.Column("receiver_authentication_version", sa.Integer(), nullable=False),
        sa.Column(
            "issuer_id",
            sa.String(64),
            sa.ForeignKey("identity_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("issuer_authentication_version", sa.Integer(), nullable=False),
        sa.Column("issuer_membership_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("issue_count", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("binding_digest", sa.String(71), nullable=False),
        sa.Column("receipt_digest", sa.String(71), nullable=False),
        sa.Column("credential_digest", sa.String(71), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version BETWEEN 1 AND 9007199254740991 AND generation BETWEEN 1 AND 9007199254740991 AND project_restore_epoch BETWEEN 1 AND 9007199254740991 AND receiver_authentication_version BETWEEN 1 AND 9007199254740991 AND issuer_authentication_version BETWEEN 1 AND 9007199254740991 AND issuer_membership_version BETWEEN 1 AND 9007199254740991 AND issue_count BETWEEN 1 AND 100",
            name="ck_receiver_recovery_versions",
        ),
        sa.CheckConstraint(
            "mode IN ('status_only','status_terminal') AND length(installation_id)=32 AND length(token_hash)=64 AND length(binding_digest)=71 AND length(receipt_digest)=71 AND length(credential_digest)=71",
            name="ck_receiver_recovery_binding",
        ),
        sa.CheckConstraint(
            "issued_at <= last_observed_at AND issued_at < expires_at",
            name="ck_receiver_recovery_time",
        ),
    )
    for name, body in GUARDS.items():
        op.execute(sa.text(f"CREATE TRIGGER {name} {body}"))


def downgrade():
    if (
        op.get_bind()
        .execute(sa.select(sa.literal(1)).select_from(sa.table(TABLES[0])).limit(1))
        .first()
    ):
        raise RuntimeError("Retained receiver recovery history prevents downgrade.")
    op.drop_table(TABLES[0])
