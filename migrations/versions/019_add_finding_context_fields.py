"""Add finding explanation, guidance, and evidence classification.

Revision ID: 019_add_finding_context_fields
Revises: 018_add_evidence_identity_fields
Create Date: 2026-05-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "019_add_finding_context_fields"
down_revision = "018_add_evidence_identity_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "findings",
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "findings",
        sa.Column("guidance_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "findings",
        sa.Column(
            "evidence_classification",
            sa.String(length=30),
            nullable=False,
            server_default="deterministic",
        ),
    )
    op.execute(
        "UPDATE findings SET explanation = description "
        "WHERE explanation IS NULL OR explanation = ''"
    )
    op.execute(
        "UPDATE findings SET evidence_classification = 'model_inferred' "
        "WHERE deterministic = 0"
    )


def downgrade() -> None:
    op.drop_column("findings", "evidence_classification")
    op.drop_column("findings", "guidance_json")
    op.drop_column("findings", "explanation")
