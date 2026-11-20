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
    def test_reader_fences_cancelled_native_request_before_transport(self):
        from threading import Event
        from types import SimpleNamespace
        from cloud.aws.client import AwsReader, Call

        cancel, finished = Event(), Event()
        with (
            patch.dict(os.environ, ENV, clear=True),
            patch.object(
                socket, "socket", side_effect=AssertionError("network forbidden")
            ),
            patch("botocore.httpsession.URLLib3Session.send") as send,
        ):
            client = AmbientSession().create_client("ec2", {"region": "us-east-1"})
            client.meta.events.register(
                "before-sign.ec2.DescribeInstances", lambda **_: cancel.set()
            )
            original = client._make_api_call

            def invoke(*args):
                try:
                    return original(*args)
                finally:
                    finished.set()

            reader = AwsReader(SimpleNamespace(create_client=lambda *a, **kw: client))
            with patch.object(client, "_make_api_call", side_effect=invoke):
                result = reader.execute(
                    [
                        Call(
                            capability="instance",
                            parameters={"InstanceIds": ["i-00000000000000001"]},
                        )
                    ],
                    cancel=cancel,
                )
                self.assertTrue(finished.wait(2))
            self.assertEqual(result.attempts, 1)
            self.assertEqual(result.items[0].status, "cancelled")
            send.assert_not_called()

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

    def test_redirects_never_add_requests_or_change_region(self):
        from botocore.awsrequest import AWSResponse
        from cloud.aws.client import AwsReader, Call, Limits

        class Raw:
            def stream(self, amt=None, decode_content=False):
                yield b"<Error><Code>PermanentRedirect</Code></Error>"

        cases = [
            (status, headers)
            for status in (301, 302, 307, 308, 500)
            for headers in ({}, {"x-amz-bucket-region": "us-west-2"})
        ]
        for status, headers in cases:
            with self.subTest(status=status, headers=headers):
                requests = []

                def send(_transport, request):
                    requests.append((request.method, request.url))
                    return AWSResponse(request.url, status, headers, Raw())

                with (
                    patch.dict(os.environ, ENV, clear=True),
                    patch.object(
                        socket,
                        "socket",
                        side_effect=AssertionError("network forbidden"),
                    ),
                    patch("botocore.httpsession.URLLib3Session.send", send),
                ):
                    call = Call(
                        capability="bucket_versioning",
                        parameters={
                            "Bucket": "demo-bucket",
                            "ExpectedBucketOwner": "000000000000",
                        },
                    )
                    result = AwsReader(AmbientSession()).execute(
                        [call], limits=Limits(call_budget=1)
                    )
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0][0], "GET")
                self.assertNotIn("us-west-2", requests[0][1])
                self.assertTrue(result.partial)

    def test_unrelated_urllib3_diagnostics_remain_enabled(self):
        import logging

        logger = logging.getLogger("urllib3.unrelated-http-client")
        logger.disabled = False
        logger.setLevel(logging.WARNING)
        with patch.dict(os.environ, ENV, clear=True):
            AmbientSession().create_client("ec2", {"region": "us-east-1"})
        with self.assertLogs(logger, level="WARNING") as logs:
            logger.warning("ordinary transport warning")
        self.assertIn("ordinary transport warning", str(logs.output))
        self.assertFalse(logger.disabled)

    def test_shared_file_signing_keeps_raw_logs_credential_free(self):
        import logging
        from botocore.awsrequest import AWSRequest

        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = Capture()
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            with (
                tempfile.TemporaryDirectory() as temp,
                patch.dict(os.environ, {}, clear=True),
            ):
                path = Path(temp) / "credentials"
                values = (
                    "SYNTHETIC-shared-key",
                    "synthetic-shared-secret",
                    "synthetic-shared-token",
                )
                path.write_text(
                    "[qualified]\naws_access_key_id = "
                    + values[0]
                    + "\naws_secret_access_key = "
                    + values[1]
                    + "\naws_session_token = "
                    + values[2]
                    + "\n"
                )
                logger = logging.getLogger("botocore.auth")
                logger.disabled = False
                logger.setLevel(logging.DEBUG)
                with patch.object(
                    socket, "socket", side_effect=AssertionError("network forbidden")
                ):
                    client = AmbientSession(
                        mechanisms=("shared-credentials-file",),
                        credentials_file=str(path),
                        trusted_profile="qualified",
                    ).create_client("ec2", {"region": "us-east-1"})
                    client._request_signer.sign(
                        "DescribeInstances",
                        AWSRequest(
                            method="POST",
                            url=client.meta.endpoint_url,
                            data="Action=DescribeInstances",
                        ),
                    )
                text = "\n".join(record.getMessage() for record in records)
                for value in values:
                    self.assertNotIn(value, text)
        finally:
            root.removeHandler(handler)

    def test_direct_mutation_and_second_operation_are_refused(self):
        from cloud.aws.session import SessionError

        with (
            patch.dict(os.environ, ENV, clear=True),
            patch.object(
                socket, "socket", side_effect=AssertionError("network forbidden")
            ),
        ):
            client = AmbientSession().create_client("ec2", {"region": "us-east-1"})
            with self.assertRaises(SessionError):
                client.terminate_instances(InstanceIds=["i-00000000000000001"])
            # Refusal consumes no permitted operation.
            with Stubber(client) as stub:
                stub.add_response(
                    "describe_instances",
                    {"Reservations": []},
                    {"InstanceIds": ["i-00000000000000001"]},
                )
                client.describe_instances(InstanceIds=["i-00000000000000001"])
            with self.assertRaises(SessionError):
                client.describe_instances(InstanceIds=["i-00000000000000001"])

    def test_transport_failure_is_never_retried(self):
        from botocore.exceptions import ConnectTimeoutError
        from cloud.aws.client import AwsReader, Call, Limits

        requests = []

        def send(_transport, request):
            requests.append(request.url)
            raise ConnectTimeoutError(endpoint_url=request.url)

        with (
            patch.dict(os.environ, ENV, clear=True),
            patch.object(
                socket, "socket", side_effect=AssertionError("network forbidden")
            ),
            patch("botocore.httpsession.URLLib3Session.send", send),
        ):
            result = AwsReader(AmbientSession()).execute(
                [
                    Call(
                        capability="bucket_versioning",
                        parameters={
                            "Bucket": "demo-bucket",
                            "ExpectedBucketOwner": "000000000000",
                        },
                    )
                ],
                limits=Limits(call_budget=1),
            )
        self.assertEqual(len(requests), 1)
        self.assertTrue(result.partial)

    def test_parsed_error_stops_retry_handlers_even_with_http_200(self):
        from types import SimpleNamespace
        from botocore.exceptions import ClientError

        with patch.dict(os.environ, ENV, clear=True):
            client = AmbientSession().create_client("s3", {"region": "us-east-1"})
            with self.assertRaises(ClientError):
                client.meta.events.emit(
                    "needs-retry.s3.GetBucketVersioning",
                    response=(
                        SimpleNamespace(status_code=200),
                        {"Error": {"Code": "PermanentRedirect"}},
                    ),
                    operation=client.meta.service_model.operation_model(
                        "GetBucketVersioning"
                    ),
                )

    def test_s3_arn_cannot_override_configured_region_before_send(self):
        from botocore.exceptions import UnsupportedS3AccesspointConfigurationError
        from botocore.awsrequest import AWSResponse

        class Raw:
            def stream(self, amt=None, decode_content=False):
                yield b'<VersioningConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/"/>'

        def send_response(request):
            return AWSResponse(request.url, 200, {}, Raw())

        with (
            patch.dict(
                os.environ, {**ENV, "AWS_S3_USE_ARN_REGION": "true"}, clear=True
            ),
            patch.object(
                socket, "socket", side_effect=AssertionError("network forbidden")
            ),
            patch(
                "botocore.httpsession.URLLib3Session.send", side_effect=send_response
            ) as send,
        ):
            client = AmbientSession().create_client("s3", {"region": "us-east-1"})
            with self.assertRaises(UnsupportedS3AccesspointConfigurationError):
                client.get_bucket_versioning(
                    Bucket="arn:aws:s3:us-west-2:000000000000:accesspoint/example",
                    ExpectedBucketOwner="000000000000",
                )
            send.assert_not_called()

    def test_s3_regular_bucket_keeps_canonical_region_endpoint(self):
        from botocore.awsrequest import AWSResponse

        class Raw:
            def stream(self, amt=None, decode_content=False):
                yield b'<VersioningConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/"/>'

        requests = []

        def send(_transport, request):
            requests.append(request.url)
            return AWSResponse(request.url, 200, {}, Raw())

        with (
            patch.dict(
                os.environ, {**ENV, "AWS_S3_USE_ARN_REGION": "true"}, clear=True
            ),
            patch.object(
                socket, "socket", side_effect=AssertionError("network forbidden")
            ),
            patch("botocore.httpsession.URLLib3Session.send", send),
        ):
            client = AmbientSession().create_client("s3", {"region": "us-west-2"})
            client.get_bucket_versioning(
                Bucket="demo-bucket", ExpectedBucketOwner="000000000000"
            )
        self.assertEqual(
            requests, ["https://s3.us-west-2.amazonaws.com/demo-bucket?versioning"]
        )

    def test_catalog_services_do_not_retry_server_errors(self):
        from botocore.awsrequest import AWSResponse
        from cloud.aws.allowlist import _CATALOG
        from cloud.aws.client import AwsReader, Call, Limits

        class Raw:
            def __init__(self, content):
                self.content = content

            def stream(self, amt=None, decode_content=False):
                yield self.content

        examples = {
            "instance": {"InstanceIds": ["i-00000000000000001"]},
            "lb": {
                "LoadBalancerArns": [
                    "arn:aws:elasticloadbalancing:us-east-1:000000000000:loadbalancer/app/example/0000000000000000"
                ]
            },
            "asg": {"AutoScalingGroupNames": ["example"], "MaxRecords": 100},
            "db": {"DBInstanceIdentifier": "example"},
            "bucket_versioning": {
                "Bucket": "demo-bucket",
                "ExpectedBucketOwner": "000000000000",
            },
            "role": {"RoleName": "example"},
            "ecs_cluster": {
                "clusters": ["arn:aws:ecs:us-east-1:000000000000:cluster/example"],
                "include": ["STATISTICS", "TAGS"],
            },
            "eks_cluster": {"name": "example"},
            "function_concurrency": {
                "FunctionName": "arn:aws:lambda:us-east-1:000000000000:function:example"
            },
            "table": {"TableName": "example"},
            "queue": {
                "QueueUrl": "https://sqs.us-east-1.amazonaws.com/000000000000/example",
                "AttributeNames": [
                    "QueueArn",
                    "ApproximateNumberOfMessages",
                    "RedrivePolicy",
                    "MessageRetentionPeriod",
                    "LastModifiedTimestamp",
                ],
            },
            "record": {
                "HostedZoneId": "Z123",
                "StartRecordName": "example.com.",
                "StartRecordType": "A",
                "MaxItems": "1",
            },
        }
        self.assertEqual(
            {_CATALOG["operations"][capability]["service"] for capability in examples},
            {row["service"] for row in _CATALOG["operations"].values()},
        )
        for capability, parameters in examples.items():
            requests = []

            def send(_transport, request):
                requests.append(request.url)
                is_json = request.headers.get("Content-Type", b"")
                if isinstance(is_json, bytes):
                    is_json = is_json.decode("ascii")
                if "json" in is_json:
                    body = b'{"__type":"InternalFailure","message":"synthetic"}'
                    headers = {"Content-Type": "application/x-amz-json-1.1"}
                else:
                    body = b"<Error><Code>InternalFailure</Code><Message>synthetic</Message></Error>"
                    headers = {"Content-Type": "application/xml"}
                return AWSResponse(request.url, 500, headers, Raw(body))

            with (
                self.subTest(capability=capability),
                patch.dict(os.environ, ENV, clear=True),
                patch.object(
                    socket, "socket", side_effect=AssertionError("network forbidden")
                ),
                patch("botocore.httpsession.URLLib3Session.send", send),
            ):
                result = AwsReader(AmbientSession()).execute(
                    [Call(capability=capability, parameters=parameters)],
                    limits=Limits(call_budget=1),
                )
                self.assertEqual(len(requests), 1)
                self.assertEqual(result.attempts, 1)
                self.assertTrue(result.partial)
