"""Tests for stable AI-agent output adaptation."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from services.agent_interface_service import (
    AGENT_MAX_COLLECTION_ITEMS,
    AGENT_MAX_EVIDENCE,
    AGENT_MAX_FINDINGS,
    AGENT_MAX_STRING_CHARACTERS,
    AGENT_APPROVAL_STATEMENT,
    build_agent_analysis_data,
    build_agent_interface_response,
    collect_agent_report_verification_guidance,
    collect_agent_verification_guidance,
)


class AgentInterfaceServiceTests(unittest.TestCase):
    @staticmethod
    def _analysis(*, include_items: bool, include_workspace: bool) -> SimpleNamespace:
        context_source = SimpleNamespace(
            source_id="artifact:plan",
            source_type="artifact",
            source_ref="plan.json",
            scope="project:payments/workspace:prod",
            freshness_status="current",
            last_observed_at="2026-07-28T10:00:00Z",
            age_days=0,
            confidence=0.92,
            conflicts=[],
            limitations=[],
        )
        evidence = SimpleNamespace(
            evidence_id="ev-1",
            analysis_id=42,
            finding_id="finding-1",
            source_type="artifact",
            source_ref="terraform://plan.json#aws_security_group.main",
            artifact="plan.json",
            location="plan.json:12",
            resource="aws_security_group.main",
            operation="modify",
            project_id=7,
            project_key="payments",
            workspace_id=9,
            workspace_key="prod",
            source_kind="artifact",
            determinism_level="deterministic",
            redaction_status="none",
            summary="Ingress changed.",
            severity_hint="high",
            deterministic=True,
            confidence=0.92,
            evidence_label=None,
            related_change_ids=["chg-1"],
            context_source=context_source,
        )
        finding = SimpleNamespace(
            finding_id="finding-1",
            analysis_id=42,
            title="Public ingress",
            description="Ingress may be public.",
            explanation="Public ingress expands exposure.",
            guidance=["Confirm the ingress policy."],
            severity="high",
            category="network",
            deterministic=True,
            confidence=0.92,
            uncertainty_note=None,
            evidence_classification="deterministic",
            evidence_refs=["ev-1"],
            evidence_label=None,
            skill_id=None,
        )
        workspace = (
            SimpleNamespace(id=9, workspace_key="prod") if include_workspace else None
        )
        return SimpleNamespace(
            findings=[finding] if include_items else [],
            evidence_items=[evidence] if include_items else [],
            incident_matches=[],
            share_summary=SimpleNamespace(
                json_payload=SimpleNamespace(
                    evidence_law_status="Satisfied",
                    evidence_law_detail="Severe claims have deterministic evidence.",
                    scanner_conflicts=[],
                )
            ),
            narrative=SimpleNamespace(guidance=[], warnings=[]),
            advisory=SimpleNamespace(uncertainty_flags=[]),
            assessment=SimpleNamespace(
                score=78,
                severity="high",
                recommendation="no-go",
                top_risk="Public ingress",
                confidence=0.92,
                confidence_ledger=SimpleNamespace(
                    contributors=["Public ingress"],
                    confidence_factors=["Deterministic artifact evidence"],
                    why_not_lower=["The ingress is public."],
                    why_not_higher=["No credential exposure was observed."],
                    uncertainty_drivers=[],
                ),
                context_completeness=SimpleNamespace(
                    uncertainty=None,
                    partial_context=False,
                    insufficient_context=False,
                    context_todos=[],
                ),
                warnings=[],
            ),
            persisted_report=SimpleNamespace(
                id=42,
                report_schema_version="1.0",
                project=SimpleNamespace(id=7, project_key="payments"),
                workspace=workspace,
            ),
        )

    def test_verification_guidance_is_ordered_deduplicated_and_human_gated(
        self,
    ) -> None:
        analysis = SimpleNamespace(
            findings=[
                SimpleNamespace(
                    guidance=[
                        "Confirm the ingress policy.",
                        "Confirm the ingress policy.",
                    ]
                )
            ],
            incident_matches=[
                SimpleNamespace(
                    verification_guidance=["Compare against the incident pattern."]
                )
            ],
            share_summary=SimpleNamespace(
                json_payload=SimpleNamespace(
                    scanner_conflicts=[
                        SimpleNamespace(
                            recommended_verification="Reconcile scanner evidence."
                        )
                    ]
                )
            ),
            narrative=SimpleNamespace(
                guidance=[
                    "  compare   AGAINST the incident pattern.  ",
                    "Confirm the ingress policy.",
                ]
            ),
        )

        guidance = collect_agent_verification_guidance(analysis)

        self.assertEqual(
            guidance,
            [
                "Confirm the ingress policy.",
                "Compare against the incident pattern.",
                "Reconcile scanner evidence.",
                "Have a human reviewer inspect the evidence and findings before deployment.",
            ],
        )

    def test_persisted_guidance_ignores_malformed_scalar_collections(self) -> None:
        report = {
            "findings": [{"guidance": "Do not split this into characters."}],
            "incident_matches": [
                {"verification_guidance": "Do not split this either."}
            ],
            "narrative_guidance": ["Verify the narrative with an operator."],
            "share_summary": SimpleNamespace(
                json_payload=SimpleNamespace(scanner_conflicts=[])
            ),
        }

        guidance = collect_agent_report_verification_guidance(report)

        self.assertEqual(
            guidance,
            [
                "Verify the narrative with an operator.",
                "Have a human reviewer inspect the evidence and findings before deployment.",
            ],
        )

    def test_builder_locks_nested_v1_contract_keys(self) -> None:
        payload = build_agent_analysis_data(
            self._analysis(include_items=True, include_workspace=True)
        ).model_dump(mode="json")

        self.assertEqual(
            set(payload["evidence"][0]),
            {
                "evidence_id",
                "analysis_id",
                "finding_id",
                "source_type",
                "source_ref",
                "artifact",
                "location",
                "resource",
                "operation",
                "project_id",
                "project_key",
                "workspace_id",
                "workspace_key",
                "source_kind",
                "determinism_level",
                "redaction_status",
                "summary",
                "severity_hint",
                "deterministic",
                "confidence",
                "evidence_label",
                "related_change_ids",
                "context_source",
            },
        )
        self.assertEqual(
            set(payload["evidence"][0]["context_source"]),
            {
                "source_id",
                "source_type",
                "source_ref",
                "scope",
                "freshness_status",
                "last_observed_at",
                "age_days",
                "confidence",
                "conflicts",
                "limitations",
            },
        )
        self.assertEqual(
            set(payload["findings"][0]),
            {
                "finding_id",
                "analysis_id",
                "title",
                "description",
                "explanation",
                "guidance",
                "severity",
                "category",
                "deterministic",
                "confidence",
                "uncertainty_note",
                "evidence_classification",
                "evidence_refs",
                "evidence_label",
                "skill_id",
            },
        )
        self.assertEqual(
            set(payload["confidence"]["ledger"]),
            {
                "contributors",
                "confidence_factors",
                "why_not_lower",
                "why_not_higher",
                "uncertainty_drivers",
            },
        )

    def test_builder_preserves_workspace_scope_and_empty_collections(self) -> None:
        payload = build_agent_analysis_data(
            self._analysis(include_items=False, include_workspace=True)
        ).model_dump(mode="json")

        self.assertEqual(
            payload["scope"],
            {
                "project_id": 7,
                "project_key": "payments",
                "workspace_id": 9,
                "workspace_key": "prod",
            },
        )
        self.assertEqual(payload["evidence"], [])
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["context_todos"], [])
        self.assertTrue(payload["advisory_only"])
        self.assertFalse(payload["deployment_approval"])
        self.assertTrue(payload["human_decision_required"])
        self.assertEqual(payload["approval_statement"], AGENT_APPROVAL_STATEMENT)

    def test_interface_response_applies_explicit_collection_and_string_bounds(
        self,
    ) -> None:
        data = build_agent_analysis_data(
            self._analysis(include_items=True, include_workspace=True)
        )
        payload = data.model_dump(mode="json")
        payload["findings"] = payload["findings"] * (AGENT_MAX_FINDINGS + 1)
        payload["context_todos"] = [
            f"todo-{index}" for index in range(AGENT_MAX_COLLECTION_ITEMS + 1)
        ]
        payload["verdict"]["top_risk"] = "x" * (AGENT_MAX_STRING_CHARACTERS + 1)

        response = build_agent_interface_response(
            type(data).model_validate(payload),
            operation="analysis.submit",
        )

        self.assertEqual(len(response.data.findings), AGENT_MAX_FINDINGS)
        self.assertEqual(
            len(response.data.context_todos),
            AGENT_MAX_COLLECTION_ITEMS,
        )
        self.assertEqual(
            len(response.data.verdict.top_risk),
            AGENT_MAX_STRING_CHARACTERS,
        )
        self.assertTrue(response.meta.truncated)
        self.assertEqual(
            set(response.meta.truncated_fields),
            {"findings", "context_todos", "verdict.top_risk"},
        )

    def test_interface_bounds_preserve_finding_evidence_referential_integrity(
        self,
    ) -> None:
        data = build_agent_analysis_data(
            self._analysis(include_items=True, include_workspace=True)
        )
        payload = data.model_dump(mode="json")
        base_finding = payload["findings"][0]
        base_evidence = payload["evidence"][0]
        findings = []
        evidence = []
        for finding_index in range(AGENT_MAX_FINDINGS + 1):
            finding_id = f"finding-{finding_index}"
            evidence_refs = [
                f"evidence-{finding_index}-{evidence_index}"
                for evidence_index in range(3)
            ]
            findings.append(
                {
                    **base_finding,
                    "finding_id": finding_id,
                    "evidence_refs": evidence_refs,
                }
            )
            evidence.extend(
                {
                    **base_evidence,
                    "evidence_id": evidence_id,
                    "finding_id": finding_id,
                }
                for evidence_id in evidence_refs
            )
        payload["findings"] = findings
        payload["evidence"] = evidence

        response = build_agent_interface_response(
            type(data).model_validate(payload),
            operation="report.read",
        )

        returned_findings = response.data.findings
        returned_evidence = response.data.evidence
        finding_ids = {item.finding_id for item in returned_findings}
        evidence_ids = {item.evidence_id for item in returned_evidence}
        self.assertEqual(len(returned_findings), AGENT_MAX_FINDINGS)
        self.assertEqual(len(returned_evidence), AGENT_MAX_EVIDENCE)
        self.assertTrue(
            all(item.finding_id in finding_ids for item in returned_evidence)
        )
        self.assertTrue(
            all(
                evidence_ref in evidence_ids
                for finding in returned_findings
                for evidence_ref in finding.evidence_refs
            )
        )
        self.assertIn("findings", response.meta.truncated_fields)
        self.assertIn("evidence", response.meta.truncated_fields)


if __name__ == "__main__":
    unittest.main()
