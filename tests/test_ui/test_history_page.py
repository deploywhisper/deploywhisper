"""Helpers and smoke tests for the history page."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from importlib import reload

import app as app_module
import config as config_module
import models.database as database_module
import models.repositories.analysis_reports as analysis_reports_repository_module
import models.tables as tables_module
import services.deployment_outcome_service as deployment_outcome_service_module
import services.feedback_service as feedback_service_module
import services.report_service as report_service_module
import services.project_service as project_service_module
import ui.components.report_detail_page as report_detail_page_module
import ui.routes.history as history_module
from analysis.risk_scorer import RiskAssessment, RiskContributor
from analysis.rollback_planner import RollbackPlan, RollbackStep
from evidence.models import EvidenceItem, Finding
from fastapi.testclient import TestClient
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult, UnifiedChange
from services.confidence_ledger import (
    build_confidence_ledger,
    normalize_confidence_ledger_payload,
)
from ui.formatters.datetime import format_history_timestamp
from ui.formatters.recommendations import recommendation_classes, recommendation_text
from ui.routes.history import page_selection_state
from analysis.incident_matcher import IncidentMatch


class HistoryPageHelpersTests(unittest.TestCase):
    def test_format_history_timestamp_humanizes_iso_values(self) -> None:
        self.assertEqual(
            format_history_timestamp("2026-04-16T15:24:44.380822"),
            "Apr 16, 2026 · 3:24 PM",
        )

    def test_page_selection_state_handles_empty_partial_and_full_pages(self) -> None:
        self.assertEqual(page_selection_state(set(), {1, 2}), (False, 0))
        self.assertEqual(page_selection_state({1, 2, 3}, {1}), (False, 1))
        self.assertEqual(page_selection_state({1, 2, 3}, {1, 2, 3, 4}), (True, 3))

    def test_history_toolchain_options_keeps_empty_default(self) -> None:
        self.assertEqual(
            history_module._history_toolchain_options(["kubernetes", "terraform"]),
            {
                "": "Any toolchain",
                "kubernetes": "Kubernetes",
                "terraform": "Terraform",
            },
        )

    def test_recommendation_helpers_preserve_semantic_go_no_go_styling(self) -> None:
        self.assertEqual(recommendation_text("no-go"), "NO-GO")
        self.assertIn("dw-danger-text", recommendation_classes("no-go"))
        self.assertIn("dw-success-text", recommendation_classes("go"))

    def test_operational_narrative_suppresses_sensitive_evidence_refs(self) -> None:
        items = report_detail_page_module._operational_narrative_items(
            {
                "report_schema_version": "v2",
                "top_risk": "Sensitive evidence ref risk",
                "parse_summary": "Parsed one sensitive artifact.",
                "contributors": [
                    {
                        "contribution": 90,
                        "resource_id": "aws_iam_policy.admin",
                        "source_file": "policy.tf",
                        "normalized_action": "modify",
                        "tool": "terraform",
                        "summary": "Policy changed.",
                        "resource_category": "identity",
                    }
                ],
                "findings": [
                    {
                        "finding_id": "finding-sensitive",
                        "severity": "high",
                        "confidence": 0.91,
                        "title": "HIGH: sensitive ref",
                        "description": "Sensitive evidence ref risk.",
                        "evidence_refs": "ev-sensitive",
                    }
                ],
                "evidence_items": [
                    {
                        "evidence_id": "ev-sensitive",
                        "source_type": "artifact",
                        "source_ref": "terraform://secret.env#TOKEN?action=inspect",
                        "summary": "Sensitive summary.",
                        "severity_hint": "high",
                        "deterministic": True,
                        "confidence": 0.9,
                        "redaction_status": "sensitive_blocked",
                    }
                ],
                "rollback_plan": {"steps": []},
            }
        )

        exact_resource = dict(items)["Exact resource/file"]
        verify_before_deploy = dict(items)["Verify before deploying"]
        self.assertIn("Sensitive evidence reference blocked", exact_resource)
        self.assertNotIn("secret.env", exact_resource)
        self.assertNotIn("TOKEN", exact_resource)
        self.assertIn("linked evidence metadata", verify_before_deploy)
        self.assertNotIn("Sensitive summary", verify_before_deploy)

    def test_operational_narrative_prefers_safe_mixed_redaction_evidence(
        self,
    ) -> None:
        items = report_detail_page_module._operational_narrative_items(
            {
                "report_schema_version": "v2",
                "top_risk": "Mixed evidence ordering risk",
                "parse_summary": "Parsed mixed evidence.",
                "contributors": [
                    {
                        "contribution": 90,
                        "resource_id": "aws_security_group.main",
                        "source_file": "plan.tf",
                        "normalized_action": "modify",
                        "tool": "terraform",
                        "summary": "Security group changed.",
                        "resource_category": "networking",
                    }
                ],
                "findings": [
                    {
                        "finding_id": "finding-mixed",
                        "severity": "high",
                        "confidence": 0.91,
                        "title": "HIGH: mixed evidence",
                        "description": "Mixed evidence ordering risk.",
                        "evidence_refs": ["ev-redacted", "ev-safe"],
                    }
                ],
                "evidence_items": [
                    {
                        "evidence_id": "ev-redacted",
                        "source_type": "artifact",
                        "source_ref": "terraform://redacted-plan.json#aws_security_group.main",
                        "summary": "Redacted summary.",
                        "severity_hint": "high",
                        "deterministic": True,
                        "confidence": 0.9,
                        "redaction_status": "redacted",
                    },
                    {
                        "evidence_id": "ev-safe",
                        "source_type": "artifact",
                        "source_ref": "terraform://safe-plan.json#L9",
                        "summary": "Safe summary.",
                        "severity_hint": "high",
                        "deterministic": True,
                        "confidence": 0.9,
                        "redaction_status": "none",
                    },
                ],
                "rollback_plan": {"steps": []},
            }
        )

        exact_resource = dict(items)["Exact resource/file"]
        self.assertIn("safe-plan.json", exact_resource)
        self.assertIn("line 9", exact_resource)
        self.assertNotIn("Evidence reference redacted", exact_resource)
        self.assertNotIn("redacted-plan.json", exact_resource)

    def test_operational_narrative_does_not_use_unrelated_evidence_when_refs_missing(
        self,
    ) -> None:
        items = report_detail_page_module._operational_narrative_items(
            {
                "report_schema_version": "v2",
                "top_risk": "Missing evidence ordering risk",
                "parse_summary": "Parsed missing evidence.",
                "contributors": [
                    {
                        "contribution": 95,
                        "resource_id": "aws_security_group.missing",
                        "source_file": "missing.tf",
                        "normalized_action": "modify",
                        "tool": "terraform",
                        "summary": "Security group changed.",
                        "resource_category": "networking",
                    }
                ],
                "findings": [
                    {
                        "finding_id": "finding-missing",
                        "severity": "critical",
                        "confidence": 0.95,
                        "title": "CRITICAL: missing evidence",
                        "description": "Primary finding evidence is unavailable.",
                        "evidence_refs": ["ev-missing"],
                    },
                    {
                        "finding_id": "finding-safe",
                        "severity": "low",
                        "confidence": 0.1,
                        "title": "LOW: unrelated safe evidence",
                        "description": "Unrelated finding has safe evidence.",
                        "evidence_refs": ["ev-safe"],
                    },
                ],
                "evidence_items": [
                    {
                        "evidence_id": "ev-safe",
                        "source_type": "artifact",
                        "source_ref": "terraform://safe-plan.json#L9",
                        "summary": "Safe but unrelated summary.",
                        "severity_hint": "low",
                        "deterministic": True,
                        "confidence": 0.9,
                        "redaction_status": "none",
                    },
                ],
                "rollback_plan": {"steps": []},
            }
        )

        exact_resource = dict(items)["Exact resource/file"]
        self.assertNotIn("Evidence reference:", exact_resource)
        self.assertNotIn("safe-plan.json", exact_resource)
        self.assertNotIn("line 9", exact_resource)

    def test_operational_narrative_does_not_use_unrelated_global_fallback(
        self,
    ) -> None:
        items = report_detail_page_module._operational_narrative_items(
            {
                "report_schema_version": "v2",
                "top_risk": "No linked evidence risk",
                "parse_summary": "Parsed no linked evidence.",
                "contributors": [
                    {
                        "contribution": 95,
                        "resource_id": "aws_security_group.unlinked",
                        "source_file": "unlinked.tf",
                        "normalized_action": "modify",
                        "tool": "terraform",
                        "summary": "Security group changed.",
                        "resource_category": "networking",
                    }
                ],
                "findings": [
                    {
                        "finding_id": "finding-unlinked",
                        "severity": "critical",
                        "confidence": 0.95,
                        "title": "CRITICAL: unlinked evidence",
                        "description": "Primary finding does not link evidence.",
                    },
                    {
                        "finding_id": "finding-safe",
                        "severity": "low",
                        "confidence": 0.1,
                        "title": "LOW: unrelated safe evidence",
                        "description": "Unrelated finding has safe evidence.",
                        "evidence_refs": ["ev-safe"],
                    },
                ],
                "evidence_items": [
                    {
                        "evidence_id": "ev-safe",
                        "finding_id": "finding-safe",
                        "source_type": "artifact",
                        "source_ref": "terraform://safe-plan.json#L9",
                        "summary": "Safe but unrelated summary.",
                        "severity_hint": "low",
                        "deterministic": True,
                        "confidence": 0.9,
                        "redaction_status": "none",
                    },
                ],
                "rollback_plan": {"steps": []},
            }
        )

        exact_resource = dict(items)["Exact resource/file"]
        self.assertNotIn("Evidence reference:", exact_resource)
        self.assertNotIn("safe-plan.json", exact_resource)

    def test_operational_narrative_allows_single_finding_legacy_fallback(
        self,
    ) -> None:
        items = report_detail_page_module._operational_narrative_items(
            {
                "report_schema_version": "v2",
                "top_risk": "Single finding evidence risk",
                "parse_summary": "Parsed one finding.",
                "contributors": [
                    {
                        "contribution": 95,
                        "resource_id": "aws_security_group.single",
                        "source_file": "single.tf",
                        "normalized_action": "modify",
                        "tool": "terraform",
                        "summary": "Security group changed.",
                        "resource_category": "networking",
                    }
                ],
                "findings": [
                    {
                        "finding_id": "finding-single",
                        "severity": "critical",
                        "confidence": 0.95,
                        "title": "CRITICAL: single evidence",
                        "description": "Single finding relies on report evidence.",
                    }
                ],
                "evidence_items": [
                    {
                        "evidence_id": "ev-single",
                        "source_type": "artifact",
                        "source_ref": "terraform://single-plan.json#L7",
                        "summary": "Single fallback summary.",
                        "severity_hint": "critical",
                        "deterministic": True,
                        "confidence": 0.9,
                        "redaction_status": "none",
                    },
                ],
                "rollback_plan": {"steps": []},
            }
        )

        exact_resource = dict(items)["Exact resource/file"]
        self.assertIn("single-plan.json", exact_resource)
        self.assertIn("line 7", exact_resource)

    def test_operational_narrative_treats_malformed_refs_as_unresolved(
        self,
    ) -> None:
        for evidence_refs in ({}, "{}"):
            with self.subTest(evidence_refs=evidence_refs):
                items = report_detail_page_module._operational_narrative_items(
                    {
                        "report_schema_version": "v2",
                        "top_risk": "Malformed refs risk",
                        "parse_summary": "Parsed malformed evidence refs.",
                        "contributors": [
                            {
                                "contribution": 95,
                                "resource_id": "aws_security_group.malformed",
                                "source_file": "malformed.tf",
                                "normalized_action": "modify",
                                "tool": "terraform",
                                "summary": "Security group changed.",
                                "resource_category": "networking",
                            }
                        ],
                        "findings": [
                            {
                                "finding_id": "finding-malformed",
                                "severity": "critical",
                                "confidence": 0.95,
                                "title": "CRITICAL: malformed evidence refs",
                                "description": "Primary finding evidence refs are malformed.",
                                "evidence_refs": evidence_refs,
                            },
                            {
                                "finding_id": "finding-safe",
                                "severity": "low",
                                "confidence": 0.1,
                                "title": "LOW: unrelated safe evidence",
                                "description": "Unrelated finding has safe evidence.",
                                "evidence_refs": ["ev-safe"],
                            },
                        ],
                        "evidence_items": [
                            {
                                "evidence_id": "ev-safe",
                                "source_type": "artifact",
                                "source_ref": "terraform://safe-plan.json#L9",
                                "summary": "Safe but unrelated summary.",
                                "severity_hint": "low",
                                "deterministic": True,
                                "confidence": 0.9,
                                "redaction_status": "none",
                            },
                        ],
                        "rollback_plan": {"steps": []},
                    }
                )

                exact_resource = dict(items)["Exact resource/file"]
                self.assertNotIn("Evidence reference:", exact_resource)
                self.assertNotIn("safe-plan.json", exact_resource)

    def test_operational_narrative_uses_same_finding_evidence_for_stale_refs(
        self,
    ) -> None:
        items = report_detail_page_module._operational_narrative_items(
            {
                "report_schema_version": "v2",
                "top_risk": "Stale evidence ref risk",
                "parse_summary": "Parsed stale evidence refs.",
                "contributors": [
                    {
                        "contribution": 95,
                        "resource_id": "aws_security_group.stale",
                        "source_file": "stale.tf",
                        "normalized_action": "modify",
                        "tool": "terraform",
                        "summary": "Security group changed.",
                        "resource_category": "networking",
                    }
                ],
                "findings": [
                    {
                        "finding_id": "finding-stale",
                        "severity": "critical",
                        "confidence": 0.95,
                        "title": "CRITICAL: stale evidence ref",
                        "description": "Primary finding evidence refs are stale.",
                        "evidence_refs": ["ev-stale"],
                    },
                    {
                        "finding_id": "finding-safe",
                        "severity": "low",
                        "confidence": 0.1,
                        "title": "LOW: unrelated safe evidence",
                        "description": "Unrelated finding has safe evidence.",
                        "evidence_refs": ["ev-safe"],
                    },
                ],
                "evidence_items": [
                    {
                        "evidence_id": "ev-owned",
                        "finding_id": "finding-stale",
                        "source_type": "artifact",
                        "source_ref": "terraform://owned-plan.json#L12",
                        "summary": "Owned fallback summary.",
                        "severity_hint": "critical",
                        "deterministic": True,
                        "confidence": 0.9,
                        "redaction_status": "none",
                    },
                    {
                        "evidence_id": "ev-safe",
                        "finding_id": "finding-safe",
                        "source_type": "artifact",
                        "source_ref": "terraform://safe-plan.json#L9",
                        "summary": "Safe but unrelated summary.",
                        "severity_hint": "low",
                        "deterministic": True,
                        "confidence": 0.9,
                        "redaction_status": "none",
                    },
                ],
                "rollback_plan": {"steps": []},
            }
        )

        exact_resource = dict(items)["Exact resource/file"]
        self.assertIn("owned-plan.json", exact_resource)
        self.assertIn("line 12", exact_resource)
        self.assertNotIn("safe-plan.json", exact_resource)

    def test_operational_narrative_suppresses_ambiguous_same_finding_fallback(
        self,
    ) -> None:
        items = report_detail_page_module._operational_narrative_items(
            {
                "report_schema_version": "v2",
                "top_risk": "Duplicate stale evidence ref risk",
                "parse_summary": "Parsed duplicate finding ids.",
                "contributors": [
                    {
                        "contribution": 95,
                        "resource_id": "aws_security_group.duplicate",
                        "source_file": "duplicate.tf",
                        "normalized_action": "modify",
                        "tool": "terraform",
                        "summary": "Security group changed.",
                        "resource_category": "networking",
                    }
                ],
                "findings": [
                    {
                        "finding_id": "finding-duplicate",
                        "severity": "critical",
                        "confidence": 0.95,
                        "title": "CRITICAL: duplicate stale evidence ref",
                        "description": "Primary finding evidence refs are stale.",
                        "evidence_refs": ["ev-stale"],
                    },
                    {
                        "finding_id": "finding-duplicate",
                        "severity": "low",
                        "confidence": 0.1,
                        "title": "LOW: duplicate id safe evidence",
                        "description": "Duplicate finding has safe evidence.",
                        "evidence_refs": ["ev-owned"],
                    },
                ],
                "evidence_items": [
                    {
                        "evidence_id": "ev-owned",
                        "finding_id": "finding-duplicate",
                        "source_type": "artifact",
                        "source_ref": "terraform://duplicate-plan.json#L6",
                        "summary": "Duplicate fallback summary.",
                        "severity_hint": "low",
                        "deterministic": True,
                        "confidence": 0.9,
                        "redaction_status": "none",
                    },
                ],
                "rollback_plan": {"steps": []},
            }
        )

        exact_resource = dict(items)["Exact resource/file"]
        self.assertNotIn("Evidence reference:", exact_resource)
        self.assertNotIn("duplicate-plan.json", exact_resource)
        self.assertNotIn("line 6", exact_resource)

    def test_operational_narrative_uses_same_finding_evidence_for_malformed_refs(
        self,
    ) -> None:
        items = report_detail_page_module._operational_narrative_items(
            {
                "report_schema_version": "v2",
                "top_risk": "Malformed evidence ref risk",
                "parse_summary": "Parsed malformed evidence refs.",
                "contributors": [
                    {
                        "contribution": 95,
                        "resource_id": "aws_security_group.malformed",
                        "source_file": "malformed.tf",
                        "normalized_action": "modify",
                        "tool": "terraform",
                        "summary": "Security group changed.",
                        "resource_category": "networking",
                    }
                ],
                "findings": [
                    {
                        "finding_id": "finding-malformed",
                        "severity": "critical",
                        "confidence": 0.95,
                        "title": "CRITICAL: malformed evidence ref",
                        "description": "Primary finding evidence refs are malformed.",
                        "evidence_refs": {},
                    },
                    {
                        "finding_id": "finding-safe",
                        "severity": "low",
                        "confidence": 0.1,
                        "title": "LOW: unrelated safe evidence",
                        "description": "Unrelated finding has safe evidence.",
                        "evidence_refs": ["ev-safe"],
                    },
                ],
                "evidence_items": [
                    {
                        "evidence_id": "ev-owned",
                        "finding_id": "finding-malformed",
                        "source_type": "artifact",
                        "source_ref": "terraform://owned-malformed-plan.json#L18",
                        "summary": "Owned fallback summary.",
                        "severity_hint": "critical",
                        "deterministic": True,
                        "confidence": 0.9,
                        "redaction_status": "none",
                    },
                    {
                        "evidence_id": "ev-safe",
                        "finding_id": "finding-safe",
                        "source_type": "artifact",
                        "source_ref": "terraform://safe-plan.json#L9",
                        "summary": "Safe but unrelated summary.",
                        "severity_hint": "low",
                        "deterministic": True,
                        "confidence": 0.9,
                        "redaction_status": "none",
                    },
                ],
                "rollback_plan": {"steps": []},
            }
        )

        exact_resource = dict(items)["Exact resource/file"]
        self.assertIn("owned-malformed-plan.json", exact_resource)
        self.assertIn("line 18", exact_resource)
        self.assertNotIn("safe-plan.json", exact_resource)

    def test_operational_narrative_suppresses_unknown_redaction_summary(
        self,
    ) -> None:
        items = report_detail_page_module._operational_narrative_items(
            {
                "report_schema_version": "v2",
                "top_risk": "Unknown redaction summary risk",
                "parse_summary": "Parsed one future-redaction artifact.",
                "contributors": [
                    {
                        "contribution": 90,
                        "resource_id": "aws_iam_policy.admin",
                        "source_file": "policy.tf",
                        "normalized_action": "modify",
                        "tool": "terraform",
                        "summary": "Policy changed.",
                        "resource_category": "identity",
                    }
                ],
                "findings": [
                    {
                        "finding_id": "finding-unknown-redaction",
                        "severity": "high",
                        "confidence": 0.91,
                        "title": "HIGH: unknown redaction",
                        "description": "Unknown redaction summary risk.",
                        "evidence_refs": "ev-unknown",
                    }
                ],
                "evidence_items": [
                    {
                        "evidence_id": "ev-unknown",
                        "source_type": "artifact",
                        "source_ref": "terraform://unknown-secret.json#TOKEN",
                        "summary": "Unknown redaction summary should not render.",
                        "severity_hint": "high",
                        "deterministic": True,
                        "confidence": 0.9,
                        "redaction_status": "future_status",
                    }
                ],
                "rollback_plan": {"steps": []},
            }
        )

        exact_resource = dict(items)["Exact resource/file"]
        verify_before_deploy = dict(items)["Verify before deploying"]
        self.assertIn("Evidence reference unavailable", exact_resource)
        self.assertNotIn("unknown-secret.json", exact_resource)
        self.assertIn("linked evidence metadata", verify_before_deploy)
        self.assertNotIn("Unknown redaction summary", verify_before_deploy)

    def test_confidence_ledger_builds_grounded_reasoning_sections(self) -> None:
        ledger = build_confidence_ledger(
            {
                "risk_score": 76,
                "severity": "high",
                "recommendation": "caution",
                "confidence": 0.72,
                "top_risk": "Security group exposure risk",
                "warnings": ["Narrative degraded: provider unavailable."],
                "narrative_available": False,
                "contributors": [
                    {
                        "resource_id": "aws_security_group.main",
                        "source_file": "plan.json",
                        "normalized_action": "modify",
                        "resource_category": "networking",
                        "severity": "high",
                        "contribution": 20,
                        "reasoning": "Ingress is exposed to the internet.",
                    }
                ],
                "findings": [
                    {
                        "title": "HIGH: aws_security_group.main",
                        "severity": "high",
                        "confidence": 0.68,
                        "deterministic": True,
                        "uncertainty_note": "Parser coverage is partial.",
                    }
                ],
                "context_completeness": {
                    "context_score": 0.64,
                    "confidence_level": "low",
                    "uncertainty": "Uncertainty: topology context is stale.",
                },
            }
        )

        self.assertEqual(
            ledger["contributors"][0],
            "aws_security_group.main · HIGH · contribution 20 · plan.json",
        )
        self.assertIn(
            "Report confidence is Medium (0.72).", ledger["confidence_factors"]
        )
        self.assertIn(
            "Context confidence is low with score 0.64.",
            ledger["confidence_factors"],
        )
        self.assertTrue(
            any("Severity stays elevated" in item for item in ledger["why_not_lower"])
        )
        self.assertTrue(
            any("not higher" in item.lower() for item in ledger["why_not_higher"])
        )
        self.assertIn(
            "Uncertainty: topology context is stale.", ledger["uncertainty_drivers"]
        )
        self.assertIn("Parser coverage is partial.", ledger["uncertainty_drivers"])

    def test_confidence_ledger_tolerates_legacy_contributor_payloads(
        self,
    ) -> None:
        ledger = build_confidence_ledger(
            {
                "risk_score": 76,
                "severity": "high",
                "confidence": 0.72,
                "contributors": [
                    {
                        "resource_id": "hidden.low",
                        "source_file": "low.json",
                        "severity": "medium",
                        "contribution": "2.5",
                    },
                    {
                        "resource_id": "visible.top",
                        "source_file": "top.json",
                        "severity": "high",
                        "contribution": "20.5",
                    },
                    {
                        "resource_id": "invalid.legacy",
                        "source_file": "legacy.json",
                        "severity": "low",
                        "contribution": "unknown",
                    },
                ],
                "findings": [
                    {
                        "title": "HIGH: visible.top",
                        "severity": "high",
                        "confidence": 0.68,
                        "deterministic": True,
                    }
                ],
                "context_completeness": {
                    "context_score": 0.72,
                    "confidence_level": "medium",
                },
            }
        )

        self.assertEqual(
            ledger["contributors"][0],
            "visible.top · HIGH · contribution 20.5 · top.json",
        )
        self.assertIn(
            "invalid.legacy · LOW · contribution unknown · legacy.json",
            ledger["contributors"],
        )
        self.assertIn("visible.top", ledger["why_not_lower"][0])
        self.assertTrue(
            any(
                "below the CRITICAL threshold of 90" in item
                for item in ledger["why_not_higher"]
            )
        )
        self.assertTrue(any("visible.top" in item for item in ledger["why_not_higher"]))

    def test_confidence_ledger_uses_canonical_thresholds_without_false_below_claims(
        self,
    ) -> None:
        low_ledger = build_confidence_ledger(
            {
                "risk_score": 41,
                "severity": "low",
                "confidence": 0.72,
                "contributors": [],
                "findings": [],
                "context_completeness": {},
            }
        )
        medium_ledger = build_confidence_ledger(
            {
                "risk_score": 70,
                "severity": "medium",
                "confidence": 0.72,
                "contributors": [],
                "findings": [
                    {
                        "title": "MEDIUM: change",
                        "severity": "medium",
                        "confidence": 0.72,
                        "deterministic": True,
                    }
                ],
                "context_completeness": {},
            }
        )

        self.assertTrue(
            any(
                "below the MEDIUM threshold of 42" in item
                for item in low_ledger["why_not_higher"]
            )
        )
        self.assertFalse(
            any(
                "below the HIGH threshold" in item
                for item in medium_ledger["why_not_higher"]
            )
        )
        self.assertTrue(
            any(
                "persisted MEDIUM verdict" in item
                for item in medium_ledger["why_not_higher"]
            )
        )

    def test_confidence_ledger_filters_administrative_warnings_from_uncertainty(
        self,
    ) -> None:
        ledger = build_confidence_ledger(
            {
                "risk_score": 76,
                "severity": "high",
                "confidence": 0.72,
                "warnings": [
                    "Evidence Law reconciled report score to match severity metadata.",
                    "Submission manifest metadata was inferred from available analysis artifacts.",
                    "Context completeness metadata was unavailable because persisted JSON was malformed.",
                ],
                "contributors": [],
                "findings": [],
                "context_completeness": {},
            }
        )

        uncertainty = " ".join(ledger["uncertainty_drivers"])
        self.assertNotIn("Evidence Law reconciled", uncertainty)
        self.assertNotIn("Submission manifest metadata", uncertainty)
        self.assertIn("Context completeness metadata", uncertainty)

    def test_confidence_ledger_marks_evidence_detail_omitted_for_summary_payloads(
        self,
    ) -> None:
        ledger = build_confidence_ledger(
            {
                "risk_score": 76,
                "severity": "high",
                "confidence": 0.72,
                "contributors": [],
                "findings": [
                    {
                        "title": "HIGH: change",
                        "severity": "high",
                        "confidence": 0.72,
                        "deterministic": True,
                        "evidence_refs": ["ev-001"],
                    }
                ],
                "context_completeness": {},
            },
            evidence_detail_available=False,
        )

        factors = " ".join(ledger["confidence_factors"])
        why_not_higher = " ".join(ledger["why_not_higher"])
        self.assertIn("Evidence Law: Detail omitted", factors)
        self.assertNotIn("lacks linked deterministic evidence", factors)
        self.assertNotIn("Evidence Law does not provide support", why_not_higher)

    def test_confidence_ledger_normalizes_malformed_ledger_sections(self) -> None:
        fallback = {
            "contributors": ["fallback contributor"],
            "confidence_factors": ["fallback confidence"],
            "why_not_lower": ["fallback lower"],
            "why_not_higher": ["fallback higher"],
            "uncertainty_drivers": ["fallback uncertainty"],
        }

        ledger = normalize_confidence_ledger_payload(
            {
                "contributors": "single contributor",
                "confidence_factors": [],
                "why_not_higher": "single why-not-higher reason",
            },
            fallback_ledger=fallback,
        )
        html = app_module._shared_report_confidence_ledger_html(
            {"confidence_ledger": {"why_not_higher": "single reason"}}
        )
        fallback_html = app_module._shared_report_confidence_ledger_html(
            {
                "risk_score": 76,
                "severity": "high",
                "confidence": 0.72,
                "contributors": [
                    {
                        "resource_id": "fallback.top",
                        "source_file": "plan.json",
                        "severity": "high",
                        "contribution": 20,
                    }
                ],
                "findings": [],
                "context_completeness": {},
            }
        )

        self.assertEqual(ledger["contributors"], ["single contributor"])
        self.assertEqual(ledger["confidence_factors"], ["fallback confidence"])
        self.assertEqual(ledger["why_not_lower"], ["fallback lower"])
        self.assertEqual(ledger["why_not_higher"], ["single why-not-higher reason"])
        self.assertIn("<li>single reason</li>", html)
        self.assertNotIn("<li>s</li>", html)
        self.assertIn("fallback.top", fallback_html)

    def test_history_row_confidence_does_not_fallback_to_finding_confidence(
        self,
    ) -> None:
        from ui.components.analysis_history_row import _report_confidence

        self.assertIsNone(_report_confidence({"findings": [{"confidence": 1.0}]}))
        self.assertIsNone(
            _report_confidence(
                {"confidence": "invalid", "findings": [{"confidence": 1.0}]}
            )
        )


class HistoryPageRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, "history.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(project_service_module)
        reload(report_service_module)
        reload(feedback_service_module)
        reload(report_detail_page_module)
        reload(history_module)
        reload(app_module)
        database_module.init_db()
        self.client = TestClient(app_module.create_app())

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("APP_BASE_URL", None)
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("DEPLOYWHISPER_PROJECT_KEYS", None)
        self.tempdir.cleanup()

    def _persist_report(
        self,
        *,
        score: int = 90,
        severity: str = "critical",
        recommendation: str = "no-go",
        top_risk: str = "Security group exposure risk",
        opening_sentence: str = "Ingress widens access to production resources.",
        finding_description: str = "Security group exposure risk",
        context_completeness: dict | None = None,
        assessment_confidence: float = 1.0,
        finding_confidence: float = 1.0,
        project_id: int | None = None,
        workspace_id: int | None = None,
        tool: str = "terraform",
        incident_matches: list[IncidentMatch] | None = None,
        include_finding: bool = True,
    ) -> dict:
        source_file = "plan.json" if tool == "terraform" else f"{tool}-review.yaml"
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name=source_file,
                    tool=tool,
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file=source_file,
                            tool=tool,
                            resource_id="aws_security_group.main",
                            action="modify",
                            summary="Security group exposure risk",
                            metadata={
                                "module_address": "module.network",
                                "redacted_fields": ["ingress.0.description"],
                                "plan_unsupported_fields": ["plan.planned_values"],
                            },
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=score,
            severity=severity,
            recommendation=recommendation,
            top_risk=top_risk,
            context_completeness=context_completeness or {},
            confidence=assessment_confidence,
            contributors=[
                RiskContributor(
                    evidence_id="ev-001",
                    source_file=source_file,
                    tool=tool,
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=20,
                    summary="Security group exposure risk",
                    metadata={
                        "module_address": "module.network",
                        "redacted_fields": ["ingress.0.description"],
                        "plan_unsupported_fields": ["plan.planned_values"],
                    },
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
            source="heuristic+llm",
        )
        narrative = NarrativeResult(
            opening_sentence=opening_sentence,
            explanation="Review the security group change before deployment.",
            guidance=[],
            degraded=False,
            warnings=[],
            source="llm",
            provider="ollama",
            model="ollama/llama3",
            local_mode=True,
            skills_applied=["git", "terraform"],
        )
        findings = (
            [
                Finding(
                    finding_id="finding-001",
                    analysis_id=0,
                    title=f"{severity.upper()}: aws_security_group.main",
                    description=finding_description,
                    severity=severity,
                    category="networking/ingress",
                    deterministic=True,
                    confidence=finding_confidence,
                    uncertainty_note=None,
                    evidence_refs=["ev-001"],
                    skill_id=None,
                )
            ]
            if include_finding
            else []
        )
        evidence_items = (
            [
                EvidenceItem(
                    evidence_id="ev-001",
                    analysis_id=0,
                    finding_id="pending:change-1",
                    source_type="artifact",
                    source_ref=(
                        "terraform://plan.json#aws_security_group.main?action=modify"
                    ),
                    summary="Terraform changed a security group.",
                    severity_hint=severity,
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ]
            if include_finding
            else []
        )
        return report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            rollback_plan=RollbackPlan(
                steps=[
                    RollbackStep(
                        order=1,
                        title="Revert aws_security_group.main",
                        detail="Rollback the terraform change safely.",
                        estimated_minutes=15,
                        critical=True,
                    )
                ],
                complexity="medium",
                complexity_score=3,
                complexity_explanation=(
                    "Score 3/5 because the plan covers 1 rollback step."
                ),
                warning=None,
            ),
            findings=findings,
            evidence_items=evidence_items,
            audit_context={"source_interface": "ui"},
            project_id=project_id,
            workspace_id=workspace_id,
            incident_matches=incident_matches,
        )

    def test_history_page_exposes_filters_and_row_metadata(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        prod = project_service_module.create_workspace(
            project_key=project.project_key,
            workspace_key="prod",
            display_name="Production",
            environment="prod",
        )
        self._persist_report(
            score=91,
            severity="critical",
            recommendation="no-go",
            top_risk="Payments production ingress widened.",
            opening_sentence="NO-GO: payments production ingress widened.",
            project_id=project.id,
            workspace_id=prod.id,
            tool="terraform",
        )
        legacy_report = self._persist_report(
            score=63,
            severity="high",
            recommendation="caution",
            top_risk="Legacy Ansible release metadata changed.",
            opening_sentence="CAUTION: legacy Ansible release metadata changed.",
            project_id=project.id,
            workspace_id=prod.id,
            tool="ansible",
        )
        with database_module.SessionLocal() as session:
            report = session.get(
                tables_module.AnalysisReport,
                legacy_report["id"],
            )
            report.report_schema_version = "v999"
            session.commit()
        project_service_module.set_active_project(project.id)

        response = self.client.get("/history")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Search top risk or summary", response.text)
        self.assertIn("Project filter", response.text)
        self.assertIn("Workspace", response.text)
        self.assertIn("Time range", response.text)
        self.assertIn("Risk verdict", response.text)
        self.assertIn("Toolchain", response.text)
        self.assertIn("Analysis status", response.text)
        self.assertIn("Payments", response.text)
        self.assertIn("Production", response.text)
        self.assertIn("Tools: terraform", response.text)
        self.assertIn("Schema: v2", response.text)
        self.assertIn("Status: complete", response.text)
        self.assertNotIn("Ansible", response.text)

    def test_history_page_scopes_unselected_project_to_authorized_project(
        self,
    ) -> None:
        payments = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        platform = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        self._persist_report(
            top_risk="Payments production ingress widened.",
            opening_sentence="NO-GO: payments production ingress widened.",
            project_id=payments.id,
        )
        self._persist_report(
            top_risk="Platform production ingress widened.",
            opening_sentence="NO-GO: platform production ingress widened.",
            project_id=platform.id,
            tool="kubernetes",
        )
        project_service_module.clear_active_project_selection()
        os.environ["DEPLOYWHISPER_PROJECT_KEYS"] = "payments"
        try:
            response = self.client.get("/history")
        finally:
            os.environ.pop("DEPLOYWHISPER_PROJECT_KEYS", None)

        self.assertEqual(response.status_code, 200)
        self.assertIn("NO-GO: payments production ingress widened.", response.text)
        self.assertNotIn("NO-GO: platform production ingress widened.", response.text)

    def test_public_report_route_shows_compare_button_and_diff_view(self) -> None:
        self._persist_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Initial security group review",
            opening_sentence="Initial review of the security group change.",
            finding_description="Security group exposure risk",
            context_completeness={
                "topology_freshness_days": 12,
                "topology_last_imported_at": "2026-04-18T11:22:33Z",
                "incident_index_size": 7,
                "parser_success_rate": 1.0,
                "parser_success_by_tool": {"terraform": 1.0},
                "context_score": 0.92,
            },
        )
        self._persist_report(
            score=88,
            severity="critical",
            recommendation="no-go",
            top_risk="Security group exposure risk",
            opening_sentence="Ingress widens access to production resources.",
            finding_description="Security group exposure risk",
            context_completeness={
                "topology_freshness_days": 95,
                "topology_last_imported_at": "2026-01-18T11:22:33Z",
                "incident_index_size": 7,
                "parser_success_rate": 1.0,
                "parser_success_by_tool": {"terraform": 1.0},
                "context_score": 0.82,
            },
        )

        overview_response = self.client.get("/reports/2")
        self.assertEqual(overview_response.status_code, 200)
        self.assertIn("Compare with previous", overview_response.text)

        compare_response = self.client.get("/reports/2?compare=previous")

        self.assertEqual(compare_response.status_code, 200)
        self.assertIn("Comparison with report #1", compare_response.text)
        self.assertIn(
            "previous comparable report in the same project, workspace, and workflow context",
            compare_response.text,
        )
        self.assertIn("Risk score delta", compare_response.text)
        self.assertIn("+48", compare_response.text)
        self.assertIn("MEDIUM → CRITICAL", compare_response.text)
        self.assertIn("Resolved findings", compare_response.text)
        self.assertIn("Evidence resolved", compare_response.text)
        self.assertIn("New findings", compare_response.text)
        self.assertIn("Persistent findings", compare_response.text)
        self.assertIn("Changed context", compare_response.text)
        self.assertIn("Topology freshness", compare_response.text)
        self.assertIn("12 days old", compare_response.text)
        self.assertIn("95 days old", compare_response.text)
        self.assertIn("CURRENT", compare_response.text)
        self.assertIn("CRITICAL 90+", compare_response.text)

    def test_public_report_route_renders_incident_matches(self) -> None:
        report = self._persist_report(
            incident_matches=[
                IncidentMatch(
                    incident_id=0,
                    match_type="public_risk_pattern",
                    public_pattern_id="public-ingress-wide-open",
                    title="Wide-open administrative ingress",
                    severity="high",
                    source_file="plan.json",
                    incident_date=None,
                    similarity=0.86,
                    confidence=0.86,
                    reason="The change exposes administrative ingress publicly.",
                    evidence=[
                        "plan.json: aws_security_group.main (modify) - public SSH"
                    ],
                    verification_guidance=["Confirm public CIDR is intentional."],
                    summary=(
                        "Public risk pattern match: wide-open administrative ingress."
                    ),
                )
            ],
        )

        response = self.client.get(f"/reports/{report['id']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Incident and risk pattern similarity", response.text)
        self.assertIn("Public risk pattern", response.text)
        self.assertIn("86% confidence", response.text)
        self.assertIn("Evidence:", response.text)
        self.assertIn("Confirm public CIDR is intentional.", response.text)

    def test_history_detail_route_shows_compare_button_and_diff_view(self) -> None:
        self._persist_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Initial security group review",
            opening_sentence="Initial review of the security group change.",
            finding_description="Security group exposure risk",
            context_completeness={
                "topology_freshness_days": 12,
                "topology_last_imported_at": "2026-04-18T11:22:33Z",
                "incident_index_size": 7,
                "parser_success_rate": 1.0,
                "parser_success_by_tool": {"terraform": 1.0},
                "context_score": 0.92,
            },
        )
        self._persist_report(
            score=88,
            severity="critical",
            recommendation="no-go",
            top_risk="Security group exposure risk",
            opening_sentence="Ingress widens access to production resources.",
            finding_description="Security group exposure risk",
            context_completeness={
                "topology_freshness_days": 95,
                "topology_last_imported_at": "2026-01-18T11:22:33Z",
                "incident_index_size": 7,
                "parser_success_rate": 1.0,
                "parser_success_by_tool": {"terraform": 1.0},
                "context_score": 0.82,
            },
        )

        overview_response = self.client.get("/history/2")
        self.assertEqual(overview_response.status_code, 200)
        self.assertIn("Compare with previous", overview_response.text)

        compare_response = self.client.get("/history/2/compare")

        self.assertEqual(compare_response.status_code, 200)
        self.assertIn("Comparison with report #1", compare_response.text)
        self.assertIn(
            "previous comparable report in the same project, workspace, and workflow context",
            compare_response.text,
        )
        self.assertIn("Risk score delta", compare_response.text)
        self.assertIn("+48", compare_response.text)
        self.assertIn("MEDIUM → CRITICAL", compare_response.text)
        self.assertIn("Resolved findings", compare_response.text)
        self.assertIn("Evidence resolved", compare_response.text)
        self.assertIn("New findings", compare_response.text)
        self.assertIn("Persistent findings", compare_response.text)
        self.assertIn("Changed context", compare_response.text)
        self.assertIn("Topology freshness", compare_response.text)
        self.assertIn("12 days old", compare_response.text)
        self.assertIn("95 days old", compare_response.text)
        self.assertIn("CURRENT", compare_response.text)
        self.assertIn("CRITICAL 90+", compare_response.text)
        self.assertIn("/settings#topology-context", compare_response.text)

    def test_history_detail_route_shows_operational_narrative(self) -> None:
        self._persist_report()

        response = self.client.get("/history/1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Operational narrative", response.text)
        self.assertIn("What changed?", response.text)

    def test_history_detail_route_shows_reviewer_feedback_controls(self) -> None:
        self._persist_report()

        response = self.client.get("/history/1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Reviewer feedback", response.text)
        self.assertIn("Thumbs up", response.text)
        self.assertIn("Mark noisy", response.text)
        self.assertIn("False positive reason", response.text)
        self.assertIn("Missed finding note", response.text)
        self.assertIn("Why is it risky?", response.text)
        self.assertIn("Exact resource/file", response.text)
        self.assertIn("Verify before deploying", response.text)
        self.assertIn("Rollback concern", response.text)
        self.assertIn("aws_security_group.main", response.text)
        self.assertIn("plan.json", response.text)
        self.assertIn(
            "Review the security group change before deployment.", response.text
        )

    def test_history_detail_route_labels_false_positive_without_noisy_status(
        self,
    ) -> None:
        report = self._persist_report()
        feedback_service_module.record_finding_feedback(
            analysis_id=report["id"],
            finding_id=report["findings"][0]["finding_id"],
            useful=False,
            false_positive_flag=True,
            false_positive_reason="Compensating control already approved.",
        )

        response = self.client.get(f"/history/{report['id']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Latest vote: false positive", response.text)
        self.assertNotIn("Latest vote: noisy", response.text)

    def test_history_detail_route_shows_finding_scoped_missed_note(self) -> None:
        report = self._persist_report()
        feedback_service_module.record_false_negative_feedback(
            analysis_id=report["id"],
            finding_id=report["findings"][0]["finding_id"],
            note="Missed rollback alarm dependency.",
        )

        response = self.client.get(f"/history/{report['id']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Latest note: Missed rollback alarm dependency.", response.text)

    def test_history_detail_route_shows_legacy_report_level_missed_note(self) -> None:
        report = self._persist_report()
        with database_module.SessionLocal() as session:
            session.add(
                tables_module.FeedbackEvent(
                    project_id=report["project"]["id"],
                    workspace_id=(
                        report["workspace"]["id"]
                        if report.get("workspace") is not None
                        else None
                    ),
                    analysis_id=report["id"],
                    false_negative_note="Legacy report-level missed rollback dependency.",
                    outcome_label="missed",
                )
            )
            session.commit()

        response = self.client.get(f"/history/{report['id']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Report-level missed finding notes", response.text)
        self.assertIn(
            "Legacy note: Legacy report-level missed rollback dependency.",
            response.text,
        )

    def test_history_detail_route_shows_report_level_missed_note_for_clean_report(
        self,
    ) -> None:
        report = self._persist_report(
            severity="low",
            recommendation="go",
            top_risk="No findings detected.",
            opening_sentence="GO: no findings detected.",
            include_finding=False,
        )
        feedback_service_module.record_false_negative_feedback(
            analysis_id=report["id"],
            note="Missed cross-service rollback dependency.",
        )

        response = self.client.get(f"/history/{report['id']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Report-level missed finding note", response.text)
        self.assertIn("Missed finding note", response.text)
        self.assertIn(
            "Latest note: Missed cross-service rollback dependency.",
            response.text,
        )
        self.assertIn("Save missed finding note", response.text)

    def test_history_detail_route_hides_report_from_other_active_project(self) -> None:
        self._persist_report()
        other = project_service_module.create_project(
            project_key="other",
            display_name="Other",
        )
        project_service_module.set_active_project(other.id)

        response = self.client.get("/history/1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Analysis report not found", response.text)

    def test_history_active_project_ignores_stale_saved_selection(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        project_service_module.set_active_project(project.id)
        with database_module.engine.begin() as connection:
            connection.exec_driver_sql(
                "DELETE FROM projects WHERE id = ?",
                (project.id,),
            )

        active = history_module.resolve_history_active_project()

        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active.project_key, project_service_module.DEFAULT_PROJECT_KEY)

    def test_public_report_route_blocks_compare_view_when_previous_report_is_protected(
        self,
    ) -> None:
        self._persist_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Initial security group review",
            opening_sentence="Initial review of the security group change.",
            finding_description="Security group exposure risk",
        )
        report_service_module.configure_report_share(
            1,
            password="previous-only",
            redact_filenames=False,
        )
        self._persist_report(
            score=88,
            severity="critical",
            recommendation="no-go",
            top_risk="Security group exposure risk",
            opening_sentence="Ingress widens access to production resources.",
            finding_description="Security group exposure risk",
        )

        overview_response = self.client.get("/reports/2")
        self.assertEqual(overview_response.status_code, 200)
        self.assertIn("Compare with previous", overview_response.text)

        compare_response = self.client.get("/reports/2?compare=previous")

        self.assertEqual(compare_response.status_code, 200)
        self.assertIn(
            "The previous shared report requires a password before comparison.",
            compare_response.text,
        )
        self.assertNotIn("Comparison with report #1", compare_response.text)

        unlocked_response = self.client.post(
            "/reports/1/unlock",
            data={
                "password": "previous-only",
                "next": "/reports/2?compare=previous#report-comparison",
            },
            follow_redirects=True,
        )

        self.assertEqual(unlocked_response.status_code, 200)
        self.assertIn("Comparison with report #1", unlocked_response.text)

    def test_public_report_compare_allows_same_password_protected_reruns(
        self,
    ) -> None:
        self._persist_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Initial security group review",
            opening_sentence="Initial review of the security group change.",
            finding_description="Security group exposure risk",
        )
        report_service_module.configure_report_share(
            1,
            password="shared-secret",
            redact_filenames=False,
        )
        self._persist_report(
            score=88,
            severity="critical",
            recommendation="no-go",
            top_risk="Security group exposure risk",
            opening_sentence="Ingress widens access to production resources.",
            finding_description="Security group exposure risk",
        )
        report_service_module.configure_report_share(
            2,
            password="shared-secret",
            redact_filenames=False,
        )

        current_unlock = self.client.post(
            "/reports/2/unlock",
            data={
                "password": "shared-secret",
                "next": "/reports/2?compare=previous#report-comparison",
            },
            follow_redirects=True,
        )

        self.assertEqual(current_unlock.status_code, 200)
        self.assertIn(
            "The previous shared report requires a password before comparison.",
            current_unlock.text,
        )
        previous_unlock = self.client.post(
            "/reports/1/unlock",
            data={
                "password": "shared-secret",
                "next": "/reports/2?compare=previous#report-comparison",
            },
            follow_redirects=True,
        )

        self.assertEqual(previous_unlock.status_code, 200)
        self.assertIn("Comparison with report #1", previous_unlock.text)
        self.assertIn("Risk score delta", previous_unlock.text)

    def test_history_page_renders_toolbar_and_report_actions(self) -> None:
        self._persist_report(
            context_completeness={
                "topology_freshness_days": 45,
                "topology_last_imported_at": "2026-04-18T11:22:33Z",
                "incident_index_size": 7,
                "parser_success_rate": 1.0,
                "parser_success_by_tool": {"terraform": 1.0},
                "context_score": 0.82,
            }
        )

        response = self.client.get("/history")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Select all on page", response.text)
        self.assertIn("Delete selected", response.text)
        self.assertIn("Security group exposure risk", response.text)
        self.assertIn("NO-GO", response.text)
        self.assertIn("Topology freshness", response.text)
        self.assertIn("45 days old", response.text)
        self.assertIn("STALE 30+", response.text)
        self.assertIn("/settings#topology-context", response.text)
        self.assertIn("MEDIUM CONFIDENCE", response.text)
        self.assertIn('"title":"Confidence 0.82"', response.text)
        self.assertIn("Risk: heuristic+llm", response.text)
        self.assertIn("Narrative: llm", response.text)

    def test_history_page_renders_report_level_confidence(self) -> None:
        self._persist_report(assessment_confidence=0.52, finding_confidence=1.0)

        response = self.client.get("/history")

        self.assertEqual(response.status_code, 200)
        self.assertIn("LOW CONFIDENCE", response.text)
        self.assertIn('"title":"Confidence 0.52"', response.text)
        self.assertNotIn('"title":"Confidence 1.00"', response.text)

    def test_history_page_renders_calibration_snapshot_from_backtest_feed(self) -> None:
        report = self._persist_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Review warned deployment outcome.",
            opening_sentence="Warned deployment later failed.",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=report["id"],
            outcome="failure",
            deployed_at=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
        )

        response = self.client.get("/history")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Calibration snapshot", response.text)
        self.assertIn("1 failed deploys", response.text)
        self.assertIn("1 warned", response.text)
        self.assertIn("Precision 1.00", response.text)
        self.assertIn("Recall 1.00", response.text)

    def test_history_page_shows_diff_indicator_for_rescanned_same_artifact(
        self,
    ) -> None:
        self._persist_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Initial security group review",
            opening_sentence="Initial review of the security group change.",
        )
        self._persist_report(
            score=88,
            severity="critical",
            recommendation="no-go",
            top_risk="Security group exposure risk",
            opening_sentence="Ingress widens access to production resources.",
        )

        response = self.client.get("/history")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Rescan diff", response.text)
        self.assertIn("+48 risk vs report #1", response.text)
        self.assertIn("MEDIUM → CRITICAL", response.text)
        self.assertIn("CAUTION → NO-GO", response.text)

    def test_history_detail_route_renders_dedicated_report_page(self) -> None:
        self._persist_report(
            context_completeness={
                "topology_freshness_days": 45,
                "topology_last_imported_at": "2026-04-18T11:22:33Z",
                "incident_index_size": 0,
                "evidence_success_rate": 0.5,
                "parser_success_rate": 0.5,
                "parser_success_by_tool": {"terraform": 0.5},
                "context_score": 0.52,
                "confidence_level": "low",
                "uncertainty": "Insufficient context: topology and parser coverage are incomplete.",
                "context_todos": [
                    "Refresh stale topology context for this project/workspace.",
                    "Review parser errors and resubmit supported artifacts.",
                ],
                "insufficient_context": True,
            }
        )

        response = self.client.get("/history/1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Back to History", response.text)
        self.assertIn("Analysis report detail", response.text)
        self.assertIn("Rollback plan", response.text)
        self.assertIn("Revert aws_security_group.main", response.text)
        self.assertIn("Findings table", response.text)
        self.assertIn("Context completeness", response.text)
        self.assertIn("Summary context check", response.text)
        self.assertIn("Context follow-ups", response.text)
        self.assertIn("Refresh stale topology context", response.text)
        self.assertLess(
            response.text.index("Summary context check"),
            response.text.index("Findings table"),
        )
        self.assertIn("Blast radius", response.text)
        self.assertIn("Audit metadata", response.text)
        self.assertIn("Module: module.network", response.text)
        self.assertIn("Redacted fields: ingress.0.description", response.text)
        self.assertIn("Unsupported plan fields: plan.planned_values", response.text)
        self.assertNotIn('"data-dw-modal-root":"1"', response.text)

    def test_history_detail_route_renders_report_level_confidence(self) -> None:
        self._persist_report(assessment_confidence=0.52, finding_confidence=1.0)

        response = self.client.get("/history/1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("LOW CONFIDENCE", response.text)
        self.assertIn('"title":"Confidence 0.52"', response.text)

    def test_history_detail_route_renders_verdict_first_header(self) -> None:
        self._persist_report()

        response = self.client.get("/history/1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Verdict", response.text)
        self.assertIn("NO-GO · CRITICAL RISK", response.text)
        self.assertIn("Advisory posture", response.text)
        self.assertIn("Advisory only", response.text)
        self.assertIn("Evidence Law", response.text)
        self.assertIn("Satisfied", response.text)
        self.assertIn("Confidence", response.text)
        self.assertIn("High (1.00)", response.text)
        self.assertIn("Top risk", response.text)
        self.assertIn("Security group exposure risk", response.text)
        self.assertIn("Next action", response.text)
        self.assertIn("Review linked evidence", response.text)

    def test_history_detail_route_renders_confidence_ledger(self) -> None:
        self._persist_report(
            assessment_confidence=0.72,
            finding_confidence=0.68,
            context_completeness={
                "topology_freshness_days": 45,
                "topology_last_imported_at": "2026-04-18T11:22:33Z",
                "incident_index_size": 7,
                "parser_success_rate": 0.8,
                "parser_success_by_tool": {"terraform": 0.8},
                "context_score": 0.64,
                "confidence_level": "low",
                "uncertainty": "Uncertainty: topology context is stale.",
            },
        )

        response = self.client.get("/history/1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Confidence ledger", response.text)
        self.assertIn("Why not lower", response.text)
        self.assertIn("Why not higher", response.text)
        self.assertIn("Uncertainty drivers", response.text)
        self.assertIn("Report confidence is Medium (0.64).", response.text)
        self.assertIn(
            "Context confidence is low with score 0.64.",
            response.text,
        )
        self.assertIn("aws_security_group.main", response.text)
        self.assertIn("Uncertainty: topology context is stale.", response.text)

    def test_history_detail_route_tolerates_legacy_contributor_values(self) -> None:
        report = self._persist_report()
        with database_module.SessionLocal() as session:
            stored = session.get(tables_module.AnalysisReport, report["id"])
            assert stored is not None
            stored.contributors_json = json.dumps(
                [
                    {
                        "resource_id": "legacy.invalid",
                        "source_file": "legacy.json",
                        "severity": "low",
                        "contribution": "unknown",
                    },
                    {
                        "resource_id": "legacy.decimal",
                        "source_file": "top.json",
                        "severity": "high",
                        "contribution": "20.5",
                    },
                ]
            )
            session.commit()

        response = self.client.get("/history/1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("legacy.decimal", response.text)
        self.assertIn("Confidence ledger", response.text)
        self.assertIn("Why not lower", response.text)

    def test_history_detail_route_shows_topology_freshness_badge(self) -> None:
        self._persist_report(
            context_completeness={
                "topology_freshness_days": 45,
                "topology_last_imported_at": "2026-04-18T11:22:33Z",
                "incident_index_size": 7,
                "parser_success_rate": 1.0,
                "parser_success_by_tool": {"terraform": 1.0},
                "context_score": 0.82,
            }
        )

        response = self.client.get("/history/1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Topology freshness", response.text)
        self.assertIn("45 days old", response.text)
        self.assertIn("STALE 30+", response.text)
        self.assertIn("Manage topology", response.text)
        self.assertIn("/settings#topology-context", response.text)

    def test_public_report_route_renders_read_only_share_view(self) -> None:
        self._persist_report()

        response = self.client.get("/reports/1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Shared DeployWhisper report", response.text)
        self.assertIn("Analysis report", response.text)
        self.assertIn("Confidence ledger", response.text)
        self.assertIn("Why not lower", response.text)
        self.assertIn("Why not higher", response.text)
        self.assertIn("aws_security_group.main", response.text)
        self.assertNotIn("Delete selected", response.text)

    def test_public_report_route_shows_topology_freshness_without_internal_settings_link(
        self,
    ) -> None:
        self._persist_report(
            context_completeness={
                "topology_freshness_days": 45,
                "topology_last_imported_at": "2026-04-18T11:22:33Z",
                "incident_index_size": 7,
                "parser_success_rate": 1.0,
                "parser_success_by_tool": {"terraform": 1.0},
                "context_score": 0.82,
            }
        )

        response = self.client.get("/reports/1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Topology freshness", response.text)
        self.assertIn("45 days old", response.text)
        self.assertIn("STALE 30+", response.text)
        self.assertIn(
            "Workspace admins refresh topology from the internal settings page.",
            response.text,
        )
        self.assertNotIn("/settings#topology-context", response.text)

    def test_public_report_route_requires_password_and_redacts_filenames(self) -> None:
        self._persist_report()
        report_service_module.configure_report_share(
            1,
            password="s3cret-pass",
            redact_filenames=True,
        )

        prompt_response = self.client.get("/reports/1")
        self.assertEqual(prompt_response.status_code, 200)
        self.assertIn("Password required", prompt_response.text)
        self.assertIn("method='post'", prompt_response.text)

        shared_response = self.client.post(
            "/reports/1/unlock",
            data={"password": "s3cret-pass"},
            follow_redirects=True,
        )
        self.assertEqual(shared_response.status_code, 200)
        self.assertIn("Artifact 1", shared_response.text)
        self.assertNotIn("plan.json", shared_response.text)
        self.assertNotIn("password=s3cret-pass", shared_response.text)

    def test_public_report_unlock_sets_secure_cookie_for_https_share_urls(self) -> None:
        os.environ["APP_BASE_URL"] = "https://install.example.com"
        self._persist_report()
        report_service_module.configure_report_share(
            1,
            password="s3cret-pass",
            redact_filenames=True,
        )

        response = self.client.post(
            "/reports/1/unlock",
            data={"password": "s3cret-pass"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        cookie_header = response.headers.get("set-cookie", "")
        self.assertIn("Secure", cookie_header)
        self.assertIn("HttpOnly", cookie_header)
        self.assertIn("Path=/reports", cookie_header)

    def test_history_page_keeps_legacy_query_parameter_as_detail_fallback(self) -> None:
        self._persist_report()

        response = self.client.get("/history?report_id=1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Analysis report detail", response.text)
        self.assertIn("Back to History", response.text)


if __name__ == "__main__":
    unittest.main()
