"""Add lightweight project/workspace scoping.

Revision ID: 010_add_project_workspaces
Revises: 009_add_report_share_settings
Create Date: 2026-04-28
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "010_add_project_workspaces"
down_revision = "009_add_report_share_settings"
branch_labels = None
depends_on = None


def _ensure_default_project(connection) -> int:
    existing = connection.execute(
        sa.text("SELECT id FROM projects WHERE project_key = :project_key LIMIT 1"),
        {"project_key": "unassigned"},
    ).scalar()
    if existing is not None:
        return int(existing)

    now = datetime.now(UTC).isoformat()
    connection.execute(
        sa.text(
            """
            INSERT INTO projects (
                project_key,
                display_name,
                description,
                repository_url,
                default_branch,
                is_default,
                created_at,
                updated_at
            ) VALUES (
                :project_key,
                :display_name,
                :description,
                NULL,
                NULL,
                :is_default,
                :created_at,
                :updated_at
            )
            """
        ),
        {
            "project_key": "unassigned",
            "display_name": "Unassigned",
            "description": "Legacy and unassigned analyses.",
            "is_default": 1,
            "created_at": now,
            "updated_at": now,
        },
    )
    created = connection.execute(
        sa.text("SELECT id FROM projects WHERE project_key = :project_key LIMIT 1"),
        {"project_key": "unassigned"},
    ).scalar()
    return int(created)


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_key", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("repository_url", sa.String(length=512), nullable=True),
        sa.Column("default_branch", sa.String(length=120), nullable=True),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_key", name="uq_projects_project_key"),
    )
    op.create_index(
        "ix_projects_project_key", "projects", ["project_key"], unique=False
    )

    op.create_table(
        "topology_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column(
            "source_type", sa.String(length=30), nullable=False, server_default="manual"
        ),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_topology_versions_project_id",
        "topology_versions",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "deployment_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("analysis_id", sa.Integer(), nullable=True),
        sa.Column("environment", sa.String(length=80), nullable=True),
        sa.Column(
            "outcome_label",
            sa.String(length=40),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analysis_reports.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_deployment_outcomes_project_id",
        "deployment_outcomes",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "feedback_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("analysis_id", sa.Integer(), nullable=True),
        sa.Column("reviewer_role", sa.String(length=80), nullable=True),
        sa.Column("useful", sa.Boolean(), nullable=True),
        sa.Column("correctness_rating", sa.Integer(), nullable=True),
        sa.Column(
            "false_positive_flag",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("false_negative_note", sa.Text(), nullable=True),
        sa.Column("outcome_label", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analysis_reports.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_feedback_events_project_id",
        "feedback_events",
        ["project_id"],
        unique=False,
    )

    connection = op.get_bind()
    default_project_id = _ensure_default_project(connection)

    op.add_column(
        "analysis_reports",
        sa.Column("project_id", sa.Integer(), nullable=True),
    )
    connection.execute(
        sa.text(
            "UPDATE analysis_reports SET project_id = :project_id WHERE project_id IS NULL"
        ),
        {"project_id": default_project_id},
    )
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.alter_column("project_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_analysis_reports_project_id_projects",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_analysis_reports_project_id",
            ["project_id"],
            unique=False,
        )

    with op.batch_alter_table("projects") as batch_op:
        batch_op.alter_column(
            "is_default",
            existing_type=sa.Boolean(),
            server_default=None,
        )


def downgrade() -> None:
    op.drop_index("ix_feedback_events_project_id", table_name="feedback_events")
    op.drop_table("feedback_events")
    op.drop_index(
        "ix_deployment_outcomes_project_id",
        table_name="deployment_outcomes",
    )
    op.drop_table("deployment_outcomes")
    with op.batch_alter_table("analysis_reports") as batch_op:
        batch_op.drop_index("ix_analysis_reports_project_id")
        batch_op.drop_constraint(
            "fk_analysis_reports_project_id_projects",
            type_="foreignkey",
        )
        batch_op.drop_column("project_id")

    op.drop_index("ix_topology_versions_project_id", table_name="topology_versions")
    op.drop_table("topology_versions")
    op.drop_index("ix_projects_project_key", table_name="projects")
    op.drop_table("projects")
