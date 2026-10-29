"""Immutable severity confirmation and versioned decision audit transition proof."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

from pydantic import ValidationError
from sqlalchemy import select

import config
from infra_automation.decisions import binding_digest, freeze_report_snapshot
from infra_automation.lifecycle import LifecycleError
from infra_automation.state import AuditActor
from models.repositories import infra_automation_decisions as decisions
from models.repositories.settings import upsert_setting
from models.tables import (
    AnalysisReport,
    IdentityAccount,
    InfraAutomationAudit,
)
from services import infra_automation_decisions as service
from services.policy_adapter_settings import PolicyAdapterSettings
from services.report_service import _serialize_report
from services.settings_service import _policy_adapter_settings_key
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation import test_decision_service as fixture


class ApprovalConfirmationTests(LifecycleCase):
    publish_fixture = fixture.DecisionServiceTests.publish_fixture
    setUp = fixture.DecisionServiceTests.setUp
    pending = fixture.DecisionServiceTests.pending
    request = fixture.DecisionServiceTests.request

    def enable(self):
        fixture.DecisionServiceTests.enable(self)
        # Seed an explicitly advisory policy before the immutable run is captured.
        # Confirmation must work for eligible high/critical evidence without
        # weakening a hard policy floor in the service under test.
        if getattr(self, "allow_high", True):
            policy = PolicyAdapterSettings(
                project_key="lifecycle-one",
                source="project",
                warn_at=None,
                soft_block_at=None,
                hard_block_at=None,
            )
            with self.factory.begin() as db:
                upsert_setting(
                    db,
                    key=_policy_adapter_settings_key(project_key=policy.project_key),
                    value=policy.model_dump_json(),
                    commit=False,
                )

    def severity(self, severity, recommendation="go"):
        with self.factory.begin() as db:
            report = db.get(AnalysisReport, 1)
            report.severity = severity
            report.recommendation = recommendation
            report.risk_assessment.overall_severity = severity
            report.risk_assessment.recommendation = recommendation
            self.raw_report, digest = freeze_report_snapshot(_serialize_report(report))
        binding = self.material.binding.model_copy(
            update={"report_bytes_digest": digest}
        )
        identity = binding_digest(binding)
        self.material = replace(
            self.material,
            binding=binding,
            live=self.material.live.model_copy(
                update={
                    "expected_tuple_digest": identity,
                    "current_tuple_digest": identity,
                }
            ),
        )

    def request_with_confirmation(self, row, outcome="approve", confirmation=None):
        return service.DecisionRequest(
            **{**self.request(row, outcome).model_dump(), "confirmation": confirmation}
        )

    def audit_rows(self, event_type=None):
        with self.factory() as db:
            query = select(InfraAutomationAudit).order_by(InfraAutomationAudit.sequence)
            if event_type:
                query = query.where(InfraAutomationAudit.event_type == event_type)
            return list(db.scalars(query))

    def assert_pending_without_audit(self, row, count):
        with self.factory() as db:
            stored = decisions.get_request(db, row["id"])
            self.assertEqual((stored.status, stored.version), ("pending", 1))
        self.assertEqual(len(self.audit_rows()), count)

    def test_confirmation_is_derived_from_retained_severity_and_server_model(self):
        for severity in ("low", "medium", "high", "critical"):
            for kind, approve in (
                ("independent-approval", "APPROVE target"),
                ("acknowledgement", "ACKNOWLEDGE target"),
            ):
                with self.subTest(severity=severity, kind=kind):
                    value = service.confirmation_requirements(
                        self.material.binding, {"severity": severity}, kind
                    )
                    self.assertEqual(value.required, severity in {"high", "critical"})
                    self.assertEqual(
                        value.approve_phrase, approve if value.required else None
                    )
                    self.assertEqual(
                        value.reject_phrase, "REJECT target" if value.required else None
                    )
        for bad in (None, "unknown", True, [], {}):
            with self.subTest(severity=bad), self.assertRaises(LifecycleError):
                service.confirmation_requirements(
                    self.material.binding, {"severity": bad}, "independent-approval"
                )

    def test_high_and_critical_missing_or_wrong_confirmation_preserve_pending(self):
        self.severity("critical")
        row = self.pending()
        count = len(self.audit_rows())
        for outcome in ("approve", "reject"):
            for value in (
                None,
                "",
                "APPROVE other",
                "approve target",
                " APPROVE target",
                "ACKNOWLEDGE target",
            ):
                with self.subTest(outcome=outcome, confirmation=value):
                    request = self.request_with_confirmation(row, outcome, value)
                    with (
                        self.credentials("reviewer"),
                        self.assertRaises(LifecycleError) as error,
                    ):
                        self.service.decide(row["id"], request)
                    self.assertEqual(error.exception.status_code, 422)
                    self.assert_pending_without_audit(row, count)

    def test_exact_high_confirmation_approves_without_changing_report(self):
        self.severity("high")
        row = self.pending()
        with self.credentials("reviewer"):
            result = self.service.decide(
                row["id"],
                self.request_with_confirmation(row, confirmation="APPROVE target"),
            )
        self.assertEqual(result["status"], "approved")
        with self.factory() as db:
            self.assertEqual(
                decisions.get_request(db, row["id"]).report_bytes, self.raw_report
            )

    def test_exact_critical_confirmation_rejects_explicitly(self):
        self.severity("critical")
        row = self.pending()
        with self.credentials("reviewer"):
            result = self.service.decide(
                row["id"],
                self.request_with_confirmation(row, "reject", "REJECT target"),
            )
        self.assertEqual(result["status"], "rejected")

    def test_single_operator_uses_acknowledgement_phrase_selected_by_server(self):
        self.severity("high")
        with self.factory.begin() as db:
            db.get(IdentityAccount, "reviewer").enabled = False
        with patch(
            "config.settings",
            replace(config.settings, identity_decision_mode="single-operator"),
        ):
            row = self.pending()
            with self.credentials(), self.assertRaises(LifecycleError) as failure:
                self.service.decide(
                    row["id"],
                    self.request_with_confirmation(row, confirmation="APPROVE target"),
                )
            self.assertEqual(failure.exception.status_code, 422)
            with self.credentials():
                result = self.service.decide(
                    row["id"],
                    self.request_with_confirmation(
                        row, confirmation="ACKNOWLEDGE target"
                    ),
                )
            self.assertEqual(result["decision_kind"], "acknowledgement")

    def test_no_go_does_not_invent_a_new_confirmation_or_policy_block(self):
        self.severity("low", "no-go")
        row = self.pending()
        with self.credentials("reviewer"):
            result = self.service.decide(row["id"], self.request(row))
        self.assertEqual(result["status"], "approved")

    def test_confirmation_cannot_override_changed_mandatory_evidence(self):
        self.severity("high")
        row = self.pending()
        self.material = replace(
            self.material,
            evidence=self.material.evidence.model_copy(update={"complete": False}),
        )
        with self.credentials("reviewer"), self.assertRaises(LifecycleError) as failure:
            self.service.decide(
                row["id"],
                self.request_with_confirmation(row, confirmation="APPROVE target"),
            )
        self.assertEqual(failure.exception.status_code, 409)
        with self.factory() as db:
            self.assertEqual(decisions.get_request(db, row["id"]).status, "invalidated")

    def test_confirmation_is_strict_bounded_and_cannot_select_decision_mode(self):
        row = self.pending()
        for value in (True, 1, [], "x" * 257, "APPROVE\ntarget"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.request_with_confirmation(row, confirmation=value)
        with self.assertRaises(ValidationError):
            service.DecisionRequest(
                **{**self.request(row).model_dump(), "decision_kind": "acknowledgement"}
            )

    def test_repeated_request_has_equal_state_digests_without_new_generation(self):
        original = self.pending()
        repeated = self.pending()
        self.assertEqual(
            (original["id"], original["generation"], original["version"]),
            (repeated["id"], repeated["generation"], repeated["version"]),
        )
        event = self.audit_rows("decision_requested")[-1]
        self.assertEqual(event.before_digest, event.after_digest)
        self.assertIsNotNone(event.before_digest)
        with self.factory() as db:
            stored = decisions.get_request(db, repeated["id"])
            self.assertEqual(
                event.after_digest,
                service.decision_audit_digest(
                    stored, actor=AuditActor("human-a", "human", "admin")
                ),
            )

    def test_decision_audit_contains_both_state_digests_and_historical_attribution(
        self,
    ):
        row = self.pending()
        with self.factory() as db:
            stored = decisions.get_request(db, row["id"])
            before = service.decision_audit_digest(stored)
        with self.credentials("reviewer"):
            self.service.decide(row["id"], self.request(row))
        event = self.audit_rows("decision_approve")[-1]
        self.assertEqual(event.before_digest, before)
        self.assertNotEqual(event.before_digest, event.after_digest)
        self.assertNotEqual(event.after_digest, row["binding_digest"])
        self.assertEqual(
            (event.actor_principal_id, event.actor_type, event.actor_role),
            ("reviewer", "human", "reviewer"),
        )
        with self.factory() as db:
            stored = decisions.get_request(db, row["id"])
            after = service.decision_audit_digest(
                stored,
                actor=AuditActor(
                    event.actor_principal_id, event.actor_type, event.actor_role
                ),
            )
            self.assertEqual(event.after_digest, after)
        self.member("read-only", principal="reviewer")
        unchanged = self.audit_rows("decision_approve")[-1]
        self.assertEqual(unchanged.actor_role, "reviewer")

    def test_expiration_audits_state_transition_without_rewriting_old_events(self):
        row = self.pending()
        original = [
            (event.id, event.before_digest, event.after_digest)
            for event in self.audit_rows()
        ]
        self.now += timedelta(minutes=5)
        # Keep the original requester session live at the decision boundary.
        from models.tables import IdentitySession

        with self.factory.begin() as db:
            for session in db.scalars(select(IdentitySession)):
                session.last_seen_at = self.now
        with self.credentials("reviewer"), self.assertRaises(LifecycleError):
            self.service.decide(row["id"], self.request(row))
        event = self.audit_rows("decision_invalidated")[-1]
        self.assertIsNotNone(event.before_digest)
        self.assertIsNotNone(event.after_digest)
        self.assertNotEqual(event.before_digest, event.after_digest)
        self.assertEqual(
            original,
            [
                (event.id, event.before_digest, event.after_digest)
                for event in self.audit_rows()[: len(original)]
            ],
        )
