"""Database engine and session helpers."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy import inspect
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

engine = create_engine(settings.database_url, future=True)
_KNOWN_ALEMBIC_REVISIONS = {
    "0001_create_analysis_reports",
    "005_add_evidence_model",
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
