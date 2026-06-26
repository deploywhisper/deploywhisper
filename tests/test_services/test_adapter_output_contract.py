"""Tests for future workflow adapter output contracts."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from services.adapter_output_contract import (
    AdapterMetadata,
    AdapterOutputContract,
    AdapterOutputContractError,
    build_adapter_output_contract,
)
from services.analysis_service import build_share_summary


class AdapterOutputContractTests(unittest.TestCase):
    def test_contract_combines_canonical_summary_and_adapter_metadata(self) -> None:
        summary = build_share_summary(_report_payload())

        contract = build_adapter_output_contract(
            summary,
            AdapterMetadata(
                adapter="gitlab",
                format="merge_request_note",
                version="v1",
                project_key="payments",
                workspace_key="prod",
                extra={"merge_request_iid": 42},
            ),
            adapter_payload={
                "thread_key": "deploywhisper:17",
                "rendered_markdown": "GitLab-specific wrapper",
            },
        )

        self.assertEqual(contract.contract_version, "v1")
        self.assertEqual(contract.adapter_metadata.adapter, "gitlab")
        self.assertEqual(contract.adapter_metadata.extra["merge_request_iid"], 42)
        self.assertEqual(contract.canonical_summary.severity, "high")
        self.assertEqual(contract.canonical_summary.recommendation, "caution")
        self.assertEqual(
            contract.canonical_summary.json_payload.evidence_law_status, "Satisfied"
        )
        self.assertFalse(contract.canonical_summary.should_block)
        self.assertIn("Evidence Law", contract.canonical_summary.markdown)
        self.assertEqual(contract.adapter_payload["thread_key"], "deploywhisper:17")

        share_payload = contract.canonical_summary.json_payload
        self.assertEqual(share_payload.report_schema_version, "v2")
        self.assertEqual(share_payload.evidence_law_status, "Satisfied")
        self.assertEqual(share_payload.top_findings[0].severity, "high")
        self.assertIn("evidence_law_status", contract.model_dump_json())

    def test_adapter_payload_cannot_override_canonical_fields(self) -> None:
        summary = build_share_summary(_report_payload())

        for forbidden_payload in (
            {"severity": "low"},
            {"headline": "Adapter rewrite"},
            {"evidence_law_status": "Needs review"},
            {"evidence_law_detail": "Adapter-specific rewrite"},
        ):
            with self.subTest(forbidden_payload=forbidden_payload):
                with self.assertRaises(AdapterOutputContractError):
                    build_adapter_output_contract(
                        summary,
                        AdapterMetadata(
                            adapter="jenkins",
                            format="build_comment",
                            project_key="payments",
                        ),
                        adapter_payload=forbidden_payload,
                    )

    def test_adapter_payload_cannot_shadow_canonical_fields_nested(self) -> None:
        summary = build_share_summary(_report_payload())

        for forbidden_payload in (
            {"thread": {"severity": "low"}},
            {"blocks": [{"evidence_law_status": "Needs review"}]},
            {"thread": {"confidence": 0.2}},
            {"thread": {"score": 0.1}},
            {"blocks": [{"label": "Partial context"}]},
        ):
            with self.subTest(forbidden_payload=forbidden_payload):
                with self.assertRaises(AdapterOutputContractError):
                    build_adapter_output_contract(
                        summary,
                        AdapterMetadata(
                            adapter="gitlab",
                            format="merge_request_note",
                            project_key="payments",
                        ),
                        adapter_payload=forbidden_payload,
                    )

    def test_adapter_payload_requires_json_native_values(self) -> None:
        summary = build_share_summary(_report_payload())
        metadata = AdapterMetadata(
            adapter="gitlab",
            format="merge_request_note",
            project_key="payments",
        )

        for forbidden_payload in (
            {"items": {"one", "two"}},
            {"bad": object()},
            {"ratio": float("nan")},
        ):
            with self.subTest(forbidden_payload=forbidden_payload):
                with self.assertRaises(AdapterOutputContractError):
                    build_adapter_output_contract(
                        summary,
                        metadata,
                        adapter_payload=forbidden_payload,
                    )

        canonical_summary = build_adapter_output_contract(
            summary, metadata
        ).canonical_summary
        with self.assertRaises(ValidationError):
            AdapterOutputContract(
                adapter_metadata=metadata,
                canonical_summary=canonical_summary,
                adapter_payload={"bad": object()},
            )

    def test_adapter_metadata_extra_cannot_shadow_canonical_fields(self) -> None:
        with self.assertRaises(ValidationError):
            AdapterMetadata(
                adapter="chat",
                format="message",
                project_key="payments",
                extra={"severity": "low"},
            )
        with self.assertRaises(ValidationError):
            AdapterMetadata(
                adapter="chat",
                format="message",
                project_key="payments",
                extra={"headline": "Adapter headline"},
            )

    def test_adapter_metadata_extra_requires_finite_numbers(self) -> None:
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    AdapterMetadata(
                        adapter="chat",
                        format="message",
                        project_key="payments",
                        extra={"ratio": value},
                    )

    def test_adapter_metadata_requires_project_key_or_id(self) -> None:
        with self.assertRaises(ValidationError):
            AdapterMetadata(adapter="chat", format="message")

        by_key = AdapterMetadata(
            adapter="chat",
            format="message",
            project_key="payments",
            workspace_key="prod",
        )
        by_id = AdapterMetadata(
            adapter="chat",
            format="message",
            project_id=12,
            workspace_id=7,
        )

        self.assertEqual(by_key.project_key, "payments")
        self.assertEqual(by_key.workspace_key, "prod")
        self.assertEqual(by_id.project_id, 12)
        self.assertEqual(by_id.workspace_id, 7)

    def test_adapter_metadata_rejects_coerced_scope_ids(self) -> None:
        for kwargs in (
            {"project_id": True},
            {"project_id": "12"},
            {"project_id": 12.0},
            {"project_key": "payments", "workspace_id": True},
            {"project_key": "payments", "workspace_id": "7"},
            {"project_key": "payments", "workspace_id": 7.0},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValidationError):
                    AdapterMetadata(
                        adapter="chat",
                        format="message",
                        **kwargs,
                    )

    def test_adapter_metadata_rejects_conflicting_scope_identifiers(self) -> None:
        for kwargs in (
            {"project_key": "payments", "project_id": 12},
            {
                "project_key": "payments",
                "workspace_key": "prod",
                "workspace_id": 7,
            },
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValidationError):
                    AdapterMetadata(
                        adapter="chat",
                        format="message",
                        **kwargs,
                    )

    def test_adapter_metadata_rejects_unknown_top_level_fields(self) -> None:
        with self.assertRaises(ValidationError):
            AdapterMetadata(
                adapter="chat",
                format="message",
                project_key="payments",
                severity="low",
            )

    def test_adapter_payload_rejects_direct_model_construction_shadowing(
        self,
    ) -> None:
        summary = build_share_summary(_report_payload())
        metadata = AdapterMetadata(
            adapter="jenkins",
            format="build_comment",
            project_key="payments",
        )
        canonical_summary = build_adapter_output_contract(
            summary, metadata
        ).canonical_summary

        with self.assertRaises(ValidationError):
            AdapterOutputContract(
                adapter_metadata=metadata,
                canonical_summary=canonical_summary,
                adapter_payload={"evidence_law_status": "Needs review"},
            )

    def test_contract_version_is_fixed_to_v1(self) -> None:
        summary = build_share_summary(_report_payload())
        metadata = AdapterMetadata(
            adapter="jenkins",
            format="build_comment",
            project_key="payments",
        )
        canonical_summary = build_adapter_output_contract(
            summary, metadata
        ).canonical_summary

        contract = AdapterOutputContract(
            contract_version="v1",
            adapter_metadata=metadata,
            canonical_summary=canonical_summary,
        )
        self.assertEqual(contract.contract_version, "v1")

        for contract_version in ("", " ", "v2"):
            with self.subTest(contract_version=contract_version):
                with self.assertRaises(ValidationError):
                    AdapterOutputContract(
                        contract_version=contract_version,
                        adapter_metadata=metadata,
                        canonical_summary=canonical_summary,
                    )

    def test_canonical_summary_is_immutable_for_adapter_formatters(self) -> None:
        contract = build_adapter_output_contract(
            build_share_summary(_report_payload()),
            AdapterMetadata(
                adapter="atlantis",
                format="plan_comment",
                project_key="payments",
            ),
        )

        with self.assertRaises(ValidationError):
            contract.canonical_summary.severity = "low"
        with self.assertRaises(ValidationError):
            contract.canonical_summary.json_payload.evidence_law_status = "Needs review"

    def test_share_summary_labels_external_scanner_context_for_comments(self) -> None:
        payload = _report_payload()
        payload["findings"][0]["evidence_refs"].append("ev-scanner")
        payload["evidence_items"].append(
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-scanner-context",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "deterministic": True,
                "determinism_level": "deterministic",
            }
        )

        summary = build_share_summary(payload)

        self.assertEqual(summary.json_payload.external_evidence_count, 1)
        self.assertEqual(
            summary.json_payload.external_evidence_summary,
            "1 external scanner evidence item is included as context, not DeployWhisper severity proof.",
        )
        self.assertEqual(
            summary.json_payload.top_findings[0].evidence_label,
            "Includes external context",
        )
        self.assertEqual(summary.json_payload.top_findings[0].evidence_count, 2)
        self.assertIn("[Includes external context]", summary.markdown)
        self.assertIn("External scanner context", summary.markdown)
        self.assertIn(
            "HIGH: aws_security_group.db: Includes external context.",
            summary.plain_text,
        )
        self.assertIn("external scanner evidence item", summary.plain_text)

    def test_share_summary_preserves_external_context_when_evidence_rows_omitted(
        self,
    ) -> None:
        payload = _report_payload()
        payload["findings"][0]["evidence_refs"].append("ev-scanner")
        payload["findings"][0]["evidence_label"] = "Includes external context"
        payload["evidence_items"] = []
        payload["share_summary"] = {
            "json_payload": {
                "evidence_count": 2,
                "external_evidence_count": 1,
            },
        }

        summary = build_share_summary(payload, evidence_detail_available=False)

        self.assertEqual(summary.json_payload.evidence_count, 2)
        self.assertEqual(summary.json_payload.external_evidence_count, 1)
        self.assertEqual(
            summary.json_payload.external_evidence_summary,
            "1 external scanner evidence item is included as context, not DeployWhisper severity proof.",
        )
        self.assertEqual(
            summary.json_payload.top_findings[0].evidence_label,
            "Includes external context",
        )
        self.assertEqual(summary.json_payload.top_findings[0].evidence_count, 2)
        self.assertIn("[Includes external context]", summary.markdown)
        self.assertIn("External scanner context", summary.markdown)
        self.assertIn("- Evidence Law: Detail omitted", summary.markdown)

    def test_share_summary_caps_external_context_when_rows_are_partially_redacted(
        self,
    ) -> None:
        payload = _report_payload()
        payload["findings"][0]["evidence_refs"].append("ev-scanner")
        payload["findings"][0]["evidence_label"] = "Includes external context"
        payload["evidence_items"] = [
            {
                "evidence_id": "ev-001",
                "finding_id": "finding-001",
                "source_type": "artifact",
                "source_kind": "artifact",
                "deterministic": True,
                "determinism_level": "deterministic",
            },
        ]
        payload["share_summary"] = {
            "json_payload": {
                "evidence_count": 2,
                "external_evidence_count": 9,
            },
        }

        summary = build_share_summary(payload, evidence_detail_available=False)

        self.assertEqual(summary.json_payload.evidence_count, 2)
        self.assertEqual(summary.json_payload.external_evidence_count, 1)
        self.assertIn("2 evidence items", summary.markdown)
        self.assertIn("1 external scanner evidence item", summary.markdown)
        self.assertNotIn("9 external scanner evidence", summary.markdown)

    def test_share_summary_keeps_external_scanner_findings_after_top_three(
        self,
    ) -> None:
        payload = _report_payload()
        payload["findings"] = [
            {
                "finding_id": f"finding-high-{index}",
                "title": f"HIGH: internal finding {index}",
                "severity": "high",
                "confidence": 0.99 - (index / 100),
                "evidence_refs": [f"ev-high-{index}"],
            }
            for index in range(3)
        ] + [
            {
                "finding_id": "finding-scanner-context",
                "title": "LOW: semgrep scanner context",
                "severity": "low",
                "confidence": 0.1,
                "evidence_refs": ["ev-scanner"],
            }
        ]
        payload["evidence_items"] = [
            {
                "evidence_id": f"ev-high-{index}",
                "finding_id": f"finding-high-{index}",
                "source_type": "artifact",
                "source_kind": "artifact",
                "deterministic": True,
                "determinism_level": "deterministic",
            }
            for index in range(3)
        ] + [
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-scanner-context",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "deterministic": True,
                "determinism_level": "deterministic",
            }
        ]

        summary = build_share_summary(payload)
        titles = [finding.title for finding in summary.json_payload.top_findings]

        self.assertIn("LOW: semgrep scanner context", titles)
        self.assertGreater(len(summary.json_payload.top_findings), 3)
        self.assertIn(
            "LOW: semgrep scanner context [External evidence]",
            summary.markdown,
        )
        self.assertNotIn("LOW: LOW: semgrep scanner context", summary.markdown)
        self.assertIn(
            "LOW: semgrep scanner context: External evidence.",
            summary.plain_text,
        )

    def test_share_summary_caps_external_scanner_findings_after_top_three(
        self,
    ) -> None:
        payload = _report_payload()
        payload["findings"] = (
            [
                {
                    "finding_id": f"finding-high-{index}",
                    "title": f"HIGH: internal finding {index}",
                    "severity": "high",
                    "confidence": 0.99 - (index / 100),
                    "evidence_refs": [f"ev-high-{index}"],
                }
                for index in range(3)
            ]
            + [
                {
                    "finding_id": f"finding-mixed-{index}",
                    "title": f"LOW: mixed scanner context {index}",
                    "severity": "low",
                    "confidence": 0.95 - (index / 100),
                    "evidence_refs": [f"ev-mixed-{index}", f"ev-scanner-mixed-{index}"],
                }
                for index in range(2)
            ]
            + [
                {
                    "finding_id": f"finding-scanner-{index}",
                    "title": f"LOW: scanner-only context {index}",
                    "severity": "low",
                    "confidence": 0.1 - (index / 100),
                    "evidence_refs": [f"ev-scanner-only-{index}"],
                }
                for index in range(3)
            ]
        )
        payload["evidence_items"] = (
            [
                {
                    "evidence_id": f"ev-high-{index}",
                    "finding_id": f"finding-high-{index}",
                    "source_type": "artifact",
                    "source_kind": "artifact",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                }
                for index in range(3)
            ]
            + [
                {
                    "evidence_id": f"ev-mixed-{index}",
                    "finding_id": f"finding-mixed-{index}",
                    "source_type": "artifact",
                    "source_kind": "artifact",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                }
                for index in range(2)
            ]
            + [
                {
                    "evidence_id": f"ev-scanner-mixed-{index}",
                    "finding_id": f"finding-mixed-{index}",
                    "source_type": "external_scanner",
                    "source_kind": "external_scanner",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                }
                for index in range(2)
            ]
            + [
                {
                    "evidence_id": f"ev-scanner-only-{index}",
                    "finding_id": f"finding-scanner-{index}",
                    "source_type": "external_scanner",
                    "source_kind": "external_scanner",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                }
                for index in range(3)
            ]
        )

        summary = build_share_summary(payload)
        titles = [finding.title for finding in summary.json_payload.top_findings]

        self.assertEqual(len(summary.json_payload.top_findings), 5)
        self.assertEqual(
            sum(
                1
                for finding in summary.json_payload.top_findings
                if finding.evidence_label == "External evidence"
            ),
            2,
        )
        self.assertIn("LOW: scanner-only context 0", titles)
        self.assertIn("LOW: scanner-only context 1", titles)
        self.assertNotIn("LOW: scanner-only context 2", titles)
        self.assertNotIn("LOW: mixed scanner context 0", titles)

    def test_share_summary_compact_markdown_keeps_duplicate_title_external_label(
        self,
    ) -> None:
        payload = _report_payload()
        payload["findings"] = [
            {
                "finding_id": "finding-internal-duplicate",
                "title": "DUPLICATE: shared title",
                "severity": "high",
                "confidence": 0.99,
                "evidence_refs": ["ev-internal-duplicate"],
            },
            {
                "finding_id": "finding-internal-other",
                "title": "HIGH: another internal finding",
                "severity": "high",
                "confidence": 0.98,
                "evidence_refs": ["ev-internal-other"],
            },
            {
                "finding_id": "finding-internal-third",
                "title": "HIGH: third internal finding",
                "severity": "high",
                "confidence": 0.97,
                "evidence_refs": ["ev-internal-third"],
            },
            {
                "finding_id": "finding-external-duplicate",
                "title": "DUPLICATE: shared title",
                "severity": "low",
                "confidence": 0.1,
                "evidence_refs": ["ev-scanner-duplicate"],
            },
        ]
        payload["evidence_items"] = [
            {
                "evidence_id": evidence_id,
                "finding_id": finding_id,
                "source_type": "artifact",
                "source_kind": "artifact",
                "deterministic": True,
                "determinism_level": "deterministic",
            }
            for evidence_id, finding_id in (
                ("ev-internal-duplicate", "finding-internal-duplicate"),
                ("ev-internal-other", "finding-internal-other"),
                ("ev-internal-third", "finding-internal-third"),
            )
        ] + [
            {
                "evidence_id": "ev-scanner-duplicate",
                "finding_id": "finding-external-duplicate",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "deterministic": True,
                "determinism_level": "deterministic",
            }
        ]
        payload["context_completeness"] = {
            "context_score": 0.9,
            "uncertainty": "Reviewer context remains intentionally verbose. " * 80,
        }

        summary = build_share_summary(payload)

        self.assertLessEqual(len(summary.markdown), 1500)
        self.assertIn("HIGH: third internal finding", summary.markdown)
        self.assertIn(
            "LOW: DUPLICATE: shared title [External evidence]",
            summary.markdown,
        )
        self.assertNotIn("LOW: LOW: DUPLICATE", summary.markdown)
        self.assertIn(
            "LOW: DUPLICATE: shared title: External evidence.",
            summary.plain_text,
        )

    def test_share_summary_does_not_treat_user_context_as_deploywhisper_support(
        self,
    ) -> None:
        payload = _report_payload()
        payload["findings"][0]["evidence_refs"] = ["ev-scanner", "ev-user"]
        payload["evidence_items"] = [
            {
                "evidence_id": "ev-scanner",
                "finding_id": "finding-001",
                "source_type": "external_scanner",
                "source_kind": "external_scanner",
                "deterministic": True,
                "determinism_level": "deterministic",
            },
            {
                "evidence_id": "ev-user",
                "finding_id": "finding-001",
                "source_type": "user_context",
                "source_kind": "user_context",
                "deterministic": True,
                "determinism_level": "deterministic",
            },
        ]

        summary = build_share_summary(payload)

        self.assertEqual(
            summary.json_payload.top_findings[0].evidence_label,
            "External evidence",
        )
        self.assertNotIn("Includes external context", summary.markdown)

    def test_adapter_owned_maps_are_immutable_after_validation(self) -> None:
        contract = build_adapter_output_contract(
            build_share_summary(_report_payload()),
            AdapterMetadata(
                adapter="gitlab",
                format="merge_request_note",
                project_key="payments",
                extra={"merge_request_iid": 42},
            ),
            adapter_payload={"thread": {"id": "deploywhisper:17"}},
        )

        with self.assertRaises(TypeError):
            contract.adapter_payload["severity"] = "low"
        with self.assertRaises(TypeError):
            contract.adapter_payload["thread"]["evidence_law_status"] = "Needs review"
        with self.assertRaises(TypeError):
            contract.adapter_metadata.extra["evidence_law_status"] = "Needs review"

    def test_tuple_wrapped_adapter_maps_are_immutable_after_validation(self) -> None:
        contract = build_adapter_output_contract(
            build_share_summary(_report_payload()),
            AdapterMetadata(
                adapter="gitlab",
                format="merge_request_note",
                project_key="payments",
            ),
            adapter_payload={"items": ({"id": "deploywhisper:17"},)},
        )

        self.assertIsInstance(contract.adapter_payload["items"], tuple)
        with self.assertRaises(TypeError):
            contract.adapter_payload["items"][0]["severity"] = "low"


def _report_payload() -> dict:
    return {
        "id": 17,
        "report_schema_version": "v2",
        "severity": "high",
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
                "evidence_refs": ["ev-001"],
            }
        ],
        "evidence_items": [
            {
                "evidence_id": "ev-001",
                "finding_id": "finding-001",
                "deterministic": True,
                "determinism_level": "deterministic",
            }
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
