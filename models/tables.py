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
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evidence.models import FINDING_EVIDENCE_CLASSIFICATION_VALUES
from models.database import Base

_FINDING_EVIDENCE_CLASSIFICATION_SQL = ", ".join(
    f"'{value}'" for value in FINDING_EVIDENCE_CLASSIFICATION_VALUES
)

if "IncidentRecord" not in globals():

    class IncidentRecord(Base):
        """Stored incident context for later similarity matching."""

        __tablename__ = "incident_records"
        __table_args__ = (
            ForeignKeyConstraint(
                ["project_id", "workspace_id"],
                ["project_workspaces.project_id", "project_workspaces.id"],
                name="fk_incident_records_project_workspace_scope",
            ),
        )

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="CASCADE"),
            index=True,
        )
        workspace_id: Mapped[int | None] = mapped_column(
            ForeignKey("project_workspaces.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        )
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
        project: Mapped["Project"] = relationship(back_populates="incident_records")
        workspace: Mapped["ProjectWorkspace | None"] = relationship(
            back_populates="incident_records",
            foreign_keys=[workspace_id],
        )


if "IncidentIngestionSource" not in globals():

    class IncidentIngestionSource(Base):
        """Durable ingestion status for one incident source in a project scope."""

        __tablename__ = "incident_ingestion_sources"
        __table_args__ = (
            UniqueConstraint(
                "project_id",
                "workspace_id",
                "source_file",
                name="uq_incident_ingestion_sources_scope_source",
            ),
            Index(
                "uq_incident_ingestion_sources_project_source",
                "project_id",
                "source_file",
                unique=True,
                sqlite_where=text("workspace_id IS NULL"),
                postgresql_where=text("workspace_id IS NULL"),
            ),
            ForeignKeyConstraint(
                ["project_id", "workspace_id"],
                ["project_workspaces.project_id", "project_workspaces.id"],
                name="fk_incident_ingestion_sources_project_workspace_scope",
            ),
            CheckConstraint(
                "status IN ('indexed', 'failed', 'removed')",
                name="ck_incident_ingestion_sources_status",
            ),
        )

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="CASCADE"),
            index=True,
        )
        workspace_id: Mapped[int | None] = mapped_column(
            ForeignKey("project_workspaces.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        )
        source_file: Mapped[str] = mapped_column(String(255))
        status: Mapped[str] = mapped_column(String(20), default="indexed")
        indexed_count: Mapped[int] = mapped_column(Integer, default=0)
        rejected_count: Mapped[int] = mapped_column(Integer, default=0)
        redaction_status: Mapped[str] = mapped_column(String(40), default="unknown")
        failure_summaries_json: Mapped[str] = mapped_column(Text, default="[]")
        index_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
        last_indexed_at: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True), nullable=True
        )
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )
        updated_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC),
            onupdate=lambda: datetime.now(UTC),
        )


if "ScannerImport" not in globals():

    class ScannerImport(Base):
        """Durable scanner import status for one project scope."""

        __tablename__ = "scanner_imports"
        __table_args__ = (
            ForeignKeyConstraint(
                ["project_id", "workspace_id"],
                ["project_workspaces.project_id", "project_workspaces.id"],
                name="fk_scanner_imports_project_workspace_scope",
            ),
            CheckConstraint(
                "status IN ('imported', 'failed')",
                name="ck_scanner_imports_status",
            ),
        )

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="CASCADE"),
            index=True,
        )
        workspace_id: Mapped[int | None] = mapped_column(
            ForeignKey("project_workspaces.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        )
        workspace_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
        source_file: Mapped[str] = mapped_column(String(255))
        format: Mapped[str] = mapped_column(String(40), default="sarif")
        tool_names_json: Mapped[str] = mapped_column(Text, default="[]")
        status: Mapped[str] = mapped_column(String(20), default="imported")
        imported_count: Mapped[int] = mapped_column(Integer, default=0)
        rejected_count: Mapped[int] = mapped_column(Integer, default=0)
        failure_summaries_json: Mapped[str] = mapped_column(Text, default="[]")
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )
        updated_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC),
            onupdate=lambda: datetime.now(UTC),
        )
        evidence: Mapped[list["ExternalScannerEvidence"]] = relationship(
            back_populates="scanner_import",
            cascade="all, delete-orphan",
        )


