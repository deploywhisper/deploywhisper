"""Tests for blast radius analysis."""

from __future__ import annotations

import unittest

from analysis.blast_radius import compute_blast_radius
from parsers.base import UnifiedChange


class BlastRadiusTests(unittest.TestCase):
    def test_compute_blast_radius_returns_direct_and_transitive_impact(self) -> None:
        topology = {
            "services": [
                {
                    "id": "database",
                    "label": "Database",
                    "resource_keys": ["aws_security_group.main"],
                    "downstream": ["api"],
                },
                {
                    "id": "api",
                    "label": "API Service",
                    "resource_keys": ["Deployment/api"],
                    "downstream": [],
                },
            ]
        }
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Terraform changed a security group.",
            )
        ]
        result = compute_blast_radius(changes, topology)
        self.assertEqual(result.direct_count, 1)
        self.assertEqual(result.transitive_count, 1)
        self.assertIsNone(result.warning)

    def test_compute_blast_radius_warns_when_no_matches_found(self) -> None:
        topology = {
            "services": [
                {
                    "id": "api",
                    "label": "API Service",
                    "resource_keys": ["Deployment/api"],
                    "downstream": [],
                }
            ]
        }
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Terraform changed a security group.",
            )
        ]
        result = compute_blast_radius(changes, topology)
        self.assertTrue(result.warning)
        self.assertIn("no topology mapping found", result.warning)
        self.assertEqual(result.unmatched_resources, ["aws_security_group.main"])
