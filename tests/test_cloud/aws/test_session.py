"""Credential and targeting refusals need no SDK."""

from __future__ import annotations
import unittest
from unittest.mock import patch
from cloud.aws.session import AmbientSession, validate_config


class SessionTests(unittest.TestCase):
    def test_targeting_corpus(self):
        for key in (
            "endpoint_url",
            "host",
            "role_arn",
            "account",
            "aws_access_key_id",
            "profile",
            "verify",
            "proxies",
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_config({"region": "us-east-1", key: "secret-canary"})

    def test_only_qualified_mechanisms(self):
        for name in (
            "sso",
            "iam-role",
            "assume-role-with-web-identity",
            "container-role",
            "custom-process",
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                AmbientSession(mechanisms=(name,))

    def test_does_not_resolve_on_construction(self):
        with patch(
            "builtins.__import__", side_effect=AssertionError("import forbidden")
        ):
            AmbientSession()

    def test_repr_does_not_echo_paths(self):
        self.assertNotIn(
            "secret-canary",
            repr(
                AmbientSession(
                    mechanisms=("shared-credentials-file",),
                    credentials_file="secret-canary",
                )
            ),
        )

    def test_noncommercial_regions_fail_before_sdk_or_credentials(self):
        regions = (
            "us-gov-west-1",
            "us-gov-east-1",
            "us-iso-east-1",
            "us-isob-east-1",
            "eu-isoe-west-1",
            "us-isof-south-1",
            "cn-north-1",
            "cn-northwest-1",
            "eusc-de-east-1",
            "us-extra-west-1",
        )
        with patch(
            "cloud.aws.session.session",
            side_effect=AssertionError("credentials forbidden"),
        ) as resolve:
            for region in regions:
                with self.subTest(region=region), self.assertRaises(ValueError):
                    AmbientSession().create_client("ec2", {"region": region})
            resolve.assert_not_called()

    def test_commercial_regions_remain_valid_without_sdk(self):
        for region in (
            "us-east-1",
            "us-west-2",
            "eu-central-1",
            "ap-southeast-7",
            "ca-west-1",
            "mx-central-1",
            "il-central-1",
            "af-south-1",
        ):
            with self.subTest(region=region):
                self.assertEqual(
                    validate_config({"region": region}), {"region": region}
                )
