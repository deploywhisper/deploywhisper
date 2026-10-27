"""Protect immutable uploaded manifests and relational report provenance.

Revision ID: 033_add_infra_preflight
Revises: 032_add_infra_automation_engine
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import (
    Column,
    String,
    Integer,
    LargeBinary,
    DateTime,
    ForeignKeyConstraint,
    UniqueConstraint,
    CheckConstraint,
)

revision = "033_add_infra_preflight"
down_revision = "032_add_infra_automation_engine"
branch_labels = None
depends_on = None
TABLES = ("infra_automation_artifact_manifests", "infra_automation_report_links")
GUARDS = {}
for table in TABLES:
    GUARDS[f"infra_preflight_{table}_no_update"] = (
        f"BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'Immutable preflight evidence'); END"
    )
    GUARDS[f"infra_preflight_{table}_no_delete"] = (
        f"BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'Immutable preflight evidence'); END"
    )
    GUARDS[f"infra_preflight_{table}_no_replace"] = (
        f"BEFORE INSERT ON {table} WHEN EXISTS (SELECT 1 FROM {table} WHERE id=NEW.id) BEGIN SELECT RAISE(ABORT, 'Immutable preflight evidence'); END"
    )
GUARDS["infra_preflight_manifest_unique"] = (
    "BEFORE INSERT ON infra_automation_artifact_manifests WHEN EXISTS (SELECT 1 FROM infra_automation_artifact_manifests WHERE run_id=NEW.run_id AND step_id=NEW.step_id) BEGIN SELECT RAISE(ABORT, 'Immutable preflight identity'); END"
)
GUARDS["infra_preflight_link_unique"] = (
    "BEFORE INSERT ON infra_automation_report_links WHEN EXISTS (SELECT 1 FROM infra_automation_report_links WHERE attempt_id=NEW.attempt_id OR report_id=NEW.report_id) BEGIN SELECT RAISE(ABORT, 'Immutable preflight identity'); END"
)
GUARDS["infra_preflight_report_no_replace"] = (
    "BEFORE INSERT ON analysis_reports WHEN EXISTS (SELECT 1 FROM infra_automation_report_links WHERE report_id=NEW.id) BEGIN SELECT RAISE(ABORT, 'Immutable linked report'); END"
)
GUARDS["infra_preflight_manifest_scope"] = (
    "BEFORE INSERT ON infra_automation_artifact_manifests WHEN NOT EXISTS (SELECT 1 FROM infra_automation_runs r WHERE r.id=NEW.run_id AND r.project_id=NEW.project_id AND r.workspace_id=NEW.workspace_id AND r.requested_by=NEW.requested_by) BEGIN SELECT RAISE(ABORT, 'Preflight scope mismatch'); END"
)
GUARDS["infra_preflight_report_scope"] = (
    "BEFORE INSERT ON infra_automation_report_links WHEN NOT EXISTS (SELECT 1 FROM analysis_reports r JOIN infra_automation_attempts a ON a.id=NEW.attempt_id WHERE r.id=NEW.report_id AND r.project_id=NEW.project_id AND r.workspace_id=NEW.workspace_id AND r.authorization_required=1 AND a.run_id=NEW.run_id AND a.project_id=NEW.project_id AND a.workspace_id=NEW.workspace_id AND a.requested_by=NEW.requested_by AND a.step_kind='shared_analysis') BEGIN SELECT RAISE(ABORT, 'Preflight report scope mismatch'); END"
)
for table, column, primary_key in (
    ("analysis_reports", "id", "id"),
    ("findings", "analysis_id", "finding_id"),
    ("evidence_items", "analysis_id", "evidence_id"),
    ("risk_assessments", "analysis_id", "analysis_id"),
    ("context_snapshots", "analysis_id", "analysis_id"),
):
    old_parent = f"EXISTS (SELECT 1 FROM infra_automation_report_links WHERE report_id=OLD.{column})"
    new_parent = f"EXISTS (SELECT 1 FROM infra_automation_report_links WHERE report_id=NEW.{column})"
    # REPLACE deletes conflicting rows without firing DELETE guards when SQLite
    # recursive_triggers is off. Check the existing identity before both INSERT
    # and UPDATE OR REPLACE can remove a child of a protected report. Findings'
    # other UNIQUE key includes its globally unique finding_id primary key.
    conflicting_identity = (
        f"EXISTS (SELECT 1 FROM {table} child JOIN infra_automation_report_links linked "
        f"ON linked.report_id=child.{column} WHERE child.{primary_key}=NEW.{primary_key})"
    )
    GUARDS[f"infra_preflight_{table}_no_update"] = (
        f"BEFORE UPDATE ON {table} WHEN {old_parent} OR {new_parent} OR {conflicting_identity} "
        "BEGIN SELECT RAISE(ABORT, 'Immutable linked report'); END"
    )
    GUARDS[f"infra_preflight_{table}_no_delete"] = (
        f"BEFORE DELETE ON {table} WHEN {old_parent} "
        "BEGIN SELECT RAISE(ABORT, 'Immutable linked report'); END"
    )
    if table != "analysis_reports":
        GUARDS[f"infra_preflight_{table}_no_insert"] = (
            f"BEFORE INSERT ON {table} WHEN {new_parent} OR {conflicting_identity} "
            "BEGIN SELECT RAISE(ABORT, 'Immutable linked report'); END"
        )


def upgrade():
    op.create_table(
        "infra_automation_artifact_manifests",
        Column("id", String(64), primary_key=True),
        Column("run_id", String(64), nullable=False),
        Column("step_id", String(128), nullable=False),
        Column("project_id", Integer(), nullable=False),
        Column("workspace_id", Integer(), nullable=False),
        Column("requested_by", String(64), nullable=False),
        Column("artifacts_bytes", LargeBinary(), nullable=False),
        Column("digest", String(71), nullable=False),
        Column("collection_bytes", LargeBinary(), nullable=True),
        Column("collection_digest", String(71), nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        ForeignKeyConstraint(
            ["run_id", "project_id", "workspace_id", "requested_by"],
            [
                "infra_automation_runs.id",
                "infra_automation_runs.project_id",
                "infra_automation_runs.workspace_id",
                "infra_automation_runs.requested_by",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("run_id", "step_id"),
        UniqueConstraint("id", "run_id", "project_id", "workspace_id", "requested_by"),
        CheckConstraint(
            "length(artifacts_bytes) BETWEEN 1 AND 50331648 AND length(digest) = 71",
            name="ck_preflight_manifest_bounds",
        ),
        CheckConstraint(
            "(collection_bytes IS NULL) = (collection_digest IS NULL) AND (collection_bytes IS NULL OR length(collection_bytes) BETWEEN 1 AND 16384)",
            name="ck_preflight_collection_bounds",
        ),
    )
    op.create_table(
        "infra_automation_report_links",
        Column("id", String(64), primary_key=True),
        Column("run_id", String(64), nullable=False),
        Column("attempt_id", String(64), nullable=False),
        Column("manifest_id", String(64), nullable=False),
        Column("report_id", Integer(), nullable=False),
        Column("project_id", Integer(), nullable=False),
        Column("workspace_id", Integer(), nullable=False),
        Column("requested_by", String(64), nullable=False),
        Column("provenance_bytes", LargeBinary(), nullable=False),
        Column("digest", String(71), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        ForeignKeyConstraint(
            ["manifest_id", "run_id", "project_id", "workspace_id", "requested_by"],
            [
                "infra_automation_artifact_manifests.id",
                "infra_automation_artifact_manifests.run_id",
                "infra_automation_artifact_manifests.project_id",
                "infra_automation_artifact_manifests.workspace_id",
                "infra_automation_artifact_manifests.requested_by",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["attempt_id"], ["infra_automation_attempts.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["report_id"], ["analysis_reports.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("attempt_id"),
        UniqueConstraint("report_id"),
        CheckConstraint(
            "length(provenance_bytes) BETWEEN 1 AND 16384 AND length(digest) = 71",
            name="ck_preflight_link_bounds",
        ),
    )
    for name, body in GUARDS.items():
        op.execute(f"CREATE TRIGGER {name} {body}")


def downgrade():
    for name in reversed(GUARDS):
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
    for table in reversed(TABLES):
        op.drop_table(table)