if "ExternalScannerEvidence" not in globals():

    class ExternalScannerEvidence(Base):
        """Scanner finding normalized as external evidence."""

        __tablename__ = "external_scanner_evidence"
        __table_args__ = (
            UniqueConstraint(
                "project_id",
                "workspace_id",
                "source_ref",
                name="uq_external_scanner_evidence_scope_source_ref",
            ),
            Index(
                "uq_external_scanner_evidence_project_source_ref",
                "project_id",
                "source_ref",
                unique=True,
                sqlite_where=text("workspace_id IS NULL AND workspace_key IS NULL"),
                postgresql_where=text("workspace_id IS NULL AND workspace_key IS NULL"),
            ),
            Index(
                "uq_external_scanner_evidence_workspace_key_source_ref",
                "project_id",
                "workspace_key",
                "source_ref",
                unique=True,
                sqlite_where=text("workspace_id IS NULL AND workspace_key IS NOT NULL"),
                postgresql_where=text(
                    "workspace_id IS NULL AND workspace_key IS NOT NULL"
                ),
            ),
            Index(
                "ix_external_scanner_evidence_project_rule",
                "project_id",
                "rule_id",
            ),
            ForeignKeyConstraint(
                ["project_id", "workspace_id"],
                ["project_workspaces.project_id", "project_workspaces.id"],
                name="fk_external_scanner_evidence_project_workspace_scope",
            ),
            CheckConstraint(
                "source_type = 'external_scanner'",
                name="ck_external_scanner_evidence_source_type",
            ),
        )

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        import_id: Mapped[int] = mapped_column(
            ForeignKey("scanner_imports.id", ondelete="CASCADE"),
            index=True,
        )
        evidence_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="CASCADE"),
            index=True,
        )
        project_key: Mapped[str] = mapped_column(String(120))
        workspace_id: Mapped[int | None] = mapped_column(
            ForeignKey("project_workspaces.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        )
        workspace_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
        source_type: Mapped[str] = mapped_column(String(30), default="external_scanner")
        source_file: Mapped[str] = mapped_column(String(255))
        source_ref: Mapped[str] = mapped_column(String(512))
        tool_name: Mapped[str] = mapped_column(String(120))
        rule_id: Mapped[str] = mapped_column(String(255))
        rule_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
        severity: Mapped[str] = mapped_column(String(20))
        level: Mapped[str | None] = mapped_column(String(40), nullable=True)
        message: Mapped[str] = mapped_column(Text)
        location: Mapped[str] = mapped_column(Text)
        artifact_uri: Mapped[str] = mapped_column(Text)
        region_json: Mapped[str] = mapped_column(Text, default="{}")
        properties_json: Mapped[str] = mapped_column(Text, default="{}")
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )
        scanner_import: Mapped["ScannerImport"] = relationship(
            back_populates="evidence"
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
        authorization_required: Mapped[bool] = mapped_column(
            Boolean, default=False, server_default=text("0")
        )
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
        incident_records: Mapped[list["IncidentRecord"]] = relationship(
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
            UniqueConstraint(
                "project_id",
                "id",
                name="uq_project_workspaces_project_id_id",
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
        reports: Mapped[list["AnalysisReport"]] = relationship(
            back_populates="workspace"
        )
        deployment_outcomes: Mapped[list["DeploymentOutcome"]] = relationship(
            back_populates="workspace",
            foreign_keys="DeploymentOutcome.workspace_id",
        )
        incident_records: Mapped[list["IncidentRecord"]] = relationship(
            back_populates="workspace",
            foreign_keys="IncidentRecord.workspace_id",
        )
        topology_versions: Mapped[list["TopologyVersion"]] = relationship(
            back_populates="workspace",
            foreign_keys="TopologyVersion.workspace_id",
        )
        feedback_events: Mapped[list["FeedbackEvent"]] = relationship(
            back_populates="workspace",
            foreign_keys="FeedbackEvent.workspace_id",
        )


if "AnalysisReport" not in globals():

    class AnalysisReport(Base):
        """Stored deploy analysis report for history and audit use."""

        __tablename__ = "analysis_reports"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="RESTRICT"),
            index=True,
        )
        workspace_id: Mapped[int | None] = mapped_column(
            ForeignKey("project_workspaces.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        )
        authorization_required: Mapped[bool] = mapped_column(
            Boolean, default=False, server_default=text("0")
        )
        risk_score: Mapped[int] = mapped_column(Integer)
        severity: Mapped[str] = mapped_column(String(20))
        recommendation: Mapped[str] = mapped_column(String(20))
        top_risk: Mapped[str] = mapped_column(Text)
        report_schema_version: Mapped[str] = mapped_column(String(16), default="v2")
        parse_summary: Mapped[str] = mapped_column(Text)
        narrative_opening: Mapped[str] = mapped_column(Text)
        narrative_explanation: Mapped[str] = mapped_column(Text)
        narrative_degraded: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
        narrative_failure_notice: Mapped[str | None] = mapped_column(
            Text, nullable=True
        )
        narrative_guidance_json: Mapped[str] = mapped_column(Text, default="[]")
        warnings_json: Mapped[str] = mapped_column(Text, default="[]")
        contributors_json: Mapped[str] = mapped_column(Text, default="[]")
        analyzed_files_json: Mapped[str] = mapped_column(Text, default="[]")
        submission_manifest_json: Mapped[str] = mapped_column(Text, default="{}")
        submission_manifest_fallback_json: Mapped[str] = mapped_column(
            Text, default="[]"
        )
        blast_radius_json: Mapped[str] = mapped_column(Text, default="{}")
        rollback_plan_json: Mapped[str] = mapped_column(Text, default="{}")
        incident_matches_json: Mapped[str] = mapped_column(Text, default="[]")
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
        analysis_duration_seconds: Mapped[int | None] = mapped_column(
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
        workspace: Mapped["ProjectWorkspace | None"] = relationship(
            back_populates="reports"
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
            CheckConstraint(
                f"evidence_classification IN ({_FINDING_EVIDENCE_CLASSIFICATION_SQL})",
                name="ck_findings_evidence_classification",
            ),
        )

        finding_id: Mapped[str] = mapped_column(String(64), primary_key=True)
        analysis_id: Mapped[int] = mapped_column(
            ForeignKey("analysis_reports.id", ondelete="CASCADE"),
            index=True,
        )
        title: Mapped[str] = mapped_column(String(255))
        description: Mapped[str] = mapped_column(Text)
        explanation: Mapped[str] = mapped_column(Text, default="")
        guidance_json: Mapped[str] = mapped_column(Text, default="[]")
        severity: Mapped[str] = mapped_column(String(20))
        category: Mapped[str] = mapped_column(String(80))
        deterministic: Mapped[bool] = mapped_column(Boolean, default=True)
        confidence: Mapped[float] = mapped_column(Float, default=1.0)
        uncertainty_note: Mapped[str | None] = mapped_column(Text, nullable=True)
        evidence_classification: Mapped[str] = mapped_column(
            String(30), default="deterministic"
        )
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
        artifact: Mapped[str] = mapped_column(String(255), default="")
        location: Mapped[str] = mapped_column(Text, default="")
        resource: Mapped[str] = mapped_column(Text, default="")
        operation: Mapped[str] = mapped_column(String(40), default="")
        project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
        project_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
        workspace_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
        workspace_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
        source_kind: Mapped[str] = mapped_column(String(30), default="artifact")
        determinism_level: Mapped[str] = mapped_column(
            String(30), default="deterministic"
        )
        redaction_status: Mapped[str] = mapped_column(String(30), default="none")
        summary: Mapped[str] = mapped_column(Text)
        severity_hint: Mapped[str] = mapped_column(String(20))
        deterministic: Mapped[bool] = mapped_column(Boolean, default=True)
        confidence: Mapped[float] = mapped_column(Float, default=1.0)
        related_change_ids_json: Mapped[str] = mapped_column(Text, default="[]")
        context_source_json: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        __table_args__ = (
            ForeignKeyConstraint(
                ["project_id", "workspace_id"],
                ["project_workspaces.project_id", "project_workspaces.id"],
                name="fk_topology_versions_project_workspace_scope",
            ),
        )

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="CASCADE"),
            index=True,
        )
        workspace_id: Mapped[int | None] = mapped_column(
            ForeignKey("project_workspaces.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        )
        source_type: Mapped[str] = mapped_column(String(30), default="manual")
        payload_json: Mapped[str] = mapped_column(Text, default="{}")
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )
        project: Mapped["Project"] = relationship(back_populates="topology_versions")
        workspace: Mapped["ProjectWorkspace | None"] = relationship(
            back_populates="topology_versions",
            foreign_keys=[workspace_id],
        )


if "DeploymentOutcome" not in globals():

    class DeploymentOutcome(Base):
        """Persisted deployment outcome scoped to one project."""

        __tablename__ = "deployment_outcomes"
        __table_args__ = (
            Index(
                "ix_deployment_outcomes_analysis_deployed_outcome",
                "analysis_id",
                "deployed_at",
                "outcome_label",
            ),
            ForeignKeyConstraint(
                ["project_id", "workspace_id"],
                ["project_workspaces.project_id", "project_workspaces.id"],
                name="fk_deployment_outcomes_project_workspace_scope",
            ),
        )

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="CASCADE"),
            index=True,
        )
        workspace_id: Mapped[int | None] = mapped_column(
            ForeignKey("project_workspaces.id", ondelete="SET NULL"),
            nullable=True,
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
        notes: Mapped[str | None] = mapped_column(Text, nullable=True)
        deployed_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), default=lambda: datetime.now(UTC)
        )
        project: Mapped["Project"] = relationship(back_populates="deployment_outcomes")
        workspace: Mapped["ProjectWorkspace | None"] = relationship(
            back_populates="deployment_outcomes",
            foreign_keys=[workspace_id],
        )
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
        __table_args__ = (
            Index(
                "ix_feedback_events_analysis_created",
                "analysis_id",
                "created_at",
            ),
            ForeignKeyConstraint(
                ["project_id", "workspace_id"],
                ["project_workspaces.project_id", "project_workspaces.id"],
                name="fk_feedback_events_project_workspace_scope",
            ),
        )

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="CASCADE"),
            index=True,
        )
        workspace_id: Mapped[int | None] = mapped_column(
            ForeignKey("project_workspaces.id", ondelete="SET NULL"),
            nullable=True,
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
        workspace: Mapped["ProjectWorkspace | None"] = relationship(
            back_populates="feedback_events",
            foreign_keys=[workspace_id],
        )


if "IdentityAccount" not in globals():

    class IdentityAccount(Base):
        """Named local principals; credentials never grant project membership."""

        __tablename__ = "identity_accounts"
        id: Mapped[str] = mapped_column(String(64), primary_key=True)
        username: Mapped[str] = mapped_column(String(128), unique=True)
        principal_type: Mapped[str] = mapped_column(String(20), default="human")
        password_verifier: Mapped[str] = mapped_column(String(160))
        is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
        enabled: Mapped[bool] = mapped_column(Boolean, default=True)
        authentication_version: Mapped[int] = mapped_column(Integer, default=1)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
        revoked_at: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True), nullable=True
        )


