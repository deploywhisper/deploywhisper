"""Rendered smoke tests for the findings table evidence inspector."""

from __future__ import annotations

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
                "evidence_refs": ["ev-001", "ev-002"],
            }
        ],
        evidence_items=[
            {
                "evidence_id": "ev-001",
                "source_type": "artifact",
                "source_ref": "terraform://plan.json#L2",
                "summary": "Terraform changed a security group.",
                "severity_hint": "high",
                "deterministic": True,
                "determinism_level": "deterministic",
                "confidence": 1.0,
            },
            {
                "evidence_id": "ev-002",
                "source_type": "topology",
                "source_ref": "topology://payments/api#line=18",
                "summary": "Topology maps the gateway to the payments service.",
                "severity_hint": "medium",
                "deterministic": True,
                "determinism_level": "deterministic",
                "confidence": 0.9,
            },
        ],
        artifact_names=["plan.json"],
        report_id=14,
        expanded_finding_ids={"finding-001"},
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
        self.assertIn('"aria-controls":"evidence-inspector-finding-001"', response.text)
        self.assertIn('"data-dw-review-section":"evidence"', response.text)
        self.assertIn("SYSTEM: payments", response.text)
        self.assertIn("Artifact", response.text)
        self.assertIn("Topology", response.text)
        self.assertIn("networking/ingress", response.text)
        self.assertIn("2 evidence items", response.text)
        self.assertIn("External", response.text)
        self.assertIn("Evidence Law satisfied", response.text)

    def test_findings_grid_keeps_evidence_badges_readable(self) -> None:
        theme_css = Path("ui/theme.py").read_text(encoding="utf-8")

        self.assertIn(
            ".dw-findings-col-evidence {\n  width: min(240px, 100%);", theme_css
        )
        self.assertIn("minmax(220px, 0.7fr)", theme_css)


if __name__ == "__main__":
    unittest.main()
