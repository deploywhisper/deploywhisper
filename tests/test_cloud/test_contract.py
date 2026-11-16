"""Provider-neutral identity and read-result boundaries."""

import unittest

from pydantic import ValidationError
from cloud.base import ResourceIdentity, ResourceRead, SnapshotFact, ReadStatus


class ContractTests(unittest.TestCase):
    def test_frozen_identity_and_nested_facts(self):
        identity = ResourceIdentity(
            address="aws_instance.web",
            resource_type="aws_instance",
            tags=(("owner", "platform"),),
        )
        result = ResourceRead(
            identity=identity,
            status=ReadStatus.READ,
            facts=(SnapshotFact(name="state", value="running"),),
        )
        with self.assertRaises(ValidationError):
            identity.address = "different"
        with self.assertRaises(TypeError):
            identity.tags[0] = ("owner", "different")
        with self.assertRaises(ValidationError):
            result.facts[0].value = "stopped"

    def test_invalid_facts_and_read_failures_reject(self):
        identity = ResourceIdentity(address="resource.web", resource_type="instance")
        for value in (float("nan"), float("inf"), {"raw": "value"}, [1, 2], b"bytes"):
            with self.subTest(value=type(value)), self.assertRaises(ValidationError):
                SnapshotFact(name="state", value=value)
        for status in (ReadStatus.UNREADABLE, ReadStatus.UNKNOWN, ReadStatus.PARTIAL):
            with self.subTest(status=status), self.assertRaises(ValidationError):
                ResourceRead(identity=identity, status=status)
        self.assertEqual(
            ResourceRead(
                identity=identity, status=ReadStatus.NO_LIVE_COUNTERPART
            ).facts,
            (),
        )

    def test_duplicate_tags_and_facts_reject(self):
        with self.assertRaises(ValidationError):
            ResourceIdentity(
                address="r",
                resource_type="instance",
                tags=(("owner", "one"), ("owner", "two")),
            )
        identity = ResourceIdentity(address="r", resource_type="instance")
        with self.assertRaises(ValidationError):
            ResourceRead(
                identity=identity,
                status=ReadStatus.READ,
                facts=(
                    SnapshotFact(name="state", value="one"),
                    SnapshotFact(name="state", value="two"),
                ),
            )

    def test_whitespace_identifiers_and_causes_reject(self):
        for field in (
            "address",
            "resource_type",
            "physical_id",
            "arn",
            "name",
            "region",
        ):
            values = dict(address="resource.web", resource_type="instance")
            values[field] = " "
            with self.subTest(field=field), self.assertRaises(ValidationError):
                ResourceIdentity(**values)
        with self.assertRaises(ValidationError):
            ResourceRead(
                identity=ResourceIdentity(address="r", resource_type="instance"),
                status=ReadStatus.UNREADABLE,
                cause=" ",
            )
