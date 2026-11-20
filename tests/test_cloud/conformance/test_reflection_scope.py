"""An enumerating connector cannot widen a plan-derived request manifest."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from cloud.collection import AwsPlanCollector
from cloud.reflection import (
    ReflectionError,
    ReflectionTarget,
    build_manifest,
    extract_resources,
    guard_manifest,
)
from tests.test_cloud.test_reflection import plan


class ReflectionScopeTests(unittest.TestCase):
    def test_enumerating_connector_fails_before_dispatch(self):
        target = ReflectionTarget(account_id="000000000000", regions=("us-east-1",))
        resources = extract_resources(plan(), target=target)
        expected = build_manifest(resources, target=target)

        def enumerate_account(manifest):
            broad = manifest.entries[0].model_copy(update={"parameters_json": "{}"})
            return manifest.model_copy(update={"entries": (broad,)})

        with self.assertRaises(ReflectionError):
            guard_manifest(
                enumerate_account(expected), target=target, resources=resources
            )
        session = Mock()
        collector = AwsPlanCollector(target=target, session=session)
        with self.assertRaises(ReflectionError):
            collector.collect_manifest(
                enumerate_account(expected),
                resources=resources,
                project_id=1,
                scope_id="test-scope",
            )
        session.create_client.assert_not_called()

    def test_coherent_new_resource_set_does_not_replace_private_scope(self):
        target = ReflectionTarget(account_id="000000000000", regions=("us-east-1",))
        original = extract_resources(plan(), target=target)
        other = plan()
        other["resource_changes"][0]["address"] = "aws_instance.unrequested"
        other["resource_changes"][0]["change"]["before"]["id"] = "i-00000000000000002"
        forged = build_manifest(extract_resources(other, target=target), target=target)
        with self.assertRaises(ReflectionError):
            guard_manifest(forged, target=target, resources=original)
