"""Transactional membership persistence and constrained scope contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import reload
import os
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

import config
import models.database as database
from models.repositories import project_memberships as repository
from models.tables import (
    IdentityAccount,
    Project,
    ProjectAuthorizationAudit,
    ProjectWorkspace,
)


class ProjectMembershipRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ, {"DATABASE_URL": f"sqlite:///{self.temp.name}/test.db"}
        )
        self.env.start()
        reload(config)
        reload(database)
        database.init_db()
        self.now = datetime.now(UTC)
        with database.SessionLocal.begin() as session:
            session.add(
                IdentityAccount(
                    id="principal",
                    username="human",
                    password_verifier="synthetic",
                    created_at=self.now,
                )
            )
            session.add_all(
                [
                    Project(id=100, project_key="a", display_name="A"),
                    Project(id=200, project_key="b", display_name="B"),
                ]
            )
            session.flush()
            session.add_all(
                [
                    ProjectWorkspace(
                        id=100, project_id=100, workspace_key="a", display_name="A"
                    ),
                    ProjectWorkspace(
                        id=200, project_id=200, workspace_key="b", display_name="B"
                    ),
                ]
            )

    def tearDown(self):
        database.engine.dispose()
        self.env.stop()
        reload(config)
        reload(database)
        self.temp.cleanup()

    def put(self, session, **kwargs):
        return repository.upsert_membership(
            session,
            principal_id="principal",
            project_id=100,
            role=kwargs.pop("role", "reviewer"),
            **kwargs,
        )

    def test_upsert_revoke_restore_increments_version_without_deletion(self):
        with database.SessionLocal.begin() as session:
            member = self.put(session)
            member_id = member.id
            self.assertEqual(member.authorization_version, 1)
            self.assertTrue(member.enabled)
            self.assertIsNone(member.workspace_id)
            self.put(session, role="maintainer", workspace_id=100)
            self.assertEqual(member.authorization_version, 2)
            self.assertEqual(member.workspace_id, 100)
            repository.revoke_membership(
                session, principal_id="principal", project_id=100
            )
            self.assertEqual(member.authorization_version, 3)
            self.assertFalse(member.enabled)
            self.put(session, role="admin")
            self.assertEqual(member.authorization_version, 4)
            self.assertTrue(member.enabled)
            self.assertEqual(member.id, member_id)
            self.assertEqual(
                len(repository.list_memberships(session, project_id=100)), 1
            )

    def test_caller_rollback_reverts_membership_and_audit_together(self):
        with database.SessionLocal() as session:
            member = self.put(session)
            repository.append_audit(
                session,
                actor_principal_id="principal",
                target_principal_id="principal",
                project_id=100,
                action="membership.assign",
                object_id=member.id,
                after={"role": member.role},
            )
            session.rollback()
        with database.SessionLocal() as session:
            self.assertIsNone(
                repository.get_membership(
                    session, principal_id="principal", project_id=100
                )
            )
            self.assertEqual(
                session.scalars(select(ProjectAuthorizationAudit)).all(), []
            )

    def test_audit_retains_only_supplied_metadata_and_opaque_id(self):
        with database.SessionLocal.begin() as session:
            record = repository.append_audit(
                session,
                actor_principal_id="principal",
                project_id=100,
                workspace_id=100,
                action="decision.acknowledge",
                before={"version": 1},
                after={"version": 2},
            )
            self.assertGreaterEqual(len(record.id), 32)
            self.assertEqual(record.before_json, '{"version":1}')
            self.assertEqual(record.after_json, '{"version":2}')

    def test_unknown_role_rejected_by_repository_and_database(self):
        with database.SessionLocal() as session:
            with self.assertRaises(ValueError):
                self.put(session, role="owner")
        with database.SessionLocal.begin() as session:
            self.put(session)
        for field, value in (("role", "owner"), ("authorization_version", 0)):
            with self.subTest(field=field), database.SessionLocal() as session:
                with self.assertRaises(IntegrityError):
                    session.execute(
                        text(f"UPDATE project_memberships SET {field}=:value"),
                        {"value": value},
                    )

    def test_cross_project_workspace_and_missing_references_fail_closed(self):
        for kwargs in ({"workspace_id": 200}, {"workspace_id": 999}):
            with self.subTest(kwargs=kwargs), database.SessionLocal() as session:
                with self.assertRaises(IntegrityError):
                    self.put(session, **kwargs)
        for principal_id, project_id in (("missing", 100), ("principal", 999)):
            with (
                self.subTest(principal=principal_id, project=project_id),
                database.SessionLocal() as session,
            ):
                with self.assertRaises(IntegrityError):
                    repository.upsert_membership(
                        session,
                        principal_id=principal_id,
                        project_id=project_id,
                        role="admin",
                    )

    def test_live_query_refreshes_preloaded_membership(self):
        with database.SessionLocal.begin() as session:
            member = self.put(session)
            session.execute(
                text(
                    "UPDATE project_memberships SET enabled=0, authorization_version=2 WHERE id=:id"
                ),
                {"id": member.id},
            )
            live = repository.get_membership(
                session, principal_id="principal", project_id=100
            )
            self.assertIs(live, member)
            self.assertFalse(live.enabled)
            self.assertEqual(live.authorization_version, 2)

    def test_unique_principal_project_and_restricted_workspace_cannot_be_deleted(self):
        with database.SessionLocal.begin() as session:
            self.put(session, workspace_id=100)
        with database.SessionLocal() as session:
            with self.assertRaises(IntegrityError):
                session.execute(
                    text(
                        "INSERT INTO project_memberships SELECT 'duplicate',principal_id,project_id,workspace_id,role,enabled,authorization_version,created_at,updated_at FROM project_memberships"
                    )
                )
        with database.SessionLocal() as session:
            with self.assertRaises(IntegrityError):
                session.execute(text("DELETE FROM project_workspaces WHERE id=100"))

    def test_protection_defaults_preserve_legacy_projects(self):
        with database.SessionLocal() as session:
            self.assertFalse(session.get(Project, 100).authorization_required)
