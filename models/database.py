"""Database engine and session helpers."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
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


def _bootstrap_brownfield_revision() -> None:
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        tables = _repair_partial_evidence_schema(connection, tables)

        has_baseline_tables = _BASELINE_TABLES.issubset(tables)
        has_evidence_tables = _EVIDENCE_TABLES.issubset(tables)
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
