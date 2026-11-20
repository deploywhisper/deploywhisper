"""Only recorded identities can generate exact frozen AWS read requests."""

from __future__ import annotations

import unittest

from cloud.reflection import (
    ReflectionError,
    ReflectionTarget,
    build_manifest,
    extract_resources,
    guard_manifest,
)
from tests.test_cloud.test_reflection import plan


class ReflectionManifestTests(unittest.TestCase):
    def setUp(self):
        self.target = ReflectionTarget(
            account_id="000000000000", regions=("us-east-1",)
        )

    def manifest(self, source):
        return build_manifest(
            extract_resources(source, target=self.target), target=self.target
        )

    def test_exact_frozen_calls_and_mutation_rejected(self):
        manifest = self.manifest(plan())
        self.assertEqual(manifest.planned_calls, 2)
        self.assertEqual(
            [e.capability for e in manifest.entries],
            ["instance", "termination_protection"],
        )
        self.assertEqual(guard_manifest(manifest, target=self.target), manifest)
        entry = manifest.entries[0].model_copy(
            update={"parameters_json": '{"InstanceIds":["i-00000000000000002"]}'}
        )
        forged = manifest.model_copy(update={"entries": (entry, *manifest.entries[1:])})
        with self.assertRaises(ReflectionError):
            guard_manifest(forged, target=self.target)
        entry = manifest.entries[0].model_copy(
            update={"parameters_json": '{"Filters":[]}'}
        )
        with self.assertRaises(ReflectionError):
            guard_manifest(
                manifest.model_copy(update={"entries": (entry,)}), target=self.target
            )

    def test_manifest_cannot_replay_in_another_opaque_account_scope(self):
        original = self.manifest(plan())
        other = ReflectionTarget(account_id="111111111111", regions=("us-east-1",))
        with self.assertRaises(ReflectionError):
            guard_manifest(original, target=other, resources=original.resources)

    def test_missing_parents_do_not_broaden(self):
        source = plan(
            "aws_ecs_service",
            {"id": "arn:aws:ecs:us-east-1:000000000000:service/example"},
        )
        result = self.manifest(source)
        self.assertEqual(result.entries, ())
        self.assertEqual(result.issues[0].cause, "missing_selector")

    def test_queue_url_rebuilt_and_account_scope_checked(self):
        source = plan(
            "aws_sqs_queue",
            {"id": "https://attacker.invalid/stolen", "name": "queue.fifo"},
        )
        result = self.manifest(source)
        queue = next(e for e in result.entries if e.capability == "queue")
        self.assertEqual(
            queue.call().parameters["QueueUrl"],
            "https://sqs.us-east-1.amazonaws.com/000000000000/queue.fifo",
        )
        self.assertNotIn("attacker", result.model_dump_json())
        source = plan(
            "aws_lambda_function",
            {
                "id": "example",
                "arn": "arn:aws:lambda:us-east-1:111111111111:function:example",
            },
        )
        with self.assertRaises(ReflectionError):
            self.manifest(source)

    def test_expected_mapping_uuid_and_dns_variant_stay_outside_call(self):
        source = plan(
            "aws_lambda_event_source_mapping",
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "function_arn": "arn:aws:lambda:us-east-1:000000000000:function:example",
                "event_source_arn": "arn:aws:sqs:us-east-1:000000000000:queue",
            },
        )
        entry = self.manifest(source).entries[0]
        self.assertEqual(
            dict(entry.expected)["UUID"], "00000000-0000-0000-0000-000000000001"
        )
        self.assertNotIn("UUID", entry.call().parameters)
        source = plan(
            "aws_route53_record",
            {
                "id": "Z1_example_A_blue",
                "zone_id": "Z1",
                "name": "example.invalid.",
                "type": "A",
                "set_identifier": "blue",
            },
        )
        entry = self.manifest(source).entries[0]
        self.assertEqual(dict(entry.expected)["SetIdentifier"], "blue")
        self.assertNotIn("SetIdentifier", entry.call().parameters)

    def test_capacity_is_explicit_and_pure_create_is_successful(self):
        result = build_manifest(
            extract_resources(plan(), target=self.target),
            target=self.target,
            max_calls=1,
        )
        self.assertEqual(result.planned_calls, 2)
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.issues[-1].cause, "manifest_capacity")
        self.assertEqual(guard_manifest(result, target=self.target), result)
        source = plan(actions=["create"])
        source["resource_changes"][0]["change"]["before"] = None
        result = self.manifest(source)
        self.assertEqual(result.entries, ())
        self.assertEqual(result.issues, ())

    def test_region_is_bound_or_ambiguous_not_fanned_out(self):
        target = ReflectionTarget(
            account_id="000000000000", regions=("us-east-1", "us-west-2")
        )
        result = build_manifest(extract_resources(plan(), target=target), target=target)
        self.assertEqual(result.entries, ())
        self.assertEqual({i.cause for i in result.issues}, {"ambiguous_region"})
        source = plan(
            "aws_lambda_function",
            {
                "id": "example",
                "arn": "arn:aws:lambda:us-west-2:000000000000:function:example",
            },
        )
        result = build_manifest(extract_resources(source, target=target), target=target)
        self.assertEqual({e.region for e in result.entries}, {"us-west-2"})

    def test_multiregion_lambda_mapping_and_global_route53_are_exactly_bound(self):
        target = ReflectionTarget(
            account_id="000000000000", regions=("us-west-2", "us-east-1")
        )
        mapping = plan(
            "aws_lambda_event_source_mapping",
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "function_arn": "arn:aws:lambda:us-west-2:000000000000:function:example",
                "event_source_arn": "arn:aws:sqs:us-west-2:000000000000:queue",
            },
        )
        record = plan(
            "aws_route53_record",
            {
                "id": "Z1_example_A",
                "zone_id": "Z1",
                "name": "example.invalid.",
                "type": "A",
            },
        )
        source = {
            "format_version": "1.2",
            "resource_changes": [
                *mapping["resource_changes"],
                *record["resource_changes"],
            ],
        }
        result = build_manifest(extract_resources(source, target=target), target=target)
        self.assertEqual(
            {entry.capability: entry.region for entry in result.entries},
            {"event_mapping": "us-west-2", "record": "us-east-1"},
        )
        self.assertEqual(result.issues, ())

    def test_queue_arn_agrees_with_canonical_name_in_extraction_and_guard(self):
        source = plan(
            "aws_sqs_queue",
            {"name": "example", "arn": "arn:aws:sqs:us-east-1:000000000000:different"},
        )
        with self.assertRaises(ReflectionError):
            self.manifest(source)
        before = source["resource_changes"][0]["change"]["before"]
        before["id"] = before.pop("arn")
        with self.assertRaises(ReflectionError):
            self.manifest(source)
        before.pop("id")
        before["arn"] = "arn:aws:sqs:us-east-1:000000000000:example"
        manifest = self.manifest(source)
        row = manifest.resources[0]
        different = "arn:aws:sqs:us-east-1:000000000000:different"
        selectors = dict(row.selectors, arn=different)
        forged_row = row.model_copy(
            update={
                "identity": row.identity.model_copy(update={"arn": different}),
                "selectors": tuple(selectors.items()),
            }
        )
        forged = manifest.model_copy(update={"resources": (forged_row,)})
        with self.assertRaises(ReflectionError):
            guard_manifest(forged, target=self.target, resources=(forged_row,))

    def test_call_copies_cannot_change_bound_manifest(self):
        result = self.manifest(plan())
        copy = result.entries[0].call()
        copy.parameters.clear()
        self.assertEqual(
            result.entries[0].call().parameters,
            {"InstanceIds": ["i-00000000000000001"]},
        )


