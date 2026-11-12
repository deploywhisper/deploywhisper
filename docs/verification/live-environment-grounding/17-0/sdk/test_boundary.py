"""Offline real-SDK trust-boundary qualification."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from botocore.stub import Stubber
from boundary import authorize, client, dispatch, manifest, session, validate_config

CANARY = "SYNTHETIC-sdk-credential-canary"
ENV = {
    "AWS_ACCESS_KEY_ID": "AKIA" + "A" * 16,
    "AWS_SECRET_ACCESS_KEY": CANARY,
    "AWS_SESSION_TOKEN": "SYNTHETIC-session-token",
    "AWS_ENDPOINT_URL": "http://169.254.169.254/latest/meta-data/",
    "AWS_ENDPOINT_URL_EC2": "http://attacker.invalid",
    "AWS_CA_BUNDLE": "/nonexistent/hostile.pem",
    "HTTPS_PROXY": "http://attacker.invalid",
    "AWS_PROFILE": "hostile-profile",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI": "http://attacker.invalid/credentials",
}
PARAMS = {"InstanceIds": ["i-00000000000000001"]}


class BoundaryTests(unittest.TestCase):
    def test_denial_before_session_or_client_construction(self):
        factory = Mock()
        for action in (
            "ec2:TerminateInstances",
            "secretsmanager:GetSecretValue",
            "ec2:DescribeEverything",
        ):
            with self.subTest(action=action), self.assertRaises(PermissionError):
                authorize(action, PARAMS, factory)
        factory.assert_not_called()

    def test_config_rejects_transport_and_authority_overrides(self):
        for key in (
            "endpoint_url",
            "host",
            "role_arn",
            "account",
            "profile",
            "access_key",
            "secret",
            "proxy",
            "ca_bundle",
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_config({"region": "us-east-1", key: "hostile"})
        with self.assertRaises(ValueError):
            validate_config({"region": "http://attacker.invalid"})

    def test_default_credentials_are_environment_only(self):
        with (
            patch.dict(os.environ, ENV, clear=True),
            patch.object(
                socket, "socket", side_effect=AssertionError("network forbidden")
            ),
        ):
            sdk = session()
            self.assertEqual(
                [p.METHOD for p in sdk.get_component("credential_provider").providers],
                ["env"],
            )
            self.assertEqual(sdk.get_credentials().method, "env")

    def test_missing_environment_does_not_fall_through_to_host_role(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                socket, "socket", side_effect=AssertionError("network forbidden")
            ),
        ):
            self.assertIsNone(session().get_credentials())

    def test_shared_credentials_require_explicit_operator_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            filename = Path(tmp) / "credentials"
            filename.write_text(
                "[qualified]\naws_access_key_id = SYNTHETIC\naws_secret_access_key = synthetic-only\n"
            )
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(
                    socket, "socket", side_effect=AssertionError("network forbidden")
                ),
            ):
                sdk = session(
                    mechanisms=("shared-credentials-file",),
                    credentials_file=str(filename),
                    trusted_profile="qualified",
                )
                self.assertEqual(
                    sdk.get_credentials().method, "shared-credentials-file"
                )
                self.assertIsNone(session().get_credentials())
        for mechanism in (
            "iam-role",
            "container-role",
            "custom-process",
            "assume-role",
            "sso",
            "assume-role-with-web-identity",
        ):
            with self.subTest(mechanism=mechanism), self.assertRaises(ValueError):
                session(mechanisms=(mechanism,))

    def test_real_sdk_ignores_hostile_endpoint_env_and_stub_matches_exact_request(self):
        with patch.dict(os.environ, ENV, clear=True):
            sdk_client = client("ec2:DescribeInstances", {"region": "us-east-1"})
            self.assertEqual(
                sdk_client.meta.endpoint_url, "https://ec2.us-east-1.amazonaws.com"
            )
            self.assertEqual(sdk_client.meta.config.proxies, {})
            self.assertEqual(sdk_client.meta.config.retries["total_max_attempts"], 1)
            self.assertEqual(sdk_client.meta.config.connect_timeout, 1)
            self.assertEqual(sdk_client.meta.config.read_timeout, 1)
            with (
                Stubber(sdk_client) as stub,
                patch.object(
                    socket, "socket", side_effect=AssertionError("network forbidden")
                ),
            ):
                stub.add_response("describe_instances", {"Reservations": []}, PARAMS)
                self.assertEqual(
                    dispatch("ec2:DescribeInstances", PARAMS, sdk_client),
                    {"status": "recorded", "instance_count": 0},
                )
                stub.assert_no_pending_responses()

    def test_pagination_is_partial_without_hidden_followup(self):
        with patch.dict(os.environ, ENV, clear=True):
            sdk_client = client("ec2:DescribeInstances", {"region": "us-east-1"})
            with Stubber(sdk_client) as stub:
                stub.add_response(
                    "describe_instances",
                    {"Reservations": [], "NextToken": "synthetic-next"},
                    PARAMS,
                )
                self.assertEqual(
                    dispatch("ec2:DescribeInstances", PARAMS, sdk_client)["status"],
                    "incomplete",
                )
                stub.assert_no_pending_responses()

    def test_model_loader_rejects_environment_and_home_overrides(self):
        import botocore
        from botocore.loaders import Loader

        trusted_data = str(Path(botocore.__file__).resolve().parent / "data")
        with tempfile.TemporaryDirectory() as home:
            injected = Path(home) / "injected"
            user_models = Path(home) / ".aws" / "models"
            # Real format-model overrides would normally be discovered in these paths.
            for directory in (injected, user_models):
                model = directory / "ec2" / "2016-11-15"
                model.mkdir(parents=True)
                (model / "service-2.json").write_text(
                    json.dumps(
                        {
                            "metadata": {
                                "endpointPrefix": "attacker",
                                "serviceId": "EC2",
                            },
                            "operations": {},
                            "shapes": {},
                        }
                    )
                )
                (directory / "endpoints.json").write_text(
                    json.dumps({"partitions": [], "malicious": True})
                )
            hostile = dict(ENV, HOME=home, AWS_DATA_PATH=str(injected))
            with (
                patch.dict(os.environ, hostile, clear=True),
                patch.object(Loader, "CUSTOMER_DATA_PATH", str(user_models)),
            ):
                sdk = session()
                loader = sdk.get_component("data_loader")
                self.assertEqual(loader.search_paths, [trusted_data])
                self.assertEqual(
                    loader.load_service_model("ec2", "service-2")["metadata"][
                        "endpointPrefix"
                    ],
                    "ec2",
                )
                self.assertNotIn("malicious", loader.load_data("endpoints"))
                sdk_client = client("ec2:DescribeInstances", {"region": "us-east-1"})
                self.assertEqual(
                    sdk_client.meta.endpoint_url, "https://ec2.us-east-1.amazonaws.com"
                )

    def test_error_projection_never_returns_raw_provider_secret(self):
        with patch.dict(os.environ, ENV, clear=True):
            sdk_client = client("ec2:DescribeInstances", {"region": "us-east-1"})
            with Stubber(sdk_client) as stub:
                stub.add_client_error(
                    "describe_instances", "AccessDenied", CANARY, expected_params=PARAMS
                )
                output = dispatch("ec2:DescribeInstances", PARAMS, sdk_client)
        self.assertNotIn(CANARY, json.dumps(output))
        self.assertEqual(
            output,
            {
                "status": "unreadable",
                "missing_permission": "ec2:DescribeInstances",
                "cause": "AccessDenied",
            },
        )

    def test_fixed_manifest_has_no_discovery_or_pagination_followups(self):
        calls = manifest(["i-00000000000000001", "i-00000000000000002"])
        self.assertEqual(
            calls,
            [
                {
                    "action": "ec2:DescribeInstances",
                    "params": {"InstanceIds": [identity]},
                }
                for identity in ["i-00000000000000001", "i-00000000000000002"]
            ],
        )
        self.assertFalse(any("NextToken" in row["params"] for row in calls))
        for parameters in (
            {},
            {"Filters": []},
            {"InstanceIds": []},
            dict(PARAMS, NextToken="hostile"),
        ):
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                authorize("ec2:DescribeInstances", parameters, Mock())

    def test_credential_free_manifest_does_not_import_sdk(self):
        script = Path(__file__).with_name("boundary.py")
        with tempfile.TemporaryDirectory() as home:
            output = subprocess.run(
                [sys.executable, str(script), "dry-run"],
                env={"HOME": home},
                check=True,
                capture_output=True,
                text=True,
            )
        result = json.loads(output.stdout)
        self.assertFalse(result["sdk_imported"])
        self.assertEqual(result["issued"], 0)
        self.assertEqual(result["calls"], manifest(["i-00000000000000001"]))
        self.assertEqual(output.stderr, "")


if __name__ == "__main__":
    unittest.main()
