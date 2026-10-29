"""Reviewer-aware immutable packet reads with live authority and no audit writes."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json
from unittest.mock import patch

from pydantic import ValidationError
from infra_automation.review_contracts import ApprovalReviewPacket
from sqlalchemy import func, select

from models.tables import (
    InfraAutomationAudit,
    InfraAutomationPolicy,
    AnalysisReport,
    IdentityAccount,
)
import config
from infra_automation.decisions import freeze_report_snapshot, binding_digest
from services.report_service import _serialize_report
from services import infra_automation_review as review
from services import project_service as authorization
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation import test_decision_service as fixture
from tests.test_infra_automation import (
    test_approval_confirmation as confirmation_fixture,
)


class ApprovalReviewTests(LifecycleCase):
    enable = confirmation_fixture.ApprovalConfirmationTests.enable
    publish_fixture = fixture.DecisionServiceTests.publish_fixture
    setUp = fixture.DecisionServiceTests.setUp
    pending = fixture.DecisionServiceTests.pending
    request = fixture.DecisionServiceTests.request
    approve = fixture.DecisionServiceTests.approve

    def read(self, row, principal="reviewer", **kwargs):
        with self.credentials(principal):
            return review.get_approval(
                row["id"], 100, 100, decision_service=self.service, **kwargs
            )

    def test_pending_packet_is_current_immutable_and_read_does_not_audit(self):
        row = self.pending()
        with self.factory() as db:
            before = db.scalar(select(func.count()).select_from(InfraAutomationAudit))
        result = self.read(row)
        self.assertTrue(result.context.can_submit)
        self.assertEqual(result.context.status, "eligible")
        self.assertEqual(result.context.decision_kind, "independent-approval")
        self.assertEqual(
            result.report.report_bytes_digest, row["binding"]["report_bytes_digest"]
        )
        self.assertEqual(result.report.report_url, "/reports/1")
        self.assertEqual(result.action.payload_digest, row["binding"]["payload_digest"])
        self.assertFalse(result.report.should_block)
        self.assertIsNone(result.attribution)
        self.assertFalse(result.can_export_audit)
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraAutomationAudit)),
                before,
            )

    def test_selected_scope_mismatch_denies_without_disclosing_packet(self):
        row = self.pending()
        with (
            self.credentials("reviewer"),
            self.assertRaises(authorization.TrustedAuthorizationError),
        ):
            review.get_approval(row["id"], 200, 200, decision_service=self.service)

    def test_shared_requester_reads_but_cannot_submit(self):
        result = self.read(self.pending(), "human-a")
        self.assertFalse(result.context.can_submit)
        self.assertIn("requester_excluded", result.context.reasons)
        self.assertTrue(result.can_export_audit)

    def test_unavailable_material_keeps_historical_packet_readable(self):
        row = self.pending()
        self.service.material_port = None
        result = self.read(row)
        self.assertEqual(result.receipt.id, row["id"])
        self.assertEqual(result.context.status, "unavailable")
        self.assertFalse(result.context.can_submit)
        self.assertIn("authority_unavailable", result.context.reasons)

    def test_feature_off_keeps_history_readable_and_blocks_controls(self):
        row = self.pending()
        with self.factory.begin() as db:
            policy = db.scalar(select(InfraAutomationPolicy))
            settings = json.loads(policy.settings_json)
            settings["enabled"] = False
            policy.settings_json = json.dumps(settings)
        result = self.read(row)
        self.assertEqual(result.context.status, "blocked")
        self.assertIn("feature_disabled", result.context.reasons)
        self.assertFalse(result.context.can_submit)

    def test_report_summary_uses_stored_bytes_not_live_decorations(self):
        row = self.pending()
        with self.factory.begin() as db:
            report = db.get(AnalysisReport, 1)
            report.risk_score = 99
            report.recommendation = "no-go"
        result = self.read(row)
        self.assertEqual(result.report.recommendation, "go")
        self.assertEqual(result.report.confidence.score, 1.0)
        self.assertEqual(
            result.receipt.binding.report_bytes_digest,
            row["binding"]["report_bytes_digest"],
        )

    def test_effective_deadline_includes_run_ceiling(self):
        row = self.pending()
        with self.factory.begin() as db:
            run = fixture.runs.get_run(db, self.run.id)
            run.deadline_at = self.now + timedelta(seconds=10)
        result = self.read(row)
        self.assertEqual(
            result.context.effective_deadline,
            fixture.support.utc(self.now + timedelta(seconds=10)),
        )

    def test_expired_decision_is_blocked_with_typed_guidance(self):
        row = self.pending()
        self.now += timedelta(minutes=5)
        # Obtain a fresh authenticated session after the fixture's idle boundary.
        with self.factory.begin() as db:
            for session in db.scalars(
                select(fixture.IdentitySession).where(
                    fixture.IdentitySession.principal_id == "reviewer"
                )
            ):
                session.last_seen_at = self.now
        result = self.read(row)
        self.assertFalse(result.context.can_submit)
        self.assertIn("approval_expired", result.context.reasons)

    def test_decided_receipt_survives_missing_material_and_keeps_historical_role(self):
        row = self.approve()
        self.member("contributor", principal="reviewer")
        self.service.material_port = None
        result = self.read(row, "human-a")
        self.assertEqual(result.context.status, "decided")
        self.assertFalse(result.context.can_submit)
        self.assertEqual(result.attribution.principal_id, "reviewer")
        self.assertEqual(result.attribution.role, "reviewer")
        self.assertEqual(result.attribution.state_digest_version, 1)
        self.assertIsNotNone(result.attribution.before_digest)

    def refresh_report(self, mutate):
        with self.factory.begin() as db:
            report = db.get(AnalysisReport, 1)
            mutate(report)
            self.raw_report, digest = freeze_report_snapshot(_serialize_report(report))
        binding = self.material.binding.model_copy(
            update={"report_bytes_digest": digest}
        )
        value = binding_digest(binding)
        self.material = replace(
            self.material,
            binding=binding,
            live=self.material.live.model_copy(
                update={"expected_tuple_digest": value, "current_tuple_digest": value}
            ),
        )

    def test_pending_high_severity_confirmation_is_server_selected(self):
        self.refresh_report(lambda report: setattr(report, "severity", "high"))
        result = self.read(self.pending())
        self.assertEqual(result.report.severity, "high")
        self.assertTrue(result.context.confirmation.required)
        self.assertEqual(result.context.confirmation.approve_phrase, "APPROVE target")
        self.assertEqual(result.context.confirmation.reject_phrase, "REJECT target")

    def test_pending_single_operator_has_acknowledgement_label_before_submission(self):
        self.refresh_report(lambda report: setattr(report, "severity", "high"))
        row = self.pending()
        with self.factory.begin() as db:
            db.get(IdentityAccount, "reviewer").enabled = False
        with patch(
            "config.settings",
            replace(config.settings, identity_decision_mode="single-operator"),
        ):
            result = self.read(row, "human-a")
        self.assertEqual(result.context.decision_kind, "acknowledgement")
        self.assertTrue(result.context.can_submit)
        self.assertEqual(
            result.context.confirmation.approve_phrase, "ACKNOWLEDGE target"
        )

    def test_pre_screened_marker_and_paths_do_not_hide_historical_packet(self):
        for text in (
            "A [REDACTED] dependency remains.",
            "Review /operator/local/plan.bin first.",
        ):
            with self.subTest(text=text):
                case = ApprovalReviewTests()
                try:
                    case.setUp()

                    def mutate(report):
                        rollback = json.loads(
                            _serialize_report(report)["rollback_plan"]
                            if isinstance(
                                _serialize_report(report)["rollback_plan"], str
                            )
                            else json.dumps(_serialize_report(report)["rollback_plan"])
                        )
                        rollback["complexity_explanation"] = text
                        report.rollback_plan_json = json.dumps(rollback)

                    case.refresh_report(mutate)
                    row = case.pending()
                    result = case.read(row)
                    self.assertTrue(result.screening_limited)
                    self.assertTrue(result.report.summary_limited)
                    self.assertNotIn(text, result.model_dump_json())
                    self.assertEqual(
                        result.receipt.binding.report_bytes_digest,
                        row["binding"]["report_bytes_digest"],
                    )
                finally:
                    case.doCleanups()

    def test_unavailable_clock_preserves_pending_and_decided_history(self):
        row = self.pending()
        with patch.object(
            self.service, "_now", side_effect=fixture.LifecycleError(503)
        ):
            pending = self.read(row)
        self.assertEqual(pending.context.status, "unavailable")
        self.assertIsNone(pending.context.evaluated_at)
        self.assertEqual(pending.context.reasons, ("invalid_clock",))
        with self.credentials("reviewer"):
            recorded = self.service.decide(row["id"], self.request(row))
        self.service.clock = lambda: None
        decided = self.read(recorded)
        self.assertEqual(decided.receipt.status, "approved")
        self.assertFalse(decided.context.can_submit)
        self.assertIsNone(decided.context.evaluated_at)

    def test_closed_projection_rejects_coerced_literals_and_incoherent_permission(self):
        packet = self.read(self.approve()).model_dump(mode="json")
        for path, value in (
            (("version",), True),
            (("version",), "1"),
            (("report", "should_block"), 0),
            (("attribution", "state_digest_version"), True),
            (("attribution", "state_digest_version"), "1"),
            (("context", "can_submit"), True),
        ):
            changed = json.loads(json.dumps(packet))
            target = changed
            for component in path[:-1]:
                target = target[component]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValidationError):
                ApprovalReviewPacket.model_validate_json(json.dumps(changed))

    def test_uploaded_action_never_fabricates_repository_or_commit(self):
        from tests.test_infra_automation.test_decisions import binding_payload
        from infra_automation.decisions import DecisionBinding

        binding = DecisionBinding.model_validate_json(json.dumps(binding_payload()))
        result = review._action(binding)
        self.assertEqual(result.source_kind, "uploaded")
        self.assertIsNone(result.source_repository_id)
        self.assertIsNone(result.source_commit_sha)

    def test_unicode_summary_budget_is_bytes_without_altering_retained_evidence(self):
        message = "🙂" * 2000

        def mutate(report):
            rollback = dict(_serialize_report(report)["rollback_plan"])
            rollback["complexity_explanation"] = message
            report.rollback_plan_json = json.dumps(rollback)

        self.refresh_report(mutate)
        row = self.pending()
        result = self.read(row)
        self.assertLessEqual(
            len(result.report.rollback.explanation.encode("utf-8")), 512
        )
        self.assertTrue(result.report.summary_limited)
        self.assertTrue(result.report.rollback.explanation.endswith("…"))
        self.assertEqual(
            result.receipt.binding.report_bytes_digest,
            row["binding"]["report_bytes_digest"],
        )
