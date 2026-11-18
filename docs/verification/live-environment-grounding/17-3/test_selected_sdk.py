"""Optional pinned-SDK model proof for screened selected-response publication."""

from __future__ import annotations

import os
import socket
import unittest
from unittest.mock import patch

from botocore.stub import Stubber

from cloud.aws.client import AwsReader
from cloud.aws.session import AmbientSession
from cloud.reflection import ReflectionTarget, build_manifest, extract_resources


class SelectedSdkProjectionTests(unittest.TestCase):
    def check_projection(self, family, values, capability, method, response):
        secret = "selected-provider-secret-canary"
        target = ReflectionTarget(account_id="000000000000", regions=("us-east-1",))
        plan = {
            "format_version": "1.2",
            "resource_changes": [
                {
                    "address": family + ".example",
                    "type": family,
                    "change": {"actions": ["update"], "before": values},
                }
            ],
        }
        original = extract_resources(plan, target=target)
        manifest = build_manifest(original, target=target)
        index = next(
            i
            for i, entry in enumerate(manifest.entries)
            if entry.capability == capability
        )
        entry = manifest.entries[index]
        stubs = []

        class SdkPort:
            def create_client(self, service, config, *, timeout):
                client = AmbientSession().create_client(
                    service, config, timeout=timeout
                )
                stub = Stubber(client)
                stub.add_response(method, response, entry.call().parameters)
                stub.activate()
                stubs.append(stub)
                return client

        credentials = {
            "AWS_ACCESS_KEY_ID": "AKIA" + "A" * 16,
            "AWS_SECRET_ACCESS_KEY": "synthetic-sdk-credential-only",
        }
        with (
            patch.dict(os.environ, credentials, clear=True),
            patch.object(
                socket, "socket", side_effect=AssertionError("network forbidden")
            ),
        ):
            try:
                result = AwsReader(SdkPort()).execute_selected(
                    manifest, indices=(index,), target=target, resources=original
                )
                self.assertEqual(result.actual_call_count, 1)
                self.assertEqual(result.attempts, 1)
                self.assertTrue(result.partial)
                self.assertEqual(result.items[0].status, "incomplete")
                self.assertTrue(result.items[0].facts)
                self.assertNotIn(secret, repr(result))
                for fact in result.items[0].facts:
                    self.assertNotIn(secret, fact.name)
                    self.assertNotIn(secret, str(fact.value))
                for stub in stubs:
                    stub.assert_no_pending_responses()
            finally:
                for stub in stubs:
                    stub.deactivate()

    def test_native_ecs_lowercase_tag_model_and_value_echo(self):
        secret = "selected-provider-secret-canary"
        arn = "arn:aws:ecs:us-east-1:000000000000:cluster/example"
        self.check_projection(
            "aws_ecs_cluster",
            {"id": arn, "arn": arn},
            "ecs_cluster",
            "describe_clusters",
            {
                "clusters": [
                    {
                        "clusterArn": arn,
                        "tags": [
                            {"key": "password", "value": secret},
                            {"key": "owner", "value": secret},
                        ],
                    }
                ]
            },
        )

    def test_native_lambda_tag_dictionary_and_secret_key(self):
        secret = "selected-provider-secret-canary"
        arn = "arn:aws:lambda:us-east-1:000000000000:function:example"
        self.check_projection(
            "aws_lambda_function",
            {"id": "example", "arn": arn},
            "function_tags",
            "list_tags",
            {
                "Tags": {
                    "password": secret,
                    secret: "public",
                    "owner": secret,
                    "team": "platform",
                }
            },
        )
