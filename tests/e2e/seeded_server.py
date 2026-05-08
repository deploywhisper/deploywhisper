"""Seeded NiceGUI server for browser accessibility tests."""

from __future__ import annotations

import os
import sys
import tempfile
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
    report_service_module.persist_analysis_report(
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
                evidence_refs=["ev-002"],
                skill_id=None,
            ),
        ],
        evidence_items=[
            EvidenceItem(
                evidence_id="ev-001",
                analysis_id=0,
                finding_id="finding-001",
                source_type="artifact",
                source_ref="artifact://plan.json#line=12",
                summary="Ingress CIDR widened to 0.0.0.0/0.",
                severity_hint="critical",
                deterministic=True,
                confidence=1.0,
                related_change_ids=["aws_security_group.main"],
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


def main() -> None:
    database_module, report_service_module = _reload_runtime()
    database_module.init_db()
    _seed_projects()
    _seed_review_report(report_service_module)
    app_module = import_module("app")
    app_module.run()


if __name__ == "__main__":
    main()
