"""Tests for rollback planning."""

from __future__ import annotations

import unittest

from analysis.rollback_planner import generate_rollback_plan
from parsers.base import UnifiedChange


class RollbackPlannerTests(unittest.TestCase):
    def test_generate_rollback_plan_orders_steps_from_last_change_back(self) -> None:
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="destroy",
                summary="Terraform changed a security group.",
            ),
            UnifiedChange(
                source_file="deployment.yaml",
                tool="kubernetes",
                resource_id="Deployment/api",
                action="modify",
                summary="Kubernetes deployment changed.",
            ),
        ]
        plan = generate_rollback_plan(changes)
        self.assertEqual(plan.steps[0].title, "Revert aws_security_group.main")
        self.assertEqual(plan.steps[1].title, "Revert Deployment/api")
        self.assertTrue(plan.steps[0].critical)

    def test_generate_rollback_plan_sets_warning_on_partial_context(self) -> None:
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Terraform changed a security group.",
            )
        ]
        plan = generate_rollback_plan(changes, partial_context=True)
        self.assertEqual(plan.complexity, "low")
        self.assertTrue(plan.warning)

    def test_generate_rollback_plan_detects_high_complexity(self) -> None:
        changes = [
            UnifiedChange(
                source_file=f"file-{index}.json",
                tool="terraform",
                resource_id=f"resource-{index}",
                action="destroy",
                summary="Terraform destroy action.",
            )
            for index in range(3)
        ]
        plan = generate_rollback_plan(changes)
        self.assertEqual(plan.complexity, "high")
