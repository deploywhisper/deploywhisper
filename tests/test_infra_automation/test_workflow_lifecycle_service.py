"""Live scope, atomic publication and immutable restore service proofs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from unittest.mock import patch

from sqlalchemy import func, select

from infra_automation.lifecycle import (
    ArchiveWorkflowRequest,
    CreateWorkflowRequest,
    LifecycleError,
    PublishWorkflowRequest,
    RestoreWorkflowRequest,
    SaveDraftRequest,
    ValidateDraftRequest,
    ValidateWorkflowRequest,
)
from models.tables import InfraAutomationAudit, InfraWorkflowRevision
from services import infra_automation_service as service
from services import project_service as authorization
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class WorkflowLifecycleServiceTests(LifecycleCase):
    def create(self, **changes):
        values = {
            "project_id": 100,
            "workspace_id": 100,
            "name": "Preflight",
            "definition": json.dumps(self.definition()),
            "reason": "initial draft",
            **changes,
        }
        with self.credentials():
            return service.create_workflow(CreateWorkflowRequest(**values))

    def test_maintainer_authoring_is_nonexecutable_and_publication_is_admin_only(self):
        self.member("maintainer")
        draft = self.create()
        with self.credentials():
            self.assertEqual(service.get_workflow(draft["id"])["draft_version"], 1)
            result = service.validate_draft(
                draft["id"], ValidateDraftRequest(expected_version=1)
            )
            self.assertTrue(result["valid"])
            with self.assertRaises(authorization.TrustedAuthorizationError):
                service.publish_workflow(
                    draft["id"],
                    PublishWorkflowRequest(
                        expected_version=1, idempotency_key="publish", reason="publish"
                    ),
                )
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraWorkflowRevision)), 0
            )

    def test_scope_and_workspace_cannot_be_rebound(self):
        draft = self.create()
        with self.credentials():
            with self.assertRaises(authorization.TrustedAuthorizationError):
                service.save_draft(
                    draft["id"],
                    SaveDraftRequest(
                        expected_version=1,
                        definition=json.dumps(
                            self.definition(project_id=200, workspace_id=200)
                        ),
                        reason="change",
                    ),
                )
        self.member("admin", workspace=101)
        with self.credentials():
            for operation in (
                lambda: service.get_workflow(draft["id"]),
                lambda: service.list_workflows(100),
                lambda: service.list_workflows(100, workspace_id=100),
            ):
                with self.assertRaises(authorization.TrustedAuthorizationError):
                    operation()

    def test_publish_retry_after_edit_returns_original_revision_and_changed_reuse_conflicts(
        self,
    ):
        draft = self.create()
        request = PublishWorkflowRequest(
            expected_version=1, idempotency_key="same-key", reason="publish stable"
        )
        with self.credentials():
            first = service.publish_workflow(draft["id"], request)
            edited = self.definition()
            edited["inputs"]["note"] = {
                "type": "string",
                "required": False,
                "default": "edited",
            }
            saved = service.save_draft(
                draft["id"],
                SaveDraftRequest(
                    expected_version=2, definition=json.dumps(edited), reason="edit"
                ),
            )
            self.assertEqual(saved["draft_version"], 3)
            self.assertEqual(service.publish_workflow(draft["id"], request), first)
            with self.assertRaises(LifecycleError) as error:
                service.publish_workflow(
                    draft["id"],
                    PublishWorkflowRequest(
                        expected_version=3,
                        idempotency_key="same-key",
                        reason="publish stable",
                    ),
                )
            self.assertEqual(error.exception.status_code, 409)
            self.assertEqual(service.get_revision(draft["id"], first["id"]), first)

    def test_different_keys_racing_one_version_create_one_revision(self):
        draft = self.create()

        def publish(key):
            with self.credentials():
                try:
                    return service.publish_workflow(
                        draft["id"],
                        PublishWorkflowRequest(
                            expected_version=1, idempotency_key=key, reason="publish"
                        ),
                    )["id"]
                except LifecycleError as error:
                    return error.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(publish, ["one", "two"]))
        self.assertEqual(results.count(409), 1)
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraWorkflowRevision)), 1
            )
            self.assertEqual(
                db.scalar(
                    select(func.count())
                    .select_from(InfraAutomationAudit)
                    .where(InfraAutomationAudit.event_type == "workflow_published")
                ),
                1,
            )

    def test_archive_restore_keeps_history_and_creates_new_draft_version(self):
        draft = self.create()
        with self.credentials():
            revision = service.publish_workflow(
                draft["id"],
                PublishWorkflowRequest(
                    expected_version=1, idempotency_key="publish", reason="publish"
                ),
            )
            archived = service.archive_workflow(
                draft["id"],
                ArchiveWorkflowRequest(expected_version=2, reason="archive"),
            )
            self.assertTrue(archived["archived"])
            with self.assertRaises(LifecycleError):
                service.save_draft(
                    draft["id"],
                    SaveDraftRequest(
                        expected_version=3,
                        definition=json.dumps(self.definition()),
                        reason="edit",
                    ),
                )
            restored = service.restore_workflow(
                draft["id"],
                RestoreWorkflowRequest(
                    expected_version=3,
                    revision_id=revision["id"],
                    reason="restore stable",
                ),
            )
            self.assertFalse(restored["archived"])
            self.assertEqual(restored["draft_version"], 4)
            self.assertEqual(restored["draft_digest"], revision["digest"])
            self.assertEqual(
                service.get_revision(draft["id"], revision["id"]), revision
            )

    def test_audit_failure_rolls_back_publication_and_version(self):
        draft = self.create()
        with (
            self.credentials(),
            patch(
                "services.infra_automation_support.repository.append_audit",
                side_effect=RuntimeError("synthetic failure"),
            ),
        ):
            with self.assertRaises(RuntimeError):
                service.publish_workflow(
                    draft["id"],
                    PublishWorkflowRequest(
                        expected_version=1, idempotency_key="atomic", reason="publish"
                    ),
                )
        with self.credentials():
            self.assertEqual(service.get_workflow(draft["id"])["draft_version"], 1)
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraWorkflowRevision)), 0
            )

    def test_validation_diagnostics_and_secret_rejection_do_not_persist_input(self):
        bad = self.definition()
        bad["workflow_version"] = True
        with self.credentials():
            result = service.validate_definition(
                ValidateWorkflowRequest(
                    project_id=100, workspace_id=100, definition=json.dumps(bad)
                )
            )
            self.assertFalse(result["valid"])
            self.assertEqual(result["errors"][0]["code"], "schema_version")
        raw = self.definition()
        raw["inputs"]["note"] = {
            "type": "string",
            "required": False,
            "default": "password=synthetic-private-value",
        }
        with self.assertRaises(LifecycleError):
            self.create(definition=json.dumps(raw))
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(InfraAutomationAudit)), 0
            )

    def test_machine_identity_cannot_publish_and_getter_cannot_mutate(self):
        draft = self.create()
        for principal_type in ("service", "agent", "runner", "receiver"):
            self.principal(
                principal_type,
                principal_type=principal_type,
                audience="service-request-v1",
            )
            self.member("admin", principal=principal_type)
            with (
                self.credentials(principal_type),
                self.assertRaises(authorization.TrustedAuthorizationError),
            ):
                service.publish_workflow(
                    draft["id"],
                    PublishWorkflowRequest(
                        expected_version=1,
                        idempotency_key=principal_type,
                        reason="publish",
                    ),
                )
        with (
            self.credentials(mutation=False),
            self.assertRaises(authorization.TrustedAuthorizationError),
        ):
            service.publish_workflow(
                draft["id"],
                PublishWorkflowRequest(
                    expected_version=1, idempotency_key="read-context", reason="publish"
                ),
            )

    def test_pages_are_scope_bound_and_exclude_new_rows(self):
        for index in range(3):
            self.create(name=f"Draft {index}")
        with self.credentials():
            page = service.list_workflows(100, 100, limit=1)
            self.assertIsNotNone(page["cursor"]["next_cursor"])
            token = page["cursor"]["next_cursor"]
            new = self.create(name="Later draft")
            seen = {page["items"][0]["id"]}
            while token:
                page = service.list_workflows(100, 100, limit=1, cursor=token)
                seen.update(row["id"] for row in page["items"])
                token = page["cursor"]["next_cursor"]
            self.assertEqual(len(seen), 3)
            self.assertNotIn(new["id"], seen)

    def test_audit_export_is_admin_scoped_and_contains_no_definition(self):
        draft = self.create()
        with self.credentials():
            result = service.export_audit(100, 100)
            self.assertEqual(result["items"][0]["workspace_id"], 100)
            self.assertEqual(result["items"][0]["target_id"], draft["id"])
            self.assertNotIn("definition", result["items"][0])
        self.member("maintainer")
        with (
            self.credentials(),
            self.assertRaises(authorization.TrustedAuthorizationError),
        ):
            service.export_audit(100, 100)
