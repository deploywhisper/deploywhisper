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