if "IdentitySession" not in globals():

    class IdentitySession(Base):
        """Hashed, audience- and deployment-bound browser sessions."""

        __tablename__ = "identity_sessions"
        id: Mapped[str] = mapped_column(String(64), primary_key=True)
        principal_id: Mapped[str] = mapped_column(
            ForeignKey("identity_accounts.id", ondelete="CASCADE"), index=True
        )
        token_hash: Mapped[str] = mapped_column(String(64), unique=True)
        csrf_hash: Mapped[str] = mapped_column(String(64))
        audience: Mapped[str] = mapped_column(String(20))
        security_profile: Mapped[str] = mapped_column(String(30))
        trusted_origin: Mapped[str] = mapped_column(String(512))
        authentication_version: Mapped[int] = mapped_column(Integer)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
        last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
        expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
        revoked_at: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True), nullable=True
        )


if "IdentityCredential" not in globals():

    class IdentityCredential(Base):
        """One-use local bootstrap/recovery possession evidence."""

        __tablename__ = "identity_credentials"
        id: Mapped[str] = mapped_column(String(64), primary_key=True)
        token_hash: Mapped[str] = mapped_column(String(64), unique=True)
        purpose: Mapped[str] = mapped_column(String(20))
        principal_id: Mapped[str | None] = mapped_column(
            ForeignKey("identity_accounts.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        )
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
        expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
        consumed_at: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True), nullable=True
        )


