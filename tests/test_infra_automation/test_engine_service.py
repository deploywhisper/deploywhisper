"""Human admission, replay and scoped read ports for durable run snapshots."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import patch

from sqlalchemy import func, select

from infra_automation.lifecycle import LifecycleError
from infra_automation.state import EngineBounds, RunRequest
from models.repositories import infra_automation_runs as repository
from models.repositories import infra_automation_workflows as workflows
from models.tables import InfraAutomationAudit, InfraAutomationRun
from services import infra_automation_engine_service as service
from services import project_service as authorization
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation import test_workflow_snapshots as snapshot_tests


class AvailableHandlers:
    """Trusted registration stand-in; it performs no work or external calls."""

    def get(self, kind):
        return object()


class EngineServiceTests(LifecycleCase):
    publish_fixture = snapshot_tests.WorkflowSnapshotTests.publish_fixture
    enable = snapshot_tests.WorkflowSnapshotTests.enable

    def setUp(self):
        super().setUp()
        self.enable()
        self.ids = self.publish_fixture()
        self.request = RunRequest(
            workflow_id=self.ids[0],
            revision_id=self.ids[1],
            workspace_id=100,
            inputs={"note": "original"},
            idempotency_key="synthetic-request",
            reason="Start synthetic advisory work.",
        )
        self.registry = AvailableHandlers()

    def admit(self, request=None, **kwargs):
        with self.credentials():
            return service.request_run(
                request or self.request, registry=self.registry, **kwargs
            )

    def counts(self):
        with self.factory() as session:
            return (
                session.scalar(select(func.count()).select_from(InfraAutomationRun)),
                session.scalar(select(func.count()).select_from(InfraAutomationAudit)),
            )

    def test_identical_concurrent_retries_create_one_snapshot_and_request(self):
        with ThreadPoolExecutor(max_workers=3) as pool:
            runs = list(pool.map(lambda _: self.admit(), range(3)))
        self.assertEqual(len({run["id"] for run in runs}), 1)
        count = self.counts()
        with patch.object(
            service, "_export", side_effect=AssertionError("No recapture")
        ):
            self.assertEqual(self.admit()["id"], runs[0]["id"])
        self.assertEqual(self.counts(), count)
        changed = self.request.model_copy(update={"inputs": {"note": "changed"}})
        with self.assertRaises(LifecycleError) as error:
            self.admit(changed)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.counts(), count)

    def test_snapshot_stays_immutable_and_replay_survives_disable_and_draft_edit(self):
        run = self.admit()
        with self.factory() as session:
            before = repository.get_run(session, run["id"]).snapshot_bytes
        with self.factory.begin() as session:
            workflow = workflows.get_workflow(session, self.ids[0])
            workflows.update_workflow(
                session,
                workflow_id=workflow.id,
                expected_version=workflow.draft_version,
                canonical_definition=workflow.draft_definition,
                digest=workflow.draft_digest,
            )
            policy = workflows.get_policy(session, project_id=100)
            settings = json.loads(policy.settings_json)
            settings["enabled"] = False
            workflows.save_policy(
                session,
                project_id=100,
                expected_version=policy.version,
                settings_json=json.dumps(settings),
            )
        with self.credentials():
            replay = service.request_run(self.request, registry=None)
            read = service.get_run(run["id"])
        self.assertEqual(replay, read)
        with self.factory() as session:
            self.assertEqual(
                repository.get_run(session, run["id"]).snapshot_bytes, before
            )

    def test_feature_off_unknown_handler_and_quota_fail_without_persistence(self):
        count = self.counts()
        with self.credentials(), self.assertRaises(LifecycleError) as error:
            service.request_run(self.request, registry={})
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(self.counts(), count)
        with self.assertRaises(LifecycleError) as error:
            self.admit(bounds=EngineBounds(project_bytes=1))
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(self.counts(), count)
        with self.factory.begin() as session:
            row = workflows.get_policy(session, project_id=100)
            settings = json.loads(row.settings_json)
            settings["enabled"] = False
            workflows.save_policy(
                session,
                project_id=100,
                expected_version=row.version,
                settings_json=json.dumps(settings),
            )
        with self.assertRaises(LifecycleError) as error:
            self.admit()
        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(self.counts(), count)

    def test_live_scope_protects_reads_lists_and_request_replay(self):
        run = self.admit()
        self.member("read-only", workspace=101)
        with (
            self.credentials(mutation=False),
            self.assertRaises(authorization.TrustedAuthorizationError),
        ):
            service.get_run(run["id"])
        with (
            self.credentials(mutation=False),
            self.assertRaises(authorization.TrustedAuthorizationError),
        ):
            service.list_runs(100, 100)
        with (
            self.credentials(),
            self.assertRaises(authorization.TrustedAuthorizationError),
        ):
            service.request_run(self.request, registry=self.registry)

    def test_deadline_is_capped_by_evidence_and_complete_response_rolls_back(self):
        now = datetime.now(timezone.utc)
        run = self.admit(now=now)
        deadline = datetime.strptime(run["deadline_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        self.assertLessEqual(deadline, now + timedelta(seconds=3600))
        self.assertGreater(deadline, now)
        count = self.counts()
        request = self.request.model_copy(update={"idempotency_key": "overflow"})
        with patch("api.schemas.build_meta", return_value={"app_name": "x" * 140000}):
            with self.assertRaises(LifecycleError) as error:
                self.admit(request)
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(self.counts(), count)

    def test_saved_draft_identifier_cannot_be_used_as_revision(self):
        bad = self.request.model_copy(update={"revision_id": self.ids[0]})
        with self.assertRaises(authorization.TrustedAuthorizationError):
            self.admit(bad)
        self.assertEqual(self.counts()[0], 0)

    def test_uncredentialed_admission_and_queue_saturation_are_atomic(self):
        before = self.counts()
        with self.assertRaises(authorization.TrustedAuthorizationError):
            service.request_run(self.request, registry=self.registry)
        self.assertEqual(self.counts(), before)
        self.admit(bounds=EngineBounds(workflow_queued_runs=1))
        before = self.counts()
        second = self.request.model_copy(update={"idempotency_key": "queue-full"})
        with self.assertRaises(LifecycleError) as error:
            self.admit(second, bounds=EngineBounds(workflow_queued_runs=1))
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(self.counts(), before)

    def test_project_queue_count_includes_other_workflows(self):
        self.admit()
        with self.factory.begin() as session:
            row = workflows.get_policy(session, project_id=100)
            settings = json.loads(row.settings_json)
            settings["max_queued_runs"] = 1
            workflows.save_policy(
                session,
                project_id=100,
                expected_version=row.version,
                settings_json=json.dumps(settings),
            )
        ids = self.publish_fixture()
        request = self.request.model_copy(
            update={
                "workflow_id": ids[0],
                "revision_id": ids[1],
                "idempotency_key": "project-full",
            }
        )
        before = self.counts()
        with self.assertRaises(LifecycleError) as error:
            self.admit(request)
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(self.counts(), before)

    def test_steps_logs_use_scoped_snapshot_pagination_and_byte_bound(self):
        from infra_automation import claims
        from infra_automation.state import LogChunk

        run = self.admit()
        with authorization.authorized_session(self.factory) as session:
            owner = claims.acquire_coordinator(
                session, project_id=100, workspace_id=100
            )
            current = repository.get_run(session, run["id"])
            claims.start_run(
                session, owner, run_id=current.id, expected_version=current.version
            )
            attempt = claims.prepare_attempt(
                session,
                owner,
                run_id=current.id,
                step_id="upload",
                handler_id="synthetic",
                handler_version="1",
                retry_safe=True,
            )
            handle = claims.claim_attempt(
                session, owner, attempt_id=attempt.id, expected_version=attempt.version
            )
            attempt = repository.get_attempt(session, handle.attempt_id)
            attempt = claims.start_attempt(
                session, handle, expected_version=attempt.version
            )
            for sequence in range(1, 10):
                attempt = claims.append_log(
                    session,
                    handle,
                    expected_version=attempt.version,
                    chunk=LogChunk(sequence=sequence, text="a" * 16000),
                )
        with self.credentials(mutation=False):
            steps = service.list_steps(run["id"], limit=100)
            first = service.get_logs(run["id"], attempt.id, limit=100)
        self.assertEqual([item["id"] for item in steps["items"]], [attempt.id])
        self.assertNotIn("owner_secret", json.dumps(steps))
        self.assertTrue(first["cursor"]["truncated"])
        self.assertFalse(first["cursor"]["gap"])
        self.assertLessEqual(len(service.support.canonical(first)), 131072)
        with authorization.authorized_session(self.factory) as session:
            current = repository.get_attempt(session, attempt.id)
            claims.append_log(
                session,
                handle,
                expected_version=current.version,
                chunk=LogChunk(sequence=10, text="new-log"),
            )
        chunks = list(first["items"])
        cursor = first["cursor"]["next_cursor"]
        while cursor:
            with self.credentials(mutation=False):
                page = service.get_logs(run["id"], attempt.id, limit=100, cursor=cursor)
            chunks.extend(page["items"])
            cursor = page["cursor"]["next_cursor"]
        self.assertEqual([item["sequence"] for item in chunks], list(range(9, 0, -1)))
        self.member("read-only", workspace=101)
        with (
            self.credentials(mutation=False),
            self.assertRaises(authorization.TrustedAuthorizationError),
        ):
            service.get_logs(run["id"], attempt.id)

    def test_existing_audit_response_accepts_truthful_background_service_actor(self):
        from api.schemas import AutomationAuditItem
        from infra_automation import claims
        from services.infra_automation_service import export_audit

        self.admit()
        with authorization.authorized_session(self.factory) as session:
            claims.acquire_coordinator(session, project_id=100, workspace_id=100)
        with self.credentials(mutation=False):
            exported = export_audit(100, 100)
        system_events = [
            item for item in exported["items"] if item["actor_type"] == "service"
        ]
        self.assertTrue(system_events)
        for item in exported["items"]:
            typed = AutomationAuditItem.model_validate(item)
            if typed.actor_type == "service":
                self.assertEqual(typed.actor_role, "coordinator")
        with self.assertRaises(ValueError):
            AutomationAuditItem.model_validate(
                {**system_events[0], "actor_type": "human"}
            )

    def test_global_backlog_cap_and_physical_reserve_fail_before_persistence(self):
        from types import SimpleNamespace
        from infra_automation import storage

        self.admit(bounds=EngineBounds(global_queued_runs=1))
        other = self.request.model_copy(update={"idempotency_key": "global-overflow"})
        before = self.counts()
        with self.assertRaises(LifecycleError) as error:
            self.admit(other, bounds=EngineBounds(global_queued_runs=1))
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(self.counts(), before)
        with patch.object(
            storage.shutil, "disk_usage", return_value=SimpleNamespace(free=0)
        ):
            with self.assertRaises(LifecycleError) as error:
                self.admit(other)
            self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(self.counts(), before)
