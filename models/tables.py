"""ORM table metadata."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
        analysis_id: Mapped[int | None] = mapped_column(
            ForeignKey("analysis_reports.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        )
        content: Mapped[str] = mapped_column(Text)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )
        deployment_outcomes: Mapped[list["DeploymentOutcome"]] = relationship(
            back_populates="incident"
        )


if "Project" not in globals():

    class Project(Base):
        """Lightweight project/workspace scope for reports and context."""

        __tablename__ = "projects"
        __table_args__ = (
            UniqueConstraint("project_key", name="uq_projects_project_key"),
        )

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        project_key: Mapped[str] = mapped_column(String(120), index=True)
        display_name: Mapped[str] = mapped_column(String(255))
        description: Mapped[str | None] = mapped_column(Text, nullable=True)
        repository_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
        default_branch: Mapped[str | None] = mapped_column(String(120), nullable=True)
        is_default: Mapped[bool] = mapped_column(Boolean, default=False)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )
        updated_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC),
            onupdate=lambda: datetime.now(UTC),
        )
        reports: Mapped[list["AnalysisReport"]] = relationship(back_populates="project")
        workspaces: Mapped[list["ProjectWorkspace"]] = relationship(
            back_populates="project",
            cascade="all, delete-orphan",
        )
        deployment_outcomes: Mapped[list["DeploymentOutcome"]] = relationship(
            back_populates="project",
            cascade="all, delete-orphan",
        )
        topology_versions: Mapped[list["TopologyVersion"]] = relationship(
            back_populates="project",
            cascade="all, delete-orphan",
        )


if "ProjectWorkspace" not in globals():

    class ProjectWorkspace(Base):
        """First-class workspace/environment scope within a project."""

        __tablename__ = "project_workspaces"
        __table_args__ = (
            UniqueConstraint(
                "project_id",
                "workspace_key",
                name="uq_project_workspaces_project_key",
            ),
        )

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="CASCADE"),
            index=True,
        )
        workspace_key: Mapped[str] = mapped_column(String(120), index=True)
        display_name: Mapped[str] = mapped_column(String(255))
        description: Mapped[str | None] = mapped_column(Text, nullable=True)
        environment: Mapped[str | None] = mapped_column(String(80), nullable=True)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )
        updated_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC),
            onupdate=lambda: datetime.now(UTC),
        )
        project: Mapped["Project"] = relationship(back_populates="workspaces")


if "AnalysisReport" not in globals():

    class AnalysisReport(Base):
        """Stored deploy analysis report for history and audit use."""

        __tablename__ = "analysis_reports"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="RESTRICT"),
            index=True,
        )
        risk_score: Mapped[int] = mapped_column(Integer)
        severity: Mapped[str] = mapped_column(String(20))
        recommendation: Mapped[str] = mapped_column(String(20))
        top_risk: Mapped[str] = mapped_column(Text)
        report_schema_version: Mapped[str] = mapped_column(String(16), default="v2")
        parse_summary: Mapped[str] = mapped_column(Text)
        narrative_opening: Mapped[str] = mapped_column(Text)
        narrative_explanation: Mapped[str] = mapped_column(Text)
        warnings_json: Mapped[str] = mapped_column(Text, default="[]")
        contributors_json: Mapped[str] = mapped_column(Text, default="[]")
        analyzed_files_json: Mapped[str] = mapped_column(Text, default="[]")
        blast_radius_json: Mapped[str] = mapped_column(Text, default="{}")
        rollback_plan_json: Mapped[str] = mapped_column(Text, default="{}")
        llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
        llm_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
        llm_local_mode: Mapped[str | None] = mapped_column(String(10), nullable=True)
        assessment_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
        narrative_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
        narrative_skills_json: Mapped[str | None] = mapped_column(Text, nullable=True)
        source_interface: Mapped[str | None] = mapped_column(String(30), nullable=True)
        trigger_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
        trigger_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
        share_password_hash: Mapped[str | None] = mapped_column(
            String(64), nullable=True
        )
        share_password_salt: Mapped[str | None] = mapped_column(
            String(32), nullable=True
        )
        share_redact_filenames: Mapped[bool] = mapped_column(Boolean, default=False)
        dashboard_display_duration_seconds: Mapped[int | None] = mapped_column(
            Integer, nullable=True
        )
        findings: Mapped[list["Finding"]] = relationship(
            back_populates="report",
            cascade="all, delete-orphan",
        )
        risk_assessment: Mapped["RiskAssessment | None"] = relationship(
            back_populates="report",
            cascade="all, delete-orphan",
            uselist=False,
        )
        context_snapshot: Mapped["ContextSnapshot | None"] = relationship(
            back_populates="report",
            cascade="all, delete-orphan",
            uselist=False,
        )
        deployment_outcomes: Mapped[list["DeploymentOutcome"]] = relationship(
            back_populates="report"
        )
        project: Mapped["Project"] = relationship(back_populates="reports")
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


if "Finding" not in globals():

    class Finding(Base):
        """Persisted reviewer-facing finding backed by one report."""

        __tablename__ = "findings"
        __table_args__ = (
            UniqueConstraint(
                "finding_id",
                "analysis_id",
                name="uq_findings_finding_id_analysis_id",
            ),
            CheckConstraint(
                "confidence >= 0.0 AND confidence <= 1.0",
                name="ck_findings_confidence_range",
            ),
        )

        finding_id: Mapped[str] = mapped_column(String(64), primary_key=True)
        analysis_id: Mapped[int] = mapped_column(
            ForeignKey("analysis_reports.id", ondelete="CASCADE"),
            index=True,
        )
        title: Mapped[str] = mapped_column(String(255))
        description: Mapped[str] = mapped_column(Text)
        severity: Mapped[str] = mapped_column(String(20))
        category: Mapped[str] = mapped_column(String(80))
        deterministic: Mapped[bool] = mapped_column(Boolean, default=True)
        confidence: Mapped[float] = mapped_column(Float, default=1.0)
        uncertainty_note: Mapped[str | None] = mapped_column(Text, nullable=True)
        evidence_refs_json: Mapped[str] = mapped_column(Text, default="[]")
        skill_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )
        report: Mapped["AnalysisReport"] = relationship(back_populates="findings")
        evidence_items: Mapped[list["EvidenceItem"]] = relationship(
            back_populates="finding",
            cascade="all, delete-orphan",
        )


if "EvidenceItem" not in globals():

    class EvidenceItem(Base):
        """Persisted evidence row attached to one finding and report."""

        __tablename__ = "evidence_items"
        __table_args__ = (
            ForeignKeyConstraint(
                ["finding_id", "analysis_id"],
                ["findings.finding_id", "findings.analysis_id"],
                ondelete="CASCADE",
                name="fk_evidence_items_finding_analysis",
            ),
            CheckConstraint(
                "confidence >= 0.0 AND confidence <= 1.0",
                name="ck_evidence_items_confidence_range",
            ),
        )

        evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
        analysis_id: Mapped[int] = mapped_column(
            ForeignKey("analysis_reports.id", ondelete="CASCADE"),
            index=True,
        )
        finding_id: Mapped[str] = mapped_column(String(64), index=True)
        source_type: Mapped[str] = mapped_column(String(20))
        source_ref: Mapped[str] = mapped_column(String(255))
        summary: Mapped[str] = mapped_column(Text)
        severity_hint: Mapped[str] = mapped_column(String(20))
        deterministic: Mapped[bool] = mapped_column(Boolean, default=True)
        confidence: Mapped[float] = mapped_column(Float, default=1.0)
        related_change_ids_json: Mapped[str] = mapped_column(Text, default="[]")
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )
        finding: Mapped["Finding"] = relationship(back_populates="evidence_items")


if "RiskAssessment" not in globals():

    class RiskAssessment(Base):
        """Persisted evidence-backed verdict for one analysis report."""

        __tablename__ = "risk_assessments"
        __table_args__ = (
            CheckConstraint("score >= 0 AND score <= 100", name="ck_score_range"),
            CheckConstraint(
                "confidence >= 0.0 AND confidence <= 1.0",
                name="ck_risk_assessments_confidence_range",
            ),
        )

        analysis_id: Mapped[int] = mapped_column(
            ForeignKey("analysis_reports.id", ondelete="CASCADE"),
            primary_key=True,
        )
        overall_severity: Mapped[str] = mapped_column(String(20))
        recommendation: Mapped[str] = mapped_column(String(20))
        score: Mapped[int] = mapped_column(Integer)
        confidence: Mapped[float] = mapped_column(Float, default=1.0)
        top_risk_contributors_json: Mapped[str] = mapped_column(Text, default="[]")
        context_completeness_json: Mapped[str] = mapped_column(Text, default="{}")
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )
        report: Mapped["AnalysisReport"] = relationship(
            back_populates="risk_assessment"
        )


if "ContextSnapshot" not in globals():

    class ContextSnapshot(Base):
        """Persisted frozen context for one analysis report."""

        __tablename__ = "context_snapshots"

        analysis_id: Mapped[int] = mapped_column(
            ForeignKey("analysis_reports.id", ondelete="CASCADE"),
            primary_key=True,
        )
        topology_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
        incident_index_version: Mapped[str | None] = mapped_column(
            String(120), nullable=True
        )
        history_window: Mapped[str | None] = mapped_column(String(60), nullable=True)
        criticality_inputs_json: Mapped[str] = mapped_column(Text, default="{}")
        owner_mapping_version: Mapped[str | None] = mapped_column(
            String(120), nullable=True
        )
        skills_active_json: Mapped[str] = mapped_column(Text, default="[]")
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )
        report: Mapped["AnalysisReport"] = relationship(
            back_populates="context_snapshot"
        )


if "TopologyVersion" not in globals():

    class TopologyVersion(Base):
        """Persisted topology snapshot scoped to one project."""

        __tablename__ = "topology_versions"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="CASCADE"),
            index=True,
        )
        source_type: Mapped[str] = mapped_column(String(30), default="manual")
        payload_json: Mapped[str] = mapped_column(Text, default="{}")
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )
        project: Mapped["Project"] = relationship(back_populates="topology_versions")


if "DeploymentOutcome" not in globals():

    class DeploymentOutcome(Base):
        """Persisted deployment outcome scoped to one project."""

        __tablename__ = "deployment_outcomes"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="CASCADE"),
            index=True,
        )
        analysis_id: Mapped[int | None] = mapped_column(
            ForeignKey("analysis_reports.id", ondelete="SET NULL"),
            nullable=True,
        )
        linked_incident_id: Mapped[int | None] = mapped_column(
            ForeignKey("incident_records.id", ondelete="SET NULL"),
            nullable=True,
        )
        environment: Mapped[str | None] = mapped_column(String(80), nullable=True)
        outcome_label: Mapped[str] = mapped_column(String(40), default="unknown")
        summary: Mapped[str | None] = mapped_column(Text, nullable=True)
        deployed_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )
        project: Mapped["Project"] = relationship(back_populates="deployment_outcomes")
        report: Mapped["AnalysisReport | None"] = relationship(
            back_populates="deployment_outcomes"
        )
        incident: Mapped["IncidentRecord | None"] = relationship(
            back_populates="deployment_outcomes"
        )


if "FeedbackEvent" not in globals():

    class FeedbackEvent(Base):
        """Persisted reviewer feedback event scoped to one project."""

        __tablename__ = "feedback_events"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="CASCADE"),
            index=True,
        )
        analysis_id: Mapped[int | None] = mapped_column(
            ForeignKey("analysis_reports.id", ondelete="SET NULL"),
            nullable=True,
        )
        finding_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
        reviewer_role: Mapped[str | None] = mapped_column(String(80), nullable=True)
        useful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
        correctness_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
        false_positive_flag: Mapped[bool] = mapped_column(Boolean, default=False)
        false_positive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
        false_negative_note: Mapped[str | None] = mapped_column(Text, nullable=True)
        outcome_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )
