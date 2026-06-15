"""Rendered smoke tests for the blast radius panel."""

from __future__ import annotations

import unittest

import app as app_module
from fastapi.testclient import TestClient
from nicegui import ui

from analysis.blast_radius import BlastRadiusResult, ImpactNode
from ui.components.blast_radius_graph import render_blast_radius_panel


@ui.page("/_test/blast-radius-panel")
def blast_radius_panel_test_page() -> None:
    render_blast_radius_panel(
        BlastRadiusResult(
            affected=[
                ImpactNode(
                    service_id="database",
                    label="Primary Database",
                    depth=0,
                    dependencies=[],
                    owners=["sre"],
                ),
                ImpactNode(
                    service_id="api",
                    label="Payments API",
                    depth=1,
                    dependencies=["database"],
                    owners=["payments"],
                ),
                ImpactNode(
                    service_id="worker",
                    label="Fulfillment Worker",
                    depth=1,
                    dependencies=["database"],
                    owners=["fulfillment"],
                ),
            ],
            direct_count=1,
            transitive_count=2,
            warning=None,
            unmatched_resources=[],
            context_source={"type": "custom", "ref": "topology.json"},
            freshness={"updated_at": "2026-06-08T12:00:00Z", "age_days": 1},
            context_state="current",
            context_limitations=[],
        ),
        severity="high",
    )


@ui.page("/_test/blast-radius-panel-legacy")
def blast_radius_panel_legacy_test_page() -> None:
    render_blast_radius_panel(
        BlastRadiusResult.model_validate(
            {
                "affected": [
                    {
                        "service_id": "api",
                        "label": "Payments API",
                        "depth": 0,
                    }
                ],
                "direct_count": 1,
                "transitive_count": 0,
                "warning": None,
                "unmatched_resources": [],
            }
        ),
        severity="low",
    )


@ui.page("/_test/blast-radius-panel-malformed-freshness")
def blast_radius_panel_malformed_freshness_test_page() -> None:
    render_blast_radius_panel(
        BlastRadiusResult(
            affected=[],
            direct_count=0,
            transitive_count=0,
            warning=None,
            unmatched_resources=[],
            freshness={"updated_at": "unknown", "age_days": "unknown"},
            context_state="current",
        ),
        severity="low",
    )


@ui.page("/_test/blast-radius-panel-malformed-additive-fields")
def blast_radius_panel_malformed_additive_fields_test_page() -> None:
    render_blast_radius_panel(
        BlastRadiusResult.model_validate(
            {
                "affected": [
                    {
                        "service_id": "api",
                        "label": "Payments API",
                        "depth": 0,
                        "dependencies": None,
                        "owners": None,
                    }
                ],
                "direct_count": 1,
                "transitive_count": 0,
                "warning": None,
                "unmatched_resources": [],
                "context_source": {"type": {"kind": "custom"}, "ref": "topology.json"},
                "freshness": {"updated_at": {"bad": "value"}, "age_days": []},
                "context_state": {"state": "missing"},
                "context_limitations": "legacy",
            }
        ),
        severity="low",
    )


@ui.page("/_test/blast-radius-panel-negative-freshness")
def blast_radius_panel_negative_freshness_test_page() -> None:
    render_blast_radius_panel(
        BlastRadiusResult(
            affected=[],
            direct_count=0,
            transitive_count=0,
            warning=None,
            unmatched_resources=[],
            freshness={"updated_at": "2026-06-08T12:00:00Z", "age_days": -3},
            context_state="current",
        ),
        severity="low",
    )


@ui.page("/_test/blast-radius-panel-incomplete")
def blast_radius_panel_incomplete_test_page() -> None:
    render_blast_radius_panel(
        BlastRadiusResult(
            affected=[],
            direct_count=0,
            transitive_count=0,
            warning="Blast radius may be incomplete.",
            unmatched_resources=["aws_security_group.main"],
        ),
        severity="high",
    )


class BlastRadiusPanelRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app_module.create_app())

    def test_blast_radius_panel_renders_graph_and_text_equivalent(self) -> None:
        response = self.client.get("/_test/blast-radius-panel")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Blast radius", response.text)
        self.assertIn('"data-dw-review-section":"blast-radius"', response.text)
        self.assertIn('"tabindex":"0"', response.text)
        self.assertIn("1 services directly affected, 2 transitively", response.text)
        self.assertIn("Primary Database", response.text)
        self.assertIn("Payments API", response.text)
        self.assertIn("Fulfillment Worker", response.text)
        self.assertIn("Owner: sre", response.text)
        self.assertIn("Depends on: database", response.text)
        self.assertIn("Topology source: custom · topology.json", response.text)
        self.assertIn("Topology freshness: 1 day old", response.text)
        self.assertIn("plotly", response.text.lower())

    def test_blast_radius_panel_does_not_mark_legacy_payload_missing(
        self,
    ) -> None:
        response = self.client.get("/_test/blast-radius-panel-legacy")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Payments API", response.text)
        self.assertNotIn("Topology context: missing", response.text)

    def test_blast_radius_panel_handles_malformed_freshness(self) -> None:
        response = self.client.get("/_test/blast-radius-panel-malformed-freshness")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Topology freshness: unknown", response.text)

    def test_blast_radius_panel_handles_malformed_additive_fields(self) -> None:
        response = self.client.get(
            "/_test/blast-radius-panel-malformed-additive-fields"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Payments API", response.text)
        self.assertIn("Topology source: unknown", response.text)
        self.assertIn("Topology freshness: unknown", response.text)

    def test_blast_radius_panel_handles_negative_freshness(self) -> None:
        response = self.client.get("/_test/blast-radius-panel-negative-freshness")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Topology freshness: unknown", response.text)
        self.assertNotIn("-3 days old", response.text)

    def test_blast_radius_panel_uses_warning_text_for_incomplete_empty_state(
        self,
    ) -> None:
        response = self.client.get("/_test/blast-radius-panel-incomplete")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Blast radius may be incomplete.", response.text)
        self.assertNotIn("No downstream dependencies found.", response.text)


if __name__ == "__main__":
    unittest.main()
