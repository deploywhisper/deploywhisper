"""Retain immutable receiver replay fences and independent carrier observations."""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "036_add_receiver_reconciliation"
down_revision = "035_add_infra_handoffs"
branch_labels = None
depends_on = None
TABLES = ("infra_automation_external_facts",)
GUARDS = {
    "infra_external_fact_no_update": "BEFORE UPDATE ON infra_automation_external_facts BEGIN SELECT RAISE(ABORT, 'Immutable receiver fact'); END",
    "infra_external_fact_no_delete": "BEFORE DELETE ON infra_automation_external_facts BEGIN SELECT RAISE(ABORT, 'Immutable receiver fact'); END",
}


def upgrade():
    op.create_table(
        "infra_automation_external_facts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "operation_id",
            sa.String(64),
            sa.ForeignKey("infra_automation_handoffs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("nonce", sa.String(128), nullable=False),
        sa.Column("payload_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("operation_id", "kind", "sequence"),
        sa.UniqueConstraint("operation_id", "nonce"),
        sa.CheckConstraint(
            "kind IN ('acceptance','observation','callback') AND sequence > 0 AND length(payload_bytes) BETWEEN 1 AND 131072",
            name="ck_external_fact_bounds",
        ),
    )
    for name, body in GUARDS.items():
        op.execute(f"CREATE TRIGGER {name} {body}")


def downgrade():
    if (
        op.get_bind()
        .exec_driver_sql("SELECT 1 FROM infra_automation_external_facts LIMIT 1")
        .first()
    ):
        raise RuntimeError("Cannot downgrade retained receiver reconciliation evidence")
    for action in ("update", "delete"):
        op.execute(f"DROP TRIGGER IF EXISTS infra_external_fact_no_{action}")
    op.drop_table("infra_automation_external_facts")
