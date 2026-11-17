"""Immutable and deterministic observation identity."""

from datetime import datetime, timedelta, timezone
import unittest
import warnings
from pydantic import ValidationError
from cloud.base import (
    ResourceIdentity,
    ResourceRead,
    SnapshotFact,
    ReadStatus,
    build_snapshot,
    validate_snapshot,
)


def observation(**overrides):
    values = dict(
        provider="reference",
        project_id=1,
        scope="123456789012",
        scope_id="reference-connection-a",
        regions=("us-west-2", "us-east-1"),
        read_window_start=datetime(2026, 11, 13, tzinfo=timezone.utc),
        read_window_end=datetime(2026, 11, 13, 0, 1, tzinfo=timezone.utc),
        resources=(
            ResourceRead(
                identity=ResourceIdentity(
                    address="resource.web", resource_type="instance"
                ),
                status=ReadStatus.READ,
                facts=(SnapshotFact(name="state", value="running"),),
            ),
        ),
        issued_actions=("reference:GetResource",),
    )
    values.update(overrides)
    return build_snapshot(**values)


class SnapshotTests(unittest.TestCase):
    def test_digest_round_trip_and_field_coverage(self):
        first = observation()
        self.assertEqual(first.digest, observation().digest)
        self.assertEqual(
            validate_snapshot(first.model_dump(mode="json")).digest, first.digest
        )
        self.assertEqual(len(first.digest), 64)
        self.assertFalse(first.partial)
        with self.assertRaises(ValidationError):
            first.scope = "other"
        changed = first.model_dump(mode="json")
        changed["scope"] = "other"
        with self.assertRaises(ValidationError):
            validate_snapshot(changed)
        with self.assertRaises(ValidationError):
            validate_snapshot(first.model_copy(update={"project_id": 2}))

    def test_unordered_sets_and_utc_are_canonical(self):
        first = observation()
        self.assertEqual(
            first.digest, observation(regions=tuple(reversed(first.regions))).digest
        )
        other = ResourceRead(
            identity=ResourceIdentity(address="resource.db", resource_type="database"),
            status=ReadStatus.NO_LIVE_COUNTERPART,
        )
        self.assertEqual(
            observation(resources=first.resources + (other,)).digest,
            observation(resources=(other,) + first.resources).digest,
        )
        offset = timezone(timedelta(hours=2))
        self.assertEqual(
            first.digest,
            observation(
                read_window_start=first.read_window_start.astimezone(offset),
                read_window_end=first.read_window_end.astimezone(offset),
            ).digest,
        )

    def test_bad_window_duplicates_and_partial_labels(self):
        first = observation()
        for args in (
            {"read_window_start": datetime(2026, 11, 13)},
            {"read_window_end": datetime(2026, 11, 12, tzinfo=timezone.utc)},
            {"resources": first.resources * 2},
        ):
            with self.subTest(args=tuple(args)), self.assertRaises(ValidationError):
                observation(**args)
        unreadable = ResourceRead(
            identity=first.resources[0].identity,
            status=ReadStatus.UNREADABLE,
            cause="AccessDenied",
            missing_permission="reference:GetResource",
        )
        partial = observation(resources=(unreadable,))
        self.assertTrue(partial.partial)
        self.assertEqual(partial.resources[0].cause, "AccessDenied")

    def test_missing_or_blank_digest_cannot_be_admitted(self):
        first = observation()
        for value in (None, ""):
            data = first.model_dump(mode="json")
            if value is None:
                data.pop("digest")
            else:
                data["digest"] = value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_snapshot(data)

    def test_tampered_model_revalidation_does_not_warn_with_sensitive_input(self):
        source = observation().model_copy(
            update={"resources": ("synthetic-private-serializer-canary",)}
        )
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            with self.assertRaises(ValidationError):
                validate_snapshot(source)
        self.assertEqual(recorded, [])
