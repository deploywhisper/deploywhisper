"""Real worker failures retain the trusted retry and authority boundaries."""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from sqlalchemy.exc import OperationalError

from infra_automation import claims
from infra_automation.coordinator import Coordinator
from infra_automation.lifecycle import LifecycleError
from infra_automation.local_workers import (
    HandlerRegistration,
    WorkerCompletion,
    WorkerInput,
    _worker_main,
)
from infra_automation.state import OutputReference, WorkerResult
from infra_automation.worker_failures import (
    InfrastructureOperationError,
    failure_outcome,
)
from models.repositories import infra_automation_runs as repo
from tests.test_infra_automation import test_engine_claims as claim_tests


def storage_error(code):
    error = sqlite3.OperationalError("sensitive storage detail")
    error.sqlite_errorcode = code
    return OperationalError("private statement", {}, error)


class WorkerFailureTests(TestCase):
    acquire = claim_tests.EngineClaimsTests.acquire

    def operation(self, function, *args, **kwargs):
        kwargs.setdefault("now", datetime.now(timezone.utc))
        return claim_tests.EngineClaimsTests.operation(self, function, *args, **kwargs)

    def setUp(self):
        fixture = claim_tests.EngineClaimsTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        for name in ("engine", "factory", "now", "snapshot", "run", "pending"):
            setattr(self, name, getattr(fixture, name))

    def claim(self):
        owner = self.acquire()
        self.operation(claims.start_run, owner, run_id=self.run.id, expected_version=1)
        handle = self.operation(
            claims.claim_attempt, owner, attempt_id=self.pending.id, expected_version=1
        )
        return owner, handle

    def registration(self, handler=None):
        output = OutputReference(
            kind="screened_artifacts", reference="safe", digest="sha256:" + "a" * 64
        )
        return HandlerRegistration(
            "synthetic",
            "1",
            "uploaded_intake",
            "screened_artifacts",
            True,
            handler
            or Mock(return_value=WorkerResult(outcome="local_success", output=output)),
        )

    def invoke(self, handle, registration):
        messages = []
        channel = SimpleNamespace(send_bytes=messages.append, close=lambda: None)
        with patch("infra_automation.local_workers.os.setsid"):
            _worker_main(
                str(self.engine.url),
                handle,
                registration,
                WorkerInput(self.snapshot.canonical_bytes, "upload", ()),
                None,
                channel,
            )
        self.assertEqual(messages[0], b"ready")
        return WorkerResult.model_validate_json(messages[-1])

    def test_upload_capacity_failure_retries_then_completes_real_success(self):
        owner, handle = self.claim()
        registration = self.registration()
        workers = SimpleNamespace(handles=(), max_workers=2, can_submit=True)
        coordinator = Coordinator(
            self.factory, workers, registry=SimpleNamespace(get=lambda _: registration)
        )
        coordinator._owner = owner
        with patch.object(
            claims, "register_upload", side_effect=LifecycleError(429)
        ) as upload:
            result = self.invoke(handle, registration)
        self.assertEqual(upload.call_count, 1)
        self.assertEqual(result.outcome, "retryable_local_failure")
        coordinator._complete(
            WorkerCompletion(handle, result), datetime.now(timezone.utc)
        )
        with self.factory() as db:
            previous = repo.get_attempt(db, handle.attempt_id)
            self.assertEqual(previous.state, "failed")
            self.assertEqual(repo.get_run(db, self.run.id).state, "running")
        successor = self.operation(
            claims.prepare_retry,
            owner,
            previous_attempt_id=previous.id,
            expected_version=previous.version,
        )
        retry = self.operation(
            claims.claim_attempt,
            owner,
            attempt_id=successor.id,
            expected_version=successor.version,
        )
        result = self.invoke(retry, registration)
        self.assertEqual(result.outcome, "local_success")
        coordinator._complete(
            WorkerCompletion(retry, result), datetime.now(timezone.utc)
        )
        with self.factory() as db:
            row = repo.get_attempt(db, retry.attempt_id)
            self.assertEqual(row.state, "succeeded")
            self.assertIsNotNone(row.output_json)
        self.assertEqual(registration.handler.call_count, 2)

    def test_busy_durable_write_is_retryable(self):
        _, handle = self.claim()
        with patch.object(
            claims, "commit_output", side_effect=storage_error(sqlite3.SQLITE_BUSY)
        ):
            self.assertEqual(
                self.invoke(handle, self.registration()).outcome,
                "retryable_local_failure",
            )

    def assert_initial_read_outcome(self, error, outcome):
        _, handle = self.claim()
        registration = self.registration()
        with patch.object(repo, "get_run", side_effect=error) as read:
            result = self.invoke(handle, registration)
        read.assert_called_once()
        registration.handler.assert_not_called()
        self.assertEqual(result.outcome, outcome)

    def test_initial_read_busy_is_retryable_before_handler(self):
        self.assert_initial_read_outcome(
            storage_error(sqlite3.SQLITE_BUSY), "retryable_local_failure"
        )

    def test_initial_read_locked_is_retryable_before_handler(self):
        self.assert_initial_read_outcome(
            storage_error(sqlite3.SQLITE_LOCKED), "retryable_local_failure"
        )

    def test_initial_read_authority_failure_remains_permanent(self):
        self.assert_initial_read_outcome(LifecycleError(503), "permanent_local_failure")

    def test_initial_binding_validation_remains_permanent(self):
        _, handle = self.claim()
        registration = self.registration()
        with patch.object(repo, "get_run", return_value=None) as read:
            result = self.invoke(handle, registration)
        read.assert_called_once()
        registration.handler.assert_not_called()
        self.assertEqual(result.outcome, "permanent_local_failure")

    def assert_setup_outcome(self, error, outcome):
        _, handle = self.claim()
        registration = self.registration()
        with patch(
            "infra_automation.local_workers.configure_engine_sqlite", side_effect=error
        ) as configure:
            result = self.invoke(handle, registration)
        configure.assert_called_once()
        registration.handler.assert_not_called()
        self.assertEqual(result.outcome, outcome)

    def test_sqlite_setup_busy_is_retryable_before_handler(self):
        self.assert_setup_outcome(
            storage_error(sqlite3.SQLITE_BUSY), "retryable_local_failure"
        )

    def test_real_sqlite_configuration_preserves_busy_for_worker_classification(self):
        _, handle = self.claim()
        registration = self.registration()
        with patch(
            "sqlalchemy.engine.Engine.connect",
            side_effect=storage_error(sqlite3.SQLITE_BUSY),
        ) as connect:
            result = self.invoke(handle, registration)
        connect.assert_called_once()
        registration.handler.assert_not_called()
        self.assertEqual(result.outcome, "retryable_local_failure")

    def test_sqlite_setup_authority_failure_remains_permanent(self):
        self.assert_setup_outcome(LifecycleError(503), "permanent_local_failure")

    def test_sqlite_setup_validation_failure_remains_permanent(self):
        self.assert_setup_outcome(ValueError("private path"), "permanent_local_failure")

    def test_repeated_capacity_pressure_stops_after_three_attempts(self):
        owner, handle = self.claim()
        registration = self.registration()
        coordinator = Coordinator(
            self.factory, SimpleNamespace(handles=(), max_workers=2, can_submit=True)
        )
        coordinator._owner = owner
        for number in range(1, 4):
            with patch.object(
                claims, "register_upload", side_effect=LifecycleError(429)
            ):
                result = self.invoke(handle, registration)
            self.assertEqual(result.outcome, "retryable_local_failure")
            coordinator._complete(
                WorkerCompletion(handle, result), datetime.now(timezone.utc)
            )
            with self.factory() as db:
                previous = repo.get_attempt(db, handle.attempt_id)
                self.assertEqual(previous.attempt_number, number)
                self.assertEqual(previous.state, "failed")
                self.assertEqual(
                    repo.get_run(db, self.run.id).state,
                    "failed" if number == 3 else "running",
                )
            if number < 3:
                successor = self.operation(
                    claims.prepare_retry,
                    owner,
                    previous_attempt_id=previous.id,
                    expected_version=previous.version,
                )
                handle = self.operation(
                    claims.claim_attempt,
                    owner,
                    attempt_id=successor.id,
                    expected_version=successor.version,
                )
        self.assertEqual(registration.handler.call_count, 3)

    def test_committed_output_is_adopted_after_lost_worker_completion(self):
        owner, handle = self.claim()
        registration = self.registration()
        self.assertEqual(self.invoke(handle, registration).outcome, "local_success")
        coordinator = Coordinator(
            self.factory,
            SimpleNamespace(handles=(), max_workers=2, can_submit=True),
        )
        coordinator._owner = owner
        # A lost result after a durable commit must not repeat the handler.
        coordinator._complete(
            WorkerCompletion(
                handle, WorkerResult(outcome="permanent_local_failure"), crashed=True
            ),
            datetime.now(timezone.utc),
        )
        with self.factory() as db:
            previous = repo.get_attempt(db, handle.attempt_id)
            self.assertEqual(previous.state, "failed")
            self.assertIsNotNone(previous.output_json)
        successor = self.operation(
            claims.prepare_retry,
            owner,
            previous_attempt_id=previous.id,
            expected_version=previous.version,
        )
        retry = self.operation(
            claims.claim_attempt,
            owner,
            attempt_id=successor.id,
            expected_version=successor.version,
        )
        self.assertEqual(self.invoke(retry, registration).outcome, "local_success")
        registration.handler.assert_called_once()

    def assert_handler_error_is_permanent(self, error):
        _, handle = self.claim()
        handler = Mock(side_effect=error)
        result = self.invoke(handle, self.registration(handler))
        handler.assert_called_once()
        self.assertEqual(result.outcome, "permanent_local_failure")

    def test_handler_capacity_error_is_permanent(self):
        self.assert_handler_error_is_permanent(LifecycleError(429))

    def test_handler_storage_error_is_permanent(self):
        self.assert_handler_error_is_permanent(storage_error(sqlite3.SQLITE_BUSY))

    def test_authority_revocation_is_never_reclassified_as_retryable(self):
        _, handle = self.claim()
        with patch.object(claims, "register_upload", side_effect=LifecycleError(403)):
            self.assertEqual(
                self.invoke(handle, self.registration()).outcome,
                "permanent_local_failure",
            )


