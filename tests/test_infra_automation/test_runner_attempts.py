"""Runner routing and payload admission regression tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from datetime import datetime, timezone

from infra_automation.lifecycle import LifecycleError
from infra_automation.runner.claims import RunnerRequirements, eligible, screened_upload
from services.infra_automation_support import canonical, digest

from datetime import timedelta
from infra_automation import claims as engine_claims
from infra_automation.contracts import ProfileContract, RegistryContract
from infra_automation.runner import claims
from infra_automation.runner.protocol import RunnerMessage
from models.repositories import infra_automation_runs as runs
from models.tables import InfraAutomationRunner
from services import project_service as auth
from tests.test_infra_automation import test_engine_claims as engine_tests
from tests.test_infra_automation import test_workflow_snapshots as snapshot_tests
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class RunnerRoutingTests(unittest.TestCase):
    def test_exact_routing_requires_all_admitted_dimensions(self):
        requirement = RunnerRequirements(
            tags=["isolated"],
            tool="opentofu",
            profile_digest="sha256:" + "a" * 64,
            runner_version="1.0",
        )
        runner = SimpleNamespace(
            status="active",
            tags_json='["isolated"]',
            tool="opentofu",
            profile_digest=requirement.profile_digest,
            runner_version="1.0",
            protocol_version=1,
            last_seen_at=datetime.now(timezone.utc),
        )
        self.assertTrue(eligible(runner, requirement))
        for field, value in (
            ("status", "revoked"),
            ("tags_json", "[]"),
            ("tool", "terraform"),
            ("runner_version", "2"),
            ("protocol_version", 2),
            ("profile_digest", "sha256:" + "b" * 64),
        ):
            changed = SimpleNamespace(**{**vars(runner), field: value})
            self.assertFalse(eligible(changed, requirement), field)

    def test_upload_requires_exact_digest_and_screened_complete_content(self):
        raw = canonical(
            [{"name": "main.tf", "content": 'resource "null_resource" "example" {}'}]
        )
        self.assertEqual(screened_upload(raw, digest(raw)), raw)
        for payload, checksum in (
            (raw, digest(b"other")),
            (raw[:-1], digest(raw[:-1])),
            (
                b'[{"name":"terraform.tfstate","content":"{}"}]',
                digest(b'[{"name":"terraform.tfstate","content":"{}"}]'),
            ),
        ):
            with self.assertRaises(LifecycleError):
                screened_upload(payload, checksum)


class RunnerAttemptTests(LifecycleCase):
    enable = engine_tests.EngineClaimsTests.enable
    admit = engine_tests.EngineClaimsTests.admit
    attempt = engine_tests.EngineClaimsTests.attempt
    operation = engine_tests.EngineClaimsTests.operation
    acquire = engine_tests.EngineClaimsTests.acquire
    profile = "sha256:" + "a" * 64

    def publish_fixture(self):
        return snapshot_tests.WorkflowSnapshotTests.publish_fixture(
            self,
            {
                "workflow_version": 2,
                "project_id": "100",
                "workspace_id": "100",
                "environment": "dev",
                "inputs": {"note": {"type": "string", "max_length": 100}},
                "steps": [
                    {
                        "id": "upload",
                        "kind": "admitted_collection",
                        "depends_on": [],
                        "source": {
                            "kind": "collected",
                            "repository_id": "synthetic-repo",
                            "commit_sha": "b" * 40,
                            "profile_digest": self.profile,
                        },
                    }
                ],
            },
        )

    def export(self, ids):
        return snapshot_tests.WorkflowSnapshotTests.export(
            self,
            ids,
            registry_contract=RegistryContract(
                profiles=(
                    ProfileContract(
                        digest=self.profile,
                        tool="opentofu",
                        authorization_kinds=("exact_plan",),
                    ),
                )
            ),
        )

    def setUp(self):
        # Invoke existing fixture initialization without inheriting its test cases.
        LifecycleCase.setUp(self)
        self.enable()
        self.snapshot = self.export(self.publish_fixture())
        from infra_automation.state import AuditActor
        from services import infra_automation_engine_support as engine_support

        self.actor = AuditActor("human-a", "human", "admin")
        self.request = dict(
            snapshot=self.snapshot,
            request_digest=digest(b"request"),
            key_digest=digest(b"key"),
            requested_by="human-a",
            deadline_at=self.now + timedelta(minutes=10),
            audit_actor=self.actor,
            reason="synthetic",
            now=self.now,
        )
        with self.credentials(), auth.authorized_session() as db:
            grant = engine_support.support.scope(
                db, 100, 100, "automation.request", mutation=True
            )
            engine_support.ensure_engine_actor(db, grant)
        self.run = self.admit()
        self.pending = self.attempt(self.run)
        self.owner = self.acquire()
        self.operation(
            engine_claims.start_run, self.owner, run_id=self.run.id, expected_version=1
        )
        self.requirements = RunnerRequirements(
            tags=["isolated"],
            tool="opentofu",
            profile_digest=self.profile,
            runner_version="1.0",
        )
        from services import infra_automation_runners as runners
        from infra_automation.runner.protocol import RunnerCredential

        with self.credentials():
            issued = runners.create_enrollment(
                runners.EnrollmentRequest(
                    project_id=100,
                    workspace_id=100,
                    tags=["isolated"],
                    tool="opentofu",
                    profile_digest=self.profile,
                    runner_version="1.0",
                    reason="Test runner.",
                ),
                now=self.now,
            )
        credential = runners.redeem(
            issued.enrollment.enrollment_id,
            issued.token.get_secret_value(),
            now=self.now,
        )
        self.credential = RunnerCredential(
            credential.runner_id, credential.token.get_secret_value()
        )
        with self.factory() as db:
            self.runner = db.get(InfraAutomationRunner, credential.runner_id)
        self.assignment = self.operation(
            claims.assign,
            self.owner,
            attempt_id=self.pending.id,
            runner=self.runner,
            requirements=self.requirements,
        )

    def message(self, operation, sequence, **kwargs):
        return RunnerMessage(
            operation=operation,
            scope=self.assignment["scope"],
            capabilities=["screened-collection-v1"],
            profile_digest=self.profile,
            sequence=sequence,
            **kwargs,
        )

    def act(self, message, **kwargs):
        result = self.operation(
            claims.operate,
            message,
            self.runner,
            self.assignment["task_token"],
            **kwargs,
        )
        self.assignment["scope"] = result["scope"]
        return result

    def test_scope_matrix_denies_every_operation_before_mutation(self):
        self.act(self.message("claim", 1))
        dimensions = {
            "runner_id": "other",
            "project_id": "200",
            "workspace_id": "101",
            "run_id": "other",
            "step_id": "other",
            "attempt": 2,
            "fence": 2,
            "coordinator_generation": 2,
            "authorization_epoch": 2,
            "restore_epoch": 2,
            "lease_deadline": "2000-01-01T00:00:00Z",
        }
        for operation, fields in (
            ("claim", {}),
            ("heartbeat", {}),
            ("log", {"log": "safe"}),
            ("upload", {"atomic_upload_id": "upload", "upload_digest": digest(b"[]")}),
            ("complete", {"atomic_upload_id": "upload", "state": "succeeded"}),
        ):
            for dimension, value in dimensions.items():
                with self.subTest(operation=operation, dimension=dimension):
                    payload = self.message(operation, 2, **fields).model_dump()
                    payload["scope"][dimension] = value
                    with self.assertRaises(LifecycleError):
                        self.act(RunnerMessage.model_validate(payload))
        with self.factory() as db:
            self.assertEqual(runs.get_attempt(db, self.pending.id).state, "running")

    def test_complete_requires_atomic_upload_and_rejects_replay(self):
        self.act(self.message("claim", 1))
        with self.assertRaises(LifecycleError):
            self.act(
                self.message(
                    "complete", 2, atomic_upload_id="upload", state="succeeded"
                )
            )
        raw = canonical(
            [{"name": "main.tf", "content": 'resource "null_resource" "example" {}'}]
        )
        self.act(
            self.message(
                "upload", 2, atomic_upload_id="upload", upload_digest=digest(raw)
            ),
            upload_bytes=raw,
        )
        result = self.act(
            self.message("complete", 3, atomic_upload_id="upload", state="succeeded")
        )
        self.assertEqual(result["state"], "succeeded")
        with self.assertRaises(LifecycleError):
            self.act(
                self.message(
                    "complete", 3, atomic_upload_id="upload", state="succeeded"
                )
            )

    def test_expired_lease_wrong_token_and_rotation_deny(self):
        self.act(self.message("claim", 1))
        with self.assertRaises(LifecycleError):
            self.act(self.message("heartbeat", 2), now=self.now + timedelta(seconds=31))
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.operate, self.message("heartbeat", 2), self.runner, "f" * 64
            )
        self.runner.generation += 1
        with self.assertRaises(LifecycleError):
            self.act(self.message("heartbeat", 2))

    def test_sequence_race_allows_one_effect(self):
        from concurrent.futures import ThreadPoolExecutor

        message = self.message("claim", 1)

        def claim(_):
            try:
                self.operation(
                    claims.operate, message, self.runner, self.assignment["task_token"]
                )
                return True
            except LifecycleError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(claim, range(2))), 1)

    def test_remote_scheduler_preserves_live_owner_and_never_spawns_collection(self):
        from unittest.mock import Mock
        from infra_automation.coordinator import Coordinator
        from infra_automation.local_workers import HandlerRegistration, HandlerRegistry

        workers = Mock(can_submit=True, max_workers=2, handles=())
        registry = HandlerRegistry(
            (
                HandlerRegistration(
                    "synthetic",
                    "1",
                    "admitted_collection",
                    "screened_artifacts",
                    True,
                    lambda _: None,
                ),
            )
        )
        coordinator = Coordinator(
            self.factory,
            workers,
            registry=registry,
            clock=lambda: self.now,
            runner_requirements={self.profile: self.requirements},
        )
        coordinator._owner = self.owner
        coordinator._schedule(self.run.id, self.now)
        workers.submit.assert_not_called()
        with self.factory() as db:
            self.assertEqual(runs.get_attempt(db, self.pending.id).state, "claimed")

    def test_authenticated_service_rechecks_revoke_disable_and_epoch(self):
        from services import infra_automation_runner_tasks as tasks
        from services import infra_automation_runners as runners

        tasks.operate(
            self.message("claim", 1),
            self.credential,
            self.assignment["task_token"],
            now=self.now,
        )
        with self.credentials():
            runners.revoke(self.runner.id, reason="Revoke test runner.", now=self.now)
        with self.assertRaises(LifecycleError):
            tasks.operate(
                self.message("heartbeat", 2),
                self.credential,
                self.assignment["task_token"],
                now=self.now,
            )
        with self.factory() as db:
            self.assertEqual(runs.get_attempt(db, self.pending.id).state, "running")

    def test_secret_upload_rejected_without_persisting_bytes(self):
        from models.tables import InfraAutomationRunnerTask

        self.act(self.message("claim", 1))
        raw = canonical(
            [
                {
                    "name": "main.tf",
                    "content": 'password = "synthetic-secret-value"',
                }
            ]
        )
        with self.assertRaises(LifecycleError):
            self.act(
                self.message(
                    "upload", 2, atomic_upload_id="upload", upload_digest=digest(raw)
                ),
                upload_bytes=raw,
            )
        with self.factory() as db:
            row = db.get(InfraAutomationRunnerTask, self.pending.id)
            self.assertIsNone(row.upload_bytes)
            self.assertEqual(row.sequence, 1)

    def test_client_http_channel_claim_upload_complete_and_revoke(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from infra_automation.runner.client import RunnerClient, RunnerClientError
        from api.routes.infra_automation_runner import router
        from services import infra_automation_runners as runners

        app = FastAPI()
        app.include_router(router)
        with TestClient(app, base_url="https://runner.invalid") as http:

            def transport(method, url, headers, body, timeout):
                response = http.request(method, url, headers=headers, content=body)
                return response.status_code, response.content

            client = RunnerClient(
                "https://runner.invalid",
                self.credential.runner_id,
                self.credential.token,
                transport=transport,
            )
            result = client.send(
                self.message("claim", 1), self.assignment["task_token"]
            )
            self.assignment["scope"] = result["scope"]
            raw = canonical(
                [
                    {
                        "name": "main.tf",
                        "content": 'resource "null_resource" "example" {}',
                    }
                ]
            )
            result = client.send(
                self.message(
                    "upload",
                    2,
                    atomic_upload_id="http-upload",
                    upload_digest=digest(raw),
                ),
                self.assignment["task_token"],
                upload_bytes=raw,
            )
            self.assignment["scope"] = result["scope"]
            result = client.send(
                self.message(
                    "complete", 3, atomic_upload_id="http-upload", state="succeeded"
                ),
                self.assignment["task_token"],
            )
            self.assertEqual(result["state"], "succeeded")
            with self.credentials():
                runners.revoke(self.runner.id, reason="Revoke test runner.")
            with self.assertRaises(RunnerClientError):
                client.poll(max_polls=1)

    def test_profile_capability_audience_denial_does_not_consume_sequence(self):
        from models.tables import InfraAutomationRunnerTask
        from pydantic import ValidationError

        for operation, fields in (
            ("claim", {}),
            ("heartbeat", {}),
            ("log", {"log": "safe"}),
            ("upload", {"atomic_upload_id": "upload", "upload_digest": digest(b"[]")}),
            ("complete", {"atomic_upload_id": "upload", "state": "succeeded"}),
        ):
            for dimension in ("profile", "audience", "capability"):
                with self.subTest(operation=operation, dimension=dimension):
                    payload = self.message(operation, 1, **fields).model_dump()
                    if dimension == "profile":
                        payload["profile_digest"] = digest(b"different")
                    elif dimension == "audience":
                        payload["scope"]["audience"] = "human"
                    else:
                        payload["capabilities"] = ["arbitrary-command"]
                    with self.assertRaises((LifecycleError, ValidationError)):
                        self.act(RunnerMessage.model_validate(payload))
                    with self.factory() as db:
                        self.assertEqual(
                            db.get(InfraAutomationRunnerTask, self.pending.id).sequence,
                            0,
                        )
                        self.assertEqual(
                            runs.get_attempt(db, self.pending.id).state, "claimed"
                        )

    def test_no_eligible_runner_persists_explicit_failure_without_fallback(self):
        from services import infra_automation_runner_tasks as tasks
        from models.tables import InfraAutomationAudit
        from sqlalchemy import select

        self.request["key_digest"] = digest(b"next-run")
        run = self.admit()
        pending = self.attempt(run)
        self.operation(
            engine_claims.start_run, self.owner, run_id=run.id, expected_version=1
        )
        mismatched = self.requirements.model_copy(update={"tags": ["unavailable"]})
        self.assertIsNone(
            tasks.queue_assignment(
                self.owner,
                pending.id,
                mismatched,
                now=self.now,
                session_factory=self.factory,
            )
        )
        with self.factory() as db:
            self.assertEqual(runs.get_attempt(db, pending.id).state, "failed")
            event = db.scalar(
                select(InfraAutomationAudit).where(
                    InfraAutomationAudit.event_type == "runner.no_eligible_runner"
                )
            )
            self.assertEqual(event.target_id, pending.id)
            self.assertIn("zero seconds", event.reason)
            self.assertEqual(runs.get_attempt(db, self.pending.id).state, "claimed")

    def test_repeated_assignment_cannot_kill_current_owner(self):
        from services import infra_automation_runner_tasks as tasks

        with self.assertRaises(LifecycleError):
            tasks.queue_assignment(
                self.owner,
                self.pending.id,
                self.requirements,
                now=self.now,
                session_factory=self.factory,
            )
        with self.factory() as db:
            self.assertEqual(runs.get_attempt(db, self.pending.id).state, "claimed")

    def test_poll_reveals_once_and_restart_fences_delivered_grant(self):
        from services import infra_automation_runner_tasks as tasks

        self.act(self.message("claim", 1))
        raw = canonical(
            [{"name": "main.tf", "content": 'resource "null_resource" "example" {}'}]
        )
        self.act(
            self.message(
                "upload", 2, atomic_upload_id="first", upload_digest=digest(raw)
            ),
            upload_bytes=raw,
        )
        self.act(
            self.message("complete", 3, atomic_upload_id="first", state="succeeded")
        )
        self.request["key_digest"] = digest(b"polled-run")
        run = self.admit()
        pending = self.attempt(run)
        self.operation(
            engine_claims.start_run, self.owner, run_id=run.id, expected_version=1
        )
        tasks.queue_assignment(
            self.owner,
            pending.id,
            self.requirements,
            now=self.now,
            session_factory=self.factory,
        )
        assignment = tasks.poll(self.credential, now=self.now)
        self.assertEqual(assignment["scope"]["run_id"], run.id)
        self.assertIsNone(tasks.poll(self.credential, now=self.now))
        self.operation(
            engine_claims.release_coordinator,
            self.owner,
            project_id=100,
            workspace_id=100,
        )
        self.acquire()
        message = RunnerMessage(
            operation="claim",
            scope=assignment["scope"],
            profile_digest=self.profile,
            capabilities=["screened-collection-v1"],
            sequence=1,
        )
        with self.assertRaises(LifecycleError):
            tasks.operate(
                message, self.credential, assignment["task_token"], now=self.now
            )

    def test_disabled_policy_denies_all_operations_without_advancing(self):
        from services import infra_automation_runner_tasks as tasks
        from services import infra_automation_policy as policy
        from infra_automation.lifecycle import AutomationSettings, UpdateSettingsRequest
        from models.tables import InfraAutomationRunnerTask

        tasks.operate(
            self.message("claim", 1),
            self.credential,
            self.assignment["task_token"],
            now=self.now,
        )
        with self.credentials():
            policy.update_settings(
                UpdateSettingsRequest(
                    project_id=100,
                    expected_version=1,
                    settings=AutomationSettings(enabled=False),
                    reason="Disable fixture.",
                )
            )
        for operation, fields in (
            ("claim", {}),
            ("heartbeat", {}),
            ("log", {"log": "safe"}),
            ("upload", {"atomic_upload_id": "upload", "upload_digest": digest(b"[]")}),
            ("complete", {"atomic_upload_id": "upload", "state": "succeeded"}),
        ):
            with self.subTest(operation=operation), self.assertRaises(LifecycleError):
                tasks.operate(
                    self.message(operation, 2, **fields),
                    self.credential,
                    self.assignment["task_token"],
                    now=self.now,
                )
        with self.factory() as db:
            self.assertEqual(
                db.get(InfraAutomationRunnerTask, self.pending.id).sequence, 1
            )

    def after_contended_reservation(self, operation):
        """Advance injected wall clock while a real SQLite writer blocks BEGIN."""
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event, current_thread
        from unittest.mock import patch
        from sqlalchemy import event

        waiting = Event()
        observed = [self.now]

        def beginning(connection, cursor, statement, parameters, context, many):
            if statement == "BEGIN IMMEDIATE" and current_thread().name.startswith(
                "runner-expiry"
            ):
                waiting.set()

        event.listen(self.engine, "before_cursor_execute", beginning)
        self.addCleanup(
            lambda: event.remove(self.engine, "before_cursor_execute", beginning)
        )
        with patch.object(
            engine_claims,
            "_now",
            side_effect=lambda value: observed[0] if value is None else value,
        ):
            with (
                self.engine.connect() as blocker,
                ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="runner-expiry"
                ) as pool,
            ):
                blocker.exec_driver_sql("BEGIN IMMEDIATE")
                future = pool.submit(operation)
                try:
                    self.assertTrue(
                        waiting.wait(5), "operation did not reach SQLite reservation"
                    )
                    observed[0] = self.now + timedelta(seconds=31)
                finally:
                    blocker.rollback()
                return future.result(timeout=5)

    def test_contention_expiry_denies_operation_using_fresh_clock(self):
        from services import infra_automation_runner_tasks as tasks
        from models.tables import InfraAutomationRunnerTask

        with self.assertRaises(LifecycleError):
            self.after_contended_reservation(
                lambda: tasks.operate(
                    self.message("claim", 1),
                    self.credential,
                    self.assignment["task_token"],
                )
            )
        with self.factory() as db:
            self.assertEqual(
                db.get(InfraAutomationRunnerTask, self.pending.id).sequence, 0
            )
            self.assertEqual(runs.get_attempt(db, self.pending.id).state, "claimed")

    def test_contention_expiry_poll_does_not_reveal_expired_grant(self):
        from services import infra_automation_runner_tasks as tasks

        tasks._MAILBOX[self.pending.id] = (
            self.now + timedelta(seconds=30),
            self.runner.id,
            self.runner.generation,
            self.assignment,
        )
        self.addCleanup(lambda: tasks._MAILBOX.pop(self.pending.id, None))
        self.assertIsNone(
            self.after_contended_reservation(lambda: tasks.poll(self.credential))
        )

    def test_contention_expiry_prevents_coordinator_assignment(self):
        from services import infra_automation_runner_tasks as tasks

        self.request["key_digest"] = digest(b"contended-queue")
        run = self.admit()
        pending = self.attempt(run)
        self.operation(
            engine_claims.start_run, self.owner, run_id=run.id, expected_version=1
        )
        with self.assertRaises(LifecycleError):
            self.after_contended_reservation(
                lambda: tasks.queue_assignment(
                    self.owner,
                    pending.id,
                    self.requirements,
                    session_factory=self.factory,
                )
            )
        with self.factory() as db:
            self.assertEqual(runs.get_attempt(db, pending.id).state, "pending")

    def test_upload_screening_expiry_rolls_back_sequence_and_bytes(self):
        from unittest.mock import patch
        from models.tables import InfraAutomationRunnerTask
        from services import infra_automation_runner_tasks as tasks

        self.act(self.message("claim", 1))
        raw = canonical(
            [{"name": "main.tf", "content": 'resource "null_resource" "example" {}'}]
        )
        observed = [self.now]
        real_screen = claims.screened_upload

        def slow_screen(raw, checksum):
            result = real_screen(raw, checksum)
            observed[0] = self.now + timedelta(seconds=31)
            return result

        with (
            patch.object(
                engine_claims,
                "_now",
                side_effect=lambda value: observed[0] if value is None else value,
            ),
            patch.object(claims, "screened_upload", side_effect=slow_screen),
            self.assertRaises(LifecycleError),
        ):
            tasks.operate(
                self.message(
                    "upload", 2, atomic_upload_id="late", upload_digest=digest(raw)
                ),
                self.credential,
                self.assignment["task_token"],
                upload_bytes=raw,
            )
        with self.factory() as db:
            row = db.get(InfraAutomationRunnerTask, self.pending.id)
            self.assertEqual(row.sequence, 1)
            self.assertIsNone(row.upload_bytes)

    def test_bearer_and_task_secret_corpus_never_persists_in_logs_uploads_or_ids(self):
        from services import infra_automation_runner_tasks as tasks
        from models.tables import InfraAutomationRunnerTask

        tasks.operate(
            self.message("claim", 1),
            self.credential,
            self.assignment["task_token"],
            now=self.now,
        )
        corpus = (
            self.credential.token,
            self.assignment["task_token"],
            "enroll-v1-" + "e" * 64,
            "runner-v1-" + "f" * 64,
        )
        for secret in corpus:
            for target in ("log", "upload", "upload_id"):
                with self.subTest(target=target, credential=corpus.index(secret)):
                    raw = canonical(
                        [
                            {
                                "name": "main.tf",
                                "content": "# "
                                + secret
                                + '\nresource "null_resource" "example" {}',
                            }
                        ]
                    )
                    if target == "log":
                        message, content = (
                            self.message("log", 2, log="diagnostic " + secret),
                            None,
                        )
                    elif target == "upload":
                        message, content = (
                            self.message(
                                "upload",
                                2,
                                atomic_upload_id="upload",
                                upload_digest=digest(raw),
                            ),
                            raw,
                        )
                    else:
                        raw = canonical(
                            [
                                {
                                    "name": "main.tf",
                                    "content": 'resource "null_resource" "example" {}',
                                }
                            ]
                        )
                        message, content = (
                            self.message(
                                "upload",
                                2,
                                atomic_upload_id=secret,
                                upload_digest=digest(raw),
                            ),
                            raw,
                        )
                    with self.assertRaises(LifecycleError) as caught:
                        tasks.operate(
                            message,
                            self.credential,
                            self.assignment["task_token"],
                            upload_bytes=content,
                            now=self.now,
                        )
                    self.assertNotIn(secret, str(caught.exception))
                    with self.factory() as db:
                        row = db.get(InfraAutomationRunnerTask, self.pending.id)
                        self.assertEqual(row.sequence, 1)
                        self.assertIsNone(row.upload_bytes)
                        self.assertEqual(
                            runs.get_attempt(db, self.pending.id).logs_json, "[]"
                        )

    def test_log_chunks_cannot_reassemble_runner_or_task_credential(self):
        from services import infra_automation_runner_tasks as tasks
        from models.tables import InfraAutomationRunnerTask

        tasks.operate(
            self.message("claim", 1),
            self.credential,
            self.assignment["task_token"],
            now=self.now,
        )
        # The first fragment does not expose a bearer; joining the second is
        # rejected before sequence/audit/log mutation in the same transaction.
        token = self.assignment["task_token"]
        tasks.operate(
            self.message("log", 2, log=token[:32]), self.credential, token, now=self.now
        )
        with self.assertRaises(LifecycleError):
            tasks.operate(
                self.message("log", 3, log=token[32:]),
                self.credential,
                token,
                now=self.now,
            )
        with self.factory() as db:
            row = db.get(InfraAutomationRunnerTask, self.pending.id)
            self.assertEqual(row.sequence, 2)
            self.assertNotIn(token, runs.get_attempt(db, self.pending.id).logs_json)
        # Split a recognizable bearer prefix itself across two log messages.
        tasks.operate(
            self.message("log", 3, log="run"), self.credential, token, now=self.now
        )
        with self.assertRaises(LifecycleError):
            tasks.operate(
                self.message("log", 4, log=self.credential.token[3:]),
                self.credential,
                token,
                now=self.now,
            )

    def wire_deadline(self):
        return datetime.strptime(
            self.assignment["scope"]["lease_deadline"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)

    def test_wire_deadline_is_exclusive_even_before_fractional_database_expiry(self):
        from models.tables import InfraAutomationRunnerTask

        deadline = self.wire_deadline()
        with self.factory() as db:
            self.assertGreater(
                runs.utc(runs.get_attempt(db, self.pending.id).lease_until), deadline
            )
        # One microsecond before the advertised deadline remains admissible.
        self.act(self.message("claim", 1), now=deadline - timedelta(microseconds=1))
        for operation, fields in (
            ("claim", {}),
            ("heartbeat", {}),
            ("log", {"log": "safe"}),
            ("upload", {"atomic_upload_id": "upload", "upload_digest": digest(b"[]")}),
            ("complete", {"atomic_upload_id": "upload", "state": "succeeded"}),
        ):
            with self.subTest(operation=operation), self.assertRaises(LifecycleError):
                self.act(self.message(operation, 2, **fields), now=deadline)
        with self.factory() as db:
            self.assertEqual(
                db.get(InfraAutomationRunnerTask, self.pending.id).sequence, 1
            )

    def test_poll_never_reveals_at_advertised_wire_deadline(self):
        from services import infra_automation_runner_tasks as tasks

        with self.factory() as db:
            database_deadline = runs.utc(
                runs.get_attempt(db, self.pending.id).lease_until
            )
        tasks._MAILBOX[self.pending.id] = (
            database_deadline,
            self.runner.id,
            self.runner.generation,
            self.assignment,
        )
        self.addCleanup(lambda: tasks._MAILBOX.pop(self.pending.id, None))
        self.assertIsNone(tasks.poll(self.credential, now=self.wire_deadline()))

    def test_screening_cannot_cross_advertised_wire_deadline(self):
        from unittest.mock import patch
        from models.tables import InfraAutomationRunnerTask
        from services import infra_automation_runner_tasks as tasks

        self.act(self.message("claim", 1))
        raw = canonical(
            [{"name": "main.tf", "content": 'resource "null_resource" "example" {}'}]
        )
        observed = [self.now]
        real_screen = claims.screened_upload

        def slow_screen(raw, checksum):
            result = real_screen(raw, checksum)
            observed[0] = self.wire_deadline()
            return result

        with (
            patch.object(
                engine_claims,
                "_now",
                side_effect=lambda value: observed[0] if value is None else value,
            ),
            patch.object(claims, "screened_upload", side_effect=slow_screen),
            self.assertRaises(LifecycleError),
        ):
            tasks.operate(
                self.message(
                    "upload", 2, atomic_upload_id="late-wire", upload_digest=digest(raw)
                ),
                self.credential,
                self.assignment["task_token"],
                upload_bytes=raw,
            )
        with self.factory() as db:
            row = db.get(InfraAutomationRunnerTask, self.pending.id)
            self.assertEqual(row.sequence, 1)
            self.assertIsNone(row.upload_bytes)
