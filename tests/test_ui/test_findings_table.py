"""Tests for findings table evidence inspector helpers."""

from __future__ import annotations

import unittest

from ui.components.findings_table import (
    describe_evidence_item,
    finding_row_signals,
)


class FindingsTableEvidenceInspectorTests(unittest.TestCase):
    def test_describe_evidence_item_builds_uploaded_artifact_link(self) -> None:
        descriptor = describe_evidence_item(
            {
                "source_type": "artifact",
                "source_ref": "terraform://deployments/prod/plan.json#L42?action=modify",
                "summary": "Terraform changed the production security group.",
                "severity_hint": "high",
                "deterministic": True,
                "redaction_status": "none",
                "confidence": 1.0,
            },
            artifact_names={"deployments/prod/plan.json"},
            report_id=17,
        )

        self.assertEqual(descriptor["source_icon"], "description")
        self.assertEqual(descriptor["source_label"], "Artifact")
        self.assertEqual(
            descriptor["display_source_ref"],
            "deployments/prod/plan.json · line 42",
        )
        self.assertEqual(
            descriptor["artifact_href"],
            "/history/17/artifacts?name=deployments%2Fprod%2Fplan.json&line=42#L42",
        )
        self.assertIsNone(descriptor["source_system"])

    def test_describe_evidence_item_matches_uploaded_artifact_by_basename(self) -> None:
        descriptor = describe_evidence_item(
            {
                "source_type": "artifact",
                "source_ref": "terraform://deployments/prod/plan.json#L7",
                "summary": "Terraform changed the production security group.",
                "severity_hint": "high",
                "deterministic": True,
                "redaction_status": "none",
                "confidence": 1.0,
            },
            artifact_names={"plan.json"},
            report_id=9,
        )

        self.assertEqual(
            descriptor["artifact_href"],
            "/history/9/artifacts?name=plan.json&line=7#L7",
        )

    def test_describe_evidence_item_preserves_current_artifact_reference_format(
        self,
    ) -> None:
        descriptor = describe_evidence_item(
            {
                "source_type": "artifact",
                "source_ref": "terraform://plan.json#aws_security_group.main?action=modify",
                "summary": "Terraform changed the production security group.",
                "severity_hint": "high",
                "deterministic": True,
                "redaction_status": "none",
                "confidence": 1.0,
            }
        )

        self.assertEqual(
            descriptor["display_source_ref"],
            "plan.json · aws_security_group.main",
        )
        self.assertIsNone(descriptor["artifact_href"])

    def test_describe_evidence_item_extracts_source_system_badges(self) -> None:
        topology_descriptor = describe_evidence_item(
            {
                "source_type": "topology",
                "source_ref": "topology://payments/api-gateway#line=18",
                "summary": "Topology maps the gateway to the payments service.",
                "severity_hint": "medium",
                "deterministic": True,
                "redaction_status": "none",
                "confidence": 0.9,
            }
        )
        incident_descriptor = describe_evidence_item(
            {
                "source_type": "incident",
                "source_ref": "incident://checkout/inc-442#database failover",
                "summary": "Past incident touched the checkout database failover path.",
                "severity_hint": "high",
                "deterministic": False,
                "redaction_status": "none",
                "confidence": 0.72,
            }
        )

        self.assertEqual(topology_descriptor["source_icon"], "hub")
        self.assertEqual(topology_descriptor["source_system"], "payments")
        self.assertEqual(incident_descriptor["source_icon"], "history")
        self.assertEqual(incident_descriptor["source_system"], "checkout")

    def test_describe_evidence_item_includes_inspector_metadata_and_redaction(
        self,
    ) -> None:
        descriptor = describe_evidence_item(
            {
                "source_type": "artifact",
                "source_ref": "terraform://deployments/prod/plan.json#aws_security_group.main?action=modify",
                "artifact": "deployments/prod/plan.json",
                "location": "deployments/prod/plan.json#aws_security_group.main",
                "resource": "aws_security_group.main",
                "operation": "modify",
                "project_id": 12,
                "project_key": "payments",
                "workspace_id": 34,
                "workspace_key": "prod",
                "source_kind": "artifact",
                "determinism_level": "deterministic",
                "redaction_status": "redacted",
                "summary": "Terraform changed the production security group.",
                "severity_hint": "high",
                "deterministic": True,
                "confidence": 1.0,
            },
            artifact_names={"deployments/prod/plan.json"},
            report_id=17,
        )

        self.assertEqual(descriptor["artifact_label"], "deployments/prod/plan.json")
        self.assertEqual(descriptor["resource_label"], "aws_security_group.main")
        self.assertEqual(descriptor["operation_label"], "modify")
        self.assertEqual(descriptor["context_source_label"], "Artifact")
        self.assertEqual(descriptor["project_scope_label"], "Project payments (#12)")
        self.assertEqual(descriptor["workspace_scope_label"], "Workspace prod (#34)")
        self.assertEqual(descriptor["determinism_label"], "deterministic")
        self.assertEqual(descriptor["redaction_label"], "Redacted")
        self.assertIn("metadata remains available", descriptor["redaction_explanation"])

    def test_describe_evidence_item_labels_unknown_redaction_as_uncertain(
        self,
    ) -> None:
        descriptor = describe_evidence_item(
            {
                "source_type": "artifact",
                "source_ref": "terraform://plan.json#aws_iam_policy.admin",
                "redaction_status": "new_upstream_status",
                "summary": "Sensitive summary should be guarded by the renderer.",
                "severity_hint": "high",
                "deterministic": True,
                "confidence": 1.0,
            }
        )

        self.assertEqual(descriptor["redaction_status"], "unknown")
        self.assertEqual(descriptor["redaction_label"], "Unknown")
        self.assertEqual(
            descriptor["display_source_ref"], "Evidence reference unavailable"
        )
        self.assertEqual(descriptor["reference_label"], "Proof reference")
        self.assertEqual(descriptor["artifact_label"], "evidence metadata unavailable")
        self.assertEqual(descriptor["resource_label"], "resource withheld")
        self.assertEqual(descriptor["operation_label"], "operation withheld")
        self.assertEqual(descriptor["context_source_label"], "unavailable")
        self.assertEqual(descriptor["project_scope_label"], "Project withheld")
        self.assertEqual(descriptor["workspace_scope_label"], "Workspace withheld")
        self.assertIn(
            "content availability is unknown", descriptor["redaction_explanation"]
        )

    def test_describe_evidence_item_fails_closed_for_missing_redaction_status(
        self,
    ) -> None:
        descriptor = describe_evidence_item(
            {
                "source_type": "artifact",
                "source_ref": "terraform://plan.json#L9",
                "summary": "Legacy evidence summary should not be treated as safe.",
                "severity_hint": "high",
                "deterministic": True,
                "confidence": 1.0,
            },
            artifact_names={"plan.json"},
            report_id=17,
        )

        self.assertEqual(descriptor["redaction_status"], "unknown")
        self.assertEqual(descriptor["redaction_label"], "Unknown")
        self.assertIsNone(descriptor["artifact_href"])

    def test_describe_evidence_item_preserves_legacy_missing_redaction_status(
        self,
    ) -> None:
        descriptor = describe_evidence_item(
            {
                "source_type": "artifact",
                "source_ref": "terraform://plan.json#L9",
                "summary": "Legacy evidence summary remains readable.",
                "severity_hint": "high",
                "deterministic": True,
                "confidence": 1.0,
            },
            artifact_names={"plan.json"},
            report_id=17,
            legacy_missing_redaction_is_none=True,
        )

        self.assertEqual(descriptor["redaction_status"], "none")
        self.assertEqual(descriptor["redaction_label"], "None")
        self.assertEqual(
            descriptor["artifact_href"],
            "/history/17/artifacts?name=plan.json&line=9#L9",
        )

    def test_describe_evidence_item_fails_closed_for_blank_redaction_status(
        self,
    ) -> None:
        descriptor = describe_evidence_item(
            {
                "source_type": "artifact",
                "source_ref": "terraform://plan.json#L9",
                "redaction_status": " ",
                "summary": "Blank status evidence summary should not be safe.",
                "severity_hint": "high",
                "deterministic": True,
                "confidence": 1.0,
            },
            artifact_names={"plan.json"},
            report_id=17,
        )

        self.assertEqual(descriptor["redaction_status"], "unknown")
        self.assertIsNone(descriptor["artifact_href"])

    def test_describe_evidence_item_suppresses_sensitive_blocked_metadata(
        self,
    ) -> None:
        descriptor = describe_evidence_item(
            {
                "source_type": "artifact",
                "source_ref": "terraform://secrets.env#aws_iam_policy.admin?action=inspect",
                "artifact": "secrets.env",
                "resource": "aws_iam_policy.admin",
                "operation": "inspect",
                "redaction_status": "sensitive_blocked",
                "summary": "Sensitive summary should not render.",
                "severity_hint": "high",
                "deterministic": True,
                "confidence": 1.0,
            },
            artifact_names={"secrets.env"},
            report_id=17,
        )

        self.assertEqual(
            descriptor["display_source_ref"], "Sensitive evidence reference blocked"
        )
        self.assertEqual(descriptor["reference_label"], "Proof reference")
        self.assertEqual(descriptor["artifact_label"], "sensitive evidence blocked")
        self.assertEqual(descriptor["resource_label"], "resource withheld")
        self.assertEqual(descriptor["operation_label"], "operation withheld")
        self.assertIsNone(descriptor["source_system"])
        self.assertIsNone(descriptor["artifact_href"])

    def test_finding_row_signals_include_category_evidence_badges_and_law_status(
        self,
    ) -> None:
        signals = finding_row_signals(
            {
                "finding_id": "finding-001",
                "severity": "critical",
                "category": "networking/ingress",
                "deterministic": True,
                "evidence_refs": ["ev-001", "ev-002"],
            },
            [
                {
                    "evidence_id": "ev-001",
                    "source_type": "artifact",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                },
                {
                    "evidence_id": "ev-002",
                    "source_type": "topology",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                },
            ],
        )

        self.assertEqual(signals["category"], "networking/ingress")
        self.assertEqual(signals["evidence_count_label"], "2 evidence items")
        self.assertEqual(signals["evidence_law_label"], "Evidence Law satisfied")

    def test_finding_row_signals_normalize_legacy_evidence_ids(self) -> None:
        signals = finding_row_signals(
            {
                "finding_id": "finding-legacy",
                "severity": "high",
                "category": "identity/access",
                "deterministic": True,
                "evidence_refs": ["0", "42", "ev-padded"],
            },
            [
                {
                    "evidence_id": 0,
                    "source_type": "artifact",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                },
                {
                    "evidence_id": 42,
                    "source_type": "artifact",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                },
                {
                    "evidence_id": " ev-padded ",
                    "source_type": "topology",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                },
            ],
        )

        self.assertEqual(signals["evidence_count"], 3)
        self.assertEqual(signals["evidence_count_label"], "3 evidence items")
        self.assertEqual(signals["evidence_law_label"], "Evidence Law satisfied")
        self.assertIn("Deterministic", signals["evidence_badges"])
        self.assertIn("External", signals["evidence_badges"])

    def test_finding_row_signals_distinguish_user_context_from_external(self) -> None:
        signals = finding_row_signals(
            {
                "finding_id": "finding-user-context",
                "severity": "medium",
                "category": "change/context",
                "deterministic": False,
                "evidence_refs": ["ctx-001"],
            },
            [
                {
                    "evidence_id": "ctx-001",
                    "source_type": "user_context",
                    "deterministic": False,
                    "determinism_level": "heuristic",
                },
            ],
        )

        self.assertIn("User context", signals["evidence_badges"])
        self.assertNotIn("External", signals["evidence_badges"])

    def test_finding_row_signals_count_missing_linked_evidence_refs(self) -> None:
        signals = finding_row_signals(
            {
                "finding_id": "finding-missing",
                "severity": "high",
                "category": "identity/access",
                "deterministic": False,
                "evidence_refs": "ev-missing",
            },
            [],
        )

        self.assertEqual(signals["evidence_count"], 1)
        self.assertEqual(signals["matched_evidence_count"], 0)
        self.assertEqual(signals["missing_evidence_count"], 1)
        self.assertEqual(
            signals["evidence_count_label"], "0 evidence items, 1 unavailable"
        )
        self.assertIn("1 unavailable", signals["evidence_badges"])
        self.assertEqual(signals["evidence_law_label"], "Evidence Law needs evidence")

    def test_finding_row_signals_deduplicate_evidence_refs(self) -> None:
        signals = finding_row_signals(
            {
                "finding_id": "finding-duplicate",
                "severity": "high",
                "category": "identity/access",
                "deterministic": False,
                "evidence_refs": ["ev-001", " ev-001 ", "ev-missing", "ev-missing"],
            },
            [
                {
                    "evidence_id": "ev-001",
                    "source_type": "artifact",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                },
            ],
        )

        self.assertEqual(signals["evidence_count"], 2)
        self.assertEqual(signals["matched_evidence_count"], 1)
        self.assertEqual(signals["missing_evidence_count"], 1)
        self.assertEqual(
            signals["evidence_count_label"], "1 evidence item, 1 unavailable"
        )

    def test_finding_row_signals_parse_json_string_evidence_refs(self) -> None:
        signals = finding_row_signals(
            {
                "finding_id": "finding-json-refs",
                "severity": "high",
                "category": "identity/access",
                "deterministic": False,
                "evidence_refs": '["ev-001", " ev-002 ", "ev-001"]',
            },
            [
                {
                    "evidence_id": "ev-001",
                    "source_type": "artifact",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                }
            ],
        )

        self.assertEqual(signals["evidence_count"], 2)
        self.assertEqual(signals["matched_evidence_count"], 1)
        self.assertEqual(signals["missing_evidence_count"], 1)
        self.assertEqual(
            signals["evidence_count_label"], "1 evidence item, 1 unavailable"
        )

    def test_finding_row_signals_parse_json_scalar_evidence_refs(self) -> None:
        signals = finding_row_signals(
            {
                "finding_id": "finding-json-scalar-ref",
                "severity": "high",
                "category": "identity/access",
                "deterministic": False,
                "evidence_refs": "42",
            },
            [
                {
                    "evidence_id": 42,
                    "source_type": "artifact",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                }
            ],
        )

        self.assertEqual(signals["evidence_count"], 1)
        self.assertEqual(signals["matched_evidence_count"], 1)
        self.assertEqual(signals["missing_evidence_count"], 0)
        self.assertEqual(signals["evidence_count_label"], "1 evidence item")
        self.assertEqual(signals["evidence_law_label"], "Evidence Law satisfied")

    def test_finding_row_signals_preserve_bare_scalar_string_evidence_refs(
        self,
    ) -> None:
        for ref in ("null", "true"):
            with self.subTest(ref=ref):
                signals = finding_row_signals(
                    {
                        "finding_id": f"finding-{ref}-ref",
                        "severity": "high",
                        "category": "identity/access",
                        "deterministic": False,
                        "evidence_refs": ref,
                    },
                    [
                        {
                            "evidence_id": ref,
                            "source_type": "artifact",
                            "deterministic": True,
                            "determinism_level": "deterministic",
                        }
                    ],
                )

                self.assertEqual(signals["evidence_count"], 1)
                self.assertEqual(signals["matched_evidence_count"], 1)
                self.assertEqual(signals["missing_evidence_count"], 0)

    def test_finding_row_signals_parse_csv_string_evidence_refs(self) -> None:
        signals = finding_row_signals(
            {
                "finding_id": "finding-csv-refs",
                "severity": "high",
                "category": "identity/access",
                "deterministic": False,
                "evidence_refs": "ev-001, ev-002, ev-001",
            },
            [
                {
                    "evidence_id": "ev-002",
                    "source_type": "artifact",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                }
            ],
        )

        self.assertEqual(signals["evidence_count"], 2)
        self.assertEqual(signals["matched_evidence_count"], 1)
        self.assertEqual(signals["missing_evidence_count"], 1)
        self.assertEqual(
            signals["evidence_count_label"], "1 evidence item, 1 unavailable"
        )

    def test_finding_row_signals_reject_mapping_evidence_refs(self) -> None:
        signals = finding_row_signals(
            {
                "finding_id": "finding-mapping",
                "severity": "high",
                "category": "identity/access",
                "deterministic": False,
                "evidence_refs": {"bad": "ev-001"},
            },
            [
                {
                    "evidence_id": "bad",
                    "source_type": "artifact",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                },
            ],
        )

        self.assertEqual(signals["evidence_count"], 0)
        self.assertEqual(signals["matched_evidence_count"], 0)
        self.assertEqual(signals["missing_evidence_count"], 0)
        self.assertEqual(signals["evidence_count_label"], "0 evidence items")

    def test_finding_row_signals_use_same_finding_evidence_for_stale_refs(
        self,
    ) -> None:
        signals = finding_row_signals(
            {
                "finding_id": "finding-stale",
                "severity": "high",
                "category": "identity/access",
                "deterministic": False,
                "evidence_refs": ["ev-stale"],
            },
            [
                {
                    "evidence_id": "ev-owned",
                    "finding_id": "finding-stale",
                    "source_type": "artifact",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                },
            ],
        )

        self.assertEqual(signals["evidence_count"], 2)
        self.assertEqual(signals["matched_evidence_count"], 1)
        self.assertEqual(signals["missing_evidence_count"], 1)
        self.assertEqual(
            signals["evidence_count_label"], "1 evidence item, 1 unavailable"
        )
        self.assertEqual(signals["evidence_law_label"], "Evidence Law satisfied")

    def test_finding_row_signals_suppress_ambiguous_same_finding_fallback(
        self,
    ) -> None:
        signals = finding_row_signals(
            {
                "finding_id": "finding-duplicate",
                "severity": "high",
                "category": "identity/access",
                "deterministic": False,
                "evidence_refs": ["ev-stale"],
            },
            [
                {
                    "evidence_id": "ev-owned",
                    "finding_id": "finding-duplicate",
                    "source_type": "artifact",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                },
            ],
            fallback_finding_ids=set(),
        )

        self.assertEqual(signals["evidence_count"], 1)
        self.assertEqual(signals["matched_evidence_count"], 0)
        self.assertEqual(signals["missing_evidence_count"], 1)
        self.assertEqual(
            signals["evidence_count_label"], "0 evidence items, 1 unavailable"
        )
        self.assertEqual(signals["evidence_law_label"], "Evidence Law needs evidence")

    def test_finding_row_signals_use_same_finding_evidence_for_mapping_refs(
        self,
    ) -> None:
        signals = finding_row_signals(
            {
                "finding_id": "finding-owned-mapping",
                "severity": "high",
                "category": "identity/access",
                "deterministic": False,
                "evidence_refs": {"bad": "ev-001"},
            },
            [
                {
                    "evidence_id": "ev-owned",
                    "finding_id": "finding-owned-mapping",
                    "source_type": "artifact",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                },
            ],
        )

        self.assertEqual(signals["evidence_count"], 1)
        self.assertEqual(signals["matched_evidence_count"], 1)
        self.assertEqual(signals["missing_evidence_count"], 0)
        self.assertEqual(signals["evidence_count_label"], "1 evidence item")

    def test_finding_row_signals_flag_severe_findings_without_deterministic_evidence(
        self,
    ) -> None:
        signals = finding_row_signals(
            {
                "finding_id": "finding-002",
                "severity": "high",
                "category": "",
                "deterministic": False,
                "evidence_refs": ["ev-heuristic"],
            },
            [
                {
                    "evidence_id": "ev-heuristic",
                    "source_type": "heuristic",
                    "deterministic": False,
                    "determinism_level": "heuristic",
                },
            ],
        )

        self.assertEqual(signals["category"], "uncategorized")
        self.assertEqual(signals["evidence_count_label"], "1 evidence item")
        self.assertEqual(signals["evidence_law_label"], "Evidence Law needs evidence")
        self.assertIn("Derived", signals["evidence_badges"])


if __name__ == "__main__":
    unittest.main()