class WorkerFailureClassificationTests(TestCase):
    def test_only_known_transient_durable_failures_retry_with_safe_registration(self):
        for error in (
            LifecycleError(429),
            storage_error(sqlite3.SQLITE_BUSY),
            storage_error(sqlite3.SQLITE_BUSY | 2 << 8),
            storage_error(sqlite3.SQLITE_LOCKED),
            storage_error(sqlite3.SQLITE_FULL),
        ):
            for retry_safe in (False, True):
                with self.subTest(error=type(error).__name__, retry_safe=retry_safe):
                    self.assertEqual(
                        failure_outcome(
                            InfrastructureOperationError(error),
                            external_started=False,
                            retry_safe=retry_safe,
                        ),
                        "retryable_local_failure"
                        if retry_safe
                        else "permanent_local_failure",
                    )

    def test_external_intent_always_preserves_uncertainty(self):
        for error in (
            ValueError("sensitive"),
            InfrastructureOperationError(LifecycleError(429)),
        ):
            self.assertEqual(
                failure_outcome(error, external_started=True, retry_safe=False),
                "external_unknown",
            )

    def test_unclassified_storage_validation_and_authority_fail_closed(self):
        for error in (
            LifecycleError(403),
            LifecycleError(409),
            LifecycleError(422),
            LifecycleError(503),
            storage_error(sqlite3.SQLITE_IOERR),
            storage_error(sqlite3.SQLITE_CORRUPT),
            sqlite3.OperationalError("database is locked"),
            ValueError("sensitive"),
        ):
            with self.subTest(error=type(error).__name__):
                self.assertEqual(
                    failure_outcome(
                        InfrastructureOperationError(error),
                        external_started=False,
                        retry_safe=True,
                    ),
                    "permanent_local_failure",
                )
