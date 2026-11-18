"""Regressions for honest bounded-call completion and sanitized diagnostics."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from cloud.aws.client import AwsReader, Call, dry_run


class CompletionTests(unittest.TestCase):
    def execute(self, capability, parameters, response):
        source = Mock()
        source.create_client.return_value._make_api_call.return_value = response
        return AwsReader(source).execute(
            [Call(capability=capability, parameters=parameters)]
        )

    def test_ecs_item_failures_never_complete(self):
        result = self.execute(
            "ecs_cluster",
            {
                "clusters": ["arn:aws:ecs:us-east-1:000000000000:cluster/example"],
                "include": ["STATISTICS", "TAGS"],
            },
            {"clusters": [], "failures": [{"reason": "MISSING"}]},
        )
        self.assertTrue(result.partial)
        self.assertEqual(result.items[0].status, "incomplete")

    def test_missing_and_wrong_instance_identity_never_complete(self):
        params = {"InstanceIds": ["i-00000000000000001"]}
        for response in (
            {},
            {"Reservations": []},
            {"Reservations": [{"Instances": [{"InstanceId": "i-00000000000000002"}]}]},
        ):
            with self.subTest(response=response):
                self.assertTrue(self.execute("instance", params, response).partial)
        self.assertFalse(
            self.execute(
                "instance",
                params,
                {
                    "Reservations": [
                        {"Instances": [{"InstanceId": params["InstanceIds"][0]}]}
                    ]
                },
            ).partial
        )

    def test_route53_exact_wildcard_is_not_an_inventory_selector(self):
        for name in ("*.example.com.", r"\052.example.com."):
            with self.subTest(name=name):
                params = {
                    "HostedZoneId": "Z123",
                    "StartRecordName": name,
                    "StartRecordType": "A",
                    "MaxItems": "1",
                }
                self.assertEqual(
                    dry_run([Call(capability="record", parameters=params)])[0][
                        "parameters"
                    ],
                    params,
                )
                self.assertFalse(
                    self.execute(
                        "record",
                        params,
                        {
                            "ResourceRecordSets": [
                                {"Name": r"\052.example.com.", "Type": "A"}
                            ]
                        },
                    ).partial
                )
                self.assertTrue(
                    self.execute(
                        "record",
                        params,
                        {
                            "ResourceRecordSets": [
                                {"Name": "other.example.com.", "Type": "A"}
                            ]
                        },
                    ).partial
                )
        for name in (
            "*",
            "a.*.example.com.",
            "*.example.com..",
            "*.example.com/?x",
            r"\999.example.com.",
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                Call(
                    capability="record",
                    parameters={
                        "HostedZoneId": "Z123",
                        "StartRecordName": name,
                        "StartRecordType": "A",
                        "MaxItems": "1",
                    },
                )

    def test_non_authorization_errors_do_not_invent_missing_permissions(self):
        for error in (
            PermissionError("credential-canary"),
            ConnectionError("transport-canary"),
            ValueError("invalid-canary"),
            RuntimeError("other-canary"),
        ):
            with self.subTest(error=type(error).__name__):
                source = Mock()
                source.create_client.side_effect = error
                result = AwsReader(source).execute(
                    [
                        Call(
                            capability="instance",
                            parameters={"InstanceIds": ["i-00000000000000001"]},
                        )
                    ]
                )
                self.assertIsNone(result.items[0].missing_permission)
                self.assertNotIn("canary", repr(result))
                self.assertNotEqual(result.items[0].cause, "permission_denied")

    def test_closed_error_causes_and_only_provider_denial_names_permission(self):
        from cloud.aws.session import SessionError

        errors = [
            (SessionError(cause), cause, None)
            for cause in (
                "sdk_unavailable",
                "credentials_unavailable",
                "session_unavailable",
                "request_refused",
            )
        ]
        for code, cause, permission in (
            ("AccessDenied", "permission_denied", "ec2:DescribeInstances"),
            ("UnauthorizedOperation", "permission_denied", "ec2:DescribeInstances"),
            ("ThrottlingException", "throttled", None),
            ("NoSuchBucket", "provider_error", None),
        ):
            error = type(
                "ClientError",
                (Exception,),
                {"response": {"Error": {"Code": code, "Message": "private-canary"}}},
            )("private-canary")
            errors.append((error, cause, permission))
        for kind in ("EndpointConnectionError", "ReadTimeoutError"):
            errors.append(
                (
                    type(kind, (Exception,), {"__module__": "botocore.exceptions"})(
                        "private-canary"
                    ),
                    "transport_error",
                    None,
                )
            )
        for kind, cause in (
            ("NoCredentialsError", "credentials_unavailable"),
            ("ParamValidationError", "invalid_request"),
        ):
            errors.append(
                (
                    type(kind, (Exception,), {"__module__": "botocore.exceptions"})(
                        "private-canary"
                    ),
                    cause,
                    None,
                )
            )
        for error, cause, permission in errors:
            with self.subTest(cause=cause, kind=type(error).__name__):
                source = Mock()
                source.create_client.side_effect = error
                result = AwsReader(source).execute(
                    [
                        Call(
                            capability="instance",
                            parameters={"InstanceIds": ["i-00000000000000001"]},
                        )
                    ]
                )
                self.assertEqual(result.items[0].cause, cause)
                self.assertEqual(result.items[0].missing_permission, permission)
                self.assertNotIn("private-canary", repr(result))
