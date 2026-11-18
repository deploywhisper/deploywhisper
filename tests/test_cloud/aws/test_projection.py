"""Selected projection refuses identity substitution and raw secret payloads."""

from __future__ import annotations

import copy
import json
import unittest

from cloud.aws.projection import project_response
from cloud.aws.allowlist import _CATALOG
from cloud.reflection import (
    BoundCall,
    ReflectionTarget,
    build_manifest,
    extract_resources,
)
from tests.test_cloud.test_reflection import plan
from tests.test_cloud.aws import test_response_status as fixtures


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.target = ReflectionTarget(
            account_id="000000000000", regions=("us-east-1",)
        )

    def descriptor(self, capability, parameters, expected=()):
        # Descriptor validation uses the frozen request schema; these response
        # fixtures test projection only, not source authority (covered separately).
        return BoundCall(
            address="example.resource",
            capability=capability,
            region="us-east-1",
            parameters_json=json.dumps(parameters),
            expected=expected,
            hop=0,
            reason="direct",
            max_results=100,
        )

    def test_every_frozen_capability_projects_only_selected_scalars(self):
        responses = {**fixtures.DIRECT, **fixtures.RELATIONS, **fixtures.OTHER}
        self.assertEqual(set(responses), set(_CATALOG["operations"]))
        for key, response in responses.items():
            params = fixtures.render(_CATALOG["operations"][key]["params"])
            expected = ()
            if key == "record":
                expected = (
                    ("Name", params["StartRecordName"]),
                    ("Type", params["StartRecordType"]),
                    ("SetIdentifier", None),
                )
            if key == "event_mapping":
                expected = tuple(
                    (name, response["EventSourceMappings"][0][name])
                    for name in ("UUID", "FunctionArn", "EventSourceArn")
                )
            entry = self.descriptor(key, params, expected)
            # Reverse endpoint expansion needs an authoritative manifest, so its
            # exact path is exercised through AwsPlanCollector tests instead.
            if key == "target_health":
                entry = entry.model_copy(update={"capability": "target_health"})
            supplied = copy.deepcopy(response)
            supplied["unselected_private"] = "private-body"
            if key == "target_health":
                source = plan(
                    "aws_lb_target_group",
                    {
                        "id": "arn:aws:elasticloadbalancing:us-east-1:000000000000:targetgroup/example/0000000000000001"
                    },
                )
                manifest = build_manifest(
                    extract_resources(source, target=self.target), target=self.target
                )
                entry = next(e for e in manifest.entries if e.capability == key)
                params = entry.call().parameters
                scope = (manifest, self.target, manifest.resources)
            else:
                scope = (None, self.target, ())
            result = project_response(entry, supplied, scope=scope)
            self.assertNotIn("private-body", repr(result))
            self.assertTrue(result.complete, key)
            self.assertLessEqual(len(result.facts), 1000)
            missing = project_response(entry, {}, scope=scope)
            self.assertFalse(missing.complete, key)

    def test_wrong_direct_resource_has_no_facts(self):
        entry = self.descriptor("instance", {"InstanceIds": ["i-00000000000000001"]})
        result = project_response(
            entry,
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-00000000000000002",
                                "State": {"Name": "stopped"},
                            }
                        ]
                    }
                ]
            },
            scope=(None, self.target, ()),
        )
        self.assertFalse(result.complete)
        self.assertEqual(result.facts, ())

    def test_event_mapping_exact_child_and_parent_identity(self):
        function = "arn:aws:lambda:us-east-1:000000000000:function:example"
        event = "arn:aws:sqs:us-east-1:000000000000:queue"
        entry = self.descriptor(
            "event_mapping",
            {"FunctionName": function, "EventSourceArn": event, "MaxItems": 100},
            (("UUID", "wanted"), ("FunctionArn", function), ("EventSourceArn", event)),
        )
        response = {
            "EventSourceMappings": [
                {"UUID": "wrong", "FunctionArn": function, "EventSourceArn": event}
            ]
        }
        self.assertEqual(
            project_response(entry, response, scope=(None, self.target, ())).facts, ()
        )
        response["EventSourceMappings"][0]["UUID"] = "wanted"
        self.assertTrue(
            project_response(entry, response, scope=(None, self.target, ())).complete
        )

    def test_route53_simple_null_variant_and_exact_weighted_selector(self):
        params = {
            "HostedZoneId": "Z1",
            "StartRecordName": "example.com.",
            "StartRecordType": "A",
            "MaxItems": "1",
        }
        expected = (("Name", "example.com."), ("Type", "A"), ("SetIdentifier", None))
        entry = self.descriptor("record", params, expected)
        record = {"Name": "example.com.", "Type": "A"}
        self.assertTrue(
            project_response(
                entry, {"ResourceRecordSets": [record]}, scope=(None, self.target, ())
            ).complete
        )
        record["SetIdentifier"] = None
        self.assertFalse(
            project_response(
                entry, {"ResourceRecordSets": [record]}, scope=(None, self.target, ())
            ).complete
        )
        weighted = entry.model_copy(
            update={
                "expected": (
                    ("Name", "example.com."),
                    ("Type", "A"),
                    ("SetIdentifier", "blue"),
                )
            }
        )
        record["SetIdentifier"] = "blue"
        self.assertTrue(
            project_response(
                weighted,
                {"ResourceRecordSets": [record]},
                scope=(None, self.target, ()),
            ).complete
        )
        self.assertFalse(
            project_response(
                weighted,
                {"ResourceRecordSets": [record], "IsTruncated": True},
                scope=(None, self.target, ()),
            ).complete
        )
        record["Name"] = "other.com."
        self.assertFalse(
            project_response(
                weighted,
                {"ResourceRecordSets": [record]},
                scope=(None, self.target, ()),
            ).complete
        )

    def test_screening_bounds_fail_closed_before_projected_output(self):
        entry = self.descriptor("instance", {"InstanceIds": ["i-00000000000000001"]})
        with self.assertRaises(ValueError):
            project_response(
                entry, {"huge": "x" * 16385}, scope=(None, self.target, ())
            )

    def test_ecs_lowercase_tags_are_screened_before_worker_publication(self):
        from unittest.mock import Mock
        from cloud.aws.client import AwsReader

        secret = "synthetic-ecs-password-canary"
        arn = "arn:aws:ecs:us-east-1:000000000000:cluster/example"
        source = plan("aws_ecs_cluster", {"id": arn})
        rows = extract_resources(source, target=self.target)
        manifest = build_manifest(rows, target=self.target)
        for key_field, value_field in (
            ("key", "value"),
            ("Key", "Value"),
            ("kEy", "vAlUe"),
        ):
            response = {
                "clusters": [
                    {
                        "clusterArn": arn,
                        "tags": [
                            {key_field: "password", value_field: secret},
                            {key_field: "owner", value_field: secret},
                        ],
                    }
                ]
            }
            with self.subTest(key_field=key_field):
                sdk = Mock()
                sdk.create_client.return_value._make_api_call.return_value = response
                result = AwsReader(sdk).execute_selected(
                    manifest, indices=(0,), target=self.target, resources=rows
                )
                self.assertNotIn(secret, repr(result))
                self.assertNotIn(secret, repr(result.items[0].facts))
                self.assertEqual(result.items[0].status, "incomplete")

    def test_secret_in_dynamic_fact_key_is_not_published(self):
        from unittest.mock import Mock
        from cloud.aws.client import AwsReader

        secret = "offline-private-canary"
        arn = "arn:aws:lambda:us-east-1:000000000000:function:example"
        source = plan("aws_lambda_function", {"id": "example", "arn": arn})
        rows = extract_resources(source, target=self.target)
        manifest = build_manifest(rows, target=self.target)
        index = next(
            i for i, e in enumerate(manifest.entries) if e.capability == "function_tags"
        )
        sdk = Mock()
        sdk.create_client.return_value._make_api_call.return_value = {
            "Tags": {"password": secret, secret: "public"}
        }
        result = AwsReader(sdk).execute_selected(
            manifest, indices=(index,), target=self.target, resources=rows
        )
        self.assertNotIn(secret, repr(result))
        self.assertEqual(result.items[0].status, "incomplete")

    def test_malformed_numeric_tag_value_fails_closed(self):
        entry = self.descriptor(
            "ecs_cluster",
            {
                "clusters": ["arn:aws:ecs:us-east-1:000000000000:cluster/example"],
                "include": ["STATISTICS", "TAGS"],
            },
        )
        response = {
            "clusters": [
                {
                    "clusterArn": entry.call().parameters["clusters"][0],
                    "tags": [
                        {"key": "password", "value": 8675309},
                        {"key": "owner", "value": 8675309},
                    ],
                }
            ]
        }
        with self.assertRaises(ValueError):
            project_response(entry, response, scope=(None, self.target, ()))
