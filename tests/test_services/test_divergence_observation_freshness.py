"""Trusted wall-clock freshness for retained plan comparison and publication."""

from contextlib import nullcontext
from datetime import timedelta
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cloud.base import build_snapshot
from services import divergence_service


FIXTURES = (
    Path(__file__).resolve().parents[1] / "fixtures" / "live_environment_divergence"
)


class RetainedObservationFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((FIXTURES / "plan.json").read_text())
        self.snapshot_fields = json.loads((FIXTURES / "snapshot.json").read_text())
        self.snapshot = build_snapshot(**self.snapshot_fields)

    def compare(self, age, *, address=None):
        fields = self.snapshot_fields.copy()
        plan = self.plan.copy()
        if address is not None:
            fields["resources"] = [
                row
                for row in fields["resources"]
                if row["identity"]["address"] == address
            ]
            plan["resource_changes"] = [
                row for row in plan["resource_changes"] if row["address"] == address
            ]
        snapshot = build_snapshot(**fields)
        with (
            patch.object(
                divergence_service,
                "divergence_admission",
                return_value=nullcontext(SimpleNamespace(snapshot=snapshot)),
            ),
            patch.object(divergence_service, "datetime", create=True) as clock,
        ):
            clock.now.return_value = snapshot.read_window_end + age
            return divergence_service.compare_retained_plan(
                [("plan.json", json.dumps(plan).encode())],
                project_id=snapshot.project_id,
                snapshot_digest=snapshot.digest,
                stale_after_seconds=3600,
            )

    def test_observation_age_is_separate_from_plan_age_and_controls_ci(self):
        for age, status, exit_code in (
            (timedelta(hours=1), "current", 0),
            (timedelta(hours=1, microseconds=1), "stale", 2),
            (timedelta(microseconds=-1), "unknown", 2),
        ):
            with self.subTest(status=status):
                result = self.compare(age, address="aws_instance.match")
                self.assertEqual(result.freshness.status, "stale")
                self.assertEqual(result.observation_status, status)
                self.assertEqual(
                    divergence_service.divergence_gate_exit_code(result), exit_code
                )

    def test_stale_partial_snapshot_keeps_denial_and_never_confirms_drift(self):
        result = self.compare(timedelta(hours=2))
        rows = {row.address: row for row in result.resources}
        self.assertTrue(self.snapshot.partial)
        self.assertEqual(result.observation_status, "stale")
        self.assertEqual(rows["aws_instance.modified"].status, "unknown")
        self.assertEqual(rows["aws_instance.unreadable"].status, "unreadable")
        self.assertEqual(
            rows["aws_instance.unreadable"].missing_permission, "ec2:DescribeInstances"
        )
        self.assertFalse(result.diverged)
        self.assertTrue(divergence_service.divergence_has_gaps(result))
        self.assertEqual(divergence_service.divergence_gate_exit_code(result), 2)

    def test_unverified_chronology_fails_even_for_an_empty_comparison(self):
        self.plan["resource_changes"] = []
        dated = self.compare(timedelta(minutes=5))
        self.assertEqual(dated.resources, ())
        self.assertEqual(divergence_service.divergence_gate_exit_code(dated), 0)
        self.plan.pop("timestamp")
        result = self.compare(timedelta(minutes=5))
        self.assertEqual(result.resources, ())
        self.assertEqual(result.freshness.status, "unknown")
        self.assertTrue(divergence_service.divergence_has_gaps(result))
        self.assertEqual(divergence_service.divergence_gate_exit_code(result), 2)

    def test_publication_fails_closed_after_a_current_observation_expires(self):
        result = self.compare(timedelta(minutes=59))
        self.assertTrue(result.diverged)
        self.assertTrue(divergence_service.divergence_has_gaps(result))
        self.assertEqual(divergence_service.divergence_gate_exit_code(result), 3)
        with patch.object(divergence_service, "datetime", create=True) as clock:
            clock.now.return_value = self.snapshot.read_window_end + timedelta(hours=2)
            with self.assertRaises(divergence_service.DivergenceRequestError) as raised:
                divergence_service.ensure_comparison_publishable(result, self.snapshot)
            self.assertEqual(raised.exception.code, "grounding_evidence_unavailable")
            stale = self.compare(timedelta(hours=2))
            divergence_service.ensure_comparison_publishable(stale, self.snapshot)
