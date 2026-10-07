"""Persist narrative verification guidance.

Revision ID: 028_add_narrative_guidance_payload
Revises: 027_add_scanner_imports
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "028_add_narrative_guidance_payload"
down_revision = "027_add_scanner_imports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_reports",
        sa.Column(
            "narrative_guidance_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("analysis_reports", "narrative_guidance_json")
