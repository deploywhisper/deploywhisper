"""Database engine and session helpers."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import DateTime, Integer, String, create_engine
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy import inspect
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings


def _ensure_sqlite_parent_directory(database_url: str) -> None:
    try:
        url = make_url(database_url)
    except Exception:  # noqa: BLE001
        return
    if url.drivername != "sqlite":
        return
    database = url.database or ""
    if not database or database == ":memory:":
        return
    Path(database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_parent_directory(settings.database_url)
engine = create_engine(settings.database_url, future=True)
_KNOWN_ALEMBIC_REVISIONS = {
    "0001_create_analysis_reports",
    "005_add_evidence_model",
    "006_add_report_schema_version",
    "007_add_blast_radius_payload",
    "008_add_rollback_plan_payload",
    "009_add_report_share_settings",
    "010_add_project_workspaces",
    "011_add_deployment_outcome_fields",
    "012_add_feedback_event_fields",
    "013_add_incident_analysis_reference",
    "014_add_project_workspace_records",
    "015_add_report_workspace_scope",
    "016_scope_learning_context_records",
}
_BASELINE_TABLES = {"analysis_reports", "app_settings"}
_EVIDENCE_TABLES = {
    "findings",
    "evidence_items",
    "risk_assessments",
    "context_snapshots",
}


def _is_sqlite_url(database_url: str) -> bool:
    return database_url.startswith("sqlite")


if _is_sqlite_url(settings.database_url):

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


existing_session_local = globals().get("SessionLocal")

if existing_session_local is not None:
    existing_session_local.configure(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    SessionLocal = existing_session_local
else:
    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )

if "Base" not in globals():
    Base = declarative_base()


def _alembic_config() -> Config:
    config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def _write_alembic_revision(connection, revision: str) -> None:
    connection.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS alembic_version (
            version_num VARCHAR(32) NOT NULL,
            CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
        )
        """
    )
    connection.exec_driver_sql("DELETE FROM alembic_version")
    connection.exec_driver_sql(
        "INSERT INTO alembic_version (version_num) VALUES (?)", (revision,)
    )


def _repair_partial_evidence_schema(connection, tables: set[str]) -> set[str]:
    present_evidence_tables = tables & _EVIDENCE_TABLES
    if not present_evidence_tables or present_evidence_tables == _EVIDENCE_TABLES:
        return tables

    for table_name in (
        "context_snapshots",
        "risk_assessments",
        "evidence_items",
        "findings",
    ):
        if table_name in present_evidence_tables:
            connection.exec_driver_sql(f"DROP TABLE IF EXISTS {table_name}")

    refreshed_tables = set(inspect(connection).get_table_names())
    return refreshed_tables


def _analysis_report_columns(connection) -> set[str]:
    return {
        column["name"] for column in inspect(connection).get_columns("analysis_reports")
    }


def _deployment_outcome_columns(connection) -> set[str]:
    return {
        column["name"]
        for column in inspect(connection).get_columns("deployment_outcomes")
    }


def _feedback_event_columns(connection) -> set[str]:
    return {
        column["name"] for column in inspect(connection).get_columns("feedback_events")
    }


def _incident_record_columns(connection) -> set[str]:
    return {
        column["name"] for column in inspect(connection).get_columns("incident_records")
    }


def _incident_record_has_analysis_link(connection) -> bool:
    inspector = inspect(connection)
    foreign_keys = inspector.get_foreign_keys("incident_records")
    indexes = inspector.get_indexes("incident_records")
    has_foreign_key = any(
        foreign_key.get("referred_table") == "analysis_reports"
        and "analysis_id" in (foreign_key.get("constrained_columns") or [])
        for foreign_key in foreign_keys
    )
    has_index = any(
        "analysis_id" in (index.get("column_names") or []) for index in indexes
    )
    return has_foreign_key and has_index


def _project_workspace_columns(connection) -> set[str]:
    return {
        column["name"]
        for column in inspect(connection).get_columns("project_workspaces")
    }


