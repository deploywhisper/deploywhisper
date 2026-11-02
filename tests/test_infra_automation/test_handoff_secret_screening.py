"""Generated receiver grants cannot be reintroduced through retained labels."""

from __future__ import annotations

import base64
import json
from urllib.parse import quote

from infra_automation.lifecycle import LifecycleError
from infra_automation.targets import BreakLockRequest, RegisterTargetRequest
from services import infra_automation_targets as targets
from services.content_security import REDACTED, redact_reference, redact_text
from tests.test_infra_automation import test_handoff_service as fixtures
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class HandoffSecretScreeningTests(LifecycleCase):
    setUp = fixtures.HandoffServiceTests.setUp
    enable = fixtures.HandoffServiceTests.enable
    publish_fixture = fixtures.HandoffServiceTests.publish_fixture
    deliver = fixtures.HandoffServiceTests.deliver
    prepare = fixtures.HandoffServiceTests.prepare
    request = fixtures.HandoffServiceTests.request
    dispatch = fixtures.HandoffServiceTests.dispatch

    def test_real_generated_grant_in_reason_or_identifier_never_persists(self):
        operation = self.prepare()
        self.dispatch(operation)
        token = self.sent[0].grant_token
        variants = [
            token,
            "prefix" + token + "suffix",
            quote(token, safe="").replace(".", "%2E"),
            base64.b64encode(token.encode()).decode(),
        ]
        for value in variants:
            with self.subTest(kind="encoded" if value != token else "bare"):
                body = BreakLockRequest(
                    project_id=100,
                    workspace_id=100,
                    expected_lock_id="held-lock",
                    expected_version=1,
                    acknowledge_uncertainty=True,
                    reason=value,
                )
                with self.credentials(), self.assertRaises(LifecycleError) as failure:
                    targets.break_lock("target", body, now=self.now)
                self.assertEqual(failure.exception.status_code, 422)
        for alias in (token, base64.b64encode(token.encode()).decode()):
            definition = self.snapshot.definition.model_dump(mode="json")
            definition.update(canonical_target="another", aliases=[alias])
            body = RegisterTargetRequest.model_validate_json(
                json.dumps(
                    dict(
                        project_id=100,
                        workspace_id=100,
                        expected_version=0,
                        definition=definition,
                        reason="Register owned alias",
                    )
                )
            )
            with self.credentials(), self.assertRaises(LifecycleError) as failure:
                targets.register_target(body, now=self.now)
            self.assertEqual(failure.exception.status_code, 422)
        with self.engine.connect() as connection:
            raw = connection.connection.driver_connection
            dump = "\n".join(raw.iterdump())
            self.assertFalse(
                any(value in dump for value in variants),
                "Generated credential persisted in a label",
            )

    def test_existing_safe_log_formatter_screens_grants_in_urls_and_exceptions(self):
        import logging
        from logging_config import SafeFormatter

        token = "handoff-v1." + "b" * 64
        record = logging.LogRecord(
            "uvicorn.access",
            logging.INFO,
            __file__,
            1,
            "POST /api/v1/infra-automation/targets/%s?reason=%s",
            (token, quote(token, safe="").replace(".", "%2E")),
            None,
        )
        rendered = SafeFormatter("%(message)s").format(record)
        self.assertFalse(token in rendered, "Grant leaked through access logging")
        self.assertIn(REDACTED, rendered)

    def test_lexical_grants_and_bounded_encodings_are_screened_without_key_lookup(self):
        token = "handoff-v1." + "a" * 64
        values = [token, token.upper(), "prefix" + token + "suffix"]
        encoded = token
        for _ in range(4):
            encoded = base64.b64encode(encoded.encode()).decode()
            values.append(encoded)
        values.append(quote(token, safe="").replace(".", "%2E"))
        for value in values:
            with self.subTest(kind="grant-format"):
                self.assertEqual(redact_reference(value), REDACTED)
                self.assertNotEqual(redact_text(value), value)
