"""Tests for shared analysis-service helpers."""

from __future__ import annotations

import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import os

from pydantic import ValidationError

from analysis.interaction_risk import InteractionRisk
from analysis.risk_scorer import RiskAssessment, RiskContributor
from analysis.blast_radius import BlastRadiusResult
from analysis.rollback_planner import RollbackPlan
from evidence.extractor import extract_batch_evidence
from evidence.models import ContextSourceMetadata, EvidenceItem
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParseIssue, ParsedFileResult, UnifiedChange
from services.analysis_service import (
    AnalysisArtifacts,
    analyze_uploaded_files,
    build_advisory_summary,
    build_analysis_artifacts,
    build_context_completeness,
    build_share_summary,
    evaluate_parse_batch,
    resolve_analysis_project_scope,
    ShareSummaryJsonPayload,
)
from services.intake_service import uniquify_artifact_names
from services.ownership_service import CodeownersSource


def _incident_snapshot(count: int = 0) -> dict:
    freshness = "current" if count else "empty"
    return {
        "incident_index_size": count,
        "incident_index_version": f"incidents:{count}:test",
        "incident_index_last_indexed_at": ("2026-05-20T00:00:00Z" if count else None),
        "incident_index_freshness_status": freshness,
    }


class AnalysisServiceTests(unittest.TestCase):
    def test_analyze_uploaded_files_persists_elapsed_analysis_duration(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[],
                )
            ]
        )
        artifacts = AnalysisArtifacts(
            parse_batch=parse_batch,
            evidence_items=[],
            findings=[],
            assessment=RiskAssessment(
                score=10,
                severity="low",
                recommendation="go",
                top_risk="Low risk fixture.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            blast_radius=BlastRadiusResult(
                affected=[],
                direct_count=0,
                transitive_count=0,
            ),
            rollback_plan=RollbackPlan(
                steps=[],
                complexity="low",
                complexity_score=1,
            ),
            incident_matches=[],
            narrative=NarrativeResult(
                opening_sentence="GO: low risk fixture.",
                explanation="No material risk.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
        )

        with (
            patch(
                "services.analysis_service.resolve_analysis_project_scope",
                return_value=SimpleNamespace(id=17),
            ),
            patch(
                "services.analysis_service.build_analysis_artifacts",
                return_value=artifacts,
            ),
            patch(
                "services.analysis_service.persist_analysis_report",
                return_value={"id": 99, "analysis_duration_seconds": 7},
            ) as persist_analysis_report,
            patch(
                "services.analysis_service.perf_counter",
                side_effect=[10.0, 17.2],
            ),
        ):
            result = analyze_uploaded_files(
                [("plan.json", b"{}")],
                project_id=17,
                audit_context={"source_interface": "api"},
            )

        self.assertEqual(result.persisted_report["analysis_duration_seconds"], 7)
        self.assertEqual(
            persist_analysis_report.call_args.kwargs["analysis_duration_seconds"],
            7,
        )

    def test_analyze_uploaded_files_requires_explicit_project_scope_before_parsing(
        self,
    ) -> None:
        with (
            patch(
                "services.analysis_service.build_parse_batch",
                side_effect=AssertionError("project must resolve before parsing"),
            ) as build_parse_batch,
            self.assertRaisesRegex(ValueError, "Project scope is required") as exc_info,
        ):
            analyze_uploaded_files([("plan.json", b'{"resource_changes": []}')])

        self.assertEqual(
            getattr(exc_info.exception, "code", ""), "missing_project_scope"
        )
        build_parse_batch.assert_not_called()

    def test_resolve_analysis_project_scope_rejects_blank_explicit_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "Project key") as exc_info:
            resolve_analysis_project_scope(project_key="   ")

        self.assertEqual(
            getattr(exc_info.exception, "code", ""), "invalid_project_reference"
        )

    def test_build_analysis_artifacts_excludes_sensitive_raw_files_downstream(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Terraform changed a security group.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        seen_raw_files: list[dict[str, bytes | None] | None] = []

        def scoring_stub(*args, **kwargs):
            seen_raw_files.append(kwargs.get("raw_files"))
            return assessment

        def narrative_stub(*args, **kwargs):
            seen_raw_files.append(kwargs.get("raw_files"))
            return NarrativeResult(
                opening_sentence="CAUTION: review the security group update.",
                explanation="The deployment should be reviewed.",
                guidance=[],
                degraded=False,
                warnings=[],
            )

        with (
            patch("services.analysis_service.load_topology", return_value=({}, None)),
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at=None),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(0),
            ),
            patch(
                "services.analysis_service.evaluate_parse_batch",
                side_effect=scoring_stub,
            ),
            patch(
                "services.analysis_service.generate_narrative",
                side_effect=narrative_stub,
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            build_analysis_artifacts(
                [
                    (
                        "plan.json",
                        b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    ),
                    ("broken.tf", b"SECRET_TOKEN=should-not-leave-intake\nresource {"),
                    (".env", b"SECRET=1"),
                    ("notes.txt", b"hello"),
                ]
            )

        self.assertEqual(
            [sorted((raw_files or {}).keys()) for raw_files in seen_raw_files],
            [["plan.json"], ["plan.json"]],
        )

    def test_build_analysis_artifacts_marks_sensitive_or_unsupported_submissions_partial(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=24,
            severity="low",
            recommendation="go",
            top_risk="Terraform changed a security group.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        seen_partial_context: list[bool | None] = []

        def scoring_stub(*args, **kwargs):
            seen_partial_context.append(kwargs.get("partial_context"))
            scoped_assessment = assessment.model_copy()
            scoped_assessment.partial_context = bool(kwargs.get("partial_context"))
            return scoped_assessment

        with (
            patch("services.analysis_service.load_topology", return_value=({}, None)),
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at=None),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(0),
            ),
            patch(
                "services.analysis_service.evaluate_parse_batch",
                side_effect=scoring_stub,
            ),
            patch(
                "services.analysis_service.generate_narrative",
                return_value=NarrativeResult(
                    opening_sentence="GO: review the security group update.",
                    explanation="The deployment was analyzed.",
                    guidance=[],
                    degraded=False,
                    warnings=[],
                ),
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            artifacts = build_analysis_artifacts(
                [
                    (
                        "plan.json",
                        b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    ),
                    (".env", b"SECRET=1"),
                    ("notes.txt", b"hello"),
                ]
            )

        self.assertEqual(seen_partial_context, [True])
        self.assertTrue(artifacts.assessment.partial_context)
        self.assertEqual(artifacts.assessment.recommendation, "caution")
        self.assertLess(artifacts.assessment.confidence, 0.7)
        self.assertTrue(artifacts.assessment.context_completeness.insufficient_context)
        self.assertIn("INSUFFICIENT CONTEXT", artifacts.assessment.top_risk)

    def test_build_analysis_artifacts_labels_public_pattern_when_incidents_empty(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=68,
            severity="high",
            recommendation="caution",
            top_risk="Public ingress requires review.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        blast_radius = BlastRadiusResult(
            affected=[],
            direct_count=0,
            transitive_count=0,
            warning=None,
            unmatched_resources=[],
        )
        rollback_plan = RollbackPlan(steps=[], complexity="low", warning=None)
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review public ingress.",
            explanation="The deployment should be reviewed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch(
                "services.analysis_service.build_parse_batch",
                return_value=ParseBatchResult(
                    files=[
                        ParsedFileResult(
                            file_name="plan.json",
                            tool="terraform",
                            status="parsed",
                            changes=[
                                UnifiedChange(
                                    source_file="plan.json",
                                    tool="terraform",
                                    resource_id="aws_security_group.ssh",
                                    action="modify",
                                    summary=(
                                        "Terraform opened SSH ingress from "
                                        "0.0.0.0/0 on port 22."
                                    ),
                                )
                            ],
                        )
                    ]
                ),
            ),
            patch("services.analysis_service.extract_batch_evidence", return_value=[]),
            patch("services.analysis_service.load_topology", return_value=({}, None)),
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at=None),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(0),
            ),
            patch(
                "analysis.incident_matcher.load_incident_candidates", return_value=[]
            ),
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=assessment,
            ),
            patch(
                "services.analysis_service.compute_blast_radius",
                return_value=blast_radius,
            ),
            patch(
                "services.analysis_service.generate_rollback_plan",
                return_value=rollback_plan,
            ),
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
        ):
            artifacts = build_analysis_artifacts(
                [("plan.json", b"{}")],
                project_id=123,
            )

        self.assertEqual(len(artifacts.incident_matches), 1)
        self.assertEqual(
            artifacts.incident_matches[0].match_type,
            "public_risk_pattern",
        )
        self.assertEqual(
            artifacts.incident_matches[0].public_pattern_id,
            "public-ingress-wide-open",
        )
        self.assertTrue(artifacts.incident_matches[0].verification_guidance)

    def test_build_analysis_artifacts_adds_owner_signals_from_codeowners_and_topology(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Terraform changed the payments security group.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        topology = {
            "updated_at": "2026-06-08T12:00:00Z",
            "metadata": {
                "import": {
                    "source_type": "custom",
                    "source_ref": "topology.json",
                    "warnings": [],
                }
            },
            "services": [
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["aws_security_group.payments"],
                    "downstream": [],
                    "owners": ["@payments-runtime"],
                }
            ],
        }
        with (
            patch(
                "services.analysis_service.load_topology",
                return_value=(topology, None),
            ),
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(
                    updated_at="2026-06-08T12:00:00Z",
                    payload=topology,
                    warnings=[],
                ),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(2),
            ),
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=assessment,
            ),
            patch(
                "services.analysis_service.generate_narrative",
                return_value=NarrativeResult(
                    opening_sentence="CAUTION: review the payments change.",
                    explanation="The deployment should be reviewed.",
                    guidance=[],
                    degraded=False,
                    warnings=[],
                ),
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            artifacts = build_analysis_artifacts(
                [
                    (
                        "CODEOWNERS",
                        "\n".join(
                            [
                                "* @platform",
                                "/services/payments/ @payments-sre @payments-dev",
                            ]
                        ).encode(),
                    ),
                    (
                        "services/payments/plan.json",
                        b'{"resource_changes": [{"address": "aws_security_group.payments", "change": {"actions": ["update"]}}]}',
                    ),
                ],
                project_id=123,
            )

        context = artifacts.assessment.context_completeness
        owner_signals = [signal.model_dump() for signal in context.owner_signals]
        self.assertIn(
            {
                "scope": "file",
                "subject": "services/payments/plan.json",
                "owners": ["@payments-sre", "@payments-dev"],
                "source": "CODEOWNERS",
                "source_ref": "CODEOWNERS",
                "matched_pattern": "/services/payments/",
                "resource_id": None,
                "service_id": None,
                "escalation_hint": "Escalate file review for services/payments/plan.json to @payments-sre, @payments-dev.",
            },
            owner_signals,
        )
        self.assertIn(
            {
                "scope": "service",
                "subject": "Payments API",
                "owners": ["@payments-runtime"],
                "source": "topology",
                "source_ref": "topology.json",
                "matched_pattern": None,
                "resource_id": "aws_security_group.payments",
                "service_id": "payments-api",
                "escalation_hint": "Escalate service review for Payments API to @payments-runtime.",
            },
            owner_signals,
        )
        self.assertIn(
            "Escalate file review for services/payments/plan.json to @payments-sre, @payments-dev.",
            context.escalation_hints,
        )
        self.assertNotIn(
            "Add CODEOWNERS or ownership mapping for analyzed files/resources.",
            context.context_todos,
        )

    def test_build_analysis_artifacts_preserves_owner_signals_after_intake_paths(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Terraform changed the payments security group.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        with (
            patch("services.analysis_service.load_topology", return_value=(None, None)),
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(
                    updated_at=None,
                    payload=None,
                    warnings=[],
                ),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(0),
            ),
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=assessment,
            ),
            patch(
                "services.analysis_service.generate_narrative",
                return_value=NarrativeResult(
                    opening_sentence="CAUTION: review the payments change.",
                    explanation="The deployment should be reviewed.",
                    guidance=[],
                    degraded=False,
                    warnings=[],
                ),
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            artifacts = build_analysis_artifacts(
                uniquify_artifact_names(
                    [
                        (
                            "repo/.github/CODEOWNERS",
                            b"/services/payments/ @payments-sre",
                        ),
                        (
                            "repo/services/payments/plan.json",
                            b'{"resource_changes": [{"address": "aws_security_group.payments", "change": {"actions": ["update"]}}]}',
                        ),
                    ]
                ),
                project_id=123,
            )

        context = artifacts.assessment.context_completeness
        self.assertIn(
            {
                "scope": "file",
                "subject": "repo/services/payments/plan.json",
                "owners": ["@payments-sre"],
                "source": "CODEOWNERS",
                "source_ref": "repo/.github/CODEOWNERS",
                "matched_pattern": "/services/payments/",
                "resource_id": None,
                "service_id": None,
                "escalation_hint": "Escalate file review for repo/services/payments/plan.json to @payments-sre.",
            },
            [signal.model_dump() for signal in context.owner_signals],
        )

    def test_codeowners_file_owner_prevents_missing_resource_ownership_downgrade(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=24,
            severity="low",
            recommendation="go",
            top_risk="Terraform changed a security group.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        topology = {
            "updated_at": "2026-06-08T12:00:00Z",
            "metadata": {
                "import": {
                    "source_type": "custom",
                    "source_ref": "topology.json",
                    "warnings": [],
                }
            },
            "services": [
                {
                    "id": "unrelated-api",
                    "label": "Unrelated API",
                    "resource_keys": ["aws_security_group.unrelated"],
                    "owners": ["@platform-runtime"],
                }
            ],
        }

        with (
            patch(
                "services.analysis_service.load_topology",
                return_value=(topology, None),
            ),
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(
                    updated_at="2026-06-08T12:00:00Z",
                    payload=topology,
                    warnings=[],
                ),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(2),
            ),
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=assessment,
            ),
            patch(
                "services.analysis_service.generate_narrative",
                return_value=NarrativeResult(
                    opening_sentence="GO: review the security group update.",
                    explanation="The deployment was analyzed.",
                    guidance=[],
                    degraded=False,
                    warnings=[],
                ),
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            artifacts = build_analysis_artifacts(
                [
                    (
                        "CODEOWNERS",
                        b"/services/payments/ @payments-sre",
                    ),
                    (
                        "services/payments/plan.json",
                        b'{"resource_changes": [{"address": "aws_security_group.payments", "change": {"actions": ["update"]}}]}',
                    ),
                ],
                project_id=123,
            )

        context = artifacts.assessment.context_completeness
        self.assertEqual([signal.scope for signal in context.owner_signals], ["file"])
        self.assertEqual(context.owner_signals[0].owners, ["@payments-sre"])
        self.assertEqual(context.ownership_unmapped_subjects, [])
        self.assertNotIn(
            "Add CODEOWNERS or ownership mapping for analyzed files/resources.",
            context.context_todos,
        )
        self.assertGreaterEqual(context.context_score, 0.7)
        self.assertFalse(context.insufficient_context)

    def test_topology_owner_prevents_missing_file_ownership_downgrade(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=24,
            severity="low",
            recommendation="go",
            top_risk="Terraform security group changed.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        topology = {
            "updated_at": "2026-06-08T12:00:00Z",
            "metadata": {
                "import": {
                    "source_type": "custom",
                    "source_ref": "topology.json",
                    "warnings": [],
                }
            },
            "services": [
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["aws_security_group.payments"],
                    "owners": ["@payments-runtime"],
                }
            ],
        }

        with (
            patch(
                "services.analysis_service.load_topology",
                return_value=(topology, None),
            ),
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(
                    updated_at="2026-06-08T12:00:00Z",
                    payload=topology,
                    warnings=[],
                ),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(2),
            ),
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=assessment,
            ),
            patch(
                "services.analysis_service.generate_narrative",
                return_value=NarrativeResult(
                    opening_sentence="GO: review the deployment update.",
                    explanation="The deployment was analyzed.",
                    guidance=[],
                    degraded=False,
                    warnings=[],
                ),
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            artifacts = build_analysis_artifacts(
                [
                    (
                        "services/payments/plan.json",
                        (
                            b'{"resource_changes": [{"address": '
                            b'"aws_security_group.payments", "change": '
                            b'{"actions": ["update"]}}]}'
                        ),
                    )
                ],
                project_id=123,
            )

        context = artifacts.assessment.context_completeness
        self.assertEqual(
            [signal.scope for signal in context.owner_signals], ["service"]
        )
        self.assertEqual(context.owner_signals[0].owners, ["@payments-runtime"])
        self.assertEqual(context.ownership_unmapped_subjects, [])
        self.assertNotIn(
            "Add CODEOWNERS or ownership mapping for analyzed files/resources.",
            context.context_todos,
        )
        self.assertGreaterEqual(context.context_score, 0.7)
        self.assertFalse(context.insufficient_context)

    def test_build_analysis_artifacts_adds_context_todo_when_ownership_missing(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=24,
            severity="low",
            recommendation="go",
            top_risk="Terraform changed a security group.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        topology = {
            "updated_at": "2026-06-08T12:00:00Z",
            "metadata": {
                "import": {
                    "source_type": "custom",
                    "source_ref": "topology.json",
                    "warnings": [],
                }
            },
            "services": [
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["aws_security_group.payments"],
                    "downstream": [],
                }
            ],
        }

        with (
            patch(
                "services.analysis_service.load_topology",
                return_value=(topology, None),
            ),
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(
                    updated_at="2026-06-08T12:00:00Z",
                    payload=topology,
                    warnings=[],
                ),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(2),
            ),
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=assessment,
            ),
            patch(
                "services.analysis_service.generate_narrative",
                return_value=NarrativeResult(
                    opening_sentence="GO: review the security group update.",
                    explanation="The deployment was analyzed.",
                    guidance=[],
                    degraded=False,
                    warnings=[],
                ),
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            artifacts = build_analysis_artifacts(
                [
                    (
                        "services/payments/plan.json",
                        b'{"resource_changes": [{"address": "aws_security_group.payments", "change": {"actions": ["update"]}}]}',
                    )
                ],
                project_id=123,
            )

        context = artifacts.assessment.context_completeness
        self.assertEqual(context.owner_signals, [])
        self.assertIn(
            "Add CODEOWNERS or ownership mapping for analyzed files/resources.",
            context.context_todos,
        )
        self.assertIn(
            "services/payments/plan.json",
            context.ownership_unmapped_subjects,
        )
        self.assertIn("Payments API", context.ownership_unmapped_subjects)
        self.assertEqual(context.context_score, 0.84)
        self.assertEqual(context.confidence_level, "medium")
        self.assertFalse(context.insufficient_context)
        self.assertIn("ownership mapping is incomplete", context.uncertainty)

    def test_build_context_completeness_suppresses_service_ownership_when_topology_disabled(
        self,
    ) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="services/payments/plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="services/payments/plan.json",
                            tool="terraform",
                            resource_id="aws_security_group.payments",
                            action="modify",
                            summary="Terraform changed a payments security group.",
                        )
                    ],
                )
            ]
        )
        topology = {
            "services": [
                {
                    "id": "payments-api",
                    "label": "Payments API",
                    "resource_keys": ["aws_security_group.payments"],
                    "owners": ["@payments-runtime"],
                }
            ]
        }
        context = build_context_completeness(
            parse_batch,
            include_topology_context=False,
            include_incident_context=False,
            topology=topology,
            codeowners_sources=(
                CodeownersSource(
                    source_ref="CODEOWNERS",
                    content="/services/payments/ @payments-sre",
                ),
            ),
        )

        self.assertEqual([signal.scope for signal in context.owner_signals], ["file"])
        self.assertEqual(context.owner_signals[0].owners, ["@payments-sre"])
        self.assertNotIn(
            "aws_security_group.payments",
            context.ownership_unmapped_subjects,
        )
        self.assertNotIn("Payments API", context.ownership_unmapped_subjects)

    def _share_report_payload(self) -> dict:
        return {
            "id": 17,
            "report_schema_version": "v2",
            "severity": "medium",
            "recommendation": "caution",
            "top_risk": "Terraform changed a security group.",
            "narrative_opening": "CAUTION: review the security group update.",
            "narrative_available": True,
            "warnings": [],
            "findings": [
                {
                    "finding_id": "finding-001",
                    "title": "CRITICAL: aws_security_group.main",
                    "severity": "critical",
                    "confidence": 1.0,
                    "evidence_refs": ["ev-001", "ev-002"],
                },
                {
                    "finding_id": "finding-002",
                    "title": "HIGH: Deployment/api",
                    "severity": "high",
                    "confidence": 0.88,
                    "evidence_refs": ["ev-003"],
                },
                {
                    "finding_id": "finding-003",
                    "title": "MEDIUM: Jenkinsfile",
                    "severity": "medium",
                    "confidence": 0.72,
                    "evidence_refs": ["ev-004"],
                },
                {
                    "finding_id": "finding-004",
                    "title": "LOW: extra detail",
                    "severity": "low",
                    "confidence": 0.55,
                    "evidence_refs": ["ev-005"],
                },
            ],
            "evidence_items": [
                {"finding_id": "finding-001"},
                {"finding_id": "finding-001"},
                {"finding_id": "finding-002"},
                {"finding_id": "finding-003"},
                {"finding_id": "finding-004"},
            ],
            "blast_radius": {
                "affected": [
                    {"label": "Primary Database"},
                    {"label": "API Service"},
                ],
                "direct_count": 1,
                "transitive_count": 1,
                "warning": None,
            },
            "rollback_plan": {
                "steps": [
                    {
                        "title": "Revert aws_security_group.main",
                    }
                ],
                "complexity": "medium",
                "complexity_score": 3,
                "warning": None,
            },
            "context_completeness": {
                "context_score": 0.84,
            },
        }

    def _satisfy_share_payload_evidence_law(self, report: dict) -> None:
        for evidence, evidence_id in zip(
            report["evidence_items"],
            ["ev-001", "ev-002", "ev-003", "ev-004", "ev-005"],
            strict=True,
        ):
            evidence["evidence_id"] = evidence_id
            evidence["deterministic"] = True
            evidence["determinism_level"] = "deterministic"

    def test_build_analysis_artifacts_extracts_evidence_items(self) -> None:
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Terraform changed a security group.",
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=12,
                    summary="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        blast_radius = BlastRadiusResult(
            affected=[],
            direct_count=0,
            transitive_count=0,
            warning=None,
            unmatched_resources=[],
        )
        rollback_plan = RollbackPlan(steps=[], complexity="low", warning=None)
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch(
                "services.analysis_service.load_topology",
                return_value=({}, None),
            ),
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at=None),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(0),
            ),
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=assessment,
            ) as evaluate_mock,
            patch(
                "services.analysis_service.compute_blast_radius",
                return_value=blast_radius,
            ),
            patch(
                "services.analysis_service.generate_rollback_plan",
                return_value=rollback_plan,
            ),
            patch(
                "services.analysis_service.find_incident_matches",
                return_value=[],
            ),
            patch(
                "services.analysis_service.generate_narrative",
                return_value=narrative,
            ),
        ):
            artifacts = build_analysis_artifacts(
                [
                    (
                        "plan.json",
                        b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    )
                ]
            )

        self.assertEqual(len(artifacts.evidence_items), 1)
        passed_evidence_items = evaluate_mock.call_args.kwargs["evidence_items"]
        self.assertEqual(len(passed_evidence_items), 1)
        self.assertEqual(
            passed_evidence_items[0].evidence_id,
            artifacts.evidence_items[0].evidence_id,
        )
        self.assertEqual(artifacts.evidence_items[0].source_type, "artifact")
        self.assertEqual(artifacts.evidence_items[0].severity_hint, "high")
        self.assertEqual(
            artifacts.evidence_items[0].related_change_ids,
            [artifacts.parse_batch.files[0].changes[0].change_id],
        )
        self.assertEqual(len(artifacts.findings), 1)
        self.assertEqual(artifacts.findings[0].confidence, 1.0)
        self.assertAlmostEqual(
            artifacts.assessment.context_completeness.context_score,
            0.55,
        )
        self.assertEqual(artifacts.assessment.confidence, 0.55)
        self.assertEqual(artifacts.assessment.recommendation, "caution")
        self.assertTrue(artifacts.assessment.context_completeness.insufficient_context)
        self.assertEqual(
            artifacts.assessment.context_completeness.confidence_level,
            "low",
        )
        self.assertIn(
            "insufficient context",
            artifacts.assessment.context_completeness.uncertainty.lower(),
        )
        self.assertIn(
            "Import or refresh topology context for this project/workspace.",
            artifacts.assessment.context_completeness.context_todos,
        )
        self.assertIn(
            "Import relevant incident history for this project/workspace.",
            artifacts.assessment.context_completeness.context_todos,
        )
        self.assertEqual(
            artifacts.assessment.context_completeness.evidence_success_rate,
            1.0,
        )
        self.assertEqual(
            artifacts.assessment.context_completeness.parser_success_by_tool,
            {"terraform": 1.0},
        )

    def test_build_context_completeness_uses_raw_score_for_thresholds(self) -> None:
        batch = ParseBatchResult(
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
                            summary="Terraform changed a security group.",
                        ),
                        UnifiedChange(
                            source_file="plan.json",
                            tool="terraform",
                            resource_id="aws_security_group.extra",
                            action="modify",
                            summary="Terraform changed another security group.",
                        ),
                    ],
                )
            ]
        )
        evidence_items = extract_batch_evidence(batch)[:1]

        with (
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at="2026-05-10T00:00:00Z"),
            ),
            patch("services.analysis_service._freshness_score", return_value=0.984),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(0),
            ),
        ):
            context = build_analysis_artifacts.__globals__[
                "_build_context_completeness"
            ](batch, evidence_items=evidence_items)

        self.assertEqual(context.context_score, 0.7)
        self.assertEqual(context.confidence_level, "low")
        self.assertTrue(context.insufficient_context)
        self.assertIn("evidence coverage", context.uncertainty)
        self.assertIn(
            "Review evidence extraction gaps for supported artifacts.",
            context.context_todos,
        )

    def test_build_context_completeness_surfaces_kubernetes_live_state_todos(
        self,
    ) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="deployment.yaml",
                    tool="kubernetes",
                    status="parsed",
                    changes=[],
                )
            ]
        )

        with patch(
            "services.analysis_service.get_topology_status",
            return_value=SimpleNamespace(
                updated_at="2026-06-09T00:00:00Z",
                warnings=[
                    "Kubernetes live-state context TODO: cluster access is unavailable."
                ],
            ),
        ):
            context = build_analysis_artifacts.__globals__[
                "_build_context_completeness"
            ](batch, include_incident_context=False)

        self.assertLess(context.context_score, 0.7)
        self.assertEqual(context.confidence_level, "low")
        self.assertTrue(context.insufficient_context)
        self.assertIn(
            "Resolve Kubernetes live-state context TODOs before relying on topology context.",
            context.context_todos,
        )
        self.assertIn("Kubernetes live-state", context.uncertainty)

    def test_build_context_completeness_keeps_partial_kubernetes_context_usable(
        self,
    ) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="deployment.yaml",
                    tool="kubernetes",
                    status="parsed",
                    changes=[],
                )
            ]
        )

        with patch(
            "services.analysis_service.get_topology_status",
            return_value=SimpleNamespace(
                updated_at="2026-06-09T00:00:00Z",
                payload={
                    "services": [
                        {
                            "id": "Deployment/payments/api",
                            "resource_keys": ["Deployment/payments/api"],
                            "downstream": [],
                        }
                    ]
                },
                warnings=[
                    "Kubernetes live-state context TODO: all-namespaces access is unavailable for 'context:prod' resource 'deployments'."
                ],
            ),
        ):
            context = build_analysis_artifacts.__globals__[
                "_build_context_completeness"
            ](batch, include_incident_context=False)

        self.assertGreaterEqual(context.context_score, 0.7)
        self.assertLess(context.context_score, 1.0)
        self.assertEqual(context.confidence_level, "medium")
        self.assertFalse(context.insufficient_context)
        self.assertIn(
            "Resolve Kubernetes live-state context TODOs before relying on topology context.",
            context.context_todos,
        )
        self.assertIn("Kubernetes live-state", context.uncertainty)

    def test_build_context_completeness_uses_kubernetes_drift_todos(
        self,
    ) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="deployment.yaml",
                    tool="kubernetes",
                    status="parsed",
                    changes=[],
                )
            ]
        )

        with patch(
            "services.analysis_service.get_topology_status",
            return_value=SimpleNamespace(
                updated_at="2026-06-09T00:00:00Z",
                payload={
                    "services": [
                        {
                            "id": "Deployment/payments/api",
                            "resource_keys": ["Deployment/payments/api"],
                            "downstream": [],
                        }
                    ]
                },
                warnings=[],
                drift=SimpleNamespace(
                    status="unavailable",
                    warnings=[
                        "Kubernetes live-state context TODO: cluster access is unavailable for 'context:prod'."
                    ],
                ),
            ),
        ):
            context = build_analysis_artifacts.__globals__[
                "_build_context_completeness"
            ](batch, include_incident_context=False)

        self.assertLess(context.context_score, 1.0)
        self.assertEqual(context.confidence_level, "medium")
        self.assertIn(
            "Resolve Kubernetes live-state context TODOs before relying on topology context.",
            context.context_todos,
        )
        self.assertIn("Kubernetes live-state", context.uncertainty)

    def test_build_context_completeness_uses_malformed_kubernetes_drift_warnings(
        self,
    ) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="deployment.yaml",
                    tool="kubernetes",
                    status="parsed",
                    changes=[],
                )
            ]
        )

        with patch(
            "services.analysis_service.get_topology_status",
            return_value=SimpleNamespace(
                updated_at="2026-06-09T00:00:00Z",
                payload={
                    "services": [
                        {
                            "id": "Deployment/payments/api",
                            "resource_keys": ["Deployment/payments/api"],
                            "downstream": [],
                        }
                    ]
                },
                warnings=[],
                drift=SimpleNamespace(
                    status="unavailable",
                    warnings=[
                        "Kubernetes live-state import partially parsed one or more objects; malformed entries were skipped."
                    ],
                ),
            ),
        ):
            context = build_analysis_artifacts.__globals__[
                "_build_context_completeness"
            ](batch, include_incident_context=False)

        self.assertLess(context.context_score, 1.0)
        self.assertEqual(context.confidence_level, "medium")
        self.assertIn("Kubernetes live-state", context.uncertainty)

    def test_build_context_completeness_does_not_degrade_for_unsupported_kind_skips(
        self,
    ) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="deployment.yaml",
                    tool="kubernetes",
                    status="parsed",
                    changes=[],
                )
            ]
        )

        with patch(
            "services.analysis_service.get_topology_status",
            return_value=SimpleNamespace(
                updated_at="2026-06-09T00:00:00Z",
                payload={
                    "metadata": {
                        "import": {
                            "source_type": "kubernetes",
                            "source_ref": "context:prod",
                        }
                    },
                    "services": [
                        {
                            "id": "Deployment/payments/api",
                            "resource_keys": ["Deployment/payments/api"],
                            "downstream": [],
                        }
                    ],
                },
                warnings=[
                    "Kubernetes live-state import skipped unsupported or duplicate objects while preserving supported context."
                ],
            ),
        ):
            context = build_analysis_artifacts.__globals__[
                "_build_context_completeness"
            ](batch, include_incident_context=False)

        self.assertEqual(context.context_score, 1.0)
        self.assertEqual(context.confidence_level, "high")
        self.assertIsNone(context.uncertainty)

    def test_build_context_completeness_treats_namespace_only_kubernetes_context_as_unusable(
        self,
    ) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="namespace.yaml",
                    tool="kubernetes",
                    status="parsed",
                    changes=[],
                )
            ]
        )

        with patch(
            "services.analysis_service.get_topology_status",
            return_value=SimpleNamespace(
                updated_at="2026-06-09T00:00:00Z",
                payload={
                    "services": [
                        {
                            "id": "Namespace/payments",
                            "resource_keys": ["Namespace/payments"],
                            "downstream": [],
                        }
                    ]
                },
                warnings=[
                    "Kubernetes live-state context TODO: all-namespaces access is unavailable for 'context:prod' resource 'deployments'."
                ],
            ),
        ):
            context = build_analysis_artifacts.__globals__[
                "_build_context_completeness"
            ](batch, include_incident_context=False)

        self.assertLess(context.context_score, 0.7)
        self.assertEqual(context.confidence_level, "low")
        self.assertTrue(context.insufficient_context)
        self.assertIn(
            "Resolve Kubernetes live-state context TODOs before relying on topology context.",
            context.context_todos,
        )

    def test_build_context_completeness_treats_namespace_only_kubernetes_context_without_todos_as_unusable(
        self,
    ) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="namespace.yaml",
                    tool="kubernetes",
                    status="parsed",
                    changes=[],
                )
            ]
        )

        with patch(
            "services.analysis_service.get_topology_status",
            return_value=SimpleNamespace(
                updated_at="2026-06-09T00:00:00Z",
                payload={
                    "metadata": {
                        "import": {
                            "source_type": "kubernetes",
                            "source_ref": "context:prod",
                        }
                    },
                    "services": [
                        {
                            "id": "Namespace/payments",
                            "resource_keys": ["Namespace/payments"],
                            "downstream": [],
                        }
                    ],
                },
                warnings=[],
            ),
        ):
            context = build_analysis_artifacts.__globals__[
                "_build_context_completeness"
            ](batch, include_incident_context=False)

        self.assertLess(context.context_score, 0.7)
        self.assertEqual(context.confidence_level, "low")
        self.assertTrue(context.insufficient_context)

    def test_build_context_completeness_counts_distinct_evidence_coverage(
        self,
    ) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            change_id="change-1",
                            source_file="plan.json",
                            tool="terraform",
                            resource_id="aws_security_group.main",
                            action="modify",
                            summary="Terraform changed a security group.",
                        ),
                        UnifiedChange(
                            change_id="change-2",
                            source_file="plan.json",
                            tool="terraform",
                            resource_id="aws_db_instance.primary",
                            action="modify",
                            summary="Terraform changed a database.",
                        ),
                    ],
                )
            ]
        )
        duplicate_evidence = [
            EvidenceItem(
                evidence_id="ev-1",
                analysis_id=0,
                finding_id="pending:change-1",
                source_type="artifact",
                source_ref="artifact://plan.json#aws_security_group.main",
                artifact="plan.json",
                location="plan.json#aws_security_group.main",
                resource="aws_security_group.main",
                operation="modify",
                summary="Security group changed.",
                severity_hint="medium",
                deterministic=True,
                confidence=1.0,
                related_change_ids=["change-1"],
            ),
            EvidenceItem(
                evidence_id="ev-2",
                analysis_id=0,
                finding_id="pending:change-1",
                source_type="artifact",
                source_ref="artifact://plan.json#aws_security_group.main?duplicate=1",
                artifact="plan.json",
                location="plan.json#aws_security_group.main",
                resource="aws_security_group.main",
                operation="modify",
                summary="Security group changed again.",
                severity_hint="medium",
                deterministic=True,
                confidence=1.0,
                related_change_ids=["change-1"],
            ),
        ]

        with (
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at="2026-05-10T00:00:00Z"),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(10),
            ),
        ):
            context = build_analysis_artifacts.__globals__[
                "_build_context_completeness"
            ](batch, evidence_items=duplicate_evidence)

        self.assertEqual(context.evidence_success_rate, 0.5)
        self.assertEqual(context.incident_index_version, "incidents:unscoped")
        self.assertEqual(context.incident_index_freshness_status, "empty")
        self.assertIn(
            "Review evidence extraction gaps for supported artifacts.",
            context.context_todos,
        )
        self.assertIn("evidence coverage", context.uncertainty)

    def test_build_context_completeness_degrades_when_incident_snapshot_fails(
        self,
    ) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[],
                )
            ]
        )

        with (
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at="2026-05-10T00:00:00Z"),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                side_effect=RuntimeError("incident snapshot unavailable"),
            ),
        ):
            context = build_analysis_artifacts.__globals__[
                "_build_context_completeness"
            ](batch, project_id=123)

        self.assertEqual(context.incident_index_size, 0)
        self.assertEqual(context.incident_index_version, "incidents:unknown")
        self.assertEqual(context.incident_index_freshness_status, "stale")
        self.assertIn(
            "Import relevant incident history for this project/workspace.",
            context.context_todos,
        )
        self.assertIn("incident history", context.uncertainty)

    def test_context_sources_are_artifact_specific_and_match_evidence(self) -> None:
        change = UnifiedChange(
            change_id="change-plan-a",
            source_file="plan-a.json",
            tool="terraform",
            resource_id="aws_security_group.main",
            action="modify",
            summary="Terraform changed a security group.",
        )
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan-a.json",
                    tool="terraform",
                    status="parsed",
                    changes=[change],
                ),
                ParsedFileResult(
                    file_name="plan-b.json",
                    tool="terraform",
                    status="failed",
                    issue=ParseIssue(
                        file_name="plan-b.json",
                        tool="terraform",
                        message="invalid plan JSON",
                    ),
                ),
            ]
        )
        evidence = EvidenceItem(
            evidence_id="ev-plan-a",
            analysis_id=0,
            finding_id="finding-1",
            source_type="artifact",
            source_ref="artifact://plan-a.json#aws_security_group.main?action=modify",
            artifact="plan-a.json",
            location="plan-a.json#aws_security_group.main",
            resource="aws_security_group.main",
            operation="modify",
            summary="Security group changed.",
            severity_hint="medium",
            deterministic=True,
            confidence=1.0,
            related_change_ids=["change-plan-a"],
        )

        with (
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at="2026-05-10T00:00:00Z"),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(1),
            ),
        ):
            context = build_analysis_artifacts.__globals__[
                "_build_context_completeness"
            ](
                batch,
                evidence_items=[evidence],
                project_id=123,
                codeowners_sources=(
                    CodeownersSource(
                        source_ref="CODEOWNERS",
                        content="plan-a.json @platform\nplan-b.json @platform\n",
                    ),
                ),
            )

        sources_by_id = {source.source_id: source for source in context.context_sources}
        self.assertIn("artifact:plan-a.json", sources_by_id)
        self.assertIn("artifact:plan-b.json", sources_by_id)
        self.assertEqual(
            sources_by_id["artifact:plan-b.json"].freshness_status, "incomplete"
        )
        self.assertIn("parser:terraform", sources_by_id)
        self.assertEqual(
            sources_by_id["ownership:CODEOWNERS:CODEOWNERS"].freshness_status,
            "current",
        )

        enriched = build_analysis_artifacts.__globals__[
            "_evidence_items_with_context_sources"
        ]([evidence], list(context.context_sources))
        self.assertIsNotNone(enriched[0].context_source)
        self.assertEqual(enriched[0].context_source.source_type, "artifact")
        self.assertEqual(enriched[0].context_source.source_ref, "plan-a.json")

    def test_context_sources_split_ownership_by_actual_signal_source(self) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan-a.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            change_id="change-plan-a",
                            source_file="plan-a.json",
                            tool="terraform",
                            resource_id="aws_instance.web",
                            action="modify",
                            summary="Terraform changed a web instance.",
                        )
                    ],
                ),
                ParsedFileResult(
                    file_name="plan-b.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            change_id="change-plan-b",
                            source_file="plan-b.json",
                            tool="terraform",
                            resource_id="aws_instance.api",
                            action="modify",
                            summary="Terraform changed an API instance.",
                        )
                    ],
                ),
            ]
        )

        with (
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at="2026-05-10T00:00:00Z"),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(1),
            ),
        ):
            context = build_analysis_artifacts.__globals__[
                "_build_context_completeness"
            ](
                batch,
                project_id=123,
                topology={
                    "metadata": {"import": {"source_ref": "topology://cluster-a"}},
                    "services": [
                        {
                            "id": "checkout",
                            "label": "checkout",
                            "owners": ["@runtime"],
                            "resource_keys": ["aws_instance.api"],
                        }
                    ],
                },
                codeowners_sources=(
                    CodeownersSource(
                        source_ref="CODEOWNERS",
                        content="plan-a.json @platform\n",
                    ),
                ),
            )

        ownership_sources = {
            source.source_id: source
            for source in context.context_sources
            if source.source_type == "ownership"
        }
        self.assertIn("ownership:CODEOWNERS:CODEOWNERS", ownership_sources)
        self.assertIn("ownership:topology:topology://cluster-a", ownership_sources)
        self.assertNotIn("ownership:mapping", ownership_sources)

    def test_topology_ownership_source_inherits_topology_freshness(self) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            change_id="change-plan",
                            source_file="plan.json",
                            tool="terraform",
                            resource_id="aws_instance.api",
                            action="modify",
                            summary="Terraform changed an API instance.",
                        )
                    ],
                )
            ]
        )

        with (
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(
                    updated_at="2026-03-01T00:00:00Z",
                    payload={
                        "metadata": {"import": {"source_ref": "topology://cluster-a"}}
                    },
                    warnings=[],
                ),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(1),
            ),
        ):
            context = build_analysis_artifacts.__globals__[
                "_build_context_completeness"
            ](
                batch,
                project_id=123,
                topology={
                    "metadata": {"import": {"source_ref": "topology://cluster-a"}},
                    "services": [
                        {
                            "id": "checkout",
                            "label": "checkout",
                            "owners": ["@runtime"],
                            "resource_keys": ["aws_instance.api"],
                        }
                    ],
                },
            )

        ownership_source = next(
            source
            for source in context.context_sources
            if source.source_id == "ownership:topology:topology://cluster-a"
        )
        self.assertEqual(ownership_source.freshness_status, "stale")
        self.assertLess(ownership_source.confidence, 1.0)
        self.assertIn(
            "topology_ownership_source_stale",
            ownership_source.limitations,
        )

    def test_blank_artifact_name_degrades_context_source_to_unknown_file(self) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="",
                    tool="terraform",
                    status="failed",
                    issue=ParseIssue(
                        file_name="",
                        tool="terraform",
                        message="raw parser error for /private/tmp/secret.tf",
                    ),
                )
            ]
        )

        context = build_analysis_artifacts.__globals__["_build_context_completeness"](
            batch,
            include_topology_context=False,
            include_incident_context=False,
        )

        artifact_source = next(
            source
            for source in context.context_sources
            if source.source_type == "artifact"
        )
        self.assertEqual(artifact_source.source_ref, "unknown-file")
        self.assertIn("missing_artifact_name", artifact_source.limitations)
        self.assertIn("parser_issue", artifact_source.limitations)
        self.assertNotIn(
            "/private/tmp/secret.tf",
            " ".join(artifact_source.limitations),
        )

    def test_evidence_context_source_matching_rejects_prefix_collisions(
        self,
    ) -> None:
        evidence = EvidenceItem(
            evidence_id="ev-prod-2",
            analysis_id=0,
            finding_id="finding-1",
            source_type="topology",
            source_ref="state://prod-2#aws_instance.web",
            artifact="topology.json",
            location="state://prod-2#aws_instance.web",
            resource="aws_instance.web",
            operation="modify",
            summary="Topology evidence came from prod-2.",
            severity_hint="medium",
            deterministic=True,
            confidence=1.0,
        )
        sources = [
            ContextSourceMetadata(
                source_id="topology:terraform-state:state://prod",
                source_type="topology",
                source_ref="state://prod",
                scope="project:payments",
                freshness_status="current",
                confidence=1.0,
            ),
            ContextSourceMetadata(
                source_id="topology:terraform-state:state://prod-2",
                source_type="topology",
                source_ref="state://prod-2",
                scope="project:payments",
                freshness_status="current",
                confidence=1.0,
            ),
        ]

        enriched = build_analysis_artifacts.__globals__[
            "_evidence_items_with_context_sources"
        ]([evidence], sources)

        self.assertIsNotNone(enriched[0].context_source)
        self.assertEqual(enriched[0].context_source.source_ref, "state://prod-2")

    def test_evidence_context_source_matching_does_not_use_type_only_fallback(
        self,
    ) -> None:
        evidence = EvidenceItem(
            evidence_id="ev-unmatched-topology",
            analysis_id=0,
            finding_id="finding-1",
            source_type="topology",
            source_ref="state://unseen#aws_instance.web",
            artifact="topology.json",
            location="state://unseen#aws_instance.web",
            resource="aws_instance.web",
            operation="modify",
            summary="Topology evidence came from an unseen source.",
            severity_hint="medium",
            deterministic=True,
            confidence=1.0,
        )
        sources = [
            ContextSourceMetadata(
                source_id="topology:terraform-state:state://prod",
                source_type="topology",
                source_ref="state://prod",
                scope="project:payments",
                freshness_status="current",
                confidence=1.0,
            )
        ]

        enriched = build_analysis_artifacts.__globals__[
            "_evidence_items_with_context_sources"
        ]([evidence], sources)

        self.assertIsNone(enriched[0].context_source)

    def test_stale_incident_index_downgrades_context_source_and_score(self) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            change_id="change-plan",
                            source_file="plan.json",
                            tool="terraform",
                            resource_id="aws_instance.web",
                            action="modify",
                            summary="Terraform changed a web instance.",
                        )
                    ],
                )
            ]
        )
        evidence = EvidenceItem(
            evidence_id="ev-plan",
            analysis_id=0,
            finding_id="finding-1",
            source_type="artifact",
            source_ref="artifact://plan.json#aws_instance.web?action=modify",
            artifact="plan.json",
            location="plan.json#aws_instance.web",
            resource="aws_instance.web",
            operation="modify",
            summary="Web instance changed.",
            severity_hint="medium",
            deterministic=True,
            confidence=1.0,
            related_change_ids=["change-plan"],
        )

        with (
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at="2026-05-10T00:00:00Z"),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value={
                    **_incident_snapshot(4),
                    "incident_index_freshness_status": "stale",
                },
            ),
        ):
            context = build_analysis_artifacts.__globals__[
                "_build_context_completeness"
            ](batch, evidence_items=[evidence], project_id=123)

        incident_source = next(
            source
            for source in context.context_sources
            if source.source_type == "incident"
        )
        self.assertEqual(incident_source.freshness_status, "stale")
        self.assertLessEqual(incident_source.confidence, 0.5)
        self.assertIn("stale_incident_index", incident_source.limitations)
        self.assertLess(context.context_score, 1.0)
        self.assertIn("incident history is stale", context.uncertainty or "")

    def test_partial_parser_and_evidence_sources_are_incomplete(self) -> None:
        covered_change = UnifiedChange(
            change_id="change-covered",
            source_file="plan-a.json",
            tool="terraform",
            resource_id="aws_instance.web",
            action="modify",
            summary="Terraform changed a web instance.",
        )
        uncovered_change = UnifiedChange(
            change_id="change-uncovered",
            source_file="plan-b.json",
            tool="terraform",
            resource_id="aws_instance.api",
            action="modify",
            summary="Terraform changed an API instance.",
        )
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan-a.json",
                    tool="terraform",
                    status="parsed",
                    changes=[covered_change],
                ),
                ParsedFileResult(
                    file_name="plan-b.json",
                    tool="terraform",
                    status="failed",
                    issue=ParseIssue(
                        file_name="plan-b.json",
                        tool="terraform",
                        message="invalid plan JSON",
                    ),
                ),
                ParsedFileResult(
                    file_name="plan-c.json",
                    tool="terraform",
                    status="parsed",
                    changes=[uncovered_change],
                ),
            ]
        )
        evidence = EvidenceItem(
            evidence_id="ev-plan-a",
            analysis_id=0,
            finding_id="finding-1",
            source_type="artifact",
            source_ref="artifact://plan-a.json#aws_instance.web?action=modify",
            artifact="plan-a.json",
            location="plan-a.json#aws_instance.web",
            resource="aws_instance.web",
            operation="modify",
            summary="Web instance changed.",
            severity_hint="medium",
            deterministic=True,
            confidence=1.0,
            related_change_ids=["change-covered"],
        )

        with (
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at="2026-05-10T00:00:00Z"),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(1),
            ),
        ):
            context = build_analysis_artifacts.__globals__[
                "_build_context_completeness"
            ](batch, evidence_items=[evidence], project_id=123)

        sources_by_type = {
            source.source_type: source for source in context.context_sources
        }
        self.assertEqual(sources_by_type["parser"].freshness_status, "incomplete")
        self.assertIn("partial_parser_coverage", sources_by_type["parser"].limitations)
        self.assertEqual(sources_by_type["evidence"].freshness_status, "incomplete")
        self.assertIn(
            "partial_evidence_coverage", sources_by_type["evidence"].limitations
        )

    def test_non_stale_incident_freshness_uses_specific_guidance(self) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            change_id="change-plan",
                            source_file="plan.json",
                            tool="terraform",
                            resource_id="aws_instance.web",
                            action="modify",
                            summary="Terraform changed a web instance.",
                        )
                    ],
                )
            ]
        )

        with (
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at="2026-05-10T00:00:00Z"),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value={
                    **_incident_snapshot(2),
                    "incident_index_freshness_status": "conflicting",
                },
            ),
        ):
            context = build_analysis_artifacts.__globals__[
                "_build_context_completeness"
            ](batch, evidence_items=[], project_id=123)

        self.assertIn(
            "Resolve incident history freshness: conflicting.",
            context.context_todos,
        )
        self.assertNotIn(
            "Refresh stale incident history for this project/workspace.",
            context.context_todos,
        )
        self.assertIn("incident history freshness is conflicting", context.uncertainty)
        incident_source = next(
            source
            for source in context.context_sources
            if source.source_type == "incident"
        )
        self.assertEqual(incident_source.freshness_status, "conflicting")
        self.assertIn("incident_index_conflicting", incident_source.limitations)
        self.assertIn("incident_index_conflicting", incident_source.conflicts)
        self.assertNotIn("stale_incident_index", incident_source.limitations)

    def test_build_context_completeness_uses_raw_parser_rate_for_tiny_gap(
        self,
    ) -> None:
        files = [
            ParsedFileResult(
                file_name=f"plan-{index}.json",
                tool="terraform",
                status="parsed",
                changes=[],
            )
            for index in range(999)
        ]
        files.append(
            ParsedFileResult(
                file_name="bad.yaml",
                tool="kubernetes",
                status="failed",
                changes=[],
            )
        )
        batch = ParseBatchResult(files=files)

        with (
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at="2026-05-10T00:00:00Z"),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(10),
            ),
        ):
            context = build_analysis_artifacts.__globals__[
                "_build_context_completeness"
            ](batch, evidence_items=[])

        self.assertEqual(context.parser_success_rate, 1.0)
        self.assertFalse(context.insufficient_context)
        self.assertIn(
            "Review parser errors and resubmit supported artifacts.",
            context.context_todos,
        )
        self.assertIn("parser coverage", context.uncertainty)

    def test_evaluate_parse_batch_preserves_non_mutating_metadata_without_evidence(
        self,
    ) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="empty-plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="empty-plan.json",
                            tool="terraform",
                            resource_id="terraform-plan",
                            action="no-op",
                            summary="Terraform plan has no resource changes.",
                            metadata={
                                "plan_format_version": "1.2",
                                "terraform_version": "1.8.5",
                                "plan_unsupported_fields": ["plan.planned_values"],
                            },
                        )
                    ],
                )
            ]
        )

        assessment = evaluate_parse_batch(batch, evidence_items=[])

        self.assertEqual(assessment.score, 0)
        self.assertEqual(assessment.severity, "low")
        self.assertEqual(len(assessment.contributors), 1)
        self.assertEqual(assessment.contributors[0].resource_id, "terraform-plan")
        self.assertEqual(assessment.contributors[0].contribution, 0)
        self.assertEqual(
            assessment.contributors[0].metadata["plan_unsupported_fields"],
            ["plan.planned_values"],
        )
        self.assertIn("no planned change", assessment.top_risk)

    def test_evaluate_parse_batch_extracts_mutating_batch_when_evidence_empty(
        self,
    ) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="plan.json",
                            tool="terraform",
                            resource_id="module.network.aws_security_group.main",
                            action="modify",
                            summary="Terraform changed an AWS security group.",
                            metadata={
                                "module_address": "module.network",
                                "plan_unsupported_fields": ["plan.planned_values"],
                            },
                        )
                    ],
                )
            ]
        )

        assessment = evaluate_parse_batch(
            batch,
            evidence_items=[],
            completion_client=lambda **_: '{"change_scores": []}',
        )

        self.assertEqual(len(assessment.contributors), 1)
        self.assertIsNotNone(assessment.contributors[0].evidence_id)
        self.assertEqual(
            assessment.contributors[0].resource_id,
            "module.network.aws_security_group.main",
        )
        self.assertEqual(
            assessment.contributors[0].metadata["plan_unsupported_fields"],
            ["plan.planned_values"],
        )
        self.assertGreater(assessment.score, 0)

    def test_evaluate_parse_batch_preserves_parser_metadata_for_evidence_scoring(
        self,
    ) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="plan.json",
                            tool="terraform",
                            resource_id="module.network.aws_security_group.main",
                            action="modify",
                            summary="Terraform changed an AWS security group.",
                            metadata={
                                "module_address": "module.network",
                                "provider_name": "registry.terraform.io/hashicorp/aws",
                                "plan_unsupported_fields": ["plan.planned_values"],
                            },
                        )
                    ],
                )
            ]
        )

        assessment = evaluate_parse_batch(
            batch,
            evidence_items=extract_batch_evidence(batch),
            completion_client=lambda **_: '{"change_scores": []}',
        )

        self.assertEqual(
            assessment.contributors[0].metadata["module_address"],
            "module.network",
        )
        self.assertEqual(
            assessment.contributors[0].metadata["plan_unsupported_fields"],
            ["plan.planned_values"],
        )

    def test_evaluate_parse_batch_preserves_mixed_non_mutating_metadata(
        self,
    ) -> None:
        batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="plan.json",
                            tool="terraform",
                            resource_id="data.aws_ami.selected",
                            action="read",
                            summary="Terraform read selected AMI.",
                            metadata={
                                "actions": ["read"],
                                "unknown_after_apply": ["id"],
                                "plan_unsupported_fields": ["plan.planned_values"],
                            },
                        ),
                        UnifiedChange(
                            source_file="plan.json",
                            tool="terraform",
                            resource_id="aws_security_group.main",
                            action="modify",
                            summary="Terraform changed an AWS security group.",
                            metadata={"module_address": "module.network"},
                        ),
                    ],
                )
            ]
        )

        assessment = evaluate_parse_batch(
            batch,
            evidence_items=extract_batch_evidence(batch),
            completion_client=lambda **_: '{"change_scores": []}',
        )

        contributors = {
            contributor.resource_id: contributor
            for contributor in assessment.contributors
        }
        self.assertEqual(
            set(contributors), {"aws_security_group.main", "data.aws_ami.selected"}
        )
        self.assertEqual(contributors["data.aws_ami.selected"].contribution, 0)
        self.assertIsNone(contributors["data.aws_ami.selected"].evidence_id)
        self.assertEqual(
            contributors["data.aws_ami.selected"].metadata["plan_unsupported_fields"],
            ["plan.planned_values"],
        )
        self.assertEqual(
            contributors["data.aws_ami.selected"].metadata["unknown_after_apply"],
            ["id"],
        )
        self.assertIsNotNone(contributors["aws_security_group.main"].evidence_id)
        self.assertGreater(assessment.score, 0)

    def test_build_analysis_artifacts_tracks_topology_timestamp_and_tool_success_rates(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Mixed parser context needs review.",
            contributors=[],
            interaction_risks=[],
            partial_context=True,
            warnings=[],
        )
        blast_radius = BlastRadiusResult(
            affected=[],
            direct_count=0,
            transitive_count=0,
            warning=None,
            unmatched_resources=[],
        )
        rollback_plan = RollbackPlan(steps=[], complexity="low", warning=None)
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review parser coverage.",
            explanation="Some artifacts could not be parsed cleanly.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch(
                "services.analysis_service.build_parse_batch",
                return_value=ParseBatchResult(
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
                                    summary="Terraform changed a security group.",
                                )
                            ],
                        ),
                        ParsedFileResult(
                            file_name="deployment.yaml",
                            tool="kubernetes",
                            status="failed",
                            changes=[],
                        ),
                    ]
                ),
            ),
            patch(
                "services.analysis_service.extract_batch_evidence",
                return_value=[],
            ),
            patch(
                "services.analysis_service.load_topology",
                return_value=({}, None),
            ),
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at="2026-04-18T11:22:33Z"),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(2),
            ),
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=assessment,
            ),
            patch(
                "services.analysis_service.compute_blast_radius",
                return_value=blast_radius,
            ),
            patch(
                "services.analysis_service.generate_rollback_plan",
                return_value=rollback_plan,
            ),
            patch(
                "services.analysis_service.find_incident_matches",
                return_value=[],
            ),
            patch(
                "services.analysis_service.generate_narrative",
                return_value=narrative,
            ),
        ):
            artifacts = build_analysis_artifacts(
                [
                    ("plan.json", b"{}"),
                    ("deployment.yaml", b"invalid"),
                ]
            )

        self.assertEqual(
            artifacts.assessment.context_completeness.topology_last_imported_at,
            "2026-04-18T11:22:33Z",
        )
        self.assertEqual(
            artifacts.assessment.context_completeness.parser_success_by_tool,
            {"kubernetes": 0.0, "terraform": 1.0},
        )

    def test_build_analysis_artifacts_builds_inferred_interaction_finding(self) -> None:
        assessment = RiskAssessment(
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="Terraform and Kubernetes changes overlap.",
            contributors=[
                RiskContributor(
                    evidence_id="ev-001",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=20,
                    summary="Terraform changed a security group.",
                    normalized_action="modify",
                    resource_category="networking/ingress",
                    blast_radius="High blast radius",
                    downstream_scope=2,
                    security_flags=[],
                    environment="production",
                    severity="high",
                    reasoning="Security group changes can affect production ingress.",
                )
            ],
            interaction_risks=[
                InteractionRisk(
                    key="terraform-kubernetes",
                    summary="Terraform and Kubernetes changes overlap around payments.",
                    contributing_files=["plan.json", "deployment.yaml"],
                    contributing_resources=["aws_security_group.main"],
                    contribution_bonus=12,
                )
            ],
            partial_context=False,
            warnings=[],
            source="heuristic+llm",
        )
        blast_radius = BlastRadiusResult(
            affected=[],
            direct_count=0,
            transitive_count=0,
            warning=None,
            unmatched_resources=[],
        )
        rollback_plan = RollbackPlan(steps=[], complexity="low", warning=None)
        narrative = NarrativeResult(
            opening_sentence="NO-GO: review the overlapping change set.",
            explanation="The deployment changes overlap.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch("services.analysis_service.load_topology", return_value=({}, None)),
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at="2026-04-18T00:00:00Z"),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(3),
            ),
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=assessment,
            ),
            patch(
                "services.analysis_service.generate_completion_with_settings",
                return_value='{"confidences":[{"key":"terraform-kubernetes","confidence":0.73}]}',
            ),
            patch(
                "services.analysis_service.compute_blast_radius",
                return_value=blast_radius,
            ),
            patch(
                "services.analysis_service.generate_rollback_plan",
                return_value=rollback_plan,
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
            patch(
                "services.analysis_service.generate_narrative",
                return_value=narrative,
            ),
        ):
            artifacts = build_analysis_artifacts(
                [
                    (
                        "plan.json",
                        b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    )
                ],
                include_topology_context=False,
                include_incident_context=False,
            )

        self.assertEqual(len(artifacts.findings), 2)
        inferred = artifacts.findings[1]
        self.assertFalse(inferred.deterministic)
        self.assertAlmostEqual(inferred.confidence, 0.73)
        self.assertGreaterEqual(
            artifacts.assessment.context_completeness.context_score,
            0.7,
        )

    def test_build_analysis_artifacts_reduces_context_score_for_stale_topology(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=24,
            severity="low",
            recommendation="go",
            top_risk="Low risk example",
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=12,
                    summary="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        blast_radius = BlastRadiusResult(
            affected=[],
            direct_count=0,
            transitive_count=0,
            warning=None,
            unmatched_resources=[],
        )
        rollback_plan = RollbackPlan(steps=[], complexity="low", warning=None)
        narrative = NarrativeResult(
            opening_sentence="GO: low risk example.",
            explanation="All good.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch("services.analysis_service.load_topology", return_value=({}, None)),
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at="2025-01-01T00:00:00Z"),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(0),
            ),
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=assessment,
            ),
            patch(
                "services.analysis_service.compute_blast_radius",
                return_value=blast_radius,
            ),
            patch(
                "services.analysis_service.generate_rollback_plan",
                return_value=rollback_plan,
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
            patch(
                "services.analysis_service.generate_narrative",
                return_value=narrative,
            ),
        ):
            artifacts = build_analysis_artifacts(
                [
                    (
                        "plan.json",
                        b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    )
                ]
            )

        self.assertGreater(
            artifacts.assessment.context_completeness.topology_freshness_days, 30
        )
        self.assertLess(artifacts.assessment.context_completeness.context_score, 0.7)

    def test_build_advisory_summary_does_not_require_attention_for_go_with_only_narrative_warnings(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=12,
            severity="low",
            recommendation="go",
            top_risk="Low risk example",
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=12,
                    summary="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: low risk example.",
            explanation="All good.",
            guidance=[],
            degraded=False,
            warnings=["Narrative provider warning."],
        )

        advisory = build_advisory_summary(assessment, narrative)

        self.assertFalse(advisory.should_block)
        self.assertFalse(advisory.requires_attention)
        self.assertIn("narrative_warnings", advisory.uncertainty_flags)

    def test_build_advisory_summary_requires_attention_for_partial_or_degraded_results(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=24,
            severity="low",
            recommendation="go",
            top_risk="Low risk example",
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=12,
                    summary="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=True,
            warnings=[
                "Analysis used partial context because one or more files failed to parse."
            ],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: low risk example.",
            explanation="All good.",
            guidance=[],
            degraded=True,
            warnings=["Narrative provider unavailable."],
        )

        advisory = build_advisory_summary(assessment, narrative)

        self.assertFalse(advisory.should_block)
        self.assertTrue(advisory.requires_attention)
        self.assertIn("partial_context", advisory.uncertainty_flags)
        self.assertIn("narrative_degraded", advisory.uncertainty_flags)

    def test_build_advisory_summary_requires_attention_for_low_context_completeness(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=18,
            severity="low",
            recommendation="go",
            top_risk="Low risk example",
            contributors=[],
            interaction_risks=[],
            context_completeness={
                "topology_freshness_days": 45,
                "incident_index_size": 0,
                "parser_success_rate": 1.0,
                "context_score": 0.52,
            },
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: low risk example.",
            explanation="All good.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        advisory = build_advisory_summary(assessment, narrative)

        self.assertTrue(advisory.requires_attention)
        self.assertIn("low_context_completeness", advisory.uncertainty_flags)

    def test_build_advisory_summary_requires_attention_for_uncertain_context(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=18,
            severity="low",
            recommendation="go",
            top_risk="Low risk example",
            contributors=[],
            interaction_risks=[],
            context_completeness={
                "topology_freshness_days": 0,
                "incident_index_size": 0,
                "parser_success_rate": 1.0,
                "evidence_success_rate": 1.0,
                "context_score": 0.8,
                "uncertainty": "Uncertainty: incident history is unavailable.",
                "context_todos": [
                    "Import relevant incident history for this project/workspace."
                ],
            },
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: low risk example.",
            explanation="All good.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        advisory = build_advisory_summary(assessment, narrative)

        self.assertTrue(advisory.requires_attention)
        self.assertIn("context_uncertainty", advisory.uncertainty_flags)
        self.assertIn("context_todos", advisory.uncertainty_flags)

    def test_build_share_summary_returns_thread_ready_markdown_and_json_payload(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {"APP_BASE_URL": "https://deploywhisper.example.com"},
            clear=False,
        ):
            summary = build_share_summary(self._share_report_payload())
        self.assertEqual(summary.severity, "medium")
        self.assertEqual(summary.recommendation, "caution")
        self.assertIn("Primary Database", summary.blast_radius_summary)
        self.assertIn("3/5", summary.rollback_summary)
        self.assertIn("Advisory only", summary.markdown)
        self.assertIn("Evidence Law", summary.markdown)
        self.assertIn("Advisory only", summary.plain_text)
        self.assertIn("Evidence Law", summary.plain_text)
        self.assertFalse(summary.should_block)
        self.assertLessEqual(len(summary.markdown), 1500)
        self.assertEqual(summary.json_payload.report_schema_version, "v2")
        self.assertEqual(summary.json_payload.evidence_law_status, "Needs review")
        self.assertIn(
            "lacks linked deterministic evidence",
            summary.json_payload.evidence_law_detail,
        )
        self.assertEqual(summary.json_payload.report_id, 17)
        self.assertEqual(len(summary.json_payload.top_findings), 3)
        self.assertEqual(summary.json_payload.evidence_count, 5)
        self.assertEqual(
            summary.json_payload.rollback_link,
            "https://deploywhisper.example.com/reports/17",
        )
        self.assertEqual(
            summary.json_payload.context_completeness.label, "STRONG CONTEXT"
        )

    def test_build_share_summary_surfaces_scanner_conflicts_without_overriding_severity(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "medium"
        report["findings"][0]["confidence"] = 0.62
        report["findings"][0]["evidence_refs"].append("ev-scanner")
        report["findings"][1]["severity"] = "low"
        report["findings"][2]["severity"] = "low"
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"][1]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "semgrep://results/sg-1",
                "artifact": "semgrep.sarif",
                "location": "main.tf:12",
                "resource": "aws_security_group.main",
                "operation": "scan",
                "summary": "Semgrep marked public ingress as high severity.",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "confidence": 0.9,
                "context_source": {
                    "source_id": "scanner:semgrep:semgrep.sarif",
                    "source_type": "scanner",
                    "source_ref": "semgrep.sarif",
                    "scope": "project:payments",
                    "freshness_status": "current",
                    "confidence": 0.9,
                    "conflicts": ["DeployWhisper finding severity is medium."],
                    "limitations": [],
                },
            }
        )

        summary = build_share_summary(report)

        self.assertEqual(summary.json_payload.top_findings[0].severity, "medium")
        self.assertEqual(len(summary.json_payload.scanner_conflicts), 2)
        conflict = summary.json_payload.scanner_conflicts[0]
        self.assertEqual(conflict.finding_id, "finding-001")
        self.assertEqual(conflict.scanner_source, "semgrep://results/sg-1")
        self.assertEqual(conflict.scanner_freshness, "current")
        self.assertEqual(conflict.deterministic_source, "ev-001")
        self.assertEqual(conflict.deterministic_freshness, "current")
        self.assertIn("high", conflict.confidence_impact)
        self.assertIn("medium", conflict.confidence_impact)
        self.assertIn("Review scanner evidence", conflict.recommended_verification)
        self.assertIn("Scanner conflict", summary.markdown)
        self.assertIn("finding-001", summary.markdown)
        self.assertIn("semgrep://results/sg-1", summary.markdown)
        self.assertIn("scanner confidence impact", summary.plain_text.lower())
        self.assertIn("finding-001", summary.plain_text)

    def test_build_share_summary_surfaces_stale_deterministic_conflict(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "high"
        report["findings"][0]["evidence_refs"].append("ev-scanner")
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "stale",
        }
        report["evidence_items"][1]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "semgrep://results/sg-1",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {
                    "freshness_status": "current",
                    "conflicts": [],
                    "limitations": [],
                },
            }
        )

        summary = build_share_summary(report)

        self.assertEqual(len(summary.json_payload.scanner_conflicts), 1)
        conflict = summary.json_payload.scanner_conflicts[0]
        self.assertEqual(conflict.scanner_freshness, "current")
        self.assertEqual(conflict.deterministic_freshness, "stale")
        self.assertIn(
            "Scanner freshness is current while deterministic evidence freshness is stale.",
            conflict.conflict_summary,
        )

    def test_build_share_summary_surfaces_each_conflicting_deterministic_source(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "high"
        report["findings"][0]["evidence_refs"].extend(
            ["ev-scanner", "ev-deterministic-context"]
        )
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"][1]["context_source"] = {
            "freshness_status": "stale",
        }
        report["evidence_items"].extend(
            [
                {
                    "evidence_id": "ev-deterministic-context",
                    "finding_id": "finding-001",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                    "context_source": {
                        "freshness_status": "current",
                        "conflicts": ["topology scope differs from scanner scope"],
                    },
                },
                {
                    "evidence_id": "ev-scanner",
                    "finding_id": "finding-001",
                    "source_type": "external_scanner",
                    "source_kind": "external_scanner",
                    "source_ref": "semgrep://results/sg-1",
                    "severity_hint": "high",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                    "context_source": {
                        "freshness_status": "current",
                        "conflicts": [],
                        "limitations": [],
                    },
                },
            ]
        )

        summary = build_share_summary(report)

        conflicts = summary.json_payload.scanner_conflicts
        self.assertEqual(
            {conflict.deterministic_source for conflict in conflicts},
            {"ev-002", "ev-deterministic-context"},
        )
        by_source = {conflict.deterministic_source: conflict for conflict in conflicts}
        self.assertEqual(by_source["ev-002"].deterministic_freshness, "stale")
        self.assertIn(
            "deterministic: topology scope differs from scanner scope",
            by_source["ev-deterministic-context"].conflict_summary,
        )
        self.assertNotIn(
            "ev-001",
            {conflict.deterministic_source for conflict in conflicts},
        )

    def test_build_share_summary_surfaces_deterministic_severity_conflict(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "high"
        report["findings"][0]["evidence_refs"].append("ev-scanner")
        report["evidence_items"][0]["severity_hint"] = "medium"
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"][1]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "semgrep://results/sg-1",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {
                    "freshness_status": "current",
                    "conflicts": [],
                    "limitations": [],
                },
            }
        )

        summary = build_share_summary(report)

        conflicts = summary.json_payload.scanner_conflicts
        self.assertEqual(len(conflicts), 1)
        conflict = conflicts[0]
        self.assertEqual(conflict.deterministic_source, "ev-001")
        self.assertIn(
            "Scanner severity high differs from deterministic evidence severity medium.",
            conflict.conflict_summary,
        )
        self.assertEqual(summary.json_payload.top_findings[0].severity, "high")

    def test_build_share_summary_keeps_all_scanner_only_deterministic_sources(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "medium"
        report["findings"][0]["evidence_refs"].append("ev-scanner")
        for item in report["evidence_items"]:
            item["context_source"] = {"freshness_status": "current"}
        report["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "semgrep://results/sg-1",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {
                    "freshness_status": "current",
                    "conflicts": [],
                    "limitations": [],
                },
            }
        )

        summary = build_share_summary(report)

        self.assertEqual(
            {
                conflict.deterministic_source
                for conflict in summary.json_payload.scanner_conflicts
            },
            {"ev-001", "ev-002"},
        )

    def test_build_share_summary_ignores_string_false_deterministic_signal(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "medium"
        report["findings"][0]["evidence_refs"].append("ev-scanner")
        report["evidence_items"][0]["deterministic"] = "false"
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"][1]["deterministic"] = False
        report["evidence_items"][1]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "semgrep://results/sg-1",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {
                    "freshness_status": "current",
                    "conflicts": [],
                    "limitations": [],
                },
            }
        )

        summary = build_share_summary(report)

        self.assertEqual(summary.json_payload.scanner_conflicts, [])

    def test_build_share_summary_keeps_distinct_scanner_rows_with_same_source(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "high"
        report["findings"][0]["evidence_refs"].extend(["ev-scanner-a", "ev-scanner-b"])
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"][1]["context_source"] = {
            "freshness_status": "current",
        }
        for scanner_id, conflict_text in (
            ("ev-scanner-a", "scanner result A disagrees with deterministic scope"),
            ("ev-scanner-b", "scanner result B disagrees with deterministic scope"),
        ):
            report["evidence_items"].append(
                {
                    "evidence_id": scanner_id,
                    "finding_id": "finding-001",
                    "source_type": "external_scanner",
                    "source_kind": "external_scanner",
                    "source_ref": "semgrep://results/shared-source",
                    "severity_hint": "high",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                    "context_source": {
                        "freshness_status": "current",
                        "conflicts": [conflict_text],
                        "limitations": [],
                    },
                }
            )

        summary = build_share_summary(report)

        conflicts = summary.json_payload.scanner_conflicts
        self.assertEqual(len(conflicts), 4)
        self.assertEqual(
            [conflict.scanner_source for conflict in conflicts],
            [
                "semgrep://results/shared-source",
                "semgrep://results/shared-source",
                "semgrep://results/shared-source",
                "semgrep://results/shared-source",
            ],
        )
        self.assertIn("scanner result A", conflicts[0].conflict_summary)
        self.assertIn("scanner result A", conflicts[1].conflict_summary)
        self.assertIn("scanner result B", conflicts[2].conflict_summary)
        self.assertIn("scanner result B", conflicts[3].conflict_summary)

    def test_build_share_summary_ignores_missing_only_scanner_conflict(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "high"
        report["findings"][0]["evidence_refs"].append("ev-scanner")
        report["evidence_items"][1]["deterministic"] = False
        report["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "scanner://missing-freshness",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
            }
        )

        summary = build_share_summary(report)

        self.assertEqual(summary.json_payload.scanner_conflicts, [])
        self.assertNotIn("scanner://missing-freshness", summary.markdown)

    def test_build_share_summary_ignores_equal_degraded_freshness_only_conflict(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "high"
        report["findings"][0]["evidence_refs"].append("ev-scanner")
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "Stale",
        }
        report["evidence_items"][1]["deterministic"] = False
        report["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "scanner://same-stale-freshness",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {
                    "freshness_status": "STALE",
                },
            }
        )

        summary = build_share_summary(report)

        self.assertEqual(summary.json_payload.scanner_conflicts, [])
        self.assertNotIn("same-stale-freshness", summary.markdown)

    def test_build_share_summary_reports_unknown_when_only_one_side_has_freshness(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "high"
        report["findings"][0]["evidence_refs"].append("ev-scanner")
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"][1]["deterministic"] = False
        report["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "scanner://missing-freshness",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
            }
        )

        summary = build_share_summary(report)

        self.assertEqual(len(summary.json_payload.scanner_conflicts), 1)
        conflict = summary.json_payload.scanner_conflicts[0]
        self.assertEqual(conflict.scanner_freshness, "unknown")
        self.assertEqual(conflict.deterministic_freshness, "current")
        self.assertIn("scanner://missing-freshness", summary.markdown)

    def test_build_share_summary_normalizes_freshness_case_for_conflicts(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "high"
        report["findings"][0]["evidence_refs"].append("ev-scanner")
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "Current",
        }
        report["evidence_items"][1]["deterministic"] = False
        report["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "scanner://case-normalized-freshness",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {
                    "freshness_status": "current",
                },
            }
        )

        summary = build_share_summary(report)

        self.assertEqual(summary.json_payload.scanner_conflicts, [])
        self.assertNotIn("case-normalized-freshness", summary.markdown)

    def test_build_share_summary_compact_markdown_prioritizes_severity_conflict(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "medium"
        report["findings"][0]["evidence_refs"].extend(
            ["ev-scanner-context", "ev-scanner-priority"]
        )
        report["context_completeness"] = {
            "context_score": 0.5,
            "uncertainty": "Reviewer context remains intentionally verbose. " * 80,
        }
        report["evidence_items"][0]["severity_hint"] = "medium"
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"][1]["deterministic"] = False
        report["evidence_items"].extend(
            [
                {
                    "evidence_id": "ev-scanner-context",
                    "finding_id": "finding-001",
                    "source_type": "external_scanner",
                    "source_kind": "external_scanner",
                    "source_ref": "semgrep://results/context-only",
                    "severity_hint": "medium",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                    "context_source": {
                        "freshness_status": "current",
                        "conflicts": ["scanner scope needs reviewer reconciliation"],
                        "limitations": [],
                    },
                },
                {
                    "evidence_id": "ev-scanner-priority",
                    "finding_id": "finding-001",
                    "source_type": "external_scanner",
                    "source_kind": "external_scanner",
                    "source_ref": "semgrep://results/priority-severity",
                    "severity_hint": "high",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                    "context_source": {
                        "freshness_status": "current",
                        "conflicts": [],
                        "limitations": [],
                    },
                },
            ]
        )

        summary = build_share_summary(report)

        self.assertLessEqual(len(summary.markdown), 1500)
        self.assertIn("semgrep://results/priority-severity", summary.markdown)
        self.assertNotIn("semgrep://results/context-only (current)", summary.markdown)

    def test_build_share_summary_escapes_scanner_conflict_markdown(self) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "medium"
        report["findings"][0]["evidence_refs"].append("ev-scanner")
        report["evidence_items"][0]["severity_hint"] = "medium"
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"][1]["deterministic"] = False
        report["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "scanner://[bad](https://example.test)<b>&raw</b>\n@here",
                "severity_hint": "medium",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {
                    "freshness_status": "current",
                    "conflicts": ["scanner says **override severity** <i>&now</i>"],
                    "limitations": [],
                },
            }
        )

        summary = build_share_summary(report)

        self.assertNotIn("[bad](https://example.test)", summary.markdown)
        self.assertNotIn("scanner says **override severity**", summary.markdown)
        self.assertNotIn("<b>", summary.markdown)
        self.assertNotIn("<i>", summary.markdown)
        self.assertIn(
            "scanner://\\[bad\\]\\(https://example.test\\)&lt;b&gt;&amp;raw&lt;/b&gt; @here",
            summary.markdown,
        )
        self.assertIn(
            "scanner says \\*\\*override severity\\*\\* &lt;i&gt;&amp;now&lt;/i&gt;",
            summary.markdown,
        )
        self.assertNotIn("\n@here", summary.plain_text)

    def test_build_share_summary_redacts_scanner_conflicts_without_evidence_detail(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "medium"
        report["findings"][0]["evidence_refs"].append("ev-scanner")
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"][1]["deterministic"] = False
        report["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "semgrep://results/hidden-when-detail-omitted",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {
                    "freshness_status": "current",
                    "conflicts": [],
                    "limitations": [],
                },
            }
        )

        summary = build_share_summary(report, evidence_detail_available=False)

        self.assertEqual(len(summary.json_payload.scanner_conflicts), 1)
        conflict = summary.json_payload.scanner_conflicts[0]
        self.assertEqual(conflict.scanner_source, "scanner evidence detail omitted")
        self.assertEqual(
            conflict.deterministic_source, "deterministic evidence detail omitted"
        )
        self.assertEqual(conflict.finding_id, "detail omitted")
        self.assertEqual(conflict.finding_title, "Finding detail omitted")
        self.assertEqual(conflict.scanner_freshness, "detail omitted")
        self.assertEqual(conflict.deterministic_freshness, "detail omitted")
        self.assertIn("source details are omitted", conflict.conflict_summary)
        self.assertNotIn("hidden-when-detail-omitted", summary.markdown)
        self.assertNotIn("hidden-when-detail-omitted", summary.plain_text)
        self.assertIn("scanner evidence detail omitted", summary.markdown)
        self.assertIn("scanner evidence detail omitted", summary.plain_text)

    def test_build_share_summary_surfaces_context_limitations_as_conflicts(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "medium"
        report["findings"][0]["evidence_refs"].append("ev-scanner")
        report["evidence_items"][0]["severity_hint"] = "medium"
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"][1]["deterministic"] = False
        report["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "semgrep://results/limitation-only",
                "severity_hint": "medium",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {
                    "freshness_status": "current",
                    "limitations": ["scanner scope excludes generated manifests"],
                },
            }
        )

        summary = build_share_summary(report)

        self.assertEqual(len(summary.json_payload.scanner_conflicts), 1)
        conflict = summary.json_payload.scanner_conflicts[0]
        self.assertIn(
            "scanner scope excludes generated manifests", conflict.conflict_summary
        )
        self.assertIn("limitation-only", summary.markdown)

    def test_build_share_summary_normalizes_scalar_context_conflict_signals(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "medium"
        report["findings"][0]["evidence_refs"].append("ev-scanner")
        report["evidence_items"][0]["severity_hint"] = "medium"
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "current",
            "conflicts": "deterministic scalar conflict",
        }
        report["evidence_items"][1]["deterministic"] = False
        report["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "semgrep://results/scalar-context",
                "severity_hint": "medium",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {
                    "freshness_status": "current",
                    "limitations": "scanner scalar limitation",
                },
            }
        )

        summary = build_share_summary(report)

        self.assertEqual(len(summary.json_payload.scanner_conflicts), 1)
        conflict = summary.json_payload.scanner_conflicts[0]
        self.assertIn("deterministic scalar conflict", conflict.conflict_summary)
        self.assertIn("scanner scalar limitation", conflict.conflict_summary)
        self.assertIn("scalar-context", summary.markdown)

    def test_build_share_summary_isolates_idless_findings_by_evidence_refs(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"] = [
            {
                "title": "First idless finding",
                "severity": "medium",
                "confidence": 0.7,
                "evidence_refs": ["det-a", "scan-a"],
            },
            {
                "title": "Second idless finding",
                "severity": "medium",
                "confidence": 0.7,
                "evidence_refs": ["det-b", "scan-b"],
            },
        ]
        report["evidence_items"] = [
            {
                "evidence_id": "det-a",
                "source_ref": "terraform://a",
                "severity_hint": "medium",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {"freshness_status": "current"},
            },
            {
                "evidence_id": "scan-a",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "semgrep://results/a",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {"freshness_status": "current"},
            },
            {
                "evidence_id": "det-b",
                "source_ref": "terraform://b",
                "severity_hint": "medium",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {"freshness_status": "current"},
            },
            {
                "evidence_id": "scan-b",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "semgrep://results/b",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {"freshness_status": "current"},
            },
        ]

        summary = build_share_summary(report)

        conflict_pairs = {
            (
                conflict.finding_title,
                conflict.scanner_source,
                conflict.deterministic_source,
            )
            for conflict in summary.json_payload.scanner_conflicts
        }
        self.assertEqual(
            conflict_pairs,
            {
                ("First idless finding", "semgrep://results/a", "det-a"),
                ("Second idless finding", "semgrep://results/b", "det-b"),
            },
        )

    def test_build_share_summary_compares_idless_linked_evidence_rows(self) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "medium"
        report["findings"][0]["evidence_refs"] = ["ev-scanner"]
        report["evidence_items"] = [
            {
                "finding_id": "finding-001",
                "source_ref": "terraform://plan#aws_security_group.main",
                "severity_hint": "medium",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {
                    "freshness_status": "current",
                },
            },
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "semgrep://results/idless-linked-row",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {
                    "freshness_status": "current",
                    "conflicts": [],
                    "limitations": [],
                },
            },
        ]

        summary = build_share_summary(report)

        self.assertEqual(len(summary.json_payload.scanner_conflicts), 1)
        conflict = summary.json_payload.scanner_conflicts[0]
        self.assertEqual(
            conflict.deterministic_source,
            "terraform://plan#aws_security_group.main",
        )
        self.assertIn("idless-linked-row", conflict.scanner_source)

    def test_build_share_summary_compact_markdown_keeps_conflict_fields(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "high"
        report["findings"][0]["evidence_refs"].append("ev-scanner")
        report["context_completeness"] = {
            "context_score": 0.5,
            "uncertainty": "Reviewer context remains intentionally verbose. " * 80,
        }
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "stale",
        }
        report["evidence_items"][1]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "semgrep://results/sg-1",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {
                    "freshness_status": "current",
                    "conflicts": [],
                    "limitations": [],
                },
            }
        )

        summary = build_share_summary(report)

        self.assertLessEqual(len(summary.markdown), 1500)
        self.assertIn("finding-001", summary.markdown)
        self.assertIn("semgrep://results/sg-1 (current)", summary.markdown)
        self.assertIn("ev-001 (stale)", summary.markdown)
        self.assertIn("Verification: Review scanner evidence", summary.markdown)
        self.assertIn("Scanner confidence impact", summary.markdown)

    def test_build_share_summary_compact_markdown_preserves_fields_after_long_conflict(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "high"
        report["findings"][0]["evidence_refs"].append("ev-scanner")
        report["context_completeness"] = {
            "context_score": 0.5,
            "uncertainty": "Reviewer context remains intentionally verbose. " * 80,
        }
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "stale",
            "conflicts": ["deterministic context " + "very long detail " * 60],
        }
        report["evidence_items"][1]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "semgrep://results/sg-1",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {
                    "freshness_status": "current",
                    "conflicts": ["scanner context " + "very long detail " * 60],
                    "limitations": [],
                },
            }
        )

        summary = build_share_summary(report)

        self.assertLessEqual(len(summary.markdown), 1500)
        self.assertIn("finding-001", summary.markdown)
        self.assertIn("semgrep://results/sg-1 (current)", summary.markdown)
        self.assertIn("ev-001 (stale)", summary.markdown)
        self.assertIn("Verification: Review scanner evidence", summary.markdown)
        self.assertIn("Scanner confidence impact", summary.markdown)

    def test_build_share_summary_compact_markdown_caps_long_sources(self) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "high"
        report["findings"][0]["evidence_refs"].append("ev-scanner")
        report["context_completeness"] = {
            "context_score": 0.5,
            "uncertainty": "Reviewer context remains intentionally verbose. " * 80,
        }
        report["evidence_items"][0].pop("evidence_id")
        report["evidence_items"][0]["source_ref"] = "terraform://" + "a" * 1000
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "stale",
        }
        report["evidence_items"][1]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "semgrep://" + "b" * 1000,
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {
                    "freshness_status": "current",
                    "conflicts": [],
                    "limitations": [],
                },
            }
        )

        summary = build_share_summary(report)

        self.assertLessEqual(len(summary.markdown), 1500)
        self.assertIn("Scanner source: semgrep://", summary.markdown)
        self.assertIn("deterministic source: terraform://", summary.markdown)

    def test_build_share_summary_compact_markdown_caps_multiple_conflicts(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"][0]["severity"] = "high"
        report["findings"][0]["evidence_refs"].append("ev-scanner")
        report["context_completeness"] = {
            "context_score": 0.5,
            "uncertainty": "Reviewer context remains intentionally verbose. " * 80,
        }
        report["evidence_items"][0]["context_source"] = {
            "freshness_status": "current",
        }
        report["evidence_items"][1]["context_source"] = {
            "freshness_status": "current",
        }
        for index in range(8):
            evidence_id = f"ev-conflicting-{index}"
            report["findings"][0]["evidence_refs"].append(evidence_id)
            report["evidence_items"].append(
                {
                    "evidence_id": evidence_id,
                    "finding_id": "finding-001",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                    "context_source": {
                        "freshness_status": "stale",
                        "conflicts": [
                            f"scanner scope conflicts with deterministic scope {index}"
                        ],
                    },
                }
            )
        report["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "semgrep://results/sg-many",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {
                    "freshness_status": "current",
                    "conflicts": [],
                    "limitations": [],
                },
            }
        )

        summary = build_share_summary(report)

        self.assertEqual(len(summary.json_payload.scanner_conflicts), 8)
        self.assertLessEqual(len(summary.markdown), 1500)
        self.assertIn("semgrep://results/sg-many (current)", summary.markdown)
        self.assertIn("ev-conflicting-0 (stale)", summary.markdown)
        self.assertIn("additional conflicts are available", summary.markdown)
        self.assertIn("JSON payload/report", summary.plain_text)

    def test_build_share_summary_requires_attention_for_unsatisfied_evidence_law(
        self,
    ) -> None:
        report = self._share_report_payload()
        report["severity"] = "low"
        report["recommendation"] = "go"
        report["context_completeness"] = {"context_score": 0.84}
        report["advisory"] = {"requires_attention": False}

        summary = build_share_summary(report)

        self.assertEqual(summary.json_payload.evidence_law_status, "Needs review")
        self.assertIn("requires additional human review", summary.uncertainty_summary)

    def test_build_share_summary_can_mark_evidence_detail_omitted(self) -> None:
        report = self._share_report_payload()
        report["severity"] = "low"
        report["recommendation"] = "go"
        report["advisory"] = {"requires_attention": False}

        summary = build_share_summary(report, evidence_detail_available=False)

        self.assertEqual(summary.json_payload.evidence_law_status, "Detail omitted")
        self.assertIn(
            "Evidence rows are not included",
            summary.json_payload.evidence_law_detail,
        )
        self.assertNotIn("requires additional human review", summary.plain_text.lower())

    def test_build_share_summary_normalizes_malformed_finding_confidence(self) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["severity"] = "low"
        report["recommendation"] = "go"
        report["advisory"] = {"requires_attention": False}
        report["findings"][0]["confidence"] = "oops"
        report["findings"][1]["confidence"] = math.nan

        summary = build_share_summary(report)

        self.assertEqual(summary.json_payload.top_findings[0].confidence, 0.0)
        self.assertEqual(summary.json_payload.top_findings[1].confidence, 0.0)
        self.assertNotIn("NaN", summary.json_payload.model_dump_json())

    def test_build_share_summary_ignores_malformed_finding_and_evidence_entries(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["findings"].insert(0, "oops")
        report["findings"].append(None)
        report["evidence_items"].insert(0, "oops")
        report["evidence_items"].append(None)

        summary = build_share_summary(report)

        self.assertEqual(len(summary.json_payload.top_findings), 3)
        self.assertEqual(summary.json_payload.evidence_count, 5)

    def test_share_summary_payload_rejects_unknown_evidence_law_status(self) -> None:
        with self.assertRaises(ValidationError):
            ShareSummaryJsonPayload(
                report_schema_version="v2",
                verdict_banner="DeployWhisper LOW · GO",
                evidence_law_status="Typo",
                evidence_law_detail="Invalid status should fail validation.",
                headline="GO: low risk",
                evidence_count=0,
                blast_radius_summary="0 direct / 0 transitive",
                rollback_summary="1/5 LOW · First step: No rollback steps available",
                context_completeness={
                    "score": 1.0,
                    "label": "STRONG CONTEXT",
                    "summary": "STRONG CONTEXT (1.00)",
                },
                advisory_summary="Standard approval flow is sufficient.",
            )

    def test_build_share_summary_normalizes_missing_report_schema_as_legacy(
        self,
    ) -> None:
        report = self._share_report_payload()
        report.pop("report_schema_version")

        summary = build_share_summary(report)

        self.assertEqual(summary.json_payload.version, "v1")
        self.assertEqual(summary.json_payload.report_schema_version, "v1")

    def test_build_share_summary_rejects_newer_report_schema_version(self) -> None:
        report = self._share_report_payload()
        report["report_schema_version"] = "v3"

        with self.assertRaises(ValueError):
            build_share_summary(report)

    def test_build_share_summary_rejects_malformed_report_schema_version(
        self,
    ) -> None:
        report = self._share_report_payload()
        report["report_schema_version"] = "legacy"

        with self.assertRaises(ValueError):
            build_share_summary(report)

    def test_build_share_summary_falls_back_to_deterministic_headline_without_narrative(
        self,
    ) -> None:
        report = self._share_report_payload()
        report["narrative_opening"] = ""
        report["narrative_available"] = False
        report["warnings"] = ["Narrative provider unavailable: provider offline"]
        report["context_completeness"] = {"context_score": 0.52}
        summary = build_share_summary(report)

        self.assertEqual(
            summary.headline, "CAUTION: Terraform changed a security group."
        )
        self.assertIn("CAUTION: Terraform changed a security group.", summary.markdown)
        self.assertEqual(
            summary.json_payload.context_completeness.label, "LIMITED CONTEXT"
        )

    def test_build_share_summary_requires_attention_for_partial_context_signal(
        self,
    ) -> None:
        report = self._share_report_payload()
        report["warnings"] = [
            "Analysis used partial context because one or more files failed to parse."
        ]
        summary = build_share_summary(report)

        self.assertIn(
            "requires additional human review",
            summary.uncertainty_summary.lower(),
        )
        self.assertIn("requires additional human review", summary.plain_text.lower())
        self.assertEqual(
            summary.json_payload.context_completeness.label, "LIMITED CONTEXT"
        )

    def test_build_share_summary_uses_insufficient_context_at_rounded_boundary(
        self,
    ) -> None:
        report = self._share_report_payload()
        report["context_completeness"] = {
            "context_score": 0.7,
            "parser_success_rate": 1.0,
            "evidence_success_rate": 1.0,
            "insufficient_context": True,
            "uncertainty": "Insufficient context: raw score was below threshold.",
        }

        summary = build_share_summary(report)

        self.assertEqual(
            summary.json_payload.context_completeness.label, "LIMITED CONTEXT"
        )
        self.assertIn("raw score was below threshold", summary.plain_text)
        self.assertIn("requires additional human review", summary.plain_text.lower())

    def test_build_share_summary_describes_evidence_gap_without_artifact_parse_wording(
        self,
    ) -> None:
        report = self._share_report_payload()
        report["context_completeness"] = {
            "context_score": 0.74,
            "parser_success_rate": 1.0,
            "evidence_success_rate": 0.5,
            "insufficient_context": False,
            "uncertainty": "Uncertainty: evidence coverage is partial.",
        }

        summary = build_share_summary(report)

        self.assertEqual(
            summary.json_payload.context_completeness.label, "LIMITED CONTEXT"
        )
        self.assertIn("evidence coverage is partial", summary.plain_text)
        self.assertNotIn("submitted artifacts were not analyzed", summary.plain_text)

    def test_build_share_summary_degrades_malformed_context_score(
        self,
    ) -> None:
        report = self._share_report_payload()
        report["context_completeness"] = {
            "context_score": "oops",
            "parser_success_rate": 1.0,
            "evidence_success_rate": 1.0,
            "insufficient_context": False,
        }

        summary = build_share_summary(report)

        self.assertEqual(summary.json_payload.context_completeness.score, 0.0)
        self.assertEqual(
            summary.json_payload.context_completeness.label, "LIMITED CONTEXT"
        )
        self.assertIn("requires additional human review", summary.plain_text.lower())

    def test_build_share_summary_requires_attention_for_context_uncertainty(
        self,
    ) -> None:
        report = self._share_report_payload()
        report["recommendation"] = "go"
        report["context_completeness"] = {
            "context_score": 0.82,
            "parser_success_rate": 1.0,
            "evidence_success_rate": 1.0,
            "insufficient_context": False,
            "uncertainty": "Uncertainty: topology context is stale.",
            "context_todos": [
                "Refresh stale topology context for this project/workspace."
            ],
        }

        summary = build_share_summary(report)

        self.assertEqual(
            summary.json_payload.context_completeness.label, "LIMITED CONTEXT"
        )
        self.assertIn("topology context is stale", summary.plain_text)
        self.assertIn("requires additional human review", summary.plain_text.lower())

    def test_build_share_summary_ignores_scalar_context_todos(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["recommendation"] = "go"
        report["context_completeness"] = {
            "context_score": 0.92,
            "parser_success_rate": 1.0,
            "evidence_success_rate": 1.0,
            "insufficient_context": False,
            "context_todos": "Review parser errors and resubmit supported artifacts.",
        }

        summary = build_share_summary(report)

        self.assertEqual(
            summary.json_payload.context_completeness.label, "STRONG CONTEXT"
        )
        self.assertNotIn("requires additional human review", summary.plain_text.lower())

    def test_build_share_summary_requires_attention_for_manifest_partial_analysis(
        self,
    ) -> None:
        report = self._share_report_payload()
        report["submission_manifest"] = {
            "partial_analysis": True,
            "partial_artifact_count": 1,
            "items": [
                {
                    "name": ".env",
                    "status": "sensitive",
                    "partial": True,
                }
            ],
        }

        summary = build_share_summary(report)

        self.assertEqual(
            summary.json_payload.context_completeness.label, "LIMITED CONTEXT"
        )
        self.assertIn("submitted artifacts were not analyzed", summary.plain_text)

    def test_build_share_summary_requires_attention_for_stored_partial_context(
        self,
    ) -> None:
        report = self._share_report_payload()
        report["severity"] = "low"
        report["recommendation"] = "go"
        report["context_completeness"] = {
            "context_score": 0.94,
            "parser_success_rate": 1.0,
            "evidence_success_rate": 1.0,
            "insufficient_context": False,
            "partial_context": True,
        }

        summary = build_share_summary(report)

        self.assertEqual(
            summary.json_payload.context_completeness.label, "LIMITED CONTEXT"
        )
        self.assertIn("submitted artifacts were not analyzed", summary.plain_text)
        self.assertIn("requires additional human review", summary.plain_text.lower())

    def test_build_share_summary_normalizes_false_like_context_booleans(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["severity"] = "low"
        report["recommendation"] = "go"
        report["narrative_available"] = "true"
        report["narrative_degraded"] = "false"
        report["context_completeness"] = {
            "context_score": 0.94,
            "parser_success_rate": 1.0,
            "evidence_success_rate": 1.0,
            "insufficient_context": "false",
            "partial_context": "false",
        }

        summary = build_share_summary(report)

        self.assertEqual(
            summary.json_payload.context_completeness.label, "STRONG CONTEXT"
        )
        self.assertNotIn("requires additional human review", summary.plain_text.lower())
        self.assertIn("Standard approval flow is sufficient", summary.plain_text)

    def test_build_share_summary_normalizes_false_like_narrative_availability(
        self,
    ) -> None:
        report = self._share_report_payload()
        report["severity"] = "low"
        report["recommendation"] = "go"
        report["narrative_available"] = "false"
        report["narrative_degraded"] = "false"
        report["warnings"] = []
        report["context_completeness"] = {
            "context_score": 0.94,
            "parser_success_rate": 1.0,
            "evidence_success_rate": 1.0,
            "insufficient_context": "false",
            "partial_context": "false",
        }

        summary = build_share_summary(report)

        self.assertEqual(
            summary.json_payload.context_completeness.label, "STRONG CONTEXT"
        )
        self.assertIn("requires additional human review", summary.plain_text.lower())

    def test_build_share_summary_ignores_non_finite_boolean_signals(
        self,
    ) -> None:
        report = self._share_report_payload()
        self._satisfy_share_payload_evidence_law(report)
        report["severity"] = "low"
        report["recommendation"] = "go"
        report["narrative_available"] = "true"
        report["narrative_degraded"] = math.nan
        report["context_completeness"] = {
            "context_score": 0.94,
            "parser_success_rate": 1.0,
            "evidence_success_rate": 1.0,
            "insufficient_context": math.inf,
            "partial_context": math.nan,
        }

        summary = build_share_summary(report)

        self.assertEqual(
            summary.json_payload.context_completeness.label, "STRONG CONTEXT"
        )
        self.assertNotIn("requires additional human review", summary.plain_text.lower())
        self.assertIn("Standard approval flow is sufficient", summary.plain_text)

    def test_build_share_summary_falls_back_to_local_report_link_without_public_base_url(
        self,
    ) -> None:
        summary = build_share_summary(self._share_report_payload())

        self.assertEqual(
            summary.json_payload.report_link,
            "http://127.0.0.1:8080/reports/17",
        )
        self.assertEqual(
            summary.json_payload.rollback_link,
            "http://127.0.0.1:8080/reports/17",
        )
        self.assertIn(
            "[View rollback plan](http://127.0.0.1:8080/reports/17)",
            summary.markdown,
        )

    def test_build_analysis_artifacts_shields_scored_assessment_from_narrator_mutation(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="Security group exposure risk",
            contributors=[
                RiskContributor(
                    evidence_id="ev-001",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=20,
                    summary="Security group exposure risk",
                    normalized_action="modify",
                    resource_category="networking/ingress",
                    blast_radius="High blast radius",
                    downstream_scope=2,
                    security_flags=[],
                    environment="production",
                    severity="high",
                    reasoning="Security group changes can affect production ingress.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        blast_radius = BlastRadiusResult(
            affected=[],
            direct_count=0,
            transitive_count=0,
            warning=None,
            unmatched_resources=[],
        )
        rollback_plan = RollbackPlan(steps=[], complexity="low", warning=None)

        def mutating_narrator(
            passed_assessment, passed_findings, completion_client=None, raw_files=None
        ):
            passed_assessment.score = 1
            passed_assessment.severity = "low"
            passed_findings[0].confidence = 0.1
            return NarrativeResult(
                opening_sentence="NO-GO: review the security group update.",
                explanation="The deployment widens database access and should be reviewed.",
                guidance=[],
                degraded=False,
                warnings=[],
            )

        with (
            patch("services.analysis_service.load_topology", return_value=({}, None)),
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at="2026-04-18T00:00:00Z"),
            ),
            patch(
                "services.analysis_service.get_incident_index_snapshot",
                return_value=_incident_snapshot(0),
            ),
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=assessment,
            ),
            patch(
                "services.analysis_service.compute_blast_radius",
                return_value=blast_radius,
            ),
            patch(
                "services.analysis_service.generate_rollback_plan",
                return_value=rollback_plan,
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
            patch(
                "services.analysis_service.generate_narrative",
                side_effect=mutating_narrator,
            ),
        ):
            artifacts = build_analysis_artifacts(
                [
                    (
                        "plan.json",
                        b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    )
                ]
            )

        self.assertEqual(artifacts.assessment.score, 72)
        self.assertEqual(artifacts.assessment.severity, "high")
        self.assertEqual(artifacts.findings[0].confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
