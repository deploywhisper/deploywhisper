"""Scope learning and context records by project/workspace.

Revision ID: 016_scope_learning_context_records
Revises: 015_add_report_workspace_scope
Create Date: 2026-05-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "016_scope_learning_context_records"
down_revision = "015_add_report_workspace_scope"
branch_labels = None
depends_on = None


def _default_project_id(connection) -> int:
    project_id = connection.execute(
        sa.text(
            """
            SELECT id
            FROM projects
            WHERE is_default = 1 OR project_key = 'unassigned'
            ORDER BY is_default DESC, id ASC
            LIMIT 1
            """
        )
    ).scalar()
    if project_id is None:
        project_id = connection.execute(
            sa.text("SELECT id FROM projects LIMIT 1")
        ).scalar()
    if project_id is None:
        raise RuntimeError("Cannot scope existing learning records without a project.")
    return int(project_id)


def upgrade() -> None:
    connection = op.get_bind()
    default_project_id = _default_project_id(connection)

    op.add_column(
        "incident_records", sa.Column("project_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "incident_records", sa.Column("workspace_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "deployment_outcomes", sa.Column("workspace_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "feedback_events", sa.Column("workspace_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "topology_versions", sa.Column("workspace_id", sa.Integer(), nullable=True)
    )

    connection.execute(
        sa.text(
            """
            UPDATE incident_records
            SET project_id = (
                    SELECT analysis_reports.project_id
                    FROM analysis_reports
                    WHERE analysis_reports.id = incident_records.analysis_id
                ),
                workspace_id = (
                    SELECT analysis_reports.workspace_id
                    FROM analysis_reports
                    WHERE analysis_reports.id = incident_records.analysis_id
                )
            WHERE analysis_id IS NOT NULL
            """
        )
    )
    connection.execute(
        sa.text(
            "UPDATE incident_records SET project_id = :project_id WHERE project_id IS NULL"
        ),
        {"project_id": default_project_id},
    )
    connection.execute(
        sa.text(
            """
            UPDATE deployment_outcomes
            SET workspace_id = (
                SELECT analysis_reports.workspace_id
                FROM analysis_reports
                WHERE analysis_reports.id = deployment_outcomes.analysis_id
            )
            WHERE analysis_id IS NOT NULL
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE feedback_events
            SET workspace_id = (
                SELECT analysis_reports.workspace_id
                FROM analysis_reports
                WHERE analysis_reports.id = feedback_events.analysis_id
            )
            WHERE analysis_id IS NOT NULL
            """
        )
    )

    with op.batch_alter_table("project_workspaces") as batch_op:
        batch_op.create_unique_constraint(
            "uq_project_workspaces_project_id_id",
            ["project_id", "id"],
        )

    with op.batch_alter_table("incident_records") as batch_op:
        batch_op.alter_column(
            "project_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.create_foreign_key(
            "fk_incident_records_project_id_projects",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_incident_records_workspace_id_project_workspaces",
            "project_workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_incident_records_project_workspace_scope",
            "project_workspaces",
            ["project_id", "workspace_id"],
            ["project_id", "id"],
        )
        batch_op.create_index("ix_incident_records_project_id", ["project_id"])
        batch_op.create_index("ix_incident_records_workspace_id", ["workspace_id"])

    for table_name in ("deployment_outcomes", "feedback_events", "topology_versions"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_foreign_key(
                f"fk_{table_name}_workspace_id_project_workspaces",
                "project_workspaces",
                ["workspace_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_foreign_key(
                f"fk_{table_name}_project_workspace_scope",
                "project_workspaces",
                ["project_id", "workspace_id"],
                ["project_id", "id"],
            )
            batch_op.create_index(f"ix_{table_name}_workspace_id", ["workspace_id"])


def downgrade() -> None:
    for table_name in ("topology_versions", "feedback_events", "deployment_outcomes"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_index(f"ix_{table_name}_workspace_id")
            batch_op.drop_constraint(
                f"fk_{table_name}_project_workspace_scope",
                type_="foreignkey",
            )
            batch_op.drop_constraint(
                f"fk_{table_name}_workspace_id_project_workspaces",
                type_="foreignkey",
            )
            batch_op.drop_column("workspace_id")

    with op.batch_alter_table("incident_records") as batch_op:
        batch_op.drop_index("ix_incident_records_workspace_id")
        batch_op.drop_index("ix_incident_records_project_id")
        batch_op.drop_constraint(
            "fk_incident_records_project_workspace_scope",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_incident_records_workspace_id_project_workspaces",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_incident_records_project_id_projects",
            type_="foreignkey",
        )
        batch_op.drop_column("workspace_id")
        batch_op.drop_column("project_id")

    with op.batch_alter_table("project_workspaces") as batch_op:
        batch_op.drop_constraint(
            "uq_project_workspaces_project_id_id",
            type_="unique",
        )
