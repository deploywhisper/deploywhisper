"""Optional real pinned SDK tests; run separately from SDK-free core tests."""

from __future__ import annotations
import os
import socket
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from botocore.stub import Stubber
from cloud.aws.session import AmbientSession, session

ENV = {
    "AWS_ACCESS_KEY_ID": "AKIA" + "A" * 16,
    "AWS_SECRET_ACCESS_KEY": "synthetic-sdk-secret",
    "AWS_SESSION_TOKEN": "synthetic-session",
    "AWS_ENDPOINT_URL": "http://attacker.invalid",
    "AWS_ENDPOINT_URL_EC2": "http://169.254.169.254/",
    "AWS_PROFILE": "hostile",
    "HTTPS_PROXY": "http://attacker.invalid",
    "AWS_CA_BUNDLE": "/nonexistent/hostile.pem",
    "AWS_DATA_PATH": "/nonexistent/models",
}


class SdkTests(unittest.TestCase):
    def test_real_client_canonical_transport(self):
        with (
            patch.dict(os.environ, ENV, clear=True),
            patch.object(
                socket, "socket", side_effect=AssertionError("network forbidden")
            ),
        ):
            client = AmbientSession().create_client("ec2", {"region": "us-east-1"})
            self.assertEqual(
                client.meta.endpoint_url, "https://ec2.us-east-1.amazonaws.com"
            )
            self.assertEqual(client.meta.config.proxies, {})
            self.assertEqual(client.meta.config.retries["total_max_attempts"], 1)
            with Stubber(client) as stub:
                stub.add_response(
                    "describe_instances",
                    {"Reservations": []},
                    {"InstanceIds": ["i-00000000000000001"]},
                )
                self.assertEqual(
                    client.describe_instances(InstanceIds=["i-00000000000000001"]),
                    {"Reservations": []},
                )
                stub.assert_no_pending_responses()

    def test_missing_credentials_never_host_fallback(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                socket, "socket", side_effect=AssertionError("network forbidden")
            ),
        ):
            self.assertEqual(
                [
                    p.METHOD
                    for p in session().get_component("credential_provider").providers
                ],
                ["env"],
            )
            self.assertIsNone(session().get_credentials())
            with self.assertRaises(PermissionError):
                AmbientSession().create_client("ec2", {"region": "us-east-1"})

    def test_explicit_trusted_file(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                socket, "socket", side_effect=AssertionError("network forbidden")
            ),
        ):
            path = Path(temp) / "credentials"
            path.write_text(
                "[qualified]\naws_access_key_id = SYNTHETIC\naws_secret_access_key = synthetic-secret\n"
            )
            sdk = session(
                mechanisms=("shared-credentials-file",),
                credentials_file=str(path),
                trusted_profile="qualified",
            )
            self.assertEqual(sdk.get_credentials().method, "shared-credentials-file")

    def test_no_error_credential_echo(self):
        with patch(
            "cloud.aws.session.session",
            side_effect=RuntimeError("synthetic-secret-canary"),
        ):
            with self.assertRaises(PermissionError) as error:
                AmbientSession().create_client("ec2", {"region": "us-east-1"})
            self.assertNotIn("synthetic-secret-canary", str(error.exception))

    def test_signing_never_emits_credential_records(self):
        import logging
        from botocore.awsrequest import AWSRequest

        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        root = logging.getLogger()
        handler = Capture()
        root.addHandler(handler)
        try:
            for namespace in (
                "botocore",
                "botocore.auth",
                "botocore.credentials",
                "botocore.endpoint",
                "urllib3",
            ):
                logger = logging.getLogger(namespace)
                logger.disabled = False
                logger.setLevel(logging.DEBUG)
            with patch.dict(os.environ, ENV, clear=True):
                client = AmbientSession().create_client("ec2", {"region": "us-east-1"})
                client._request_signer.sign(
                    "DescribeInstances",
                    AWSRequest(
                        method="POST",
                        url=client.meta.endpoint_url,
                        data="Action=DescribeInstances",
                    ),
                )
            text = "\n".join(record.getMessage() for record in records)
            for value in (
                ENV["AWS_ACCESS_KEY_ID"],
                ENV["AWS_SECRET_ACCESS_KEY"],
                ENV["AWS_SESSION_TOKEN"],
            ):
                self.assertNotIn(value, text)
        finally:
            root.removeHandler(handler)