if "ProjectMembership" not in globals():

    class ProjectMembership(Base):
        """Server-owned role, optionally restricted to one existing workspace."""

        __tablename__ = "project_memberships"
        __table_args__ = (
            UniqueConstraint(
                "principal_id",
                "project_id",
                name="uq_project_membership_principal_project",
            ),
            ForeignKeyConstraint(
                ["project_id", "workspace_id"],
                ["project_workspaces.project_id", "project_workspaces.id"],
                name="fk_project_memberships_project_workspace_scope",
                ondelete="RESTRICT",
            ),
            CheckConstraint(
                "role IN ('admin', 'maintainer', 'reviewer', 'contributor', 'read-only')",
                name="ck_project_memberships_role",
            ),
            CheckConstraint(
                "authorization_version > 0",
                name="ck_project_memberships_authorization_version",
            ),
        )
        id: Mapped[str] = mapped_column(String(64), primary_key=True)
        principal_id: Mapped[str] = mapped_column(
            ForeignKey("identity_accounts.id", ondelete="RESTRICT"), index=True
        )
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="RESTRICT"), index=True
        )
        workspace_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
        role: Mapped[str] = mapped_column(String(20))
        enabled: Mapped[bool] = mapped_column(Boolean, default=True)
        authorization_version: Mapped[int] = mapped_column(Integer, default=1)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
        updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


if "ProjectAuthorizationAudit" not in globals():

    class ProjectAuthorizationAudit(Base):
        """Append-only repository record of membership and decision authority changes."""

        __tablename__ = "project_authorization_audit"
        __table_args__ = (
            ForeignKeyConstraint(
                ["project_id", "workspace_id"],
                ["project_workspaces.project_id", "project_workspaces.id"],
                name="fk_project_authorization_audit_project_workspace_scope",
                ondelete="RESTRICT",
            ),
        )
        id: Mapped[str] = mapped_column(String(64), primary_key=True)
        actor_principal_id: Mapped[str] = mapped_column(
            ForeignKey("identity_accounts.id", ondelete="RESTRICT")
        )
        target_principal_id: Mapped[str | None] = mapped_column(
            ForeignKey("identity_accounts.id", ondelete="RESTRICT"), nullable=True
        )
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="RESTRICT"), index=True
        )
        workspace_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
        action: Mapped[str] = mapped_column(String(80))
        object_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
        before_json: Mapped[str] = mapped_column(Text, default="{}")
        after_json: Mapped[str] = mapped_column(Text, default="{}")
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


