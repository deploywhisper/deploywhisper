"""Add deployment outcome timestamps and incident linkage.

Revision ID: 011_add_deployment_outcome_fields
Revises: 010_add_project_workspaces
Create Date: 2026-04-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "011_add_deployment_outcome_fields"
down_revision = "010_add_project_workspaces"
branch_labels = None
depends_on = None
_INCIDENT_RECORDS_CREATED_MARKER = "migration:011:created_incident_records"


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table("incident_records"):
        op.create_table(
            "incident_records",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column(
                "severity",
                sa.String(length=20),
                nullable=False,
                server_default="unknown",
            ),
            sa.Column("source_file", sa.String(length=255), nullable=False),
            sa.Column("incident_date", sa.String(length=40), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (:key, :value, CURRENT_TIMESTAMP)
                """
            ),
            {
                "key": _INCIDENT_RECORDS_CREATED_MARKER,
                "value": "true",
            },
        )
    op.add_column(
        "deployment_outcomes",
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "deployment_outcomes",
        sa.Column("linked_incident_id", sa.Integer(), nullable=True),
    )
    connection.execute(
        sa.text(
            """
            UPDATE deployment_outcomes
            SET deployed_at = created_at
            WHERE deployed_at IS NULL
            """
        )
    )
    with op.batch_alter_table("deployment_outcomes") as batch_op:
        batch_op.alter_column(
            "deployed_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )
        batch_op.create_foreign_key(
            "fk_deployment_outcomes_linked_incident_id_incident_records",
            "incident_records",
            ["linked_incident_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    connection = op.get_bind()
    with op.batch_alter_table("deployment_outcomes") as batch_op:
        batch_op.drop_constraint(
            "fk_deployment_outcomes_linked_incident_id_incident_records",
            type_="foreignkey",
        )
        batch_op.drop_column("linked_incident_id")
        batch_op.drop_column("deployed_at")
    marker_present = connection.execute(
        sa.text("SELECT value FROM app_settings WHERE key = :key LIMIT 1"),
        {"key": _INCIDENT_RECORDS_CREATED_MARKER},
    ).scalar()
    if marker_present is not None:
        connection.execute(
            sa.text("DELETE FROM app_settings WHERE key = :key"),
            {"key": _INCIDENT_RECORDS_CREATED_MARKER},
        )
        op.drop_table("incident_records")
