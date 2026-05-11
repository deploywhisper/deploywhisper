"""Rendered smoke tests for context completeness panel."""

from __future__ import annotations

import unittest

import app as app_module
from fastapi.testclient import TestClient
from nicegui import ui


@ui.page("/_test/context-panel")
def context_panel_test_page() -> None:
    from ui.components.context_completeness_panel import (
        render_context_completeness_panel,
    )

    render_context_completeness_panel(
        {
            "topology_freshness_days": 45,
            "topology_last_imported_at": "2026-04-18T11:22:33Z",
            "incident_index_size": 7,
            "evidence_success_rate": 0.5,
            "parser_success_rate": 0.5,
            "parser_success_by_tool": {"terraform": 1.0, "kubernetes": 0.0},
            "context_score": 0.52,
            "uncertainty": "Insufficient context: evidence coverage is partial.",
            "context_todos": [
                "Review evidence extraction gaps for supported artifacts.",
                "Review parser errors and resubmit supported artifacts.",
            ],
        }
    )


class ContextCompletenessPanelRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app_module.create_app())

    def test_context_panel_renders_metrics_warning_and_settings_link(self) -> None:
        response = self.client.get("/_test/context-panel")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Context completeness", response.text)
        self.assertIn('"data-dw-review-section":"context"', response.text)
        self.assertIn('"tabindex":"0"', response.text)
        self.assertIn("Last import", response.text)
        self.assertIn("2026", response.text)
        self.assertIn("Terraform", response.text)
        self.assertIn("Kubernetes", response.text)
        self.assertIn(
            "Insufficient context: evidence coverage is partial.",
            response.text,
        )
        self.assertIn("Evidence coverage", response.text)
        self.assertIn(
            "Review how much topology, evidence, parser, and incident context supported this report.",
            response.text,
        )
        self.assertIn(
            "Higher scores indicate stronger topology freshness, evidence coverage, parser coverage, and incident context.",
            response.text,
        )
        self.assertIn("Context TODOs", response.text)
        self.assertIn(
            "Review evidence extraction gaps for supported artifacts.",
            response.text,
        )
        self.assertIn("/settings", response.text)

    def test_context_panel_shows_settings_link_for_stale_topology_even_with_higher_score(
        self,
    ) -> None:
        @ui.page("/_test/context-panel-stale")
        def stale_context_panel_test_page() -> None:
            from ui.components.context_completeness_panel import (
                render_context_completeness_panel,
            )

            render_context_completeness_panel(
                {
                    "topology_freshness_days": 45,
                    "topology_last_imported_at": "2026-04-18T11:22:33Z",
                    "incident_index_size": 10,
                    "parser_success_rate": 1.0,
                    "parser_success_by_tool": {"terraform": 1.0},
                    "context_score": 0.82,
                }
            )

        response = self.client.get("/_test/context-panel-stale")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Fix in settings", response.text)
        self.assertIn("/settings", response.text)

    def test_context_panel_uses_insufficient_context_flag_at_rounded_boundary(
        self,
    ) -> None:
        @ui.page("/_test/context-panel-rounded-low")
        def rounded_low_context_panel_test_page() -> None:
            from ui.components.context_completeness_panel import (
                render_context_completeness_panel,
            )

            render_context_completeness_panel(
                {
                    "topology_freshness_days": 0,
                    "topology_last_imported_at": "2026-05-11T11:22:33Z",
                    "incident_index_size": 10,
                    "evidence_success_rate": 1.0,
                    "parser_success_rate": 1.0,
                    "parser_success_by_tool": {"terraform": 1.0},
                    "context_score": 0.7,
                    "insufficient_context": True,
                    "uncertainty": "Insufficient context: raw score was below threshold.",
                }
            )

        response = self.client.get("/_test/context-panel-rounded-low")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Insufficient context: raw score was below threshold.",
            response.text,
        )
        self.assertIn("LIMITED CONTEXT", response.text)
        self.assertIn("Review context TODOs", response.text)

    def test_context_panel_warns_when_uncertainty_exists_above_low_threshold(
        self,
    ) -> None:
        @ui.page("/_test/context-panel-uncertainty")
        def uncertainty_context_panel_test_page() -> None:
            from ui.components.context_completeness_panel import (
                render_context_completeness_panel,
            )

            render_context_completeness_panel(
                {
                    "topology_freshness_days": 0,
                    "topology_last_imported_at": "2026-05-11T11:22:33Z",
                    "incident_index_size": 10,
                    "evidence_success_rate": 0.5,
                    "parser_success_rate": 1.0,
                    "parser_success_by_tool": {"terraform": 1.0},
                    "context_score": 0.74,
                    "insufficient_context": False,
                    "uncertainty": "Uncertainty: evidence coverage is partial.",
                    "context_todos": [
                        "Review evidence extraction gaps for supported artifacts."
                    ],
                }
            )

        response = self.client.get("/_test/context-panel-uncertainty")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Uncertainty: evidence coverage is partial.", response.text)
        self.assertIn("LIMITED CONTEXT", response.text)
        self.assertIn("Review evidence", response.text)
        self.assertIn("#context-todos", response.text)
        self.assertIn(
            "Review evidence extraction gaps for supported artifacts.",
            response.text,
        )

    def test_context_panel_degrades_malformed_numeric_context_values(
        self,
    ) -> None:
        @ui.page("/_test/context-panel-malformed")
        def malformed_context_panel_test_page() -> None:
            from ui.components.context_completeness_panel import (
                render_context_completeness_panel,
            )

            render_context_completeness_panel(
                {
                    "topology_freshness_days": 0,
                    "topology_last_imported_at": "2026-05-11T11:22:33Z",
                    "incident_index_size": "many",
                    "evidence_success_rate": "bad",
                    "parser_success_rate": "bad",
                    "parser_success_by_tool": {"terraform": 1.0},
                    "context_score": "oops",
                    "insufficient_context": False,
                    "uncertainty": "Uncertainty: context metadata was malformed.",
                    "context_todos": [
                        "Review parser errors and resubmit supported artifacts."
                    ],
                }
            )

        response = self.client.get("/_test/context-panel-malformed")

        self.assertEqual(response.status_code, 200)
        self.assertIn("LIMITED CONTEXT", response.text)
        self.assertIn("Context score", response.text)
        self.assertIn("0.00 / 1.00", response.text)
        self.assertIn("Review artifacts", response.text)
        self.assertIn("Uncertainty: context metadata was malformed.", response.text)

    def test_context_panel_ignores_scalar_context_todos(
        self,
    ) -> None:
        @ui.page("/_test/context-panel-scalar-todos")
        def scalar_todos_context_panel_test_page() -> None:
            from ui.components.context_completeness_panel import (
                render_context_completeness_panel,
            )

            render_context_completeness_panel(
                {
                    "topology_freshness_days": 0,
                    "topology_last_imported_at": "2026-05-11T11:22:33Z",
                    "incident_index_size": 10,
                    "evidence_success_rate": 1.0,
                    "parser_success_rate": 1.0,
                    "parser_success_by_tool": {"terraform": 1.0},
                    "context_score": 0.92,
                    "insufficient_context": False,
                    "context_todos": "Review parser errors and resubmit supported artifacts.",
                }
            )

        response = self.client.get("/_test/context-panel-scalar-todos")

        self.assertEqual(response.status_code, 200)
        self.assertIn("STRONG CONTEXT", response.text)
        self.assertNotIn("LIMITED CONTEXT", response.text)
        self.assertNotIn("Context TODOs", response.text)
        self.assertNotIn(
            "Review parser errors and resubmit supported artifacts.",
            response.text,
        )


if __name__ == "__main__":
    unittest.main()
