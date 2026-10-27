"""Committed private ownership bounds every local worker liveness pulse."""

from __future__ import annotations

from datetime import timedelta
from importlib import import_module
from unittest.mock import patch

from sqlalchemy.orm import Session

from infra_automation import claims
from infra_automation.coordinator import Coordinator
from infra_automation.local_workers import HandlerRegistration, HandlerRegistry
from infra_automation.state import AuditActor
from models.repositories import infra_automation_runs as repository
from models.tables import InfraAutomationCoordinatorLease
from services import infra_automation_engine_support as engine_support
from services import infra_automation_support as support
from services import project_service as authorization
from tests.test_infra_automation import test_engine_coordinator as coordinator_tests
from tests.test_infra_automation import test_workflow_snapshots as snapshot_tests
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class PulseWorkers:
    """Record liveness expiry without spawning or executing any handler."""

    handles = ()
    can_submit = False
    max_workers = 2

    def __init__(self):
        self.pulses = []

    def heartbeat(self, expires_at):
        self.pulses.append(expires_at)

    def poll(self):
        return ()

    def close(self):
        pass


class EngineOwnerLivenessTests(LifecycleCase):
    publish_fixture = snapshot_tests.WorkflowSnapshotTests.publish_fixture
    enable = snapshot_tests.WorkflowSnapshotTests.enable
    export = snapshot_tests.WorkflowSnapshotTests.export

    def setUp(self):
        super().setUp()
        with self.engine.begin() as connection:
            for name, body in import_module(
                "migrations.versions.032_add_infra_automation_engine"
            ).GUARDS.items():
                connection.exec_driver_sql(f"CREATE TRIGGER {name} {body}")
        self.enable()
        snapshot = self.export(self.publish_fixture())
        with self.factory.begin() as session:
            repository.create_run(
                session,
                snapshot=snapshot,
                request_digest=support.digest(b"request"),
                key_digest=support.digest(b"key"),
                requested_by="human-a",
                deadline_at=self.now + timedelta(minutes=10),
                audit_actor=AuditActor("human-a", "human", "admin"),
                reason="Synthetic owner liveness regression.",
                now=self.now,
            )
        with (
            self.credentials(),
            authorization.authorized_session(self.factory) as session,
        ):
            engine_support.ensure_engine_actor(
                session,
                support.scope(session, 100, 100, "automation.request", mutation=True),
            )
        self.workers = PulseWorkers()
        registry = HandlerRegistry(
            (
                HandlerRegistration(
                    "synthetic",
                    "1",
                    "uploaded_intake",
                    "screened_artifacts",
                    True,
                    coordinator_tests.slow_success,
                ),
            )
        )
        self.coordinator = Coordinator(
            self.factory, self.workers, registry=registry, clock=lambda: self.now
        )
        self.addCleanup(self.coordinator.close)

    def tick(self, monotonic=1000.0):
        with patch(
            "infra_automation.coordinator.time.monotonic", return_value=monotonic
        ):
            self.coordinator.tick()

    def test_generation_takeover_rejects_pulse_before_ten_second_renewal(self):
        self.tick()
        self.assertEqual(self.workers.pulses, [1003.0])
        previous = self.coordinator._owner
        with authorization.authorized_session(self.factory) as session:
            claims.release_coordinator(
                session, previous, project_id=100, workspace_id=100, now=self.now
            )
            successor = claims.acquire_coordinator(
                session, project_id=100, workspace_id=100, now=self.now
            )
        self.assertGreater(successor.generation, previous.generation)
        self.now += timedelta(seconds=1)
        with patch.object(
            claims, "renew_coordinator", wraps=claims.renew_coordinator
        ) as renew:
            self.tick(monotonic=1001.0)
        renew.assert_not_called()
        self.assertEqual(self.workers.pulses, [1003.0])
        self.assertIsNone(self.coordinator._owner)

    def test_pulse_expiry_cannot_exceed_remaining_persisted_lease(self):
        self.tick()
        with self.factory.begin() as session:
            lease = session.get(InfraAutomationCoordinatorLease, 1)
            lease.lease_until = self.now + timedelta(milliseconds=750)
            lease.version += 1
        self.tick(monotonic=1001.0)
        self.assertEqual(self.workers.pulses, [1003.0, 1001.75])
        self.assertLessEqual(self.workers.pulses[-1] - 1001.0, 0.75)

    def test_rolled_back_acquisition_never_sends_liveness_pulse(self):
        with patch.object(
            Session, "commit", side_effect=RuntimeError("Synthetic commit failure")
        ):
            with self.assertRaises(RuntimeError):
                self.tick()
        self.assertEqual(self.workers.pulses, [])
        self.assertIsNone(self.coordinator._owner)
        with self.factory() as session:
            self.assertIsNone(session.get(InfraAutomationCoordinatorLease, 1))
        self.tick()
        self.assertEqual(self.workers.pulses, [1003.0])

    def test_rolled_back_renewal_never_extends_liveness_pulse(self):
        self.tick()
        with self.factory() as session:
            original = session.get(InfraAutomationCoordinatorLease, 1)
            original_version = original.version
            original_deadline = repository.utc(original.lease_until)
        self.now += timedelta(seconds=10)
        with patch.object(
            Session, "commit", side_effect=RuntimeError("Synthetic commit failure")
        ):
            with self.assertRaises(RuntimeError):
                self.tick(monotonic=1010.0)
        self.assertEqual(self.workers.pulses, [1003.0])
        with self.factory() as session:
            lease = session.get(InfraAutomationCoordinatorLease, 1)
            self.assertEqual(lease.version, original_version)
            self.assertEqual(repository.utc(lease.lease_until), original_deadline)