def _project_workspace_schema_complete(connection) -> bool:
    inspector = inspect(connection)
    column_map = {
        column["name"]: column
        for column in inspect(connection).get_columns("project_workspaces")
    }
    columns = set(column_map)
    required_columns = {
        "id",
        "project_id",
        "workspace_key",
        "display_name",
        "description",
        "environment",
        "created_at",
        "updated_at",
    }
    required_non_nullable_columns = {
        "project_id",
        "workspace_key",
        "display_name",
        "created_at",
        "updated_at",
    }
    has_required_nullability = all(
        column_name in column_map and column_map[column_name].get("nullable") is False
        for column_name in required_non_nullable_columns
    )
    has_primary_key = bool(column_map.get("id", {}).get("primary_key"))
    required_type_affinities = {
        "id": Integer,
        "project_id": Integer,
        "workspace_key": String,
        "display_name": String,
        "description": String,
        "environment": String,
        "created_at": DateTime,
        "updated_at": DateTime,
    }
    has_required_types = all(
        column_name in column_map
        and column_map[column_name]["type"]._type_affinity is expected_affinity
        for column_name, expected_affinity in required_type_affinities.items()
    )
    has_unique_key = any(
        set(constraint.get("column_names") or []) == {"project_id", "workspace_key"}
        for constraint in inspector.get_unique_constraints("project_workspaces")
    )
    has_project_fk = any(
        foreign_key.get("referred_table") == "projects"
        and "project_id" in (foreign_key.get("constrained_columns") or [])
        and (foreign_key.get("options") or {}).get("ondelete") == "CASCADE"
        for foreign_key in inspector.get_foreign_keys("project_workspaces")
    )
    indexed_columns = {
        tuple(index.get("column_names") or [])
        for index in inspector.get_indexes("project_workspaces")
    }
    return (
        required_columns.issubset(columns)
        and has_required_nullability
        and has_primary_key
        and has_required_types
        and has_unique_key
        and has_project_fk
        and ("project_id",) in indexed_columns
        and ("workspace_key",) in indexed_columns
    )


def _analysis_report_workspace_scope_complete(connection) -> bool:
    inspector = inspect(connection)
    column_map = {
        column["name"]: column
        for column in inspect(connection).get_columns("analysis_reports")
    }
    workspace_column = column_map.get("workspace_id")
    has_workspace_column = (
        workspace_column is not None
        and workspace_column["type"]._type_affinity is Integer
        and workspace_column.get("nullable") is True
    )
    has_workspace_fk = any(
        foreign_key.get("referred_table") == "project_workspaces"
        and "workspace_id" in (foreign_key.get("constrained_columns") or [])
        and "id" in (foreign_key.get("referred_columns") or [])
        and (foreign_key.get("options") or {}).get("ondelete") == "SET NULL"
        for foreign_key in inspector.get_foreign_keys("analysis_reports")
    )
    indexed_columns = {
        tuple(index.get("column_names") or [])
        for index in inspector.get_indexes("analysis_reports")
    }
    return (
        has_workspace_column
        and has_workspace_fk
        and ("workspace_id",) in indexed_columns
    )


