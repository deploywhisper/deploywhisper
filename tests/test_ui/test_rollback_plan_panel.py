"""Rendered smoke tests for the rollback plan panel."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import app as app_module
from analysis.rollback_planner import RollbackPlan, RollbackStep
from fastapi.testclient import TestClient
from nicegui import ui

from ui.components.rollback_plan import (
    copy_rollback_plan_to_clipboard,
    render_rollback_plan,
)


@ui.page("/_test/rollback-plan-panel")
def rollback_plan_panel_test_page() -> None:
    render_rollback_plan(
        RollbackPlan(
            steps=[
                RollbackStep(
                    order=1,
                    title="Revert aws_security_group.main",
                    detail="Rollback the terraform change safely.",
                    estimated_minutes=15,
                    critical=True,
                ),
                RollbackStep(
                    order=2,
                    title="Restore Deployment/api",
                    detail="Redeploy the prior Kubernetes manifest.",
                    estimated_minutes=8,
                    critical=False,
                ),
            ],
            complexity="medium",
            complexity_score=3,
            complexity_explanation="Score 3/5 because the plan covers 2 rollback steps.",
            warning="Rollback plan may be incomplete because one or more files failed to parse.",
        )
    )


class RollbackPlanPanelRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app_module.create_app())

    def test_rollback_plan_panel_renders_time_estimates_complexity_and_copy_action(
        self,
    ) -> None:
        response = self.client.get("/_test/rollback-plan-panel")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Rollback plan", response.text)
        self.assertIn("Complexity: 3/5 (medium)", response.text)
        self.assertIn("Copy full plan", response.text)
        self.assertIn("Critical path", response.text)
        self.assertIn("~15 min", response.text)
        self.assertIn("~8 min", response.text)
        self.assertIn("Rollback plan may be incomplete", response.text)

    def test_copy_rollback_plan_notifies_success_only_after_confirmed_copy(
        self,
    ) -> None:
        plan = RollbackPlan(
            steps=[
                RollbackStep(
                    order=1,
                    title="Revert aws_security_group.main",
                    detail="Rollback the terraform change safely.",
                    estimated_minutes=15,
                    critical=True,
                )
            ],
            complexity="medium",
            complexity_score=3,
            complexity_explanation="Score 3/5 because the plan covers 1 rollback step.",
            warning=None,
        )

        with (
            patch(
                "ui.components.rollback_plan.ui.run_javascript",
                new=AsyncMock(return_value={"ok": True}),
            ) as run_javascript_mock,
            patch("ui.components.rollback_plan.ui.notify") as notify_mock,
        ):
            asyncio.run(copy_rollback_plan_to_clipboard(plan))

        run_javascript_mock.assert_awaited_once()
        notify_mock.assert_called_once_with("Rollback plan copied.", color="positive")

    def test_copy_rollback_plan_surfaces_browser_copy_failure(self) -> None:
        plan = RollbackPlan(
            steps=[
                RollbackStep(
                    order=1,
                    title="Revert aws_security_group.main",
                    detail="Rollback the terraform change safely.",
                    estimated_minutes=15,
                    critical=True,
                )
            ],
            complexity="medium",
            complexity_score=3,
            complexity_explanation="Score 3/5 because the plan covers 1 rollback step.",
            warning=None,
        )

        with (
            patch(
                "ui.components.rollback_plan.ui.run_javascript",
                new=AsyncMock(return_value={"ok": False, "message": "NotAllowedError"}),
            ) as run_javascript_mock,
            patch("ui.components.rollback_plan.ui.notify") as notify_mock,
        ):
            asyncio.run(copy_rollback_plan_to_clipboard(plan))

        run_javascript_mock.assert_awaited_once()
        notify_mock.assert_called_once_with(
            "Unable to copy rollback plan. NotAllowedError",
            color="warning",
        )


if __name__ == "__main__":
    unittest.main()
