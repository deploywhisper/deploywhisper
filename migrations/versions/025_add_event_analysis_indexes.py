"""Add event analysis indexes for risk trends.

Revision ID: 025_add_event_analysis_indexes
Revises: 024_add_analysis_duration_seconds
Create Date: 2026-06-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "025_add_event_analysis_indexes"
down_revision = "024_add_analysis_duration_seconds"
branch_labels = None
depends_on = None


def _index_columns(table_name: str, index_name: str) -> tuple[str, ...] | None:
    inspector = sa.inspect(op.get_bind())
    for index in inspector.get_indexes(table_name):
        if index["name"] == index_name:
            return tuple(index.get("column_names") or ())
    return None


def _ensure_index(table_name: str, index_name: str, columns: list[str]) -> None:
    existing_columns = _index_columns(table_name, index_name)
    expected_columns = tuple(columns)
    if existing_columns == expected_columns:
        return
    if existing_columns is not None:
        op.drop_index(index_name, table_name=table_name)
    op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    _ensure_index(
        "deployment_outcomes",
        "ix_deployment_outcomes_analysis_deployed_outcome",
        ["analysis_id", "deployed_at", "outcome_label"],
    )
    _ensure_index(
        "feedback_events",
        "ix_feedback_events_analysis_created",
        ["analysis_id", "created_at"],
    )


def downgrade() -> None:
    if _index_columns("feedback_events", "ix_feedback_events_analysis_created"):
        op.drop_index(
            "ix_feedback_events_analysis_created",
            table_name="feedback_events",
        )
    if _index_columns(
        "deployment_outcomes",
        "ix_deployment_outcomes_analysis_deployed_outcome",
    ):
        op.drop_index(
            "ix_deployment_outcomes_analysis_deployed_outcome",
            table_name="deployment_outcomes",
        )
