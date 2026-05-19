"""Seeded NiceGUI server for browser accessibility tests."""

from __future__ import annotations

import os
import sys
import tempfile
import json
from importlib import import_module, reload
from pathlib import Path

import nicegui.run as nicegui_run

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_TEMP_ROOT = Path(tempfile.mkdtemp(prefix="dw-e2e-"))
os.environ.setdefault("APP_HOST", "127.0.0.1")
os.environ.setdefault("APP_PORT", "8080")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEMP_ROOT / 'accessibility.db'}")
os.environ.setdefault("ARTIFACT_SNAPSHOT_DIR", str(_TEMP_ROOT / "report-artifacts"))


def _safe_nicegui_setup() -> None:
    try:
        nicegui_run.process_pool = None
    except Exception:
        pass


nicegui_run.setup = _safe_nicegui_setup


def _load_runtime_modules() -> tuple[object, object, object, object, object]:
    config_module = import_module("config")
    database_module = import_module("models.database")
    analysis_reports_repository_module = import_module(
        "models.repositories.analysis_reports"
    )
    tables_module = import_module("models.tables")
    report_service_module = import_module("services.report_service")
    return (
        config_module,
        database_module,
        analysis_reports_repository_module,
        tables_module,
        report_service_module,
    )


def _reload_runtime() -> tuple[object, object]:
    (
        config_module,
        database_module,
        analysis_reports_repository_module,
        tables_module,
        report_service_module,
    ) = _load_runtime_modules()
    reload(config_module)
    reload(tables_module)
    reload(database_module)
    reload(analysis_reports_repository_module)
    reload(report_service_module)
    return database_module, report_service_module


