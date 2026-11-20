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

    def test_catalog_metadata_uses_caller_screening_context(self):
        arn = "arn:aws:lambda:us-east-1:000000000000:function:example"
        entry = self.descriptor("function_tags", {"Resource": arn})
        private = "synthetic-private-value"
        response = {"Tags": {"owner": private, "purpose": "public-service"}}
        result = project_response(
            entry, response, scope=None, sensitive_values=(private,)
        )
        self.assertFalse(result.complete)
        self.assertNotIn(private, repr(result))
        self.assertIn("public-service", [fact.value for fact in result.facts])

    def test_literal_tag_map_keys_are_not_treated_as_response_structure(self):
        arn = "arn:aws:lambda:us-east-1:000000000000:function:example"
        entry = self.descriptor("function_tags", {"Resource": arn})
        tags = {"tags": "public", "tagset": "local", "key": "team", "value": "web"}
        result = project_response(entry, {"Tags": tags}, scope=None)
        self.assertTrue(result.complete)
        self.assertEqual(
            {fact.name: fact.value for fact in result.facts},
            {f"function_tags.Tags.{key}": value for key, value in tags.items()},
        )

    def test_rds_tag_lists_screen_other_selected_fields(self):
        private = "synthetic-private-metadata"
        for capability, container, identifier, replicas in (
            (
                "db",
                "DBInstances",
                "DBInstanceIdentifier",
                "ReadReplicaDBInstanceIdentifiers",
            ),
            (
                "db_cluster",
                "DBClusters",
                "DBClusterIdentifier",
                "ReadReplicaIdentifiers",
            ),
        ):
            with self.subTest(capability=capability):
                entry = self.descriptor(capability, {identifier: "example"})
                response = {
                    container: [
                        {
                            identifier: "example",
                            replicas: [private, "public-replica"],
                            "TagList": [{"Key": "password", "Value": private}],
                        }
                    ]
                }
                result = project_response(entry, response, scope=None)
                self.assertFalse(result.complete)
                self.assertNotIn(private, repr(result))
                self.assertIn("public-replica", [fact.value for fact in result.facts])

    def test_screening_compares_equivalent_numeric_facts(self):
        entry = self.descriptor("db", {"DBInstanceIdentifier": "example"})
        response = {
            "DBInstances": [
                {
                    "DBInstanceIdentifier": "example",
                    "DBInstanceStatus": "available",
                    "BackupRetentionPeriod": 37,
                }
            ]
        }
        result = project_response(
            entry, response, scope=None, sensitive_values=("37.00",)
        )
        self.assertFalse(result.complete)
        self.assertNotIn(37, [fact.value for fact in result.facts])
        self.assertIn("available", [fact.value for fact in result.facts])

    def test_screening_compares_equivalent_numeric_tag_keys_and_values(self):
        arn = "arn:aws:lambda:us-east-1:000000000000:function:example"
        entry = self.descriptor("function_tags", {"Resource": arn})
        response = {
            "Tags": {
                "037.0": "private-key-sample",
                "owner": "ticket-0037",
                "purpose": "public-metadata",
            }
        }
        result = project_response(
            entry, response, scope=None, sensitive_values=("37.00",)
        )
        self.assertFalse(result.complete)
        self.assertNotIn("037.0", repr(result))
        self.assertNotIn("0037", repr(result))
        self.assertIn("public-metadata", [fact.value for fact in result.facts])

    def test_redrive_policy_accepts_selected_scalar_fields(self):
        entry = self.descriptor(
            "queue", fixtures.render(_CATALOG["operations"]["queue"]["params"])
        )
        dead_letter = "arn:aws:sqs:us-east-1:000000000000:dead-letter"
        for count in (5, "5"):
            with self.subTest(count=count):
                attributes = {
                    **fixtures.OTHER["queue"]["Attributes"],
                    "RedrivePolicy": json.dumps(
                        {"deadLetterTargetArn": dead_letter, "maxReceiveCount": count}
                    ),
                }
                result = project_response(entry, {"Attributes": attributes}, scope=None)
                self.assertTrue(result.complete)
                self.assertEqual(
                    {
                        fact.name.rsplit(".", 1)[-1]: fact.value
                        for fact in result.facts
                        if ".RedrivePolicy." in fact.name
                    },
                    {"deadLetterTargetArn": dead_letter, "maxReceiveCount": count},
                )

    def test_redrive_policy_rejects_non_scalar_and_invalid_count_shapes(self):
        entry = self.descriptor(
            "queue", fixtures.render(_CATALOG["operations"]["queue"]["params"])
        )
        dead_letter = "arn:aws:sqs:us-east-1:000000000000:dead-letter"
        for policy in (
            {"deadLetterTargetArn": dead_letter, "maxReceiveCount": 5},
            json.dumps({"deadLetterTargetArn": [dead_letter], "maxReceiveCount": 5}),
            json.dumps({"deadLetterTargetArn": dead_letter, "maxReceiveCount": True}),
            json.dumps({"deadLetterTargetArn": dead_letter, "maxReceiveCount": "many"}),
        ):
            with self.subTest(policy=policy):
                response = {
                    "Attributes": {
                        **fixtures.OTHER["queue"]["Attributes"],
                        "RedrivePolicy": policy,
                    }
                }
                result = project_response(entry, response, scope=None)
                self.assertFalse(result.complete)
                self.assertFalse(
                    any("RedrivePolicy" in fact.name for fact in result.facts)
                )

    def test_redrive_policy_preserves_public_leaf_when_private_count_is_screened(self):
        entry = self.descriptor(
            "queue", fixtures.render(_CATALOG["operations"]["queue"]["params"])
        )
        dead_letter = "arn:aws:sqs:us-east-1:000000000000:dead-letter"
        for count, private in ((37, "37"), (37, "37.00"), ("037", "37.00")):
            with self.subTest(count=count, private=private):
                attributes = {
                    **fixtures.OTHER["queue"]["Attributes"],
                    "RedrivePolicy": json.dumps(
                        {"deadLetterTargetArn": dead_letter, "maxReceiveCount": count}
                    ),
                }
                result = project_response(
                    entry,
                    {"Attributes": attributes},
                    scope=None,
                    sensitive_values=(private,),
                )
                self.assertFalse(result.complete)
                self.assertIn(dead_letter, [fact.value for fact in result.facts])
                self.assertNotIn(count, [fact.value for fact in result.facts])
