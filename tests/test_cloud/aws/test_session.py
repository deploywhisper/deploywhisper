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