def _seed_review_report(report_service_module) -> None:
    from analysis.blast_radius import BlastRadiusResult, ImpactNode
    from analysis.risk_scorer import RiskAssessment, RiskContributor
    from analysis.rollback_planner import RollbackPlan, RollbackStep
    from evidence.models import ContextCompleteness, EvidenceItem, Finding
    from llm.narrator import NarrativeResult
    from parsers.base import ParseBatchResult, ParsedFileResult, UnifiedChange

    parse_batch = ParseBatchResult(
        files=[
            ParsedFileResult(
                file_name="plan.json",
                tool="terraform",
                status="parsed",
                changes=[
                    UnifiedChange(
                        source_file="plan.json",
                        tool="terraform",
                        resource_id="aws_security_group.main",
                        action="modify",
                        summary="Security group exposure risk",
                        metadata={
                            "module_address": "module.network",
                            "provider_name": "registry.terraform.io/hashicorp/aws",
                            "redacted_fields": ["ingress.0.description"],
                            "unsupported_fields": ["change.importing"],
                            "plan_unsupported_fields": ["plan.planned_values"],
                        },
                    ),
                    UnifiedChange(
                        source_file="plan.json",
                        tool="terraform",
                        resource_id="aws_db_instance.primary",
                        action="modify",
                        summary="Database maintenance window changed",
                    ),
                ],
            )
        ]
    )
    previous_assessment = RiskAssessment(
        score=42,
        severity="medium",
        recommendation="caution",
        top_risk="Initial security group review",
        top_risk_contributors=["ev-prev"],
        contributors=[
            RiskContributor(
                evidence_id="ev-prev",
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                contribution=20,
                summary="Initial security group review.",
                severity="medium",
            )
        ],
        interaction_risks=[],
        context_completeness=ContextCompleteness(
            topology_freshness_days=12,
            topology_last_imported_at="2026-04-18T11:22:33+00:00",
            incident_index_size=4,
            parser_success_rate=1.0,
            parser_success_by_tool={"terraform": 1.0},
            context_score=0.92,
        ),
        partial_context=False,
        warnings=[],
        source="heuristic+llm",
    )
    previous_narrative = NarrativeResult(
        opening_sentence="CAUTION: review the security group change.",
        explanation="Initial review of the security group change.",
        guidance=["Inspect the evidence backing the finding."],
        degraded=False,
        warnings=[],
        source="llm",
        provider="ollama",
        model="ollama/llama3",
        local_mode=True,
        skills_applied=["git", "terraform"],
    )
    report_service_module.persist_analysis_report(
        parse_batch,
        previous_assessment,
        previous_narrative,
        findings=[
            Finding(
                finding_id="finding-prev",
                analysis_id=0,
                title="MEDIUM: aws_security_group.main",
                description="Initial security group review",
                severity="medium",
                category="networking/ingress",
                deterministic=True,
                confidence=1.0,
                uncertainty_note=None,
                evidence_refs=["ev-prev"],
                skill_id=None,
            )
        ],
        evidence_items=[
            EvidenceItem(
                evidence_id="ev-prev",
                analysis_id=0,
                finding_id="finding-prev",
                source_type="artifact",
                source_ref="artifact://plan.json#line=10",
                summary="Security group ingress remains under review.",
                severity_hint="medium",
                deterministic=True,
                confidence=1.0,
                related_change_ids=["aws_security_group.main"],
            )
        ],
        artifact_snapshots={
            "plan.json": b'{"resource":"aws_security_group.main","cidr_blocks":["10.0.0.0/8"]}\n'
        },
        audit_context={
            "source_interface": "ui",
            "trigger_type": "dashboard_upload",
        },
        project_key="payments",
    )
    assessment = RiskAssessment(
        score=88,
        severity="critical",
        recommendation="no-go",
        top_risk="Security group exposure risk",
        top_risk_contributors=["ev-001", "ev-002"],
        contributors=[
            RiskContributor(
                evidence_id="ev-001",
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                contribution=20,
                summary="Ingress widens production access.",
                severity="critical",
                metadata={
                    "module_address": "module.network",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "redacted_fields": ["ingress.0.description"],
                    "unsupported_fields": ["change.importing"],
                    "plan_unsupported_fields": ["plan.planned_values"],
                },
            ),
            RiskContributor(
                evidence_id="ev-002",
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_db_instance.primary",
                action="modify",
                contribution=12,
                summary="Database maintenance window changed during peak hours.",
                severity="high",
            ),
        ],
        interaction_risks=[],
        context_completeness=ContextCompleteness(
            topology_freshness_days=1,
            topology_last_imported_at="2026-04-20T11:05:00+00:00",
            incident_index_size=4,
            parser_success_rate=1.0,
            parser_success_by_tool={"terraform": 1.0},
            context_score=0.92,
        ),
        partial_context=False,
        warnings=[],
        source="heuristic+llm",
    )
    narrative = NarrativeResult(
        opening_sentence="NO-GO: review the security group update.",
        explanation="The deployment widens database access and should be reviewed.",
        guidance=["Inspect the evidence backing each finding."],
        degraded=False,
        warnings=[],
        source="llm",
        provider="ollama",
        model="ollama/llama3",
        local_mode=True,
        skills_applied=["git", "terraform"],
    )
    current_report = report_service_module.persist_analysis_report(
        parse_batch,
        assessment,
        narrative,
        blast_radius=BlastRadiusResult(
            affected=[
                ImpactNode(service_id="database", label="Primary Database", depth=0),
                ImpactNode(service_id="api", label="Payments API", depth=1),
                ImpactNode(service_id="worker", label="Ledger Worker", depth=2),
            ],
            direct_count=1,
            transitive_count=2,
            warning=None,
            unmatched_resources=[],
        ),
        rollback_plan=RollbackPlan(
            steps=[
                RollbackStep(
                    order=1,
                    title="Revert aws_security_group.main",
                    detail="Rollback the ingress rule expansion first.",
                    estimated_minutes=10,
                    critical=True,
                ),
                RollbackStep(
                    order=2,
                    title="Restore aws_db_instance.primary",
                    detail="Restore the previous maintenance window.",
                    estimated_minutes=5,
                    critical=False,
                ),
            ],
            complexity="medium",
            complexity_score=3,
            complexity_explanation=(
                "Score 3/5 because the rollback touches network and database settings."
            ),
            warning=None,
        ),
        findings=[
            Finding(
                finding_id="finding-001",
                analysis_id=0,
                title="CRITICAL: aws_security_group.main",
                description="Security group exposure risk",
                severity="critical",
                category="networking/ingress",
                deterministic=True,
                confidence=1.0,
                uncertainty_note=None,
                evidence_refs=["ev-001"],
                skill_id=None,
            ),
            Finding(
                finding_id="finding-002",
                analysis_id=0,
                title="HIGH: aws_db_instance.primary",
                description="Maintenance window overlaps business hours",
                severity="high",
                category="data/service",
                deterministic=True,
                confidence=0.86,
                uncertainty_note="Peak-hour traffic estimate is based on the current incident sample.",
                evidence_refs=[
                    "ev-002",
                    "ev-redacted",
                    "ev-sensitive-blocked",
                ],
                skill_id=None,
            ),
            Finding(
                finding_id='finding "003"/legacy',
                analysis_id=0,
                title='HIGH: "legacy"\nmissing evidence',
                description="Legacy imported finding references unavailable evidence",
                severity="high",
                category="identity/access",
                deterministic=False,
                confidence=0.61,
                uncertainty_note="Legacy imported evidence reference is unavailable.",
                evidence_refs=["ev-legacy-safe", "secret/path.env#TOKEN"],
                skill_id=None,
            ),
        ],
        evidence_items=[
            EvidenceItem(
                evidence_id="ev-001",
                analysis_id=0,
                finding_id="finding-001",
                source_type="artifact",
                source_ref="terraform://plan.json#aws_security_group.main?action=modify",
                summary="Ingress CIDR widened to 0.0.0.0/0.",
                severity_hint="critical",
                deterministic=True,
                confidence=1.0,
                related_change_ids=["aws_security_group.main"],
                redaction_status="none",
            ),
            EvidenceItem(
                evidence_id="ev-002",
                analysis_id=0,
                finding_id="finding-002",
                source_type="topology",
                source_ref="topology://payments-api#service",
                summary="Database traffic is sourced by the payments tier during peak hours.",
                severity_hint="high",
                deterministic=True,
                confidence=0.86,
                related_change_ids=["aws_db_instance.primary"],
                redaction_status="none",
            ),
            EvidenceItem(
                evidence_id="ev-redacted",
                analysis_id=0,
                finding_id="finding-002",
                source_type="artifact",
                source_ref="terraform://redacted-plan.json#aws_db_instance.primary?action=modify",
                summary="Redacted database maintenance evidence should not render.",
                severity_hint="high",
                deterministic=True,
                confidence=0.9,
                related_change_ids=["aws_db_instance.primary"],
                redaction_status="redacted",
            ),
            EvidenceItem(
                evidence_id="ev-sensitive-blocked",
                analysis_id=0,
                finding_id="finding-002",
                source_type="artifact",
                source_ref="terraform://browser-secret.env#TOKEN?action=inspect",
                summary="Sensitive blocked browser summary should not render.",
                severity_hint="high",
                deterministic=True,
                confidence=0.91,
                related_change_ids=["aws_iam_policy.browser_sensitive"],
                redaction_status="sensitive_blocked",
            ),
            EvidenceItem(
                evidence_id="ev-legacy-safe",
                analysis_id=0,
                finding_id='finding "003"/legacy',
                source_type="topology",
                source_ref="topology://legacy-import#service",
                summary="Legacy topology confirms the imported finding scope.",
                severity_hint="high",
                deterministic=True,
                confidence=0.7,
                related_change_ids=["legacy-import"],
                redaction_status="none",
            ),
        ],
        artifact_snapshots={
            "plan.json": (
                b'{"resource":"aws_security_group.main","cidr_blocks":["0.0.0.0/0"]}\n'
            )
        },
        audit_context={
            "source_interface": "ui",
            "trigger_type": "dashboard_upload",
        },
        project_key="payments",
    )
    from models.database import SessionLocal
    from models.tables import Finding as PersistedFinding

    legacy_evidence = next(
        item
        for item in current_report["evidence_items"]
        if item["source_ref"] == "topology://legacy-import#service"
    )
    legacy_finding = next(
        finding
        for finding in current_report["findings"]
        if legacy_evidence["evidence_id"] in finding["evidence_refs"]
    )
    legacy_evidence_refs = [
        *legacy_finding["evidence_refs"],
        "secret/path.env#TOKEN",
    ]
    with SessionLocal() as session:
        session.query(PersistedFinding).filter(
            PersistedFinding.analysis_id == int(current_report["id"]),
            PersistedFinding.finding_id == str(legacy_finding["finding_id"]),
        ).update(
            {PersistedFinding.evidence_refs_json: json.dumps(legacy_evidence_refs)}
        )
        session.commit()