if "InfraWorkflow" not in globals():

    class InfraWorkflow(Base):
        """Scoped automation persistence owned by caller transactions."""

        __tablename__ = "infra_workflows"
        __table_args__ = (
            UniqueConstraint("id", "project_id", name="uq_infra_workflows_id_project"),
            CheckConstraint("draft_version > 0", name="ck_infra_workflow_version"),
            CheckConstraint(
                "length(draft_definition) BETWEEN 1 AND 131072",
                name="ck_infra_workflow_bytes",
            ),
            CheckConstraint(
                "length(name) BETWEEN 1 AND 120", name="ck_infra_workflow_name"
            ),
            ForeignKeyConstraint(
                ["project_id", "workspace_id"],
                ["project_workspaces.project_id", "project_workspaces.id"],
                ondelete="RESTRICT",
                name="fk_infra_workflows_workspace",
            ),
            {"sqlite_autoincrement": True},
        )
        sequence: Mapped[int] = mapped_column(
            Integer, primary_key=True, autoincrement=True
        )
        id: Mapped[str] = mapped_column(String(64), unique=True)
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="RESTRICT"), index=True
        )
        workspace_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
        name: Mapped[str] = mapped_column(String(120))
        draft_definition: Mapped[bytes] = mapped_column(LargeBinary)
        draft_digest: Mapped[str] = mapped_column(String(71))
        draft_version: Mapped[int] = mapped_column(Integer, default=1)
        archived: Mapped[bool] = mapped_column(Boolean, default=False)
        created_by: Mapped[str] = mapped_column(
            ForeignKey("identity_accounts.id", ondelete="RESTRICT")
        )
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
        updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


if "InfraWorkflowRevision" not in globals():

    class InfraWorkflowRevision(Base):
        """Scoped automation persistence owned by caller transactions."""

        __tablename__ = "infra_workflow_revisions"
        __table_args__ = (
            UniqueConstraint(
                "workflow_id",
                "revision_number",
                name="uq_infra_workflow_revision_number",
            ),
            UniqueConstraint(
                "published_by",
                "idempotency_key_digest",
                name="uq_infra_workflow_publication_key",
            ),
            ForeignKeyConstraint(
                ["workflow_id", "project_id"],
                ["infra_workflows.id", "infra_workflows.project_id"],
                ondelete="RESTRICT",
                name="fk_infra_revision_workflow_project",
            ),
            CheckConstraint("revision_number > 0", name="ck_infra_revision_number"),
            CheckConstraint(
                "length(canonical_definition) BETWEEN 1 AND 131072",
                name="ck_infra_revision_bytes",
            ),
            ForeignKeyConstraint(
                ["project_id", "workspace_id"],
                ["project_workspaces.project_id", "project_workspaces.id"],
                ondelete="RESTRICT",
                name="fk_infra_workflow_revisions_workspace",
            ),
            {"sqlite_autoincrement": True},
        )
        sequence: Mapped[int] = mapped_column(
            Integer, primary_key=True, autoincrement=True
        )
        id: Mapped[str] = mapped_column(String(64), unique=True)
        workflow_id: Mapped[str] = mapped_column(
            ForeignKey("infra_workflows.id", ondelete="RESTRICT"), index=True
        )
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="RESTRICT"), index=True
        )
        workspace_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
        revision_number: Mapped[int] = mapped_column(Integer)
        canonical_definition: Mapped[bytes] = mapped_column(LargeBinary)
        digest: Mapped[str] = mapped_column(String(71))
        published_by: Mapped[str] = mapped_column(
            ForeignKey("identity_accounts.id", ondelete="RESTRICT")
        )
        idempotency_key_digest: Mapped[str] = mapped_column(String(71))
        request_digest: Mapped[str] = mapped_column(String(71))
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


if "InfraAutomationPolicy" not in globals():

    class InfraAutomationPolicy(Base):
        """Scoped automation persistence owned by caller transactions."""

        __tablename__ = "infra_automation_policies"
        __table_args__ = (
            CheckConstraint(
                "version > 0 AND authorization_epoch > 0 AND restore_epoch > 0",
                name="ck_infra_policy_versions",
            ),
        )
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="RESTRICT"), primary_key=True
        )
        settings_json: Mapped[str] = mapped_column(Text)
        version: Mapped[int] = mapped_column(Integer)
        authorization_epoch: Mapped[int] = mapped_column(Integer)
        restore_epoch: Mapped[int] = mapped_column(Integer)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
        updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


