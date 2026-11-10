"""Bind offline restore to an external monotonic installation ledger."""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "041_add_operator_recovery"
down_revision = "040_add_manifest_retention"
branch_labels = None
depends_on = None
TABLES = ("infra_automation_recovery_state", "infra_automation_restore_events")
GUARDS = {
    "infra_recovery_state_monotonic": "BEFORE UPDATE ON infra_automation_recovery_state WHEN NEW.id IS NOT OLD.id OR NEW.installation_id IS NOT OLD.installation_id OR NEW.generation < OLD.generation OR NEW.updated_at < OLD.updated_at BEGIN SELECT RAISE(ABORT, 'Invalid recovery generation'); END",
    "infra_recovery_state_no_delete": "BEFORE DELETE ON infra_automation_recovery_state BEGIN SELECT RAISE(ABORT, 'Retained recovery fence'); END",
    "infra_recovery_state_no_replace": "BEFORE INSERT ON infra_automation_recovery_state WHEN EXISTS(SELECT 1 FROM infra_automation_recovery_state WHERE id=NEW.id) BEGIN SELECT RAISE(ABORT, 'Retained recovery fence'); END",
    "infra_restore_events_no_update": "BEFORE UPDATE ON infra_automation_restore_events BEGIN SELECT RAISE(ABORT, 'Immutable restore event'); END",
    "infra_restore_events_no_delete": "BEFORE DELETE ON infra_automation_restore_events BEGIN SELECT RAISE(ABORT, 'Retained restore event'); END",
    "infra_restore_events_no_replace": "BEFORE INSERT ON infra_automation_restore_events WHEN EXISTS(SELECT 1 FROM infra_automation_restore_events WHERE id=NEW.id) BEGIN SELECT RAISE(ABORT, 'Retained restore event'); END",
}


def upgrade():
    op.create_table(
        TABLES[0],
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("installation_id", sa.String(32), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(32), nullable=False),
        sa.Column("manifest_digest", sa.String(71), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "id=1 AND generation BETWEEN 1 AND 9007199254740991",
            name="ck_recovery_generation",
        ),
        sa.CheckConstraint(
            "phase IN ('ready','reconciliation_required') AND length(installation_id)=32",
            name="ck_recovery_phase",
        ),
    )
    op.create_table(
        TABLES[1],
        sa.Column("id", sa.String(32), primary_key=True, nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("backup_digest", sa.String(71), nullable=False),
        sa.Column("event", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "generation BETWEEN 1 AND 9007199254740991 AND event IN ('restored','completed')",
            name="ck_restore_event",
        ),
    )
    for name, body in GUARDS.items():
        op.execute(sa.text(f"CREATE TRIGGER {name} {body}"))


def downgrade():
    bind = op.get_bind()
    if any(
        bind.execute(
            sa.select(sa.literal(1)).select_from(sa.table(table)).limit(1)
        ).first()
        for table in TABLES
    ):
        raise RuntimeError("Operator recovery history requires explicit recovery.")
    for table in reversed(TABLES):
        op.drop_table(table)
