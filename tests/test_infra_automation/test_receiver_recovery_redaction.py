"""Known reconciliation credentials never become retained advisory material."""

from __future__ import annotations

import base64
from urllib.parse import quote
import unittest

from infra_automation.artifact_intake import screen_decoded_credentials, screen_metadata
from infra_automation.lifecycle import LifecycleError
from services.content_security import redact_reference, redact_text


class ReceiverRecoveryRedactionTests(unittest.TestCase):
    def variants(self):
        token = "receiver-reconcile-v1-" + "a" * 64
        values = [token, token.upper(), quote(token, safe="")]
        encoded = token
        for _ in range(4):
            encoded = base64.b64encode(encoded.encode()).decode()
            values.append(encoded)
            values.append(quote(encoded, safe=""))
        return values

    def test_literal_and_bounded_encoded_family_are_screened_in_plain_text(self):
        for credential in self.variants():
            with self.subTest(credential=credential):
                self.assertNotEqual(
                    redact_text("recovery " + credential), "recovery " + credential
                )
                self.assertNotEqual(
                    redact_reference("https://synthetic.invalid/path/" + credential),
                    "https://synthetic.invalid/path/" + credential,
                )

    def test_generic_decoded_json_keys_values_and_metadata_reject_family(self):
        for credential in self.variants():
            for value in (
                {"ordinary": credential},
                {credential: "ordinary"},
                [credential],
            ):
                with self.subTest(value=value), self.assertRaises(LifecycleError):
                    screen_decoded_credentials(value)
            with self.subTest(metadata=credential), self.assertRaises(LifecycleError):
                screen_metadata({"ordinary": credential})
