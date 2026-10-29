"""Review regressions for finite decision authority and recoverable human pauses."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json
from unittest.mock import patch

from infra_automation.decisions import DecisionBinding, binding_digest
from infra_automation.lifecycle import LifecycleError
from models.repositories import infra_automation_decisions as decisions
from models.repositories import infra_automation_runs as runs
from models.tables import InfraAutomationArtifactManifest
from services import project_service as authorization
from services import infra_automation_support as support
from services.infra_automation_decisions import _view
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation import test_decision_service as fixture


class DecisionReviewRegressions(LifecycleCase):
    enable = fixture.DecisionServiceTests.enable
    publish_fixture = fixture.DecisionServiceTests.publish_fixture
    setUp = fixture.DecisionServiceTests.setUp
    pending = fixture.DecisionServiceTests.pending
    request = fixture.DecisionServiceTests.request
    approve = fixture.DecisionServiceTests.approve
    recheck = fixture.DecisionServiceTests.recheck

    def short_deadline(self, kind):
        payload = self.material.binding.model_dump(mode="json")
        deadline = self.now + timedelta(seconds=1)
        if kind in {"evidence", "source"}:
            payload["evidence_deadline"] = support.utc(deadline)
        if kind == "approval":
            payload["approval_deadline"] = support.utc(deadline)
        if kind == "custody":
            payload["provenance"]["custody"]["expires_at"] = support.utc(deadline)
        if kind == "source":
            payload["provenance"]["source"]["source_deadline"] = support.utc(deadline)
            with self.factory.begin() as db:
                manifest = db.get(InfraAutomationArtifactManifest, "manifest")
                collection = json.loads(manifest.collection_bytes)
                collection["source_deadline"] = support.utc(deadline)
                manifest.collection_bytes = support.canonical(collection)
                manifest.collection_digest = support.digest(manifest.collection_bytes)
        binding = DecisionBinding.model_validate_json(json.dumps(payload))
        digest = binding_digest(binding)
        self.material = replace(
            self.material,
            binding=binding,
            evidence=self.material.evidence.model_copy(
                update={"evidence_deadline": deadline}
                if kind in {"evidence", "source"}
                else {}
            ),
            live=self.material.live.model_copy(
                update={"expected_tuple_digest": digest, "current_tuple_digest": digest}
            ),
        )

    def assert_pending(self, row):
        with self.factory() as db:
            current = decisions.get_request(db, row["id"])
            self.assertEqual((current.status, current.version), ("pending", 1))
            self.assertEqual(runs.get_run(db, self.run.id).state, "waiting_approval")

    def test_total_run_timeout_denies_new_request_without_charging(self):
        with self.factory.begin() as db:
            run = runs.get_run(db, self.run.id)
            run.deadline_at = self.now
            retained = run.retained_bytes
        with self.credentials(), self.assertRaises(LifecycleError) as failure:
            self.service.request_decision(self.run.id, "decision")
        self.assertEqual(failure.exception.status_code, 409)
        with self.factory() as db:
            self.assertFalse(decisions.list_requests(db, 100))
            self.assertEqual(runs.get_run(db, self.run.id).retained_bytes, retained)

    def test_total_run_timeout_expires_pending_decision(self):
        row = self.pending()
        with self.factory.begin() as db:
            runs.get_run(db, self.run.id).deadline_at = self.now + timedelta(seconds=1)
        self.now += timedelta(seconds=1)
        with self.credentials("reviewer"), self.assertRaises(LifecycleError):
            self.service.decide(row["id"], self.request(row))
        with self.factory() as db:
            current = decisions.get_request(db, row["id"])
            self.assertEqual(current.status, "expired")
            self.assertEqual(
                _view(current)["eligibility"]["reasons"], ["run_timed_out"]
            )
            self.assertEqual(runs.get_run(db, self.run.id).state, "timed_out")

    def test_total_run_timeout_denies_dispatch_and_consumption(self):
        row = self.approve()
        with self.factory.begin() as db:
            runs.get_run(db, self.run.id).deadline_at = self.now
        for phase in ("dispatch", "consume"):
            with self.subTest(phase=phase):
                self.assertIn("run_timed_out", self.recheck(row, phase).reasons)

    def test_clock_rollback_preserves_pending_request(self):
        row = self.pending()
        self.now += timedelta(seconds=2)
        with self.factory.begin() as db:
            runs.get_run(db, self.run.id).last_observed_at = self.now
        self.service.clock = lambda: self.now - timedelta(seconds=1)
        with self.credentials("reviewer"), self.assertRaises(LifecycleError) as failure:
            self.service.decide(row["id"], self.request(row))
        self.assertEqual(failure.exception.status_code, 503)
        self.assert_pending(row)

    def test_clock_rollback_denies_new_request_without_charging(self):
        with self.factory.begin() as db:
            run = runs.get_run(db, self.run.id)
            retained = run.retained_bytes
            run.last_observed_at = self.now + timedelta(seconds=1)
        with self.credentials(), self.assertRaises(LifecycleError) as failure:
            self.service.request_decision(self.run.id, "decision")
        self.assertEqual(failure.exception.status_code, 503)
        with self.factory() as db:
            self.assertFalse(decisions.list_requests(db, 100))
            self.assertEqual(runs.get_run(db, self.run.id).retained_bytes, retained)

    def test_run_clock_floor_denies_dispatch_and_consumption(self):
        row = self.approve()
        self.now += timedelta(seconds=2)
        with self.factory.begin() as db:
            runs.get_run(db, self.run.id).last_observed_at = self.now
        self.service.clock = lambda: self.now - timedelta(seconds=1)
        for phase in ("dispatch", "consume"):
            with self.subTest(phase=phase):
                self.assertIn("invalid_clock", self.recheck(row, phase).reasons)

    def test_receipt_clock_floor_denies_dispatch_and_consumption(self):
        self.now += timedelta(seconds=2)
        row = self.approve()
        with self.factory.begin() as db:
            runs.get_run(db, self.run.id).last_observed_at = self.now - timedelta(
                seconds=2
            )
        self.service.clock = lambda: self.now - timedelta(seconds=1)
        for phase in ("dispatch", "consume"):
            with self.subTest(phase=phase):
                self.assertIn("invalid_clock", self.recheck(row, phase).reasons)

    def test_expiry_reasons_identify_each_deadline(self):
        for kind, expected in (
            ("evidence", {"stale_evidence"}),
            ("source", {"stale_evidence", "source_expired"}),
            ("custody", {"custody_expired"}),
            ("approval", {"approval_expired"}),
        ):
            with self.subTest(kind=kind):
                case = DecisionReviewRegressions()
                try:
                    case.setUp()
                    case.short_deadline(kind)
                    row = case.pending()
                    case.now += timedelta(seconds=1)
                    with (
                        case.credentials("reviewer"),
                        case.assertRaises(LifecycleError),
                    ):
                        case.service.decide(row["id"], case.request(row))
                    with case.factory() as db:
                        current = decisions.get_request(db, row["id"])
                        projection = _view(current)["eligibility"]
                        self.assertEqual(set(projection["reasons"]), expected)
                        self.assertEqual(current.status, "expired")
                        if kind in {"evidence", "source", "custody"}:
                            self.assertTrue(
                                all(
                                    "Recollect" in todo
                                    for todo in projection["context_todos"]
                                )
                            )
                finally:
                    case.doCleanups()

    def advancing_material(self):
        def resolve(*args):
            self.now += timedelta(seconds=1)
            return self.material

        self.service.material_port = resolve

    def test_slow_material_cannot_create_a_pending_expired_request(self):
        self.short_deadline("evidence")
        self.advancing_material()
        with self.credentials(), self.assertRaises(LifecycleError):
            self.service.request_decision(self.run.id, "decision")
        with self.factory() as db:
            row = decisions.list_requests(db, 100)[0]
            self.assertEqual(row.status, "expired")
            self.assertEqual(_view(row)["eligibility"]["reasons"], ["stale_evidence"])

    def test_slow_material_cannot_approve_after_expiry(self):
        self.short_deadline("approval")
        row = self.pending()
        self.advancing_material()
        with self.credentials("reviewer"), self.assertRaises(LifecycleError):
            self.service.decide(row["id"], self.request(row))
        with self.factory() as db:
            current = decisions.get_request(db, row["id"])
            self.assertEqual(current.status, "expired")
            self.assertEqual(
                _view(current)["eligibility"]["reasons"], ["approval_expired"]
            )

    def test_slow_material_cannot_create_request_after_total_run_timeout(self):
        with self.factory.begin() as db:
            runs.get_run(db, self.run.id).deadline_at = self.now + timedelta(seconds=1)
        self.advancing_material()
        with self.credentials(), self.assertRaises(LifecycleError) as failure:
            self.service.request_decision(self.run.id, "decision")
        self.assertEqual(failure.exception.status_code, 409)
        with self.factory() as db:
            self.assertFalse(decisions.list_requests(db, 100))

    def test_receipt_rechecks_refresh_clock_after_material_resolution(self):
        self.short_deadline("approval")
        row = self.approve()
        self.advancing_material()
        for phase in ("dispatch", "consume"):
            with (
                self.subTest(phase=phase),
                self.credentials(),
                authorization.authorized_session() as db,
            ):
                result = self.service._receipt_evidence(db, row["id"], phase=phase)
                self.assertIn("approval_expired", result.reasons)

    def test_transient_material_failure_preserves_pending_authority(self):
        row = self.pending()
        with patch.object(self.service, "_material", side_effect=LifecycleError(503)):
            with (
                self.credentials("reviewer"),
                self.assertRaises(LifecycleError) as failure,
            ):
                self.service.decide(row["id"], self.request(row))
        self.assertEqual(failure.exception.status_code, 503)
        self.assert_pending(row)
        with self.credentials("reviewer"):
            self.assertEqual(
                self.service.decide(row["id"], self.request(row))["status"], "approved"
            )

    def test_transient_recheck_failure_is_retryable_and_never_authorizes(self):
        row = self.approve()
        for phase in ("dispatch", "consume"):
            with (
                self.subTest(phase=phase),
                patch.object(
                    self.service, "_material", side_effect=LifecycleError(503)
                ),
            ):
                with self.assertRaises(LifecycleError) as failure:
                    self.recheck(row, phase)
                self.assertEqual(failure.exception.status_code, 503)

    def test_transient_receipt_failure_rolls_back_human_approval(self):
        row = self.pending()
        resolve = self.service._material
        calls = 0

        def unavailable_during_readiness(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise LifecycleError(503)
            return resolve(*args, **kwargs)

        with patch.object(
            self.service, "_material", side_effect=unavailable_during_readiness
        ):
            with (
                self.credentials("reviewer"),
                self.assertRaises(LifecycleError) as failure,
            ):
                self.service.decide(row["id"], self.request(row))
        self.assertEqual(failure.exception.status_code, 503)
        self.assert_pending(row)


class SerialDecisionReviewRegressions(LifecycleCase):
    serial_decisions = True
    enable = fixture.DecisionServiceTests.enable
    publish_fixture = fixture.DecisionServiceTests.publish_fixture
    setUp = fixture.DecisionServiceTests.setUp
    request = fixture.DecisionServiceTests.request

    def test_premature_later_human_request_preserves_viable_run_and_quota(self):
        with self.credentials():
            first = self.service.request_decision(self.run.id, "decision-a")
        with self.factory() as db:
            retained = runs.get_run(db, self.run.id).retained_bytes
        with self.credentials(), self.assertRaises(LifecycleError) as failure:
            self.service.request_decision(self.run.id, "decision")
        self.assertEqual(failure.exception.status_code, 409)
        with self.factory() as db:
            self.assertEqual(len(decisions.list_requests(db, 100)), 1)
            run = runs.get_run(db, self.run.id)
            self.assertEqual(run.state, "waiting_approval")
            self.assertEqual(run.retained_bytes, retained)
        with self.credentials("reviewer"):
            self.service.decide(first["id"], self.request(first))
        with self.credentials():
            second = self.service.request_decision(self.run.id, "decision")
        with self.credentials("reviewer"):
            self.assertEqual(
                self.service.decide(second["id"], self.request(second))["status"],
                "approved",
            )
        with self.factory() as db:
            self.assertEqual(runs.get_run(db, self.run.id).state, "ready_handoff")

    def test_pending_human_does_not_mask_failed_mandatory_evidence(self):
        with self.credentials():
            self.service.request_decision(self.run.id, "decision-a")
        self.material = replace(
            self.material,
            evidence=self.material.evidence.model_copy(update={"complete": False}),
        )
        with self.credentials(), self.assertRaises(LifecycleError):
            self.service.request_decision(self.run.id, "decision")
        with self.factory() as db:
            self.assertEqual(runs.get_run(db, self.run.id).state, "stopped_by_gate")
            latest = {
                row.step_id: row
                for row in decisions.list_latest_for_run(db, self.run.id)
            }
            self.assertIn(
                "incomplete_evidence",
                _view(latest["decision"])["eligibility"]["reasons"],
            )