def _learning_context_scope_complete(connection) -> bool:
    inspector = inspect(connection)
    workspace_unique_columns = {
        tuple(unique.get("column_names") or [])
        for unique in inspector.get_unique_constraints("project_workspaces")
    }
    has_workspace_project_id_unique = (
        "project_id",
        "id",
    ) in workspace_unique_columns

    def has_workspace_scope(table_name: str) -> bool:
        columns = {
            column["name"]: column for column in inspector.get_columns(table_name)
        }
        workspace_column = columns.get("workspace_id")
        has_workspace_column = (
            workspace_column is not None
            and workspace_column["type"]._type_affinity is Integer
            and workspace_column.get("nullable") is True
        )
        has_workspace_fk = any(
            foreign_key.get("referred_table") == "project_workspaces"
            and "workspace_id" in (foreign_key.get("constrained_columns") or [])
            and "id" in (foreign_key.get("referred_columns") or [])
            and (foreign_key.get("options") or {}).get("ondelete") == "SET NULL"
            for foreign_key in inspector.get_foreign_keys(table_name)
        )
        has_project_workspace_scope_fk = any(
            foreign_key.get("referred_table") == "project_workspaces"
            and (foreign_key.get("constrained_columns") or [])
            == ["project_id", "workspace_id"]
            and (foreign_key.get("referred_columns") or []) == ["project_id", "id"]
            for foreign_key in inspector.get_foreign_keys(table_name)
        )
        indexed_columns = {
            tuple(index.get("column_names") or [])
            for index in inspector.get_indexes(table_name)
        }
        return (
            has_workspace_column
            and has_workspace_fk
            and has_project_workspace_scope_fk
            and ("workspace_id",) in indexed_columns
        )

    incident_columns = {
        column["name"]: column for column in inspector.get_columns("incident_records")
    }
    incident_project_column = incident_columns.get("project_id")
    has_incident_project_column = (
        incident_project_column is not None
        and incident_project_column["type"]._type_affinity is Integer
        and incident_project_column.get("nullable") is False
    )
    has_incident_project_fk = any(
        foreign_key.get("referred_table") == "projects"
        and "project_id" in (foreign_key.get("constrained_columns") or [])
        and "id" in (foreign_key.get("referred_columns") or [])
        and (foreign_key.get("options") or {}).get("ondelete") == "CASCADE"
        for foreign_key in inspector.get_foreign_keys("incident_records")
    )
    incident_indexed_columns = {
        tuple(index.get("column_names") or [])
        for index in inspector.get_indexes("incident_records")
    }
    return (
        has_workspace_project_id_unique
        and has_incident_project_column
        and has_incident_project_fk
        and ("project_id",) in incident_indexed_columns
        and has_workspace_scope("incident_records")
        and has_workspace_scope("deployment_outcomes")
        and has_workspace_scope("feedback_events")
        and has_workspace_scope("topology_versions")
    )


