"""Add evidence-domain foundation tables.

Revision ID: 005_add_evidence_model
Revises: 0001_create_analysis_reports
Create Date: 2026-04-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "005_add_evidence_model"
down_revision = "0001_create_analysis_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "findings",
        sa.Column("finding_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.Integer(),
            sa.ForeignKey("analysis_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("deterministic", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("uncertainty_note", sa.Text(), nullable=True),
        sa.Column("evidence_refs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("skill_id", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_findings_confidence_range",
        ),
        sa.UniqueConstraint(
            "finding_id",
            "analysis_id",
            name="uq_findings_finding_id_analysis_id",
        ),
    )
    op.create_index("ix_findings_analysis_id", "findings", ["analysis_id"])

    op.create_table(
        "evidence_items",
        sa.Column("evidence_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.Integer(),
            sa.ForeignKey("analysis_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("finding_id", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("severity_hint", sa.String(length=20), nullable=False),
        sa.Column("deterministic", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column(
            "related_change_ids_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_evidence_items_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["finding_id", "analysis_id"],
            ["findings.finding_id", "findings.analysis_id"],
            name="fk_evidence_items_finding_analysis",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_evidence_items_analysis_id", "evidence_items", ["analysis_id"])
    op.create_index("ix_evidence_items_finding_id", "evidence_items", ["finding_id"])

    op.create_table(
        "risk_assessments",
        sa.Column(
            "analysis_id",
            sa.Integer(),
            sa.ForeignKey("analysis_reports.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("overall_severity", sa.String(length=20), nullable=False),
        sa.Column("recommendation", sa.String(length=20), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column(
            "top_risk_contributors_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "context_completeness_json", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_score_range"),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_risk_assessments_confidence_range",
        ),
    )

    op.create_table(
        "context_snapshots",
        sa.Column(
            "analysis_id",
            sa.Integer(),
            sa.ForeignKey("analysis_reports.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("topology_version", sa.String(length=120), nullable=True),
        sa.Column("incident_index_version", sa.String(length=120), nullable=True),
        sa.Column("history_window", sa.String(length=60), nullable=True),
        sa.Column(
            "criticality_inputs_json", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column("owner_mapping_version", sa.String(length=120), nullable=True),
        sa.Column("skills_active_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("context_snapshots")
    op.drop_table("risk_assessments")
    op.drop_index("ix_evidence_items_finding_id", table_name="evidence_items")
    op.drop_index("ix_evidence_items_analysis_id", table_name="evidence_items")
    op.drop_table("evidence_items")
    op.drop_index("ix_findings_analysis_id", table_name="findings")
    op.drop_table("findings")
