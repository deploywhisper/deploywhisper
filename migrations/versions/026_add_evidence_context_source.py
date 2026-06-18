"""Persist evidence context source metadata.

Revision ID: 026_add_evidence_context_source
Revises: 025_add_event_analysis_indexes
Create Date: 2026-06-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "026_add_evidence_context_source"
down_revision = "025_add_event_analysis_indexes"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if "context_source_json" not in _columns("evidence_items"):
        op.add_column(
            "evidence_items",
            sa.Column("context_source_json", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if "context_source_json" in _columns("evidence_items"):
        op.drop_column("evidence_items", "context_source_json")
