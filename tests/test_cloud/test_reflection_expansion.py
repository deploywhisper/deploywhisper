"""Reverse observations are bounded one-hop metadata, never request seeds."""

from __future__ import annotations

import unittest
from cloud.base import ResourceIdentity
from cloud.reflection import (
    ReflectionError,
    ReflectionTarget,
    build_manifest,
    expand_one_hop,
    extract_resources,
)
from tests.test_cloud.test_reflection import plan


class ReflectionExpansionTests(unittest.TestCase):
    def setUp(self):
        self.target = ReflectionTarget(
            account_id="000000000000", regions=("us-east-1",)
        )
        self.manifest = build_manifest(
            extract_resources(
                plan("aws_security_group", {"id": "sg-00000000000000001"}),
                target=self.target,
            ),
            target=self.target,
        )

    def test_reverse_calls_are_static_one_hop_with_reason_and_bound(self):
        self.assertEqual(len(self.manifest.entries), 4)
        reverse = [e for e in self.manifest.entries if e.hop == 1]
        self.assertEqual(len(reverse), 3)
        endpoint = ResourceIdentity(
            address="dependent.eni",
            resource_type="aws_network_interface",
            physical_id="eni-00000000000000002",
        )
        expansion = expand_one_hop(
            self.manifest, reverse[0], (endpoint,), target=self.target
        )
        self.assertEqual(expansion.hop, 1)
        self.assertTrue(expansion.reason)
        self.assertEqual(expansion.endpoints, (endpoint,))
        self.assertLessEqual(expansion.limit, 100)
        self.assertEqual(len(self.manifest.entries), 4)
        self.assertNotIn("eni-00000000000000002", self.manifest.model_dump_json())

    def test_second_hop_or_forged_call_is_denied(self):
        reverse = next(e for e in self.manifest.entries if e.hop)
        with self.assertRaises(ReflectionError):
            expand_one_hop(
                self.manifest,
                reverse.model_copy(update={"hop": 2}),
                (),
                target=self.target,
            )
        with self.assertRaises(ReflectionError):
            expand_one_hop(
                self.manifest, self.manifest.entries[0], (), target=self.target
            )

    def test_expansion_capacity_is_labelled(self):
        reverse = next(e for e in self.manifest.entries if e.hop)
        endpoints = tuple(
            ResourceIdentity(
                address=f"dependent.{i}",
                resource_type="aws_network_interface",
                physical_id=f"eni-{i:017x}",
            )
            for i in range(101)
        )
        result = expand_one_hop(self.manifest, reverse, endpoints, target=self.target)
        self.assertTrue(result.truncated)
        self.assertEqual(len(result.endpoints), 100)
