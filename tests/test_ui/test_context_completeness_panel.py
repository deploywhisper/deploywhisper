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
            "parser_success_rate": 0.5,
            "parser_success_by_tool": {"terraform": 1.0, "kubernetes": 0.0},
            "context_score": 0.52,
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
            "Context warning: supporting topology or incident history may be stale.",
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


if __name__ == "__main__":
    unittest.main()
