"""Retain scoped runner enrollment, credential generations and task bindings."""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "037_add_runner_enrollment"
down_revision = "036_add_receiver_reconciliation"
branch_labels = None
depends_on = None
TABLES = (
    "infra_automation_runners",
    "infra_automation_runner_enrollments",
    "infra_automation_runner_tasks",
)
GUARDS = {}


def upgrade():
    op.create_table(
        "infra_automation_runners",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("tags_json", sa.Text(), nullable=False),
        sa.Column("tool", sa.String(128), nullable=False),
        sa.Column("profile_digest", sa.String(71), nullable=False),
        sa.Column("runner_version", sa.String(128), nullable=False),
        sa.Column("protocol_version", sa.Integer(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("credential_hash", sa.String(64), nullable=True),
        sa.Column("credential_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "issuer_principal_id",
            sa.String(64),
            sa.ForeignKey("identity_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("issuer_authentication_version", sa.Integer(), nullable=False),
        sa.Column("issuer_membership_version", sa.Integer(), nullable=False),
        sa.Column("authorization_epoch", sa.Integer(), nullable=False),
        sa.Column("restore_epoch", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["project_workspaces.project_id", "project_workspaces.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "generation > 0 AND protocol_version = 1 AND status IN ('pending','active','revoked')",
            name="ck_runner_state",
        ),
    )
    op.create_index(
        "ix_infra_automation_runners_project_id",
        "infra_automation_runners",
        ["project_id"],
    )
    op.create_table(
        "infra_automation_runner_enrollments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "runner_id",
            sa.String(64),
            sa.ForeignKey("infra_automation_runners.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "infra_automation_runner_tasks",
        sa.Column(
            "attempt_id",
            sa.String(64),
            sa.ForeignKey("infra_automation_attempts.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "runner_id",
            sa.String(64),
            sa.ForeignKey("infra_automation_runners.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("credential_generation", sa.Integer(), nullable=False),
        sa.Column("profile_digest", sa.String(71), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("upload_id", sa.String(128), nullable=True),
        sa.Column("upload_digest", sa.String(71), nullable=True),
        sa.Column("upload_bytes", sa.LargeBinary(), nullable=True),
        sa.CheckConstraint(
            "credential_generation > 0 AND sequence >= 0",
            name="ck_runner_task_sequence",
        ),
    )
    op.create_index(
        "ix_infra_automation_runner_tasks_runner_id",
        "infra_automation_runner_tasks",
        ["runner_id"],
    )


def downgrade():
    for table in (
        "infra_automation_runner_tasks",
        "infra_automation_runner_enrollments",
        "infra_automation_runners",
    ):
        if (
            op.get_bind()
            .execute(sa.select(sa.literal(1)).select_from(sa.table(table)).limit(1))
            .first()
        ):
            raise RuntimeError("Cannot discard retained runner authority history")
    op.drop_table("infra_automation_runner_tasks")
    op.drop_table("infra_automation_runner_enrollments")
    op.drop_table("infra_automation_runners")
