"""Bounded local scheduling and immutable trusted handler contracts."""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import Mock
import asyncio
import time

from sqlalchemy import select

from infra_automation.coordinator import Coordinator
from infra_automation.lifecycle import LifecycleError
from infra_automation.local_workers import (
    HandlerRegistration,
    HandlerRegistry,
    SpawnProcessWorkers,
)
from infra_automation.state import OutputReference, WorkerResult
from models.repositories import infra_automation_runs as repository
from models.tables import InfraAutomationAttempt
from services import project_service as authorization
from services import infra_automation_engine_support as engine_support
from services import infra_automation_support as support
from tests.test_infra_automation import test_engine_repository as repository_tests


def synthetic_handler(value):
    raise RuntimeError("Synthetic failure")


def slow_success(value):
    time.sleep(1)
    return WorkerResult(
        outcome="local_success",
        output=OutputReference(
            kind="screened_artifacts",
            reference="synthetic-output",
            digest=support.digest(value.snapshot_bytes),
        ),
    )


def dead_handler(value):
    # Model a worker that disappears without reporting any result.
    import os

    os._exit(7)


class EngineCoordinatorContractTests(TestCase):
    def test_empty_registry_never_opens_database_or_workers(self):
        factory, workers = Mock(), Mock()
        coordinator = Coordinator(factory, workers)
        coordinator.tick()
        coordinator.close()
        factory.assert_not_called()
        workers.submit.assert_not_called()

    def test_registry_is_closed_unique_and_contract_bound(self):
        registration = HandlerRegistration(
            "synthetic",
            "1",
            "uploaded_intake",
            "screened_artifacts",
            True,
            synthetic_handler,
        )
        registry = HandlerRegistry((registration,))
        self.assertIs(registry.get("uploaded_intake"), registration)
        self.assertIsNone(registry.get("shared_analysis"))
        with self.assertRaises(ValueError):
            HandlerRegistry((registration, registration))
        with self.assertRaises(ValueError):
            HandlerRegistration(
                "synthetic", "1", "uploaded_intake", "report", True, synthetic_handler
            )


class EngineCoordinatorRuntimeTests(repository_tests.EngineRepositoryTests):
    def setUp(self):
        super().setUp()
        with (
            self.credentials(),
            authorization.authorized_session(self.factory) as session,
        ):
            engine_support.ensure_engine_actor(
                session,
                support.scope(session, 100, 100, "automation.request", mutation=True),
            )
        self.workers = SpawnProcessWorkers(str(self.engine.url))
        self.addCleanup(self.workers.close)

    def scheduler(self, handler=slow_success):
        registry = HandlerRegistry(
            (
                HandlerRegistration(
                    "synthetic",
                    "1",
                    "uploaded_intake",
                    "screened_artifacts",
                    True,
                    handler,
                ),
            )
        )
        coordinator = Coordinator(self.factory, self.workers, registry=registry)
        self.addCleanup(coordinator.close)
        return coordinator

    def two_runs(self):
        first = self.admit()
        with self.factory.begin() as session:
            second = repository.create_run(
                session, **{**self.request, "key_digest": support.digest(b"other-key")}
            )
        return first, second

    def await_attempts(self, coordinator, terminal_count):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            coordinator.tick()
            with self.factory() as session:
                rows = list(session.scalars(select(InfraAutomationAttempt)))
                if (
                    sum(row.state in ("succeeded", "failed") for row in rows)
                    >= terminal_count
                ):
                    return rows
            time.sleep(0.03)
        self.fail("Spawned workers did not finish within the bounded test deadline")

    def test_blocking_handler_does_not_block_tick_or_second_claim(self):
        self.two_runs()
        coordinator = self.scheduler()
        started = time.monotonic()
        coordinator.tick()
        self.assertLess(time.monotonic() - started, 0.8)
        self.assertEqual(len(self.workers.handles), 2)
        self.assertFalse(self.workers.can_submit)
        with self.factory() as session:
            self.assertEqual(
                len(list(session.scalars(select(InfraAutomationAttempt)))), 2
            )
        rows = self.await_attempts(coordinator, 2)
        self.assertTrue(all(row.state == "succeeded" for row in rows))
        self.assertTrue(
            all(
                row.output_json is not None and row.uploads_json != "[]" for row in rows
            )
        )
        self.assertEqual(len({row.owner_hash for row in rows}), 2)

    def test_dead_worker_does_not_complete_another_attempt(self):
        self.two_runs()
        coordinator = self.scheduler(dead_handler)
        coordinator.tick()
        handles = self.workers.handles
        self.assertEqual(len(handles), 2)
        rows = self.await_attempts(coordinator, 2)
        originals = [
            row for row in rows if row.id in {handle.attempt_id for handle in handles}
        ]
        self.assertTrue(
            all(row.state == "failed" and row.output_json is None for row in originals)
        )
        self.assertFalse(any(row.state == "succeeded" for row in rows))
        self.assertEqual(
            {row.id for row in originals}, {handle.attempt_id for handle in handles}
        )

    def test_worker_saturation_keeps_active_run_waiting_without_attempt(self):
        self.two_runs()
        with self.factory.begin() as session:
            third = repository.create_run(
                session, **{**self.request, "key_digest": support.digest(b"third-key")}
            )
        coordinator = self.scheduler()
        coordinator.tick()
        with self.factory() as session:
            self.assertEqual(repository.get_run(session, third.id).state, "running")
            self.assertEqual(repository.list_attempts(session, run_id=third.id), [])
        self.assertEqual(len(self.workers.handles), 2)

    def test_lifespan_loop_keeps_asyncio_responsive(self):
        self.admit()
        coordinator = self.scheduler()

        async def exercise():
            await coordinator.start()
            pulses = 0
            for _ in range(10):
                await asyncio.sleep(0.02)
                pulses += 1
            await coordinator.stop()
            return pulses

        self.assertEqual(asyncio.run(exercise()), 10)
        self.assertEqual(self.workers.handles, ())

    def test_restart_respects_healthy_owner_and_shutdown_invalidates_handles(self):
        self.admit()
        coordinator = self.scheduler()
        coordinator.tick()
        original = self.workers.handles[0]
        competitor_workers = SpawnProcessWorkers(str(self.engine.url))
        self.addCleanup(competitor_workers.close)
        competitor = Coordinator(
            self.factory, competitor_workers, registry=coordinator.registry
        )
        competitor.tick()
        self.assertIsNone(competitor._owner)
        coordinator.close()
        self.assertEqual(self.workers.handles, ())
        from infra_automation import claims

        with (
            authorization.authorized_session(self.factory) as session,
            self.assertRaises(LifecycleError),
        ):
            row = repository.get_attempt(session, original.attempt_id)
            claims.heartbeat_attempt(session, original, expected_version=row.version)
