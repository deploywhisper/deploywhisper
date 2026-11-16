"""Sensitive output never crosses the snapshot persistence boundary."""

import unittest
from cloud.base import (
    ResourceIdentity,
    ResourceRead,
    SnapshotFact,
    ReadStatus,
    validate_snapshot,
)
from cloud.redaction import redact_snapshot
from tests.test_cloud.test_snapshots import observation


class RedactionTests(unittest.TestCase):
    def test_secret_and_raw_fields_are_removed_before_digest(self):
        secret = "synthetic-private-canary-17-1"
        raw = "#!/bin/sh\necho private bootstrap content"
        identity = ResourceIdentity(
            address="resource.web",
            resource_type="instance",
            tags=(("password", secret), ("owner", secret)),
        )
        result = ResourceRead(
            identity=identity,
            status=ReadStatus.READ,
            facts=(
                SnapshotFact(name="password", value=secret),
                SnapshotFact(name="echo", value=secret),
                SnapshotFact(name="user_data", value=raw),
                SnapshotFact(name="raw_state", value='{"resources":[]}'),
                SnapshotFact(name="state", value="running"),
            ),
        )
        source = observation(resources=(result,))
        screened = redact_snapshot(source)
        rendered = screened.model_dump_json()
        self.assertNotIn(secret, rendered)
        self.assertNotIn(raw, rendered)
        self.assertNotIn('"user_data"', rendered)
        self.assertNotIn('"raw_state"', rendered)
        self.assertEqual(source.resources[0].facts[0].value, secret)
        self.assertNotEqual(screened.digest, source.digest)
        self.assertTrue(screened.partial)
        self.assertEqual(validate_snapshot(screened).digest, screened.digest)

    def test_account_masking_covers_all_retained_strings(self):
        account = "123456789012"
        identity = ResourceIdentity(
            address="resource." + account,
            resource_type="instance",
            arn=f"arn:aws:ec2:us-east-1:{account}:instance/i-synthetic",
            tags=(("owner", account),),
        )
        source = observation(
            resources=(
                ResourceRead(
                    identity=identity,
                    status=ReadStatus.READ,
                    facts=(SnapshotFact(name="account", value=account),),
                ),
            )
        )
        masked = redact_snapshot(source)
        self.assertNotIn(account, masked.model_dump_json())
        self.assertIn(
            account, redact_snapshot(source, mask_accounts=False).model_dump_json()
        )
        self.assertEqual(masked.digest, redact_snapshot(source).digest)

    def test_secret_values_in_keys_and_opaque_account_ids_are_screened(self):
        secret = "synthetic-key-canary-17-1"
        source = observation(
            resources=(
                ResourceRead(
                    identity=ResourceIdentity(
                        address="r", resource_type="instance", tags=((secret, "data"),)
                    ),
                    status=ReadStatus.READ,
                    facts=(SnapshotFact(name=secret, value="data"),),
                ),
            ),
            scope="tenant-opaque",
        )
        masked = redact_snapshot(
            source, sensitive_values=(secret,), account_identifiers=("tenant-opaque",)
        )
        self.assertNotIn(secret, masked.model_dump_json())
        self.assertNotIn("tenant-opaque", masked.model_dump_json())

    def test_masked_account_displays_do_not_merge_authorized_scopes(self):
        first = redact_snapshot(
            observation(scope="123456789012", scope_id="connection-a")
        )
        second = redact_snapshot(
            observation(scope="987654321098", scope_id="connection-b")
        )
        self.assertEqual(first.scope, second.scope)
        self.assertNotEqual(first.digest, second.digest)

    def test_redaction_is_idempotent(self):
        secret = "synthetic-idempotence-canary"
        source = observation(
            resources=(
                ResourceRead(
                    identity=ResourceIdentity(
                        address="r",
                        resource_type="instance",
                        tags=(("password", secret), ("owner", secret)),
                    ),
                    status=ReadStatus.READ,
                    facts=(
                        SnapshotFact(name="secret_key", value=secret),
                        SnapshotFact(name="echo", value=secret),
                    ),
                ),
            )
        )
        first = redact_snapshot(source)
        second = redact_snapshot(first)
        self.assertEqual(first.model_dump(mode="json"), second.model_dump(mode="json"))

    def test_raw_dotted_and_encoded_field_names_do_not_escape_projection(self):
        payload = "IyEvYmluL3NoIGVjaG8gcHJpdmF0ZQ=="
        result = ResourceRead(
            identity=ResourceIdentity(address="r", resource_type="instance"),
            status=ReadStatus.READ,
            facts=(
                SnapshotFact(name="ec2.user_data_base64", value=payload),
                SnapshotFact(name="metadata.raw_state", value="private-state-body"),
            ),
        )
        screened = redact_snapshot(observation(resources=(result,)))
        self.assertNotIn(payload, screened.model_dump_json())
        self.assertNotIn("private-state-body", screened.model_dump_json())

    def test_authority_identity_is_not_account_display(self):
        identifier = "connection-123456789012"
        source = observation(scope_id=identifier)
        screened = redact_snapshot(source)
        self.assertEqual(screened.scope_id, identifier)
        self.assertEqual(screened.project_id, source.project_id)
        self.assertEqual(screened.provider, source.provider)
        with self.assertRaises(ValueError):
            redact_snapshot(source, sensitive_values=(identifier,))

    def test_numeric_account_facts_are_maskable(self):
        result = ResourceRead(
            identity=ResourceIdentity(address="r", resource_type="instance"),
            status=ReadStatus.READ,
            facts=(SnapshotFact(name="account_id", value=123456789012),),
        )
        screened = redact_snapshot(observation(resources=(result,)))
        self.assertNotIn("123456789012", screened.model_dump_json())

    def test_integral_float_accounts_are_masked_without_changing_other_scalars(self):
        source = observation(
            scope="123456789012",
            resources=(
                ResourceRead(
                    identity=ResourceIdentity(address="r", resource_type="instance"),
                    status=ReadStatus.READ,
                    facts=(
                        SnapshotFact(name="account_id", value=123456789012.0),
                        SnapshotFact(name="count", value=2.0),
                        SnapshotFact(name="ratio", value=12.5),
                        SnapshotFact(name="enabled", value=True),
                    ),
                ),
            ),
        )
        screened = redact_snapshot(source)
        values = {fact.name: fact.value for fact in screened.resources[0].facts}
        self.assertEqual(values["account_id"], "[MASKED_ACCOUNT]")
        self.assertEqual(values["count"], 2.0)
        self.assertEqual(values["ratio"], 12.5)
        self.assertIs(values["enabled"], True)
        self.assertNotIn("123456789012", screened.model_dump_json())
        self.assertEqual(screened, redact_snapshot(screened))
        unmasked = redact_snapshot(source, mask_accounts=False)
        self.assertEqual(unmasked.resources[0].facts[0].value, 123456789012.0)

    def test_provider_user_data_aliases_are_removed_and_sibling_echoes_screened(self):
        aliases = (
            "aws_user_data",
            "instanceUserData",
            "ec2_instance_user_data_base64",
            "startup_script",
            "startup-script",
            "gcp_startup_script",
            "custom_data",
            "customData",
            "azure_vm_custom_data",
        )
        payloads = (
            "private single-line bootstrap command",
            "cHJpdmF0ZS1ib290c3RyYXAtcGF5bG9hZA==",
        )
        for alias in aliases:
            for payload in payloads:
                with self.subTest(alias=alias, payload_kind=payloads.index(payload)):
                    result = ResourceRead(
                        identity=ResourceIdentity(
                            address="r",
                            resource_type="instance",
                            name=payload,
                            tags=((alias, payload), ("owner", payload)),
                        ),
                        status=ReadStatus.READ,
                        facts=(
                            SnapshotFact(name=alias, value=payload),
                            SnapshotFact(name="echo", value=payload),
                            SnapshotFact(name="state", value="running"),
                        ),
                    )
                    screened = redact_snapshot(observation(resources=(result,)))
                    rendered = screened.model_dump_json()
                    self.assertNotIn(payload, rendered)
                    self.assertNotIn(
                        alias, {fact.name for fact in screened.resources[0].facts}
                    )
                    self.assertNotIn(alias, dict(screened.resources[0].identity.tags))
                    self.assertEqual(screened.redaction_status, "sensitive_blocked")
                    self.assertTrue(screened.partial)
                    self.assertEqual(screened.digest, redact_snapshot(screened).digest)

    def test_numeric_private_values_and_exact_sibling_echoes_are_screened(self):
        for secret in (8675309, 12.34, -56, 0, 1):
            with self.subTest(
                secret_type=type(secret).__name__, secret_case=str(secret)
            ):
                result = ResourceRead(
                    identity=ResourceIdentity(
                        address="r",
                        resource_type="instance",
                        name=str(secret),
                        tags=(("owner", str(secret)),),
                    ),
                    status=ReadStatus.READ,
                    facts=(
                        SnapshotFact(name="password", value=secret),
                        SnapshotFact(name="echo", value=secret),
                        SnapshotFact(name="string_echo", value=str(secret)),
                        SnapshotFact(name="prefixed_echo", value="echo-" + str(secret)),
                        SnapshotFact(name="unrelated_count", value=secret + 10),
                    ),
                )
                source = observation(resources=(result,))
                screened = redact_snapshot(source)
                facts = {fact.name: fact.value for fact in screened.resources[0].facts}
                self.assertNotIn("password", facts)
                self.assertEqual(facts["echo"], "[REDACTED]")
                self.assertEqual(facts["string_echo"], "[REDACTED]")
                self.assertNotEqual(facts["prefixed_echo"], "echo-" + str(secret))
                self.assertEqual(facts["unrelated_count"], secret + 10)
                self.assertEqual(screened.project_id, source.project_id)
                self.assertEqual(screened.snapshot_version, source.snapshot_version)
                self.assertEqual(screened.regions, source.regions)
                self.assertEqual(screened.scope_id, source.scope_id)
                self.assertEqual(screened.read_window_start, source.read_window_start)
                self.assertEqual(screened.read_window_end, source.read_window_end)
                self.assertEqual(screened.resources[0].identity.name, "[REDACTED]")
                self.assertEqual(
                    dict(screened.resources[0].identity.tags)["owner"], "[REDACTED]"
                )
                self.assertEqual(screened.digest, redact_snapshot(screened).digest)

    def test_numeric_secret_in_opaque_scope_identity_is_rejected_not_remapped(self):
        result = ResourceRead(
            identity=ResourceIdentity(address="r", resource_type="instance"),
            status=ReadStatus.READ,
            facts=(SnapshotFact(name="password", value=8675309),),
        )
        with self.assertRaises(ValueError):
            redact_snapshot(
                observation(resources=(result,), scope_id="connection8675309")
            )

    def test_provider_prefixed_raw_state_plan_and_response_aliases_are_blocked(self):
        aliases = (
            "aws_raw_state",
            "awsRawState",
            "azure.raw_state_base64",
            "aws_raw_plan",
            "providerRawPlanEncoded",
            "gcp.raw_plan_bytes",
            "raw_response_base64",
            "awsRawResponseBase64",
            "provider.raw_response_encoded",
        )
        payload = "cHJpdmF0ZS1zdGF0ZS1wbGFuLXJlc3BvbnNl"
        for alias in aliases:
            with self.subTest(alias=alias):
                result = ResourceRead(
                    identity=ResourceIdentity(
                        address="r", resource_type="instance", name=payload
                    ),
                    status=ReadStatus.READ,
                    facts=(
                        SnapshotFact(name=alias, value=payload),
                        SnapshotFact(name="echo", value=payload),
                    ),
                )
                screened = redact_snapshot(observation(resources=(result,)))
                self.assertNotIn(payload, screened.model_dump_json())
                self.assertNotIn(
                    alias, {fact.name for fact in screened.resources[0].facts}
                )
                self.assertTrue(screened.partial)
                self.assertEqual(screened.redaction_status, "sensitive_blocked")
                self.assertEqual(screened.digest, redact_snapshot(screened).digest)
