"""Tests for optional policy-adapter output contracts."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from services.adapter_output_contract import (
    AdapterMetadata,
    build_adapter_output_contract,
)
from services.analysis_service import build_share_summary
from services.policy_adapter_output_contract import (
    PolicyAdapterSettings,
    PolicyAdapterOutputContract,
    PolicyAdapterReason,
    PolicyAdapterStatus,
    PolicySeverity,
    build_policy_adapter_output_from_settings,
    build_policy_adapter_output_contract,
)


class PolicyAdapterOutputContractTests(unittest.TestCase):
    def test_configured_thresholds_change_only_adapter_interpretation(self) -> None:
        adapter_output = _adapter_output()
        canonical_before = adapter_output.canonical_summary.model_dump(mode="json")
        settings = PolicyAdapterSettings(
            project_key="payments",
            source="project",
            warn_at=PolicySeverity.HIGH,
            soft_block_at=PolicySeverity.CRITICAL,
            hard_block_at=None,
            reporting_default=PolicyAdapterStatus.ADVISORY,
        )

        output = build_policy_adapter_output_from_settings(adapter_output, settings)

        self.assertEqual(output.status, PolicyAdapterStatus.WARN)
        self.assertEqual(output.applied_settings, settings)
        self.assertEqual(output.reasons[0].code, "severity_threshold_matched")
        self.assertEqual(
            output.adapter_output.canonical_summary.model_dump(mode="json"),
            canonical_before,
        )
        self.assertEqual(output.adapter_output.canonical_summary.severity, "high")
        self.assertEqual(
            len(output.adapter_output.canonical_summary.json_payload.top_findings),
            1,
        )
        self.assertEqual(
            output.adapter_output.canonical_summary.json_payload.top_findings[
                0
            ].severity,
            "high",
        )

    def test_reporting_default_applies_below_configured_thresholds(self) -> None:
        adapter_output = _adapter_output(severity="low", adapter="jenkins")
        settings = PolicyAdapterSettings(
            project_key="payments",
            integration="jenkins",
            source="integration",
            warn_at=PolicySeverity.HIGH,
            soft_block_at=PolicySeverity.CRITICAL,
            hard_block_at=None,
            reporting_default=PolicyAdapterStatus.WARN,
        )

        output = build_policy_adapter_output_from_settings(adapter_output, settings)

        self.assertEqual(output.status, PolicyAdapterStatus.WARN)
        self.assertEqual(output.reasons[0].code, "reporting_default_applied")
        self.assertEqual(output.applied_settings.integration, "jenkins")
        self.assertEqual(output.adapter_output.canonical_summary.severity, "low")

    def test_threshold_settings_reject_ambiguous_or_non_monotonic_values(self) -> None:
        invalid_settings = (
            {
                "project_key": "payments",
                "source": "project",
                "warn_at": "critical",
                "soft_block_at": "high",
            },
            {
                "project_key": "payments",
                "source": "project",
                "reporting_default": "soft-block",
            },
            {
                "project_key": "payments",
                "source": "project",
                "integration": "   ",
            },
        )

        for values in invalid_settings:
            with self.subTest(values=values):
                with self.assertRaises(ValidationError):
                    PolicyAdapterSettings(**values)

    def test_settings_cannot_be_applied_across_project_or_integration_scope(
        self,
    ) -> None:
        project_mismatch = PolicyAdapterSettings(
            project_key="identity",
            source="project",
        )
        integration_mismatch = PolicyAdapterSettings(
            project_key="payments",
            integration="gitlab",
            source="integration",
        )

        for settings in (project_mismatch, integration_mismatch):
            with self.subTest(settings=settings):
                with self.assertRaises(ValueError):
                    build_policy_adapter_output_from_settings(
                        _adapter_output(), settings
                    )

        id_scoped_adapter = build_adapter_output_contract(
            build_share_summary(_report_payload()),
            AdapterMetadata(
                adapter="policy",
                format="workflow_decision",
                project_id=42,
            ),
        )
        with self.assertRaises(ValueError):
            build_policy_adapter_output_from_settings(
                id_scoped_adapter,
                PolicyAdapterSettings(project_key="payments", source="project"),
            )

    def test_project_scope_comparison_uses_canonical_project_keys(self) -> None:
        adapter_output = build_adapter_output_contract(
            build_share_summary(_report_payload()),
            AdapterMetadata(
                adapter="policy",
                format="workflow_decision",
                project_key="Payments_Core",
            ),
        )
        settings = PolicyAdapterSettings(
            project_key="payments-core",
            source="project",
        )

        output = build_policy_adapter_output_from_settings(
            adapter_output,
            settings,
            resolved_project_key="payments-core",
        )

        self.assertEqual(output.applied_settings.project_key, "payments-core")
        self.assertEqual(
            output.adapter_output.adapter_metadata.project_key,
            "Payments_Core",
        )

    def test_all_policy_statuses_preserve_the_advisory_canonical_report(self) -> None:
        summary = build_share_summary(_report_payload())
        summary_before = summary.model_dump(mode="json")
        adapter_output = build_adapter_output_contract(
            summary,
            AdapterMetadata(
                adapter="policy",
                format="workflow_decision",
                project_key="payments",
            ),
        )

        for status in PolicyAdapterStatus:
            with self.subTest(status=status):
                output = build_policy_adapter_output_contract(
                    adapter_output,
                    status=status,
                    reasons=(
                        PolicyAdapterReason(
                            code="review_required",
                            message="A human must review the deterministic evidence.",
                        ),
                    ),
                )

                self.assertEqual(output.status, status)
                self.assertEqual(output.reasons[0].code, "review_required")
                self.assertTrue(output.canonical_report_advisory)
                self.assertTrue(output.adapter_output.canonical_summary.advisory_only)
                self.assertFalse(output.adapter_output.canonical_summary.should_block)
                self.assertEqual(summary.model_dump(mode="json"), summary_before)
                self.assertEqual(
                    output.adapter_output.canonical_summary.model_dump(mode="json"),
                    summary_before,
                )

                scanner_conflicts = output.adapter_output.canonical_summary.json_payload.scanner_conflicts
                self.assertIsInstance(scanner_conflicts, tuple)
                self.assertEqual(len(scanner_conflicts), 1)
                with self.assertRaises(AttributeError):
                    scanner_conflicts.append("mutated")
                with self.assertRaises(ValidationError):
                    scanner_conflicts[0].finding_id = "mutated"

    def test_policy_output_rejects_invalid_reason_text(self) -> None:
        adapter_output = _adapter_output()

        with self.assertRaises(ValidationError):
            build_policy_adapter_output_contract(
                adapter_output,
                status=PolicyAdapterStatus.WARN,
                reasons=(),
            )

        for reason in (
            {"code": "", "message": "Review required."},
            {"code": "review_required", "message": "   "},
            {"code": "\u200b", "message": "Review required."},
            {"code": "review_required", "message": "\u200b"},
            {"code": "review_required", "message": "Invalid surrogate: \ud800"},
            {"code": "policy\x1b[31m", "message": "Review required."},
            {"code": "review_required", "message": "Hidden NUL: \x00"},
            {"code": "review_required", "message": "Unexpected\nline break"},
        ):
            with self.subTest(reason=reason):
                with self.assertRaises(ValidationError):
                    build_policy_adapter_output_contract(
                        adapter_output,
                        status=PolicyAdapterStatus.WARN,
                        reasons=(reason,),
                    )

    def test_policy_output_rejects_non_advisory_canonical_summary(self) -> None:
        for advisory_only, should_block in ((False, False), (True, True)):
            with self.subTest(
                advisory_only=advisory_only,
                should_block=should_block,
            ):
                summary = build_share_summary(_report_payload()).model_copy(
                    update={
                        "advisory_only": advisory_only,
                        "should_block": should_block,
                    }
                )
                adapter_output = build_adapter_output_contract(
                    summary,
                    AdapterMetadata(
                        adapter="policy",
                        format="workflow_decision",
                        project_key="payments",
                    ),
                )

                with self.assertRaises(ValidationError):
                    build_policy_adapter_output_contract(
                        adapter_output,
                        status=PolicyAdapterStatus.HARD_BLOCK,
                        reasons=(
                            PolicyAdapterReason(
                                code="policy_match",
                                message="Configured deterministic policy matched.",
                            ),
                        ),
                    )

    def test_policy_output_rejects_ambiguous_coerced_inputs(self) -> None:
        adapter_output = _adapter_output()
        reason = PolicyAdapterReason(code="policy_match", message="Policy matched.")

        invalid_inputs = (
            {"status": b"warn", "reasons": (reason,)},
            {"status": PolicyAdapterStatus.WARN, "reasons": {reason}},
            {
                "status": PolicyAdapterStatus.WARN,
                "reasons": (reason,),
                "canonical_report_advisory": 1,
            },
        )
        for invalid_input in invalid_inputs:
            with self.subTest(invalid_input=invalid_input):
                with self.assertRaises(ValidationError):
                    PolicyAdapterOutputContract(
                        adapter_output=adapter_output,
                        **invalid_input,
                    )

    def test_policy_output_contract_is_strict_versioned_and_immutable(self) -> None:
        output = build_policy_adapter_output_contract(
            _adapter_output(),
            status="soft-block",
            reasons=(
                {
                    "code": "override_required",
                    "message": "An authorized override is required.",
                },
            ),
        )

        self.assertEqual(output.contract_version, "v1")
        self.assertEqual(output.status, PolicyAdapterStatus.SOFT_BLOCK)
        self.assertIn('"status":"soft-block"', output.model_dump_json())
        with self.assertRaises(ValidationError):
            PolicyAdapterOutputContract(
                contract_version="v2",
                status=PolicyAdapterStatus.ADVISORY,
                reasons=output.reasons,
                adapter_output=output.adapter_output,
            )
        with self.assertRaises(ValidationError):
            PolicyAdapterOutputContract(
                status=PolicyAdapterStatus.ADVISORY,
                reasons=output.reasons,
                adapter_output=output.adapter_output,
                unexpected="value",
            )
        with self.assertRaises(ValidationError):
            output.reasons[0].message = "Changed"


def _adapter_output(*, severity: str = "high", adapter: str = "policy"):
    return build_adapter_output_contract(
        build_share_summary(_report_payload(severity=severity)),
        AdapterMetadata(
            adapter=adapter,
            format="workflow_decision",
            project_key="payments",
        ),
    )


def _report_payload(*, severity: str = "high") -> dict:
    return {
        "id": 17,
        "report_schema_version": "v2",
        "severity": severity,
        "recommendation": "caution",
        "top_risk": "Terraform opened database ingress.",
        "narrative_opening": "CAUTION: review database ingress.",
        "narrative_available": True,
        "warnings": [],
        "findings": [
            {
                "finding_id": "finding-001",
                "title": "HIGH: aws_security_group.db",
                "severity": "high",
                "confidence": 0.91,
                "evidence_refs": ["ev-001", "ev-scanner"],
            }
        ],
        "evidence_items": [
            {
                "evidence_id": "ev-001",
                "finding_id": "finding-001",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {"freshness_status": "current"},
            },
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "source_ref": "semgrep://results/sg-1",
                "severity_hint": "critical",
                "deterministic": True,
                "determinism_level": "deterministic",
                "context_source": {
                    "freshness_status": "current",
                    "conflicts": [],
                    "limitations": [],
                },
            },
        ],
        "blast_radius": {
            "affected": [{"label": "Primary Database"}],
            "direct_count": 1,
            "transitive_count": 0,
            "warning": None,
        },
        "rollback_plan": {
            "steps": [{"title": "Revert ingress rule"}],
            "complexity": "low",
            "complexity_score": 1,
            "warning": None,
        },
        "context_completeness": {"context_score": 0.9},
    }
