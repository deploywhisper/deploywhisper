"""Add inspectable evidence identity fields.

Revision ID: 018_add_evidence_identity_fields
Revises: 017_add_submission_manifest_payload
Create Date: 2026-05-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "018_add_evidence_identity_fields"
down_revision = "017_add_submission_manifest_payload"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evidence_items",
        sa.Column("artifact", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "evidence_items",
        sa.Column("location", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "evidence_items",
        sa.Column("resource", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "evidence_items",
        sa.Column("operation", sa.String(length=40), nullable=False, server_default=""),
    )
    op.add_column(
        "evidence_items", sa.Column("project_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "evidence_items", sa.Column("project_key", sa.String(length=120), nullable=True)
    )
    op.add_column(
        "evidence_items", sa.Column("workspace_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "evidence_items",
        sa.Column("workspace_key", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "evidence_items",
        sa.Column(
            "source_kind",
            sa.String(length=30),
            nullable=False,
            server_default="artifact",
        ),
    )
    op.add_column(
        "evidence_items",
        sa.Column(
            "determinism_level",
            sa.String(length=30),
            nullable=False,
            server_default="deterministic",
        ),
    )
    op.add_column(
        "evidence_items",
        sa.Column(
            "redaction_status",
            sa.String(length=30),
            nullable=False,
            server_default="none",
        ),
    )


def downgrade() -> None:
    op.drop_column("evidence_items", "redaction_status")
    op.drop_column("evidence_items", "determinism_level")
    op.drop_column("evidence_items", "source_kind")
    op.drop_column("evidence_items", "workspace_key")
    op.drop_column("evidence_items", "workspace_id")
    op.drop_column("evidence_items", "project_key")
    op.drop_column("evidence_items", "project_id")
    op.drop_column("evidence_items", "operation")
    op.drop_column("evidence_items", "resource")
    op.drop_column("evidence_items", "location")
    op.drop_column("evidence_items", "artifact")