class RealArnShapeTests(unittest.TestCase):
    def test_bucket_arn_has_no_account_and_must_match_bucket(self):
        target = ReflectionTarget(account_id="000000000000", regions=("us-east-1",))
        source = plan(
            "aws_s3_bucket",
            {
                "id": "example-bucket",
                "bucket": "example-bucket",
                "arn": "arn:aws:s3:::example-bucket",
            },
        )
        manifest = build_manifest(
            extract_resources(source, target=target), target=target
        )
        self.assertEqual(len(manifest.entries), 2)
        self.assertEqual(
            manifest.entries[0].call().parameters["ExpectedBucketOwner"],
            target.account_id,
        )
        source["resource_changes"][0]["change"]["before"]["arn"] = (
            "arn:aws:s3:::other-bucket"
        )
        with self.assertRaises(ReflectionError):
            extract_resources(source, target=target)

    def test_wrong_family_service_and_partition_rejected(self):
        target = ReflectionTarget(account_id="000000000000", regions=("us-east-1",))
        for arn in (
            "arn:aws:ecs:us-east-1:000000000000:cluster/example",
            "arn:aws-cn:lambda:cn-north-1:000000000000:function:example",
        ):
            with self.subTest(arn=arn), self.assertRaises(ReflectionError):
                extract_resources(
                    plan("aws_lambda_function", {"id": "example", "arn": arn}),
                    target=target,
                )