if "InfraAutomationAudit" not in globals():

    class InfraAutomationAudit(Base):
        """Scoped automation persistence owned by caller transactions."""

        __tablename__ = "infra_automation_audit"
        __table_args__ = (
            CheckConstraint(
                "length(reason) BETWEEN 1 AND 256", name="ck_infra_audit_reason"
            ),
            ForeignKeyConstraint(
                ["project_id", "workspace_id"],
                ["project_workspaces.project_id", "project_workspaces.id"],
                ondelete="RESTRICT",
                name="fk_infra_automation_audit_workspace",
            ),
            {"sqlite_autoincrement": True},
        )
        sequence: Mapped[int] = mapped_column(
            Integer, primary_key=True, autoincrement=True
        )
        id: Mapped[str] = mapped_column(String(64), unique=True)
        project_id: Mapped[int] = mapped_column(
            ForeignKey("projects.id", ondelete="RESTRICT"), index=True
        )
        workspace_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
        actor_principal_id: Mapped[str] = mapped_column(
            ForeignKey("identity_accounts.id", ondelete="RESTRICT")
        )
        actor_type: Mapped[str] = mapped_column(String(20))
        actor_role: Mapped[str] = mapped_column(String(20))
        event_type: Mapped[str] = mapped_column(String(80))
        target_id: Mapped[str] = mapped_column(String(128))
        reason: Mapped[str] = mapped_column(String(256))
        before_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
        after_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


if "InfraAutomationRun" not in globals():

    class InfraAutomationRun(Base):
        __tablename__ = "infra_automation_runs"
        __table_args__ = (
            ForeignKeyConstraint(
                ["project_id", "workspace_id"],
                ["project_workspaces.project_id", "project_workspaces.id"],
                ondelete="RESTRICT",
            ),
            ForeignKeyConstraint(
                ["requested_by"], ["identity_accounts.id"], ondelete="RESTRICT"
            ),
            UniqueConstraint("id"),
            UniqueConstraint("id", "project_id", "workspace_id", "requested_by"),
            ForeignKeyConstraint(
                ["workflow_id", "project_id"],
                ["infra_workflows.id", "infra_workflows.project_id"],
                ondelete="RESTRICT",
            ),
            ForeignKeyConstraint(
                ["revision_id"], ["infra_workflow_revisions.id"], ondelete="RESTRICT"
            ),
            CheckConstraint(
                "state IN ('queued','running','waiting_approval','ready_handoff','handing_off','external_running','succeeded','failed','stopped_by_gate','rejected','expired','timed_out','cancelled','delivery_unknown')",
                name="ck_engine_run_state",
            ),
            CheckConstraint(
                "version BETWEEN 1 AND 9007199254740991 AND retained_bytes >= length(snapshot_bytes) AND length(snapshot_bytes) BETWEEN 1 AND 524288",
                name="ck_engine_run_bounds",
            ),
            {"sqlite_autoincrement": True},
        )
        sequence: Mapped[int] = mapped_column(
            Integer, nullable=False, primary_key=True, autoincrement=True
        )
        id: Mapped[str] = mapped_column(String(64), nullable=False)
        project_id: Mapped[int] = mapped_column(Integer, nullable=False)
        workspace_id: Mapped[int] = mapped_column(Integer, nullable=False)
        requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
        workflow_id: Mapped[str] = mapped_column(String(64), nullable=False)
        revision_id: Mapped[str] = mapped_column(String(64), nullable=False)
        snapshot_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
        snapshot_digest: Mapped[str] = mapped_column(String(71), nullable=False)
        definition_digest: Mapped[str] = mapped_column(String(71), nullable=False)
        input_digest: Mapped[str] = mapped_column(String(71), nullable=False)
        request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), nullable=False
        )
        deadline_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), nullable=False
        )
        state: Mapped[str] = mapped_column(String(24), nullable=False)
        version: Mapped[int] = mapped_column(Integer, nullable=False)
        updated_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), nullable=False
        )
        last_observed_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), nullable=False
        )
        cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False)
        cancellation_requested_at: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True), nullable=True
        )
        retained_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
        external_possible: Mapped[bool] = mapped_column(Boolean, nullable=False)


