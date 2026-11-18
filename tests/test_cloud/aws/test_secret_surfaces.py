"""Synthetic credential corpus across retained and serialized boundary output."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
import unittest
from unittest.mock import Mock, patch

from fastapi.encoders import jsonable_encoder

from cloud.aws.allowlist import authorize
from cloud.aws.client import AwsReader, Call
from cloud.base import ResourceIdentity, ResourceRead, SnapshotFact
from cloud.redaction import redact_snapshot
from tests.test_models import test_cloud_snapshot_storage as storage


class SecretSurfaceTests(unittest.TestCase):
    def test_corpus_in_errors_logs_serialization_and_retained_snapshot(self):
        names = (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "AWS_SECRET_KEY",
            "AWS_SECURITY_TOKEN",
            "AWS_CONTAINER_AUTHORIZATION_TOKEN",
            "AWS_SSO_ACCESS_TOKEN",
        )
        for name in names:
            secret = "synthetic-aws-credential-canary-" + name.lower()
            with self.subTest(name=name), patch.dict(os.environ, {name: secret}):
                source = Mock()
                source.create_client.side_effect = RuntimeError(secret)
                out, err = StringIO(), StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    with self.assertLogs("cloud.aws", level="WARNING") as logs:
                        with self.assertRaises(PermissionError):
                            authorize(secret, Mock())
                    result = AwsReader(source).execute(
                        [
                            Call(
                                capability="instance",
                                parameters={"InstanceIds": ["i-00000000000000001"]},
                            )
                        ]
                    )
                # These are the actual public result serialization and console
                # boundaries; no new HTTP route or CLI command ships in17.2.
                outputs = [
                    json.dumps(jsonable_encoder(result)),
                    out.getvalue(),
                    err.getvalue(),
                    str(logs.output),
                ]
                fixture = storage.CloudSnapshotStorageTests()
                fixture.setUp()
                try:
                    snapshot = fixture.snapshot().model_copy(
                        update={
                            "resources": (
                                ResourceRead(
                                    identity=ResourceIdentity(
                                        address="aws_instance.test",
                                        resource_type="aws_instance",
                                    ),
                                    status="read",
                                    facts=(
                                        SnapshotFact(name=name, value=secret),
                                        SnapshotFact(name="echo", value=secret),
                                    ),
                                ),
                            )
                        }
                    )
                    # Rebuild digest before passing through the established
                    # redaction and durable publication boundary.
                    from cloud.base import build_snapshot

                    snapshot = build_snapshot(
                        **snapshot.model_dump(exclude={"digest", "partial"})
                    )
                    clean = redact_snapshot(snapshot, sensitive_values=(secret,))
                    record = fixture.put(clean)
                    fixture.session.flush()
                    outputs.extend((record.payload_json, clean.model_dump_json()))
                    for output in outputs:
                        self.assertNotIn(secret, str(output))
                finally:
                    fixture.tearDown()
