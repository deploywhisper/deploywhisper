"""Rendered smoke tests for the findings table evidence inspector."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import app as app_module
from fastapi.testclient import TestClient
from nicegui import ui

from ui.components.findings_table import render_findings_table


@ui.page("/_test/findings-table-render")
def findings_table_render_test_page() -> None:
    render_findings_table(
        findings=[
            {
                "finding_id": "finding-001",
                "title": "CRITICAL: aws_security_group.main",
                "description": "Security group exposure risk",
                "severity": "critical",
                "category": "networking/ingress",
                "confidence": 1.0,
                "deterministic": True,
                "evidence_refs": [
                    "ev-001",
                    "ev-002",
                    "ev-003",
                    "ev-004",
                    "ev-005",
                    "ev-partial-missing",
                ],
            },
            {
                "finding_id": "finding-002",
                "title": "HIGH: aws_iam_policy.admin",
                "description": "IAM policy references unavailable sensitive evidence",
                "severity": "high",
                "category": "identity/access",
                "confidence": 0.82,
                "deterministic": False,
                "evidence_refs": "secret/path.env#TOKEN",
            },
            {
                "finding_id": 'finding "003"/legacy',
                "title": 'HIGH: "quoted"\n<danger>\tcase',
                "description": "Finding title contains attribute-sensitive text",
                "severity": "high",
                "category": "identity/access",
                "confidence": 0.74,
                "deterministic": False,
                "evidence_refs": "secret-a.env, secret-b.env, secret-c.env, secret-d.env",
            },
        ],
        evidence_items=[
            {
                "evidence_id": "ev-001",
                "source_type": "artifact",
                "source_ref": "terraform://plan.json#L2",
                "artifact": "plan.json",
                "location": "plan.json#L2",
                "resource": "aws_security_group.main",
                "operation": "modify",
                "project_id": 12,
                "project_key": "payments",
                "workspace_id": 34,
                "workspace_key": "prod",
                "source_kind": "artifact",
                "summary": "Terraform changed a security group.",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "redaction_status": "none",
                "confidence": 1.0,
            },
            {
                "evidence_id": "ev-002",
                "source_type": "topology",
                "source_ref": "topology://payments/api#line=18",
                "artifact": "topology snapshot",
                "location": "payments/api#line=18",
                "resource": "payments/api",
                "operation": "context",
                "project_key": "payments",
                "workspace_key": "prod",
                "source_kind": "topology",
                "summary": "Topology maps the gateway to the payments service.",
                "severity_hint": "medium",
                "deterministic": True,
                "determinism_level": "deterministic",
                "redaction_status": "none",
                "confidence": 0.9,
            },
            {
                "evidence_id": "ev-003",
                "source_type": "artifact",
                "source_ref": "terraform://secrets.env#L1",
                "artifact": "secrets.env",
                "location": "secrets.env#L1",
                "resource": "aws_iam_policy.unknown",
                "operation": "review",
                "project_key": "payments",
                "workspace_key": "prod",
                "source_kind": "artifact",
                "summary": "Sensitive secret value should not render.",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "redaction_status": "sensitive_blocked",
                "confidence": 0.95,
            },
            {
                "evidence_id": "ev-004",
                "source_type": "artifact",
                "source_ref": "terraform://unknown-redaction.json#L4",
                "artifact": "unknown-redaction.json",
                "location": "unknown-redaction.json#L4",
                "resource": "aws_iam_policy.unknown",
                "operation": "review",
                "source_kind": "artifact",
                "summary": "Unknown redaction summary should not render.",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "redaction_status": "future_status",
                "confidence": 0.8,
            },
            {
                "evidence_id": "ev-005",
                "source_type": "artifact",
                "source_ref": "terraform://redacted-plan.json#L8",
                "artifact": "redacted-plan.json",
                "location": "redacted-plan.json#L8",
                "resource": "aws_iam_policy.redacted",
                "operation": "modify",
                "source_kind": "artifact",
                "summary": "Redacted artifact metadata remains inspectable.",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "redaction_status": "redacted",
                "confidence": 0.88,
            },
        ],
        artifact_names=[
            "plan.json",
            "redacted-plan.json",
            "secrets.env",
            "unknown-redaction.json",
        ],
        report_id=14,
        expanded_finding_ids={
            "finding-001",
            "finding-002",
            'finding "003"/legacy',
        },
        report_schema_version="v2",
    )


@ui.page("/_test/findings-table-default-schema-render")
def findings_table_default_schema_render_test_page() -> None:
    render_findings_table(
        findings=[
            {
                "finding_id": "finding-default-schema",
                "title": "HIGH: missing schema version",
                "description": "Evidence has no redaction field.",
                "severity": "high",
                "category": "identity/access",
                "confidence": 0.8,
                "deterministic": True,
                "evidence_refs": ["ev-default-schema"],
            },
        ],
        evidence_items=[
            {
                "evidence_id": "ev-default-schema",
                "source_type": "artifact",
                "source_ref": "terraform://plan.json#L2",
                "artifact": "plan.json",
                "location": "plan.json#L2",
                "resource": "aws_iam_policy.admin",
                "operation": "modify",
                "source_kind": "artifact",
                "summary": "Missing schema summary should fail closed.",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "confidence": 0.9,
            },
        ],
        artifact_names=["plan.json"],
        report_id=15,
        expanded_finding_ids={"finding-default-schema"},
    )


@ui.page("/_test/findings-table-v1-schema-render")
def findings_table_v1_schema_render_test_page() -> None:
    render_findings_table(
        findings=[
            {
                "finding_id": "finding-v1-schema",
                "title": "HIGH: legacy schema version",
                "description": "Legacy evidence has no redaction field.",
                "severity": "high",
                "category": "identity/access",
                "confidence": 0.8,
                "deterministic": True,
                "evidence_refs": ["ev-v1-schema"],
            },
        ],
        evidence_items=[
            {
                "evidence_id": "ev-v1-schema",
                "source_type": "artifact",
                "source_ref": "terraform://plan.json#L3",
                "artifact": "plan.json",
                "location": "plan.json#L3",
                "resource": "aws_iam_policy.legacy",
                "operation": "modify",
                "source_kind": "artifact",
                "summary": "Legacy schema summary remains readable.",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "confidence": 0.9,
            },
        ],
        artifact_names=["plan.json"],
        report_id=16,
        expanded_finding_ids={"finding-v1-schema"},
        report_schema_version="v1",
    )


@ui.page("/_test/findings-table-duplicate-id-render")
def findings_table_duplicate_id_render_test_page() -> None:
    render_findings_table(
        findings=[
            {
                "finding_id": "finding-duplicate",
                "title": "HIGH: duplicate first",
                "description": "First duplicate finding.",
                "severity": "high",
                "category": "identity/access",
                "confidence": 0.8,
                "deterministic": True,
                "evidence_refs": ["ev-first"],
            },
            {
                "finding_id": "finding-duplicate",
                "title": "HIGH: duplicate second",
                "description": "Second duplicate finding.",
                "severity": "high",
                "category": "identity/access",
                "confidence": 0.7,
                "deterministic": True,
                "evidence_refs": ["ev-second"],
            },
            {
                "finding_id": "",
                "title": "HIGH: blank id",
                "description": "Blank id finding.",
                "severity": "high",
                "category": "identity/access",
                "confidence": 0.6,
                "deterministic": True,
                "evidence_refs": ["ev-blank"],
            },
        ],
        evidence_items=[
            {
                "evidence_id": "ev-first",
                "finding_id": "finding-duplicate",
                "source_type": "artifact",
                "source_ref": "terraform://first.json#L1",
                "summary": "First duplicate evidence.",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "redaction_status": "none",
                "confidence": 0.9,
            },
            {
                "evidence_id": "ev-second",
                "finding_id": "finding-duplicate",
                "source_type": "artifact",
                "source_ref": "terraform://second.json#L2",
                "summary": "Second duplicate evidence.",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "redaction_status": "none",
                "confidence": 0.9,
            },
            {
                "evidence_id": "ev-blank",
                "finding_id": "",
                "source_type": "artifact",
                "source_ref": "terraform://blank.json#L3",
                "summary": "Blank id evidence.",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "redaction_status": "none",
                "confidence": 0.9,
            },
        ],
        report_schema_version="v2",
        expanded_finding_ids={"finding-duplicate"},
    )


@ui.page("/_test/findings-table-duplicate-stale-fallback-render")
def findings_table_duplicate_stale_fallback_render_test_page() -> None:
    render_findings_table(
        findings=[
            {
                "finding_id": "finding-duplicate",
                "title": "CRITICAL: duplicate stale",
                "description": "Primary duplicate has stale evidence refs.",
                "severity": "critical",
                "category": "identity/access",
                "confidence": 0.95,
                "deterministic": True,
                "evidence_refs": ["ev-stale"],
            },
            {
                "finding_id": "finding-duplicate",
                "title": "LOW: duplicate borrowed",
                "description": "Duplicate id has persisted evidence.",
                "severity": "low",
                "category": "identity/access",
                "confidence": 0.4,
                "deterministic": True,
                "evidence_refs": [],
            },
        ],
        evidence_items=[
            {
                "evidence_id": "ev-owned",
                "finding_id": "finding-duplicate",
                "source_type": "artifact",
                "source_ref": "terraform://borrowed-plan.json#L6",
                "summary": "Borrowed duplicate evidence should not render.",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "redaction_status": "none",
                "confidence": 0.9,
            },
        ],
        report_schema_version="v2",
        expanded_finding_ids={"finding-duplicate"},
    )


class FindingsTableRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app_module.create_app())

    def test_rendered_inspector_contains_real_artifact_link_and_source_badge(
        self,
    ) -> None:
        response = self.client.get("/_test/findings-table-render")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "/history/14/artifacts?name=plan.json&amp;line=2#L2", response.text
        )
        self.assertIn('"data-dw-findings-table":"1"', response.text)
        self.assertIn('"data-dw-review-section":"findings"', response.text)
        self.assertIn('"data-dw-finding-row":"1"', response.text)
        self.assertIn('"tabindex":"0"', response.text)
        self.assertIn('"aria-expanded":"true"', response.text)
        self.assertIn(
            '"aria-controls":"evidence-inspector-finding-row--finding-001',
            response.text,
        )
        self.assertIn(
            "evidence-inspector-finding-row-2-finding-003-legacy-", response.text
        )
        self.assertNotIn(
            'id":"evidence-inspector-finding \\"003\\"/legacy', response.text
        )
        self.assertIn('"data-dw-review-section":"evidence"', response.text)
        self.assertEqual(response.text.count('"data-dw-review-section":"evidence"'), 1)
        self.assertIn(
            '"aria-label":"Evidence inspector for CRITICAL: aws_security_group.main"',
            response.text,
        )
        self.assertIn(
            '"aria-label":"Finding HIGH: \\"quoted\\" &lt;danger&gt; case',
            response.text,
        )
        self.assertNotIn(
            'Evidence inspector for HIGH: \\"quoted\\"\\n&lt;danger&gt;',
            response.text,
        )
        self.assertNotIn("&amp;quot;quoted&amp;quot;", response.text)
        self.assertIn("SYSTEM: payments", response.text)
        self.assertIn("Artifact", response.text)
        self.assertIn("Topology", response.text)
        self.assertIn("networking/ingress", response.text)
        self.assertIn("5 evidence items, 1 unavailable", response.text)
        self.assertIn("0 evidence items, 1 unavailable", response.text)
        self.assertIn("1 unavailable", response.text)
        self.assertIn("External", response.text)
        self.assertIn("Evidence Law satisfied", response.text)
        self.assertIn("Artifact reference plan.json", response.text)
        self.assertIn("Proof reference topology snapshot", response.text)
        self.assertNotIn("Artifact reference topology snapshot", response.text)
        self.assertIn("Resource aws_security_group.main", response.text)
        self.assertIn("Operation modify", response.text)
        self.assertIn("Context source Artifact", response.text)
        self.assertIn("Project payments (#12)", response.text)
        self.assertIn("Workspace prod (#34)", response.text)
        self.assertIn("Determinism deterministic", response.text)
        self.assertIn("Redaction Redacted", response.text)
        self.assertIn("metadata remains available", response.text)
        self.assertNotIn(
            "Redacted artifact metadata remains inspectable.", response.text
        )
        self.assertNotIn(
            "/history/14/artifacts?name=redacted-plan.json&amp;line=8#L8",
            response.text,
        )
        self.assertNotIn(
            "/history/14/artifacts?name=secrets.env&amp;line=1#L1",
            response.text,
        )
        self.assertNotIn(
            "/history/14/artifacts?name=unknown-redaction.json&amp;line=4#L4",
            response.text,
        )
        self.assertIn("Evidence unavailable", response.text)
        self.assertIn("Missing evidence refs: 1 unavailable reference", response.text)
        self.assertIn("safe reference metadata only", response.text)
        self.assertIn("Proof reference unavailable reference 1", response.text)
        self.assertIn("Evidence content unavailable", response.text)
        self.assertIn("Redaction Sensitive blocked", response.text)
        self.assertIn("Proof reference sensitive evidence blocked", response.text)
        self.assertIn("Resource resource withheld", response.text)
        self.assertIn("Operation operation withheld", response.text)
        self.assertIn("Redaction Unknown", response.text)
        self.assertIn("content availability is unknown", response.text)
        self.assertNotIn("ev-partial-missing", response.text)
        self.assertNotIn("secret/path.env#TOKEN", response.text)
        self.assertNotIn("secret-a.env", response.text)
        self.assertNotIn("Sensitive secret value should not render.", response.text)
        self.assertNotIn("Unknown redaction summary should not render.", response.text)
        self.assertNotIn("unknown-redaction.json", response.text)
        self.assertNotIn("aws_iam_policy.unknown", response.text)
        self.assertNotIn("Artifact reference secrets.env", response.text)
        self.assertNotIn("Resource aws_iam_policy.admin", response.text)
        self.assertNotIn("Operation inspect", response.text)

    def test_missing_schema_version_keeps_missing_redaction_fail_closed(
        self,
    ) -> None:
        response = self.client.get("/_test/findings-table-default-schema-render")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Evidence content unavailable", response.text)
        self.assertIn("Redaction Unknown", response.text)
        self.assertNotIn("Missing schema summary should fail closed.", response.text)
        self.assertNotIn(
            "/history/15/artifacts?name=plan.json&amp;line=2#L2", response.text
        )

    def test_explicit_v1_schema_preserves_legacy_missing_redaction_readability(
        self,
    ) -> None:
        response = self.client.get("/_test/findings-table-v1-schema-render")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Legacy schema summary remains readable.", response.text)
        self.assertIn("Redaction None", response.text)
        self.assertIn(
            "/history/16/artifacts?name=plan.json&amp;line=3#L3", response.text
        )

    def test_duplicate_or_blank_finding_ids_get_unique_inspector_ids(self) -> None:
        response = self.client.get("/_test/findings-table-duplicate-id-render")

        self.assertEqual(response.status_code, 200)
        controls = re.findall(
            r'"aria-controls":"(evidence-inspector-[^"]+)"', response.text
        )
        self.assertEqual(len(controls), 6)
        self.assertEqual(len(set(controls)), 3)
        self.assertTrue(
            any(
                "finding-row--finding-duplicate-HIGH-duplicate-first" in item
                for item in controls
            )
        )
        self.assertTrue(
            any(
                "finding-row-1-finding-duplicate-HIGH-duplicate-second" in item
                for item in controls
            )
        )
        self.assertTrue(any("HIGH-blank-id" in item for item in controls))

    def test_duplicate_finding_ids_do_not_borrow_stale_fallback_evidence(
        self,
    ) -> None:
        response = self.client.get(
            "/_test/findings-table-duplicate-stale-fallback-render"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("0 evidence items, 1 unavailable", response.text)
        self.assertIn("Evidence unavailable", response.text)
        self.assertIn("Missing evidence refs: 1 unavailable reference", response.text)
        self.assertNotIn("borrowed-plan.json", response.text)
        self.assertNotIn(
            "Borrowed duplicate evidence should not render.", response.text
        )

    def test_findings_grid_keeps_evidence_badges_readable(self) -> None:
        theme_css = Path("ui/theme.py").read_text(encoding="utf-8")

        self.assertIn(
            ".dw-findings-col-evidence {\n  width: min(240px, 100%);", theme_css
        )
        self.assertIn("minmax(220px, 0.7fr)", theme_css)


if __name__ == "__main__":
    unittest.main()
