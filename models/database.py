"""Database engine and session helpers."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from config import settings
from models.tables import Base

engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


ANALYSIS_REPORT_AUDIT_COLUMNS = {
    "analyzed_files_json": "TEXT DEFAULT '[]'",
    "llm_provider": "VARCHAR(50)",
    "llm_model": "VARCHAR(120)",
    "llm_local_mode": "VARCHAR(10)",
    "assessment_source": "VARCHAR(30)",
    "narrative_source": "VARCHAR(30)",
    "narrative_skills_json": "TEXT DEFAULT '[]'",
    "source_interface": "VARCHAR(30)",
    "trigger_type": "VARCHAR(30)",
    "trigger_id": "VARCHAR(120)",
    "dashboard_display_duration_seconds": "INTEGER",
}


def _ensure_analysis_report_audit_columns() -> None:
    inspector = inspect(engine)
    if "analysis_reports" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("analysis_reports")}
    missing_columns = {
        name: ddl
        for name, ddl in ANALYSIS_REPORT_AUDIT_COLUMNS.items()
        if name not in existing_columns
    }
    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name, ddl in missing_columns.items():
            connection.execute(text(f"ALTER TABLE analysis_reports ADD COLUMN {column_name} {ddl}"))


def init_db() -> None:
    """Create database tables for the current metadata set."""
    Base.metadata.create_all(bind=engine)
    _ensure_analysis_report_audit_columns()
