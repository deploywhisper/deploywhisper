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
        self.assertGreater(plan.steps[0].estimated_minutes, 0)

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
        self.assertEqual(plan.complexity, "medium")
        self.assertTrue(plan.warning)
        self.assertEqual(plan.complexity_score, 2)
        self.assertIn("partial parser context", plan.complexity_explanation)

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
        self.assertEqual(plan.complexity_score, 4)

    def test_generate_rollback_plan_skips_noop_and_read_changes(self) -> None:
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="no-op",
                summary="Terraform resource aws_security_group.main has no planned changes.",
            ),
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="data.aws_ami.latest",
                action="read",
                summary="Terraform resource data.aws_ami.latest marked for read.",
            ),
        ]

        plan = generate_rollback_plan(changes)

        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].title, "No rollback steps generated")
        self.assertFalse(plan.steps[0].critical)
        self.assertEqual(plan.steps[0].estimated_minutes, 0)
        self.assertEqual(plan.complexity, "low")
        self.assertEqual(plan.complexity_score, 1)

    def test_generate_rollback_plan_treats_replace_as_destructive(self) -> None:
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_instance.web",
                action="replace",
                summary="Terraform resource aws_instance.web marked for replace.",
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

        self.assertEqual(plan.steps[0].title, "Revert aws_instance.web")
        self.assertTrue(plan.steps[0].critical)
        self.assertGreater(plan.steps[0].estimated_minutes, 10)
        self.assertEqual(plan.complexity_score, 3)
        self.assertIn("destructive change", plan.complexity_explanation)
