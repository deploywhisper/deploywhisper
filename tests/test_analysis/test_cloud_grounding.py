"""Live-context faults cannot weaken an existing advisory assessment."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from analysis.cloud_grounding import apply_grounding_degradation
from analysis.risk_scorer import RiskAssessment, SEVERITY_ORDER
from cloud.base import ResourceIdentity, ResourceRead, SnapshotFact, build_snapshot
from cloud.collection import CollectionBudget, PlanGroundingOutcome
from services.cloud_context_service import snapshot_context

NOW = datetime(2026, 11, 18, tzinfo=timezone.utc)


def outcome(cause=None, *, old=False, cancelled=False, create=False):
    end = NOW - timedelta(hours=2) if old else NOW
    read = ResourceRead(
        identity=ResourceIdentity(
            address="aws_instance.example", resource_type="aws_instance"
        ),
        status="no_live_counterpart" if create else "unreadable" if cause else "read",
        cause=cause,
        missing_permission="ec2:DescribeInstances"
        if cause == "permission_denied"
        else None,
        facts=() if cause or create else (SnapshotFact(name="state", value="running"),),
    )
    snapshot = build_snapshot(
        provider="aws",
        project_id=1,
        scope_id="opaque-scope",
        scope="masked",
        regions=("us-east-1",),
        read_window_start=end,
        read_window_end=end,
        resources=(read,),
    )
    count = 0 if create else 1
    return PlanGroundingOutcome(
        state="snapshot",
        project_id=1,
        snapshot=snapshot,
        context=snapshot_context(snapshot, now=end),
        budget=CollectionBudget(
            planned_calls=count,
            attempted_calls=count,
            actual_call_count=count,
            call_budget=100,
            budget_consumed=count,
            elapsed_seconds=0.01,
            cancelled=cancelled,
        ),
    )


def assessment(severity="low", confidence=0.926):
    return RiskAssessment(
        score={"low": 18, "medium": 42, "high": 72, "critical": 92}[severity],
        severity=severity,
        recommendation="no-go" if severity == "critical" else "go",
        confidence=confidence,
        top_risk="Existing deterministic risk",
        partial_context=False,
        context_completeness={"context_score": 0.95, "insufficient_context": False},
    )


class GroundingDegradationTests(unittest.TestCase):
    def test_every_provider_fault_respects_severity_and_confidence_floors(self):
        for severity in SEVERITY_ORDER:
            for cause in (
                "transport_error",
                "incomplete",
                "permission_denied",
                "throttled",
                "credentials_expired",
            ):
                with self.subTest(severity=severity, cause=cause):
                    before = assessment(severity)
                    original = before.model_dump()
                    result = apply_grounding_degradation(
                        before, outcome(cause), project_id=1, now=NOW
                    )
                    self.assertGreaterEqual(
                        SEVERITY_ORDER[result.severity], SEVERITY_ORDER[before.severity]
                    )
                    self.assertGreaterEqual(result.score, before.score)
                    self.assertLessEqual(result.confidence, before.confidence)
                    self.assertTrue(result.context_completeness.insufficient_context)
                    self.assertTrue(result.partial_context)
                    self.assertNotEqual(result.recommendation, "go")
                    self.assertEqual(before.model_dump(), original)

    def test_high_existing_context_cannot_hide_missing_grounding(self):
        result = apply_grounding_degradation(
            assessment(confidence=0.126),
            outcome("transport_error"),
            project_id=1,
            now=NOW,
        )
        self.assertTrue(result.context_completeness.insufficient_context)
        self.assertLessEqual(result.confidence, 0.126)
        self.assertEqual(
            result.context_completeness.context_sources[-1].freshness_status,
            "incomplete",
        )

    def test_expiry_is_recomputed_instead_of_trusting_cached_current_label(self):
        observed = outcome(old=True)
        self.assertEqual(observed.context.freshness_status, "current")
        result = apply_grounding_degradation(
            assessment(), observed, project_id=1, now=NOW
        )
        self.assertTrue(result.context_completeness.insufficient_context)
        self.assertEqual(
            result.context_completeness.context_sources[-1].freshness_status, "stale"
        )

    def test_unavailable_and_cancelled_collections_are_insufficient(self):
        missing = PlanGroundingOutcome(
            state="unavailable",
            project_id=1,
            budget=CollectionBudget(
                planned_calls=0,
                attempted_calls=0,
                actual_call_count=0,
                call_budget=100,
                budget_consumed=0,
                elapsed_seconds=0,
            ),
        )
        for observed in (missing, outcome(cancelled=True)):
            with self.subTest(state=observed.state):
                result = apply_grounding_degradation(
                    assessment(), observed, project_id=1, now=NOW
                )
                self.assertTrue(result.context_completeness.insufficient_context)

    def test_disabled_and_absent_are_byte_compatible(self):
        before = assessment()
        for observed in (None, PlanGroundingOutcome(state="disabled", project_id=1)):
            self.assertEqual(
                apply_grounding_degradation(
                    before, observed, project_id=1, now=NOW
                ).model_dump(),
                before.model_dump(),
            )

    def test_complete_and_pure_create_do_not_change_existing_verdict(self):
        before = assessment()
        for observed in (outcome(), outcome(create=True)):
            result = apply_grounding_degradation(
                before, observed, project_id=1, now=NOW
            )
            self.assertEqual(
                (
                    result.score,
                    result.severity,
                    result.confidence,
                    result.recommendation,
                ),
                (
                    before.score,
                    before.severity,
                    before.confidence,
                    before.recommendation,
                ),
            )
            self.assertFalse(result.context_completeness.insufficient_context)

    def test_project_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "grounding_scope_mismatch"):
            apply_grounding_degradation(assessment(), outcome(), project_id=2, now=NOW)

    def test_diagnostic_source_does_not_claim_an_evidence_retention_reference(self):
        result = apply_grounding_degradation(
            assessment(), outcome("permission_denied"), project_id=1, now=NOW
        )
        source = result.context_completeness.context_sources[-1]
        self.assertIsNone(source.source_ref)
        self.assertEqual(source.source_id, "live_state:collection")
        self.assertIn("collection_metadata_only", source.limitations)