def _bootstrap_brownfield_revision() -> None:
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        tables = _repair_partial_evidence_schema(connection, tables)

        has_baseline_tables = _BASELINE_TABLES.issubset(tables)
        has_evidence_tables = _EVIDENCE_TABLES.issubset(tables)
        has_project_workspace_table = "project_workspaces" in tables
        has_complete_workspace_records = (
            has_project_workspace_table
            and _project_workspace_schema_complete(connection)
            and has_baseline_tables
            and "projects" in tables
            and "topology_versions" in tables
        )
        if has_project_workspace_table and not has_complete_workspace_records:
            raise RuntimeError(
                "Detected a partial project workspace schema without a complete "
                "migration history. Manual recovery is required."
            )
        if not has_baseline_tables and "alembic_version" not in tables:
            return

        revision = None
        if "alembic_version" in tables:
            revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version LIMIT 1"
            ).scalar()

        if revision in _KNOWN_ALEMBIC_REVISIONS:
            return

        report_columns = (
            _analysis_report_columns(connection)
            if "analysis_reports" in tables
            else set()
        )
        deployment_outcome_columns = (
            _deployment_outcome_columns(connection)
            if "deployment_outcomes" in tables
            else set()
        )
        feedback_event_columns = (
            _feedback_event_columns(connection)
            if "feedback_events" in tables
            else set()
        )
        incident_record_columns = (
            _incident_record_columns(connection)
            if "incident_records" in tables
            else set()
        )
        has_feedback_fields = {
            "finding_id",
            "false_positive_reason",
        }.issubset(feedback_event_columns)
        has_complete_incident_link = {"analysis_id"}.issubset(
            incident_record_columns
        ) and _incident_record_has_analysis_link(connection)
        has_report_workspace_scope = "workspace_id" in report_columns
        has_complete_report_workspace_scope = (
            has_report_workspace_scope
            and _analysis_report_workspace_scope_complete(connection)
        )
        scoped_learning_columns_present = (
            "project_id" in incident_record_columns
            or "workspace_id" in incident_record_columns
            or "workspace_id" in deployment_outcome_columns
            or "workspace_id" in feedback_event_columns
            or (
                "topology_versions" in tables
                and "workspace_id"
                in {
                    column["name"]
                    for column in inspect(connection).get_columns("topology_versions")
                }
            )
        )
        has_complete_learning_context_scope = (
            "incident_records" in tables
            and "deployment_outcomes" in tables
            and "feedback_events" in tables
            and "topology_versions" in tables
            and scoped_learning_columns_present
            and _learning_context_scope_complete(connection)
        )
        if scoped_learning_columns_present and not has_complete_learning_context_scope:
            raise RuntimeError(
                "Detected a partial learning/context scope schema without a complete "
                "migration history. Manual recovery is required."
            )
        if has_complete_learning_context_scope:
            _write_alembic_revision(connection, "016_scope_learning_context_records")
            return
        if has_report_workspace_scope and not has_complete_report_workspace_scope:
            raise RuntimeError(
                "Detected a partial analysis report workspace scope schema without "
                "a complete migration history. Manual recovery is required."
            )
        if (
            has_complete_workspace_records
            and "projects" in tables
            and "topology_versions" in tables
            and "project_id" in report_columns
            and has_complete_report_workspace_scope
        ):
            _write_alembic_revision(connection, "015_add_report_workspace_scope")
            return
        if (
            has_complete_workspace_records
            and "projects" in tables
            and "topology_versions" in tables
            and "project_id" in report_columns
        ):
            _write_alembic_revision(connection, "014_add_project_workspace_records")
            return
        if has_complete_incident_link and has_feedback_fields:
            _write_alembic_revision(connection, "013_add_incident_analysis_reference")
            return
        if "analysis_id" in incident_record_columns:
            raise RuntimeError(
                "Detected a partial incident-analysis link schema without a complete "
                "migration history. Manual recovery is required."
            )
        if has_feedback_fields:
            _write_alembic_revision(connection, "012_add_feedback_event_fields")
            return
        if {
            "deployed_at",
            "linked_incident_id",
        }.issubset(deployment_outcome_columns):
            _write_alembic_revision(connection, "011_add_deployment_outcome_fields")
            return
        if (
            "projects" in tables
            and "topology_versions" in tables
            and "project_id" in report_columns
        ):
            _write_alembic_revision(connection, "010_add_project_workspaces")
            return
        if {
            "report_schema_version",
            "blast_radius_json",
            "rollback_plan_json",
            "share_redact_filenames",
        }.issubset(report_columns):
            _write_alembic_revision(connection, "009_add_report_share_settings")
            return
        if {
            "report_schema_version",
            "blast_radius_json",
            "rollback_plan_json",
        }.issubset(report_columns):
            _write_alembic_revision(connection, "008_add_rollback_plan_payload")
            return
        if {"report_schema_version", "blast_radius_json"}.issubset(report_columns):
            _write_alembic_revision(connection, "007_add_blast_radius_payload")
            return
        if "report_schema_version" in report_columns:
            _write_alembic_revision(connection, "006_add_report_schema_version")
            return

        if has_evidence_tables:
            _write_alembic_revision(connection, "005_add_evidence_model")
            return

        if has_baseline_tables:
            _write_alembic_revision(connection, "0001_create_analysis_reports")
            return

        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
        if not set(inspect(connection).get_table_names()):
            return
        raise RuntimeError(
            "Unable to repair database migration state automatically. "
            "Manual recovery is required."
        )


def _run_migrations() -> None:
    command.upgrade(_alembic_config(), "head")


def init_db() -> None:
    """Create database tables for the current metadata set."""
    import_module("models.tables")
    _bootstrap_brownfield_revision()
    _run_migrations()
    Base.metadata.create_all(bind=engine)