def _seed_projects() -> None:
    from services.project_service import create_project, set_active_project

    payments_project = create_project(
        project_key="payments",
        display_name="Payments",
        repository_url="https://github.com/acme/payments-api.git",
        default_branch="main",
    )
    create_project(
        project_key="platform",
        display_name="Platform",
        repository_url="https://github.com/acme/platform-hub.git",
        default_branch="main",
    )
    set_active_project(payments_project.id)


def _register_e2e_review_routes() -> None:
    from nicegui import ui

    from ui.components.findings_table import render_findings_table

    @ui.page("/_e2e/missing-evidence")
    def missing_evidence_page() -> None:
        render_findings_table(
            findings=[
                {
                    "finding_id": 'finding "missing"/legacy',
                    "title": 'HIGH: "missing"\nsecret ref',
                    "description": "Legacy imported finding references unavailable evidence.",
                    "severity": "high",
                    "category": "identity/access",
                    "confidence": 0.94,
                    "deterministic": False,
                    "evidence_refs": ["secret/path.env#TOKEN"],
                },
                {
                    "finding_id": "finding-redaction-states",
                    "title": "HIGH: fail-closed redaction states",
                    "description": "Imported evidence includes blocked and unknown redaction states.",
                    "severity": "high",
                    "category": "identity/access",
                    "confidence": 0.72,
                    "deterministic": True,
                    "evidence_refs": ["ev-e2e-sensitive", "ev-e2e-unknown"],
                },
            ],
            evidence_items=[
                {
                    "evidence_id": "ev-e2e-sensitive",
                    "source_type": "artifact",
                    "source_ref": "terraform://browser-secret.env#TOKEN?action=inspect",
                    "artifact": "browser-secret.env",
                    "resource": "aws_iam_policy.browser_sensitive",
                    "operation": "inspect",
                    "source_kind": "artifact",
                    "summary": "Sensitive blocked browser summary should not render.",
                    "severity_hint": "high",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                    "redaction_status": "sensitive_blocked",
                    "confidence": 0.91,
                },
                {
                    "evidence_id": "ev-e2e-unknown",
                    "source_type": "artifact",
                    "source_ref": "terraform://unknown-browser.json#aws_iam_policy.browser_unknown?action=modify",
                    "artifact": "unknown-browser.json",
                    "resource": "aws_iam_policy.browser_unknown",
                    "operation": "modify",
                    "source_kind": "artifact",
                    "summary": "Future redaction browser summary should not render.",
                    "severity_hint": "high",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                    "redaction_status": "future_status",
                    "confidence": 0.89,
                },
            ],
            title="E2E missing evidence findings",
        )

    @ui.page("/_e2e/v1-evidence")
    def v1_evidence_page() -> None:
        render_findings_table(
            findings=[
                {
                    "finding_id": "finding-v1-browser",
                    "title": "HIGH: legacy browser evidence",
                    "description": "Legacy report evidence predates redaction metadata.",
                    "severity": "high",
                    "category": "identity/access",
                    "confidence": 0.88,
                    "deterministic": True,
                    "evidence_refs": ["ev-v1-browser"],
                },
            ],
            evidence_items=[
                {
                    "evidence_id": "ev-v1-browser",
                    "source_type": "artifact",
                    "source_ref": "terraform://legacy-plan.json#L7",
                    "artifact": "legacy-plan.json",
                    "resource": "aws_iam_policy.legacy_browser",
                    "operation": "modify",
                    "source_kind": "artifact",
                    "summary": "Legacy browser summary remains visible.",
                    "severity_hint": "high",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                    "confidence": 0.88,
                },
            ],
            artifact_names=["legacy-plan.json"],
            report_id=44,
            title="E2E v1 evidence findings",
            report_schema_version="v1",
        )


def main() -> None:
    database_module, report_service_module = _reload_runtime()
    database_module.init_db()
    _seed_projects()
    _seed_review_report(report_service_module)
    app_module = import_module("app")
    _register_e2e_review_routes()
    app_module.run()


if __name__ == "__main__":
    main()