if "InfraAutomationAttempt" not in globals():

    class InfraAutomationAttempt(Base):
        __tablename__ = "infra_automation_attempts"
        __table_args__ = (
            ForeignKeyConstraint(
                ["project_id", "workspace_id"],
                ["project_workspaces.project_id", "project_workspaces.id"],
                ondelete="RESTRICT",
            ),
            ForeignKeyConstraint(
                ["requested_by"], ["identity_accounts.id"], ondelete="RESTRICT"
            ),
            UniqueConstraint("id"),
            UniqueConstraint("run_id", "step_id", "attempt_number"),
            UniqueConstraint("run_id", "step_id", "fence"),
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
            CheckConstraint(
                "state IN ('pending','claimed','running','succeeded','failed','timed_out','cancelled')",
                name="ck_engine_attempt_state",
            ),
            CheckConstraint(
                "version BETWEEN 1 AND 9007199254740991 AND attempt_number BETWEEN 1 AND 3 AND fence BETWEEN 1 AND 9007199254740991 AND coordinator_generation BETWEEN 0 AND 9007199254740991 AND log_bytes BETWEEN 0 AND 1048576 AND last_log_sequence >= 0",
                name="ck_engine_attempt_bounds",
            ),
            CheckConstraint(
                "(output_json IS NULL) = (output_digest IS NULL)",
                name="ck_engine_attempt_output",
            ),
            {"sqlite_autoincrement": True},
        )
        sequence: Mapped[int] = mapped_column(
            Integer, nullable=False, primary_key=True, autoincrement=True
        )
        id: Mapped[str] = mapped_column(String(64), nullable=False)
        project_id: Mapped[int] = mapped_column(Integer, nullable=False)
        workspace_id: Mapped[int] = mapped_column(Integer, nullable=False)
        requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
        run_id: Mapped[str] = mapped_column(String(64), nullable=False)
        step_id: Mapped[str] = mapped_column(String(128), nullable=False)
        step_kind: Mapped[str] = mapped_column(String(40), nullable=False)
        attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
        fence: Mapped[int] = mapped_column(Integer, nullable=False)
        handler_id: Mapped[str] = mapped_column(String(128), nullable=False)
        handler_version: Mapped[str] = mapped_column(String(128), nullable=False)
        retry_safe: Mapped[bool] = mapped_column(Boolean, nullable=False)
        input_digest: Mapped[str] = mapped_column(String(71), nullable=False)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), nullable=False
        )
        deadline_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), nullable=False
        )
        state: Mapped[str] = mapped_column(String(24), nullable=False)
        version: Mapped[int] = mapped_column(Integer, nullable=False)
        owner_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
        owner_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
        coordinator_generation: Mapped[int] = mapped_column(Integer, nullable=False)
        lease_until: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True), nullable=True
        )
        last_observed_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), nullable=False
        )
        logs_json: Mapped[str] = mapped_column(Text, nullable=False)
        uploads_json: Mapped[str] = mapped_column(Text, nullable=False)
        output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
        output_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
        log_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
        last_log_sequence: Mapped[int] = mapped_column(Integer, nullable=False)


if "InfraAutomationCoordinatorLease" not in globals():

    class InfraAutomationCoordinatorLease(Base):
        __tablename__ = "infra_automation_coordinator_lease"
        __table_args__ = (
            CheckConstraint(
                "id = 1 AND generation BETWEEN 1 AND 9007199254740991 AND version BETWEEN 1 AND 9007199254740991",
                name="ck_engine_lease_bounds",
            ),
        )
        id: Mapped[int] = mapped_column(
            Integer, nullable=False, primary_key=True, autoincrement=True
        )
        generation: Mapped[int] = mapped_column(Integer, nullable=False)
        version: Mapped[int] = mapped_column(Integer, nullable=False)
        owner_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
        owner_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
        lease_until: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True), nullable=True
        )
        last_observed_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), nullable=False
        )


if "InfraAutomationRunRequest" not in globals():

    class InfraAutomationRunRequest(Base):
        __tablename__ = "infra_automation_run_requests"
        __table_args__ = (
            ForeignKeyConstraint(
                ["project_id", "workspace_id"],
                ["project_workspaces.project_id", "project_workspaces.id"],
                ondelete="RESTRICT",
            ),
            ForeignKeyConstraint(
                ["requested_by"], ["identity_accounts.id"], ondelete="RESTRICT"
            ),
            UniqueConstraint("id"),
            UniqueConstraint(
                "project_id", "workspace_id", "requested_by", "operation", "key_digest"
            ),
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
            {"sqlite_autoincrement": True},
        )
        sequence: Mapped[int] = mapped_column(
            Integer, nullable=False, primary_key=True, autoincrement=True
        )
        id: Mapped[str] = mapped_column(String(64), nullable=False)
        project_id: Mapped[int] = mapped_column(Integer, nullable=False)
        workspace_id: Mapped[int] = mapped_column(Integer, nullable=False)
        requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
        operation: Mapped[str] = mapped_column(String(32), nullable=False)
        key_digest: Mapped[str] = mapped_column(String(71), nullable=False)
        request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
        run_id: Mapped[str] = mapped_column(String(64), nullable=False)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), nullable=False
        )


if "InfraAutomationArtifactManifest" not in globals():

    class InfraAutomationArtifactManifest(Base):
        """Immutable screened payload bound to one run intake step."""

        __tablename__ = "infra_automation_artifact_manifests"
        __table_args__ = (
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
            CheckConstraint(
                "(collection_bytes IS NULL) = (collection_digest IS NULL) AND (collection_bytes IS NULL OR length(collection_bytes) BETWEEN 1 AND 16384)",
                name="ck_preflight_collection_bounds",
            ),
            UniqueConstraint(
                "id", "run_id", "project_id", "workspace_id", "requested_by"
            ),
            CheckConstraint(
                "length(artifacts_bytes) BETWEEN 1 AND 50331648 AND length(digest) = 71",
                name="ck_preflight_manifest_bounds",
            ),
        )
        id: Mapped[str] = mapped_column(String(64), primary_key=True)
        run_id: Mapped[str] = mapped_column(String(64), nullable=False)
        step_id: Mapped[str] = mapped_column(String(128), nullable=False)
        project_id: Mapped[int] = mapped_column(Integer, nullable=False)
        workspace_id: Mapped[int] = mapped_column(Integer, nullable=False)
        requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
        collection_bytes: Mapped[bytes | None] = mapped_column(
            LargeBinary, nullable=True
        )
        collection_digest: Mapped[str | None] = mapped_column(String(71), nullable=True)
        artifacts_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
        digest: Mapped[str] = mapped_column(String(71), nullable=False)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), nullable=False
        )


