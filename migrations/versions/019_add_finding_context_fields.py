"""Add finding explanation, guidance, and evidence classification.

Revision ID: 019_add_finding_context_fields
Revises: 018_add_evidence_identity_fields
Create Date: 2026-05-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

_FINDING_EVIDENCE_CLASSIFICATION_VALUES = (
    "deterministic",
    "derived",
    "external",
    "model_inferred",
    "user_provided",
)
_FINDING_EVIDENCE_CLASSIFICATION_SQL = ", ".join(
    f"'{value}'" for value in _FINDING_EVIDENCE_CLASSIFICATION_VALUES
)


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
            sa.CheckConstraint(
                f"evidence_classification IN ({_FINDING_EVIDENCE_CLASSIFICATION_SQL})",
                name="ck_findings_evidence_classification",
            ),
            nullable=False,
            server_default="deterministic",
        ),
    )
    findings = sa.table(
        "findings",
        sa.column("description", sa.Text()),
        sa.column("explanation", sa.Text()),
        sa.column("deterministic", sa.Boolean()),
        sa.column("evidence_classification", sa.String(length=30)),
    )
    op.execute(
        findings.update()
        .where(sa.or_(findings.c.explanation.is_(None), findings.c.explanation == ""))
        .values(explanation=findings.c.description)
    )
    op.execute(
        findings.update()
        .where(findings.c.deterministic.is_(sa.false()))
        .values(evidence_classification="model_inferred")
    )


def downgrade() -> None:
    op.drop_column("findings", "evidence_classification")
    op.drop_column("findings", "guidance_json")
    op.drop_column("findings", "explanation")
