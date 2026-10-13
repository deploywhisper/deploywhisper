"""Request credentials must reach service-owned authorization transactions."""

from __future__ import annotations

from dataclasses import replace
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
from api.errors import ApiRoute
from api.routes.projects import router as projects_router
from models.database import Base
from models.tables import Project
from services.identity_service import IdentityService
from services.project_service import (
    authorized_session,
    bootstrap_project_membership,
    guard_project,
)


class ProjectAuthorizationContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine(f"sqlite:///{Path(self.temp.name) / 'scope.db'}")
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        factory_patch = patch("services.project_service.SessionLocal", self.factory)
        factory_patch.start()
        self.addCleanup(factory_patch.stop)
        self.origin = "https://permissions.invalid"
        self.service = IdentityService(
            self.factory, security_profile="https", trusted_origin=self.origin
        )
        self.service.bootstrap(
            self.service.issue_setup_credential().token.get_secret_value(),
            "operator",
            "public identity test input",
        )
        with self.factory.begin() as db:
            project = Project(project_key="private-scope", display_name="Private scope")
            db.add(project)
            db.flush()
            self.project_id = project.id
        app = FastAPI()
        router = APIRouter(route_class=ApiRoute)

        @router.post("/bootstrap")
        def bootstrap():
            return bootstrap_project_membership(self.project_id).model_dump()

        @router.get("/protected")
        def protected():
            with authorized_session() as db:
                scope = guard_project(db, self.project_id, capability="project.read")
                return {"principal_id": scope.principal.principal_id}

        @router.post("/protected")
        def mutate():
            with authorized_session() as db:
                guard_project(
                    db, self.project_id, capability="project.manage", mutation=True
                )
                return {"allowed": True}

        app.include_router(router)
        app.include_router(projects_router)
        self.client = TestClient(app, base_url=self.origin)
        self.addCleanup(self.client.close)
        service_patch = patch(
            "api.dependencies.identity_service", return_value=self.service
        )
        service_patch.start()
        self.addCleanup(service_patch.stop)
        settings_patch = patch.object(
            config,
            "settings",
            replace(
                config.settings,
                identity_profile="https",
                identity_origin=self.origin,
                authorization_profile="legacy-evaluation",
            ),
        )
        settings_patch.start()
        self.addCleanup(settings_patch.stop)

    def headers(self):
        issued = self.service.login("operator", "public identity test input")
        return {
            "Origin": self.origin,
            "Cookie": f"__Host-dw-session={issued.token.get_secret_value()}",
            "X-CSRF-Token": issued.csrf_token.get_secret_value(),
        }

    def test_sync_routes_receive_credentials_and_live_revocation(self):
        headers = self.headers()
        response = self.client.post("/bootstrap", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            self.client.get("/protected", headers=headers).status_code, 403
        )
        headers = self.headers()
        self.assertEqual(
            self.client.get("/protected", headers=headers).status_code, 200
        )
        self.assertEqual(
            self.client.post("/protected", headers=headers).status_code, 200
        )
        headers.pop("X-CSRF-Token")
        denied = self.client.post("/protected", headers=headers)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["error"]["message"], "Operation unavailable.")
        self.assertIn("correlation_id", denied.json()["error"]["details"])
        self.assertNotIn("private-scope", denied.text)

    def test_context_is_cleared_between_requests(self):
        self.assertEqual(
            self.client.post("/bootstrap", headers=self.headers()).status_code, 200
        )
        self.assertEqual(
            self.client.get("/protected", headers=self.headers()).status_code, 200
        )
        self.assertEqual(self.client.get("/protected").status_code, 403)

    def test_membership_routes_require_explicit_bootstrap_and_live_scoped_admin(self):
        path = "/api/v1/projects/private-scope/memberships"
        self.assertEqual(self.client.post(path + "/bootstrap").status_code, 403)
        first = self.client.post(path + "/bootstrap", headers=self.headers())
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["data"]["role"], "admin")
        headers = self.headers()
        token = headers["Cookie"].split("=", 1)[1]
        reader = self.service.create_account(
            token,
            "reader",
            "public second identity input",
            csrf_token=headers["X-CSRF-Token"],
        )
        assigned = self.client.put(
            path + "/" + reader.principal_id, headers=headers, json={"role": "reviewer"}
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)
        self.assertEqual(assigned.json()["data"]["authorization_version"], 1)
        self.assertEqual(len(self.client.get(path, headers=headers).json()["data"]), 2)
        issued = self.service.login("reader", "public second identity input")
        reader_headers = {
            "Origin": self.origin,
            "Cookie": f"__Host-dw-session={issued.token.get_secret_value()}",
            "X-CSRF-Token": issued.csrf_token.get_secret_value(),
            "X-DeployWhisper-Project-Role": "admin",
        }
        self.assertEqual(self.client.get(path, headers=reader_headers).status_code, 403)
        self.assertEqual(
            self.client.post(
                "/api/v1/projects/private-scope/workspaces",
                headers=reader_headers,
                json={"workspace_key": "forged", "display_name": "Forged"},
            ).status_code,
            403,
        )
        revoked = self.client.delete(path + "/" + reader.principal_id, headers=headers)
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertFalse(revoked.json()["data"]["enabled"])
        self.assertEqual(revoked.json()["data"]["authorization_version"], 2)

    def test_protected_projects_and_workspace_names_do_not_leak(self):
        self.assertEqual(
            self.client.post("/bootstrap", headers=self.headers()).status_code, 200
        )
        listed = self.client.get("/api/v1/projects")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertNotIn("private-scope", listed.text)
        response = self.client.get(
            "/api/v1/projects/private-scope/workspaces",
            headers={"X-DeployWhisper-Project-Role": "admin"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("private-scope", response.text)
