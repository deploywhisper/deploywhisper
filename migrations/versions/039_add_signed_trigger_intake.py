"""Retain bounded signed replay fences and immutable run provenance."""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "039_add_signed_trigger_intake"
down_revision = "038_add_declared_unit_maps"
branch_labels = None
depends_on = None
TABLES = (
    "infra_automation_trigger_clock",
    "infra_automation_trigger_nonces",
    "infra_automation_run_origins",
)
GUARDS = {
    "infra_run_origin_no_update": "BEFORE UPDATE ON infra_automation_run_origins BEGIN SELECT RAISE(ABORT, 'immutable run origin'); END",
    "infra_run_origin_no_delete": "BEFORE DELETE ON infra_automation_run_origins BEGIN SELECT RAISE(ABORT, 'retained run origin'); END",
    "infra_run_origin_no_replace": "BEFORE INSERT ON infra_automation_run_origins WHEN EXISTS(SELECT 1 FROM infra_automation_run_origins WHERE run_id=NEW.run_id) BEGIN SELECT RAISE(ABORT, 'retained run origin'); END",
    "infra_trigger_clock_monotonic": "BEFORE UPDATE ON infra_automation_trigger_clock WHEN NEW.id != OLD.id OR NEW.last_seen_at < OLD.last_seen_at BEGIN SELECT RAISE(ABORT, 'invalid trigger clock'); END",
    "infra_trigger_clock_no_delete": "BEFORE DELETE ON infra_automation_trigger_clock BEGIN SELECT RAISE(ABORT, 'retained trigger clock'); END",
    "infra_trigger_clock_no_replace": "BEFORE INSERT ON infra_automation_trigger_clock WHEN EXISTS(SELECT 1 FROM infra_automation_trigger_clock WHERE id=NEW.id) BEGIN SELECT RAISE(ABORT, 'retained trigger clock'); END",
    "infra_trigger_nonce_no_update": "BEFORE UPDATE ON infra_automation_trigger_nonces BEGIN SELECT RAISE(ABORT, 'immutable trigger nonce'); END",
    "infra_trigger_nonce_no_replace": "BEFORE INSERT ON infra_automation_trigger_nonces WHEN EXISTS(SELECT 1 FROM infra_automation_trigger_nonces WHERE key_id=NEW.key_id AND nonce_digest=NEW.nonce_digest) BEGIN SELECT RAISE(ABORT, 'retained trigger nonce'); END",
}


def upgrade():
    op.create_table(
        TABLES[0],
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_trigger_clock_singleton"),
    )
    op.create_table(
        TABLES[1],
        sa.Column("key_id", sa.String(128), primary_key=True),
        sa.Column("nonce_digest", sa.String(64), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_infra_automation_trigger_nonces_expires_at", TABLES[1], ["expires_at"]
    )
    op.create_index(
        "ix_infra_automation_trigger_nonces_project_id", TABLES[1], ["project_id"]
    )
    op.create_table(
        TABLES[2],
        sa.Column(
            "run_id",
            sa.String(64),
            sa.ForeignKey("infra_automation_runs.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("origin_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("origin_digest", sa.String(71), nullable=False),
        sa.Column("operation_digest", sa.String(71), nullable=True),
        sa.Column("key_id", sa.String(128), nullable=True),
        sa.Column("source_repository_id", sa.String(128), nullable=True),
        sa.Column("source_commit_sha", sa.String(40), nullable=True),
        sa.CheckConstraint(
            "length(origin_bytes) BETWEEN 1 AND 32768", name="ck_run_origin_bytes"
        ),
    )
    op.create_index("ix_infra_automation_run_origins_key_id", TABLES[2], ["key_id"])
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
        raise RuntimeError("Retained signed authority requires explicit recovery.")
    for table in reversed(TABLES):
        op.drop_table(table)
