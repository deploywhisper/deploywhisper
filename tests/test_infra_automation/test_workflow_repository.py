"""Transaction ownership, immutable history and scoped cursor repository proofs."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from importlib import reload
import os
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import config
import models.database as database
from models.repositories import infra_automation_workflows as repo
from models.tables import IdentityAccount, Project, ProjectWorkspace


class WorkflowRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ, {"DATABASE_URL": f"sqlite:///{self.temp.name}/test.db"}
        )
        self.env.start()
        reload(config)
        reload(database)
        database.init_db()
        self.session = database.SessionLocal()
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.session.add_all(
            [
                Project(id=100, project_key="one", display_name="One"),
                Project(id=200, project_key="two", display_name="Two"),
                IdentityAccount(
                    id="human",
                    username="human",
                    password_verifier="synthetic",
                    created_at=self.now,
                ),
            ]
        )
        self.session.flush()
        self.session.add(
            ProjectWorkspace(
                id=100, project_id=100, workspace_key="dev", display_name="Dev"
            )
        )
        self.session.commit()

    def tearDown(self):
        self.session.close()
        database.engine.dispose()
        self.env.stop()
        reload(config)
        reload(database)
        self.temp.cleanup()

    def workflow(self, **kwargs):
        return repo.create_workflow(
            self.session,
            project_id=100,
            workspace_id=100,
            name="Workflow",
            canonical_definition=b"{}",
            digest="a" * 64,
            created_by="human",
            now=self.now,
            **kwargs,
        )

    def revision(self, workflow, **kwargs):
        return repo.append_revision(
            self.session,
            workflow_id=workflow.id,
            project_id=100,
            workspace_id=100,
            revision_number=1,
            canonical_definition=b"{}",
            digest="a" * 64,
            published_by="human",
            idempotency_key_digest="b" * 64,
            request_digest="c" * 64,
            now=self.now,
            **kwargs,
        )

    def test_cas_and_rollback_remain_caller_owned(self):
        workflow = self.workflow()
        identifier = workflow.id
        self.assertEqual(workflow.draft_version, 1)
        self.assertEqual(
            repo.update_workflow(
                self.session, workflow_id=identifier, expected_version=1
            ).draft_version,
            2,
        )
        self.assertIsNone(
            repo.update_workflow(
                self.session, workflow_id=identifier, expected_version=1
            )
        )
        self.session.rollback()
        self.assertIsNone(repo.get_workflow(self.session, identifier))

    def test_revision_audit_immutable_and_parent_cannot_erase_history(self):
        workflow = self.workflow()
        revision = self.revision(workflow)
        audit = repo.append_audit(
            self.session,
            project_id=100,
            workspace_id=100,
            actor_principal_id="human",
            actor_type="human",
            actor_role="admin",
            event_type="publish",
            target_id=workflow.id,
            reason="Reviewed",
            before_digest=None,
            after_digest="a" * 64,
            now=self.now,
        )
        self.session.commit()
        self.assertEqual(
            repo.get_publication(
                self.session, published_by="human", idempotency_key_digest="b" * 64
            ).id,
            revision.id,
        )
        for sql in [
            "UPDATE infra_workflow_revisions SET digest='changed'",
            "DELETE FROM infra_workflow_revisions",
            "INSERT OR REPLACE INTO infra_workflow_revisions SELECT * FROM infra_workflow_revisions",
            "UPDATE infra_automation_audit SET reason='changed'",
            "DELETE FROM infra_automation_audit",
            "INSERT OR REPLACE INTO infra_automation_audit SELECT * FROM infra_automation_audit",
            "DELETE FROM infra_workflows",
            "INSERT OR REPLACE INTO infra_workflows SELECT * FROM infra_workflows",
            "DELETE FROM projects WHERE id=100",
            "UPDATE infra_workflows SET project_id=200",
            "UPDATE infra_workflows SET sequence=100",
        ]:
            with self.subTest(sql=sql), self.assertRaises(IntegrityError):
                self.session.execute(text(sql))
            self.session.rollback()
        self.assertEqual(audit.reason, "Reviewed")

    def test_scope_and_uniqueness_constraints(self):
        workflow = self.workflow()
        self.revision(workflow)
        self.session.commit()
        with self.assertRaises(IntegrityError):
            self.revision(workflow)
        self.session.rollback()
        with self.assertRaises(IntegrityError):
            repo.create_workflow(
                self.session,
                project_id=200,
                workspace_id=100,
                name="Wrong",
                canonical_definition=b"{}",
                digest="a" * 64,
                created_by="human",
            )
        self.session.rollback()
        with self.assertRaises(IntegrityError):
            repo.append_revision(
                self.session,
                workflow_id=workflow.id,
                project_id=100,
                workspace_id=None,
                revision_number=2,
                canonical_definition=b"{}",
                digest="a" * 64,
                published_by="human",
                idempotency_key_digest="d" * 64,
                request_digest="c" * 64,
            )

    def test_snapshot_excludes_new_rows_even_clock_rollback(self):
        first = self.workflow()
        snapshot = repo.maximum_sequence(self.session, "workflows", project_id=100)
        self.now -= timedelta(days=1)
        later = self.workflow()
        rows = repo.list_workflows(
            self.session, project_id=100, snapshot_sequence=snapshot
        )
        self.assertEqual([row.id for row in rows], [first.id])
        self.assertGreater(later.sequence, snapshot)
        self.assertEqual(repo.count_workflows(self.session, project_id=100), 2)
        self.assertEqual(repo.list_workflows(self.session, project_id=200), [])

    def test_policy_cas_and_epochs_never_reset(self):
        policy = repo.save_policy(
            self.session,
            project_id=100,
            expected_version=0,
            settings_json='{"enabled":false}',
            now=self.now,
        )
        self.assertEqual(
            (policy.version, policy.authorization_epoch, policy.restore_epoch),
            (1, 1, 1),
        )
        self.assertIsNone(
            repo.save_policy(
                self.session, project_id=100, expected_version=0, settings_json="{}"
            )
        )
        policy = repo.bump_policy_epoch(
            self.session, project_id=100, expected_version=1, restore=True
        )
        self.assertEqual(
            (policy.version, policy.authorization_epoch, policy.restore_epoch),
            (2, 2, 2),
        )
        self.session.commit()
        for sql in [
            "UPDATE infra_automation_policies SET authorization_epoch=1",
            "DELETE FROM infra_automation_policies",
            "INSERT OR REPLACE INTO infra_automation_policies SELECT * FROM infra_automation_policies",
        ]:
            with self.assertRaises(IntegrityError):
                self.session.execute(text(sql))
            self.session.rollback()

    def test_publication_key_and_revision_number_have_independent_uniqueness(self):
        workflow = self.workflow()
        self.revision(workflow)
        second = self.workflow()
        workflow_id, second_id = workflow.id, second.id
        self.session.commit()
        for identifier, number, key in (
            (workflow_id, 2, "b" * 64),
            (workflow_id, 1, "d" * 64),
            (second_id, 1, "b" * 64),
        ):
            with (
                self.subTest(workflow=identifier, number=number, key=key),
                self.assertRaises(IntegrityError),
            ):
                repo.append_revision(
                    self.session,
                    workflow_id=identifier,
                    project_id=100,
                    workspace_id=100,
                    revision_number=number,
                    canonical_definition=b"{}",
                    digest="a" * 64,
                    published_by="human",
                    idempotency_key_digest=key,
                    request_digest="c" * 64,
                )
            self.session.rollback()
        self.assertEqual(repo.count_revisions(self.session, workflow_id=workflow_id), 1)
        self.assertEqual(
            repo.max_revision_number(self.session, workflow_id=workflow_id), 1
        )

    def test_equal_timestamp_pages_and_scope_filter_precede_limit(self):
        identifiers = {self.workflow().id for _ in range(3)}
        snapshot = repo.workflow_max_sequence(
            self.session, project_id=100, workspace_id=100
        )
        first = repo.list_workflows(
            self.session,
            project_id=100,
            workspace_id=100,
            snapshot_sequence=snapshot,
            limit=1,
        )[0]
        self.workflow()
        remaining = repo.list_workflows(
            self.session,
            project_id=100,
            workspace_id=100,
            snapshot_sequence=snapshot,
            before=(first.created_at, first.id),
            limit=100,
        )
        self.assertEqual({first.id, *(row.id for row in remaining)}, identifiers)
        self.assertEqual(
            [first.id, *(row.id for row in remaining)],
            sorted(identifiers, reverse=True),
        )
        self.assertEqual(
            repo.list_workflows(
                self.session, project_id=100, workspace_id=200, limit=1
            ),
            [],
        )
        with self.assertRaises(ValueError):
            repo.list_workflows(self.session, project_id=100, limit=101)

    def test_repository_does_not_commit_policy_or_audit(self):
        repo.save_policy(
            self.session, project_id=100, expected_version=0, settings_json="{}"
        )
        repo.append_audit(
            self.session,
            project_id=100,
            workspace_id=None,
            actor_principal_id="human",
            actor_type="human",
            actor_role="admin",
            event_type="settings",
            target_id="100",
            reason="Reviewed",
        )
        self.session.rollback()
        self.assertIsNone(repo.get_policy(self.session, project_id=100))
        self.assertEqual(repo.list_audit(self.session, project_id=100), [])