if "InfraAutomationReportLink" not in globals():

    class InfraAutomationReportLink(Base):
        """Immutable relational provenance; no report schema/hash mutation."""

        __tablename__ = "infra_automation_report_links"
        __table_args__ = (
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
        id: Mapped[str] = mapped_column(String(64), primary_key=True)
        run_id: Mapped[str] = mapped_column(String(64), nullable=False)
        attempt_id: Mapped[str] = mapped_column(String(64), nullable=False)
        manifest_id: Mapped[str] = mapped_column(String(64), nullable=False)
        report_id: Mapped[int] = mapped_column(Integer, nullable=False)
        project_id: Mapped[int] = mapped_column(Integer, nullable=False)
        workspace_id: Mapped[int] = mapped_column(Integer, nullable=False)
        requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
        provenance_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
        digest: Mapped[str] = mapped_column(String(71), nullable=False)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), nullable=False
        )


if "InfraAutomationDecision" not in globals():

    class InfraAutomationDecision(Base):
        """Durable decision generation with immutable evidence and exact report bytes."""

        __tablename__ = "infra_automation_decisions"
        __table_args__ = (
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
            ForeignKeyConstraint(
                ["report_id"], ["analysis_reports.id"], ondelete="RESTRICT"
            ),
            UniqueConstraint("run_id", "step_id", "generation"),
            CheckConstraint(
                "generation > 0 AND version > 0", name="ck_infra_decision_versions"
            ),
            CheckConstraint(
                "status IN ('pending','approved','rejected','expired','invalidated','superseded')",
                name="ck_infra_decision_status",
            ),
            CheckConstraint(
                "length(binding_bytes) BETWEEN 1 AND 131072 AND length(report_bytes) BETWEEN 1 AND 8388608 AND length(binding_digest)=71 AND length(report_digest)=71",
                name="ck_infra_decision_bounds",
            ),
            CheckConstraint(
                "(status='pending' AND reviewer_id IS NULL AND reason IS NULL AND decided_at IS NULL) OR (status IN ('approved','rejected') AND reviewer_id IS NOT NULL AND length(reviewer_id)>0 AND reason IS NOT NULL AND length(reason) BETWEEN 1 AND 2048 AND decided_at IS NOT NULL) OR (status IN ('expired','invalidated','superseded') AND reviewer_id IS NULL AND reason IS NOT NULL AND length(reason) BETWEEN 1 AND 2048 AND decided_at IS NOT NULL)",
                name="ck_infra_decision_terminal",
            ),
            CheckConstraint(
                "(status IN ('approved','rejected') AND reviewer_authentication_version > 0 AND reviewer_authorization_version > 0 AND reviewer_authentication_version IS NOT NULL AND reviewer_authorization_version IS NOT NULL) OR (status NOT IN ('approved','rejected') AND reviewer_authentication_version IS NULL AND reviewer_authorization_version IS NULL)",
                name="ck_infra_decision_reviewer_versions",
            ),
            CheckConstraint(
                "(status IN ('approved','rejected') AND decision_kind IS NOT NULL AND decision_kind IN ('independent-approval','acknowledgement')) OR (status NOT IN ('approved','rejected') AND decision_kind IS NULL)",
                name="ck_infra_decision_kind",
            ),
            {"sqlite_autoincrement": True},
        )
        sequence: Mapped[int] = mapped_column(
            Integer, primary_key=True, autoincrement=True
        )
        id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
        run_id: Mapped[str] = mapped_column(String(64), nullable=False)
        step_id: Mapped[str] = mapped_column(String(128), nullable=False)
        project_id: Mapped[int] = mapped_column(Integer, nullable=False)
        workspace_id: Mapped[int] = mapped_column(Integer, nullable=False)
        requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
        report_id: Mapped[int] = mapped_column(Integer, nullable=False)
        generation: Mapped[int] = mapped_column(Integer, nullable=False)
        version: Mapped[int] = mapped_column(Integer, nullable=False)
        status: Mapped[str] = mapped_column(String(32), nullable=False)
        binding_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
        binding_digest: Mapped[str] = mapped_column(String(71), nullable=False)
        report_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
        report_digest: Mapped[str] = mapped_column(String(71), nullable=False)
        decision_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
        reviewer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
        reviewer_authentication_version: Mapped[int | None] = mapped_column(
            Integer, nullable=True
        )
        reviewer_authorization_version: Mapped[int | None] = mapped_column(
            Integer, nullable=True
        )
        reason: Mapped[str | None] = mapped_column(String(2048), nullable=True)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), nullable=False
        )
        deadline_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), nullable=False
        )
        decided_at: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True), nullable=True
        )
