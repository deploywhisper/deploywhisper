"""ORM table metadata."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base

if "IncidentRecord" not in globals():

    class IncidentRecord(Base):
        """Stored incident context for later similarity matching."""

        __tablename__ = "incident_records"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        title: Mapped[str] = mapped_column(String(255))
        severity: Mapped[str] = mapped_column(String(20), default="unknown")
        source_file: Mapped[str] = mapped_column(String(255))
        incident_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
        content: Mapped[str] = mapped_column(Text)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )


if "AnalysisReport" not in globals():

    class AnalysisReport(Base):
        """Stored deploy analysis report for history and audit use."""

        __tablename__ = "analysis_reports"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        risk_score: Mapped[int] = mapped_column(Integer)
        severity: Mapped[str] = mapped_column(String(20))
        recommendation: Mapped[str] = mapped_column(String(20))
        top_risk: Mapped[str] = mapped_column(Text)
        parse_summary: Mapped[str] = mapped_column(Text)
        narrative_opening: Mapped[str] = mapped_column(Text)
        narrative_explanation: Mapped[str] = mapped_column(Text)
        warnings_json: Mapped[str] = mapped_column(Text, default="[]")
        contributors_json: Mapped[str] = mapped_column(Text, default="[]")
        analyzed_files_json: Mapped[str] = mapped_column(Text, default="[]")
        llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
        llm_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
        llm_local_mode: Mapped[str | None] = mapped_column(String(10), nullable=True)
        assessment_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
        narrative_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
        narrative_skills_json: Mapped[str | None] = mapped_column(Text, nullable=True)
        source_interface: Mapped[str | None] = mapped_column(String(30), nullable=True)
        trigger_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
        trigger_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
        dashboard_display_duration_seconds: Mapped[int | None] = mapped_column(
            Integer, nullable=True
        )
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )


if "AppSetting" not in globals():

    class AppSetting(Base):
        """Stored non-secret application settings."""

        __tablename__ = "app_settings"

        key: Mapped[str] = mapped_column(String(100), primary_key=True)
        value: Mapped[str] = mapped_column(Text)
        updated_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC),
            onupdate=lambda: datetime.now(UTC),
        )
