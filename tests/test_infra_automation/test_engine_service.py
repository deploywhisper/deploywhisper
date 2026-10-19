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