class FrozenFamilyCoverageTests(unittest.TestCase):
    def test_all_twenty_five_families_render_all_forty_two_capabilities(self):
        from cloud.aws.allowlist import _CATALOG

        target = ReflectionTarget(account_id="000000000000", regions=("us-east-1",))

        def arn(service, resource):
            return f"arn:aws:{service}:us-east-1:000000000000:{resource}"

        values = {
            **{
                family: {"id": f"{prefix}-00000000000000001"}
                for family, prefix in {
                    "aws_instance": "i",
                    "aws_security_group": "sg",
                    "aws_network_interface": "eni",
                    "aws_subnet": "subnet",
                    "aws_vpc": "vpc",
                    "aws_route_table": "rtb",
                    "aws_ebs_volume": "vol",
                    "aws_ebs_snapshot": "snap",
                }.items()
            },
            "aws_lb": {
                "id": arn(
                    "elasticloadbalancing", "loadbalancer/app/example/0000000000000001"
                )
            },
            "aws_lb_target_group": {
                "id": arn(
                    "elasticloadbalancing", "targetgroup/example/0000000000000001"
                )
            },
            "aws_lb_listener": {
                "id": arn(
                    "elasticloadbalancing",
                    "listener/app/example/0000000000000001/0000000000000002",
                )
            },
            "aws_autoscaling_group": {"id": "example", "name": "example"},
            "aws_db_instance": {
                "id": "example",
                "identifier": "example",
                "arn": arn("rds", "db:example"),
            },
            "aws_rds_cluster": {
                "id": "example",
                "cluster_identifier": "example",
                "arn": arn("rds", "cluster:example"),
            },
            "aws_s3_bucket": {
                "id": "example-bucket",
                "bucket": "example-bucket",
                "arn": "arn:aws:s3:::example-bucket",
            },
            "aws_iam_role": {
                "id": "example",
                "name": "example",
                "arn": "arn:aws:iam::000000000000:role/example",
            },
            "aws_iam_instance_profile": {
                "id": "example",
                "name": "example",
                "arn": "arn:aws:iam::000000000000:instance-profile/example",
            },
            "aws_ecs_cluster": {"id": arn("ecs", "cluster/example")},
            "aws_ecs_service": {
                "id": arn("ecs", "service/cluster/example"),
                "cluster": arn("ecs", "cluster/cluster"),
            },
            "aws_eks_cluster": {
                "id": "example",
                "name": "example",
                "arn": arn("eks", "cluster/example"),
            },
            "aws_lambda_function": {
                "id": "example",
                "arn": arn("lambda", "function:example"),
            },
            "aws_lambda_event_source_mapping": {
                "id": "00000000-0000-0000-0000-000000000001",
                "function_arn": arn("lambda", "function:example"),
                "event_source_arn": arn("sqs", "example"),
            },
            "aws_dynamodb_table": {
                "id": "example",
                "name": "example",
                "arn": arn("dynamodb", "table/example"),
            },
            "aws_sqs_queue": {
                "id": "https://untrusted.invalid/x",
                "name": "example",
                "arn": arn("sqs", "example"),
            },
            "aws_route53_record": {
                "id": "Z1_example_A",
                "zone_id": "Z1",
                "name": "example.invalid.",
                "type": "A",
            },
        }
        self.assertEqual(set(values), set(_CATALOG["families"]))
        changes = [
            plan(family, value)["resource_changes"][0]
            for family, value in values.items()
        ]
        result = build_manifest(
            extract_resources(
                {"format_version": "1.2", "resource_changes": changes}, target=target
            ),
            target=target,
        )
        self.assertEqual(result.issues, ())
        self.assertEqual(len(result.entries), 42)
        self.assertEqual(
            {e.capability for e in result.entries}, set(_CATALOG["operations"])
        )
        self.assertEqual(
            guard_manifest(result, target=target, resources=result.resources), result
        )
