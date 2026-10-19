"""Synthetic isolated database/identity fixture for workflow lifecycle tests."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import config
from models.database import Base
from models.repositories.project_memberships import upsert_membership
from models.tables import IdentityAccount, IdentitySession, Project, ProjectWorkspace
from services.identity_service import IdentityService
from services import project_service as auth


class LifecycleCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine(
            f"sqlite:///{self.temp.name}/lifecycle.db", connect_args={"timeout": 10}
        )

        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        self.now = datetime.now(timezone.utc)
        self.project_id = self.workspace_id = 100
        self.origin = "https://lifecycle.invalid"
        self.identity = IdentityService(
            self.factory,
            now=lambda: self.now,
            security_profile="https",
            trusted_origin=self.origin,
        )
        for target, value in (
            (
                "config.settings",
                replace(
                    config.settings,
                    identity_profile="https",
                    identity_origin=self.origin,
                    authorization_profile="legacy-evaluation",
                ),
            ),
            ("services.project_service.SessionLocal", self.factory),
        ):
            context = patch(target, value)
            context.start()
            self.addCleanup(context.stop)
        with self.factory.begin() as db:
            db.add_all(
                [
                    Project(
                        id=100,
                        project_key="lifecycle-one",
                        display_name="One",
                        authorization_required=True,
                    ),
                    Project(
                        id=200,
                        project_key="lifecycle-two",
                        display_name="Two",
                        authorization_required=True,
                    ),
                ]
            )
            db.flush()
            db.add_all(
                [
                    ProjectWorkspace(
                        id=100, project_id=100, workspace_key="one", display_name="One"
                    ),
                    ProjectWorkspace(
                        id=101,
                        project_id=100,
                        workspace_key="other",
                        display_name="Other",
                    ),
                    ProjectWorkspace(
                        id=200, project_id=200, workspace_key="two", display_name="Two"
                    ),
                ]
            )
        self.tokens = {}
        self.principal("human-a", is_admin=True)
        self.member("admin")

    def principal(
        self, name, *, is_admin=False, principal_type="human", audience="human"
    ):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.factory.begin() as db:
            db.add(
                IdentityAccount(
                    id=name,
                    username=name,
                    principal_type=principal_type,
                    password_verifier="synthetic-unused",
                    is_admin=is_admin,
                    enabled=True,
                    authentication_version=1,
                    created_at=self.now,
                )
            )
            db.flush()
            db.add(
                IdentitySession(
                    id=secrets.token_hex(16),
                    principal_id=name,
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                    csrf_hash=hashlib.sha256(csrf.encode()).hexdigest(),
                    audience=audience,
                    security_profile="https",
                    trusted_origin=self.origin,
                    authentication_version=1,
                    created_at=self.now,
                    last_seen_at=self.now,
                    expires_at=self.now + timedelta(hours=1),
                )
            )
        self.tokens[name] = (token, csrf)
        return token, csrf

    def member(self, role="admin", *, principal="human-a", project=100, workspace=None):
        with self.factory.begin() as db:
            return upsert_membership(
                db,
                principal_id=principal,
                project_id=project,
                workspace_id=workspace,
                role=role,
            )

    @contextmanager
    def credentials(self, principal="human-a", *, mutation=True, token=None, csrf=None):
        pair = self.tokens[principal]
        with auth.credential_context(
            self.identity,
            token if token is not None else pair[0],
            csrf_token=csrf if csrf is not None else pair[1],
            mutation=mutation,
        ):
            yield

    def definition(self, *, project_id=100, workspace_id=100):
        path = (
            Path(__file__).resolve().parents[1]
            / "fixtures/infra_automation/workflow_v2/valid.json"
        )
        value = json.loads(path.read_text())[0]["definition"]
        value["project_id"] = str(project_id)
        value["workspace_id"] = str(workspace_id) if workspace_id is not None else None
        return value
