"""Human cancellation remains durable when local signaling fails."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from infra_automation.lifecycle import LifecycleError
from infra_automation.state import CancelRunRequest
from models.repositories import infra_automation_runs as repository
from services import project_service as authorization
from services import infra_automation_engine_service as service
from tests.test_infra_automation import test_engine_service as admission
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class CancelServiceTests(LifecycleCase):
    def setUp(self):
        LifecycleCase.setUp(self)
        self.enable()
        self.ids = self.publish_fixture()
        self.request = admission.RunRequest(
            workflow_id=self.ids[0],
            revision_id=self.ids[1],
            workspace_id=100,
            inputs={"note": "original"},
            idempotency_key="synthetic-request",
            reason="Start synthetic advisory work.",
        )
        self.registry = admission.AvailableHandlers()

    publish_fixture = admission.EngineServiceTests.publish_fixture
    enable = admission.EngineServiceTests.enable
    admit = admission.EngineServiceTests.admit
    counts = admission.EngineServiceTests.counts

    def cancel(self, run, **kwargs):
        with self.credentials():
            return service.cancel_run(
                run["id"],
                CancelRunRequest(
                    expected_version=run["version"], reason="Stop synthetic work."
                ),
                **kwargs,
            )

    def test_commit_precedes_signal_and_identical_retry_is_audit_free(self):
        run = self.admit()
        signals = []

        def signal(run_id):
            self.assertFalse(authorization.has_authorized_session())
            with self.factory() as session:
                row = repository.get_run(session, run_id)
                self.assertTrue(row.cancel_requested)
                self.assertEqual(row.state, "cancelled")
            signals.append(run_id)

        result = self.cancel(run, cancel_port=signal)
        count = self.counts()
        self.assertEqual(self.cancel(run, cancel_port=signal), result)
        self.assertEqual(self.counts(), count)
        self.assertEqual(signals, [run["id"], run["id"]])
        with self.credentials(), self.assertRaises(LifecycleError) as error:
            service.cancel_run(
                run["id"],
                CancelRunRequest(
                    expected_version=run["version"], reason="Different explanation."
                ),
            )
        self.assertEqual(error.exception.status_code, 409)
        for version in (result["version"], 999):
            with self.credentials(), self.assertRaises(LifecycleError) as changed:
                service.cancel_run(
                    run["id"],
                    CancelRunRequest(
                        expected_version=version, reason="Different explanation."
                    ),
                    cancel_port=signal,
                )
            self.assertEqual(changed.exception.status_code, 409)
        self.assertEqual(signals, [run["id"], run["id"]])
        self.assertEqual(self.counts(), count)

    def test_signal_failure_returns_unavailable_but_flag_survives(self):
        run = self.admit()

        def fail(_):
            raise RuntimeError("synthetic signal failure")

        with self.assertRaises(LifecycleError) as error:
            self.cancel(run, cancel_port=fail)
        self.assertEqual(error.exception.status_code, 503)
        self.assertTrue(self.cancel(run)["cancel_requested"])

    def test_outer_rollback_never_signals_and_overflow_rolls_back(self):
        run = self.admit()
        signals = []
        with self.credentials(), self.assertRaises(RuntimeError):
            with authorization.authorized_session():
                service.cancel_run(
                    run["id"],
                    CancelRunRequest(
                        expected_version=run["version"], reason="Stop synthetic work."
                    ),
                    cancel_port=signals.append,
                )
                self.assertEqual(signals, [])
                raise RuntimeError("synthetic rollback")
        self.assertEqual(signals, [])
        with self.credentials(mutation=False):
            self.assertFalse(service.get_run(run["id"])["cancel_requested"])
        with patch("api.schemas.build_meta", return_value={"app_name": "x" * 140000}):
            with self.assertRaises(LifecycleError):
                self.cancel(run, cancel_port=signals.append)
        self.assertEqual(signals, [])
        with self.credentials(mutation=False):
            self.assertFalse(service.get_run(run["id"])["cancel_requested"])

    def test_only_scoped_owner_or_admin_and_admin_uses_original_owner_binding(self):
        self.member("contributor")
        run = self.admit()
        self.principal("human-b", is_admin=True)
        self.member("contributor", principal="human-b")
        request = CancelRunRequest(
            expected_version=run["version"], reason="Stop synthetic work."
        )
        with (
            self.credentials("human-b"),
            self.assertRaises(authorization.TrustedAuthorizationError),
        ):
            service.cancel_run(run["id"], request)
        self.member("admin", principal="human-b")
        with self.credentials("human-b"):
            result = service.cancel_run(run["id"], request)
            self.assertEqual(result["state"], "cancelled")
            self.assertEqual(service.cancel_run(run["id"], request), result)

    def test_expired_deadline_does_not_claim_successful_cancellation(self):
        run = self.admit()
        now = datetime.strptime(run["deadline_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        ) + timedelta(seconds=1)
        result = self.cancel(run, now=now)
        self.assertIn(result["state"], ("timed_out", "expired"))
        self.assertTrue(result["cancel_requested"])
