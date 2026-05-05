"""Tests for lightweight project/workspace service behavior."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.exc import IntegrityError

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.project_service as project_service_module


class ProjectServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "projects.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        database_module.init_db()

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_default_project_exists_for_legacy_records(self) -> None:
        project = project_service_module.ensure_default_project()

        self.assertEqual(
            project.project_key, project_service_module.DEFAULT_PROJECT_KEY
        )
        self.assertTrue(project.is_default)

    def test_create_project_normalizes_key_and_persists_metadata(self) -> None:
        project = project_service_module.create_project(
            project_key="Payments/API Service",
            display_name="Payments API",
            description="Primary production repo",
            repository_url="https://github.com/acme/payments-api",
            default_branch="main",
        )

        self.assertEqual(project.project_key, "payments-api-service")
        self.assertEqual(project.display_name, "Payments API")
        self.assertEqual(project.repository_url, "https://github.com/acme/payments-api")
        self.assertEqual(project.default_branch, "main")

    def test_project_duplicate_integrity_error_uses_explicit_validation_error(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )

        with (
            patch.object(
                project_service_module, "get_project_by_key", return_value=None
            ),
            self.assertRaisesRegex(ValueError, "Project key already exists"),
        ):
            project_service_module.create_project(
                project_key="platform",
                display_name="Platform Duplicate",
            )

        projects = [
            project
            for project in project_service_module.list_projects()
            if project.project_key == "platform"
        ]
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].display_name, "Platform")

    def test_create_workspace_normalizes_key_and_persists_metadata(self) -> None:
        project = project_service_module.create_project(
            project_key="payments-api",
            display_name="Payments API",
        )

        workspace = project_service_module.create_workspace(
            project_key=project.project_key,
            workspace_key="Production / US East",
            display_name="Production US East",
            description="Primary production environment",
            environment="prod",
        )

        self.assertEqual(workspace.project_id, project.id)
        self.assertEqual(workspace.project_key, "payments-api")
        self.assertEqual(workspace.workspace_key, "production-us-east")
        self.assertEqual(workspace.display_name, "Production US East")
        self.assertEqual(workspace.description, "Primary production environment")
        self.assertEqual(workspace.environment, "prod")
        self.assertTrue(workspace.created_at)
        self.assertTrue(workspace.updated_at)

        workspaces = project_service_module.list_workspaces(project_key="payments-api")
        self.assertEqual(
            [item.workspace_key for item in workspaces], ["production-us-east"]
        )

    def test_invalid_workspace_key_does_not_create_partial_record(self) -> None:
        project = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )

        with self.assertRaisesRegex(ValueError, "Workspace key"):
            project_service_module.create_workspace(
                project_key=project.project_key,
                workspace_key=" !!! ",
                display_name="Invalid",
            )

        self.assertEqual(
            project_service_module.list_workspaces(project_key="platform"), []
        )

    def test_duplicate_workspace_key_does_not_create_partial_record(self) -> None:
        project = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        project_service_module.create_workspace(
            project_key=project.project_key,
            workspace_key="prod",
            display_name="Production",
        )

        with self.assertRaisesRegex(ValueError, "Workspace key already exists"):
            project_service_module.create_workspace(
                project_key=project.project_key,
                workspace_key="prod",
                display_name="Production Duplicate",
            )

        workspaces = project_service_module.list_workspaces(project_key="platform")
        self.assertEqual(len(workspaces), 1)
        self.assertEqual(workspaces[0].display_name, "Production")

    def test_workspace_duplicate_integrity_error_uses_explicit_validation_error(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        project_service_module.create_workspace(
            project_key=project.project_key,
            workspace_key="prod",
            display_name="Production",
        )

        with (
            patch.object(
                project_service_module, "get_workspace_by_key", return_value=None
            ),
            self.assertRaisesRegex(ValueError, "Workspace key already exists"),
        ):
            project_service_module.create_workspace(
                project_key=project.project_key,
                workspace_key="prod",
                display_name="Production Duplicate",
            )

        workspaces = project_service_module.list_workspaces(project_key="platform")
        self.assertEqual(len(workspaces), 1)
        self.assertEqual(workspaces[0].display_name, "Production")

    def test_workspace_project_fk_integrity_error_uses_project_not_found(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        integrity_error = IntegrityError(
            "insert",
            {},
            Exception("FOREIGN KEY constraint failed"),
        )

        with (
            patch.object(
                project_service_module, "get_workspace_by_key", return_value=None
            ),
            patch.object(
                project_service_module,
                "create_workspace_record",
                side_effect=integrity_error,
            ),
            self.assertRaises(
                project_service_module.ProjectResolutionError
            ) as exc_info,
        ):
            project_service_module.create_workspace(
                project_key=project.project_key,
                workspace_key="prod",
                display_name="Production",
            )

        self.assertEqual(exc_info.exception.code, "project_not_found")

    def test_non_duplicate_workspace_integrity_error_is_not_rewritten(self) -> None:
        project = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        integrity_error = IntegrityError(
            "insert",
            {},
            Exception("CHECK constraint failed: project_workspaces_environment"),
        )

        with (
            patch.object(
                project_service_module, "get_workspace_by_key", return_value=None
            ),
            patch.object(
                project_service_module,
                "create_workspace_record",
                side_effect=integrity_error,
            ),
            self.assertRaises(IntegrityError),
        ):
            project_service_module.create_workspace(
                project_key=project.project_key,
                workspace_key="prod",
                display_name="Production",
            )

    def test_list_workspaces_without_project_key_uses_default_project_only(
        self,
    ) -> None:
        default_project = project_service_module.ensure_default_project()
        project_service_module.create_workspace(
            project_key=default_project.project_key,
            workspace_key="legacy",
            display_name="Legacy",
        )
        other_project = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        project_service_module.create_workspace(
            project_key=other_project.project_key,
            workspace_key="prod",
            display_name="Production",
        )

        workspaces = project_service_module.list_workspaces()

        self.assertEqual(
            [workspace.workspace_key for workspace in workspaces], ["legacy"]
        )
        self.assertEqual(workspaces[0].project_key, default_project.project_key)

    def test_invalid_workspace_list_project_key_does_not_create_default_project(
        self,
    ) -> None:
        with database_module.engine.begin() as connection:
            connection.exec_driver_sql(
                "DELETE FROM projects WHERE project_key = ?",
                ("unassigned",),
            )

        with self.assertRaisesRegex(ValueError, "Project key"):
            project_service_module.list_workspaces(project_key=" !!! ")

        with database_module.SessionLocal() as session:
            self.assertIsNone(project_service_module.get_default_project(session))

    def test_blank_workspace_list_project_key_does_not_create_default_project(
        self,
    ) -> None:
        with database_module.engine.begin() as connection:
            connection.exec_driver_sql(
                "DELETE FROM projects WHERE project_key = ?",
                ("unassigned",),
            )

        with self.assertRaisesRegex(ValueError, "Project key"):
            project_service_module.list_workspaces(project_key="")

        with database_module.SessionLocal() as session:
            self.assertIsNone(project_service_module.get_default_project(session))

    def test_resolve_project_reference_derives_stable_repository_key(self) -> None:
        project = project_service_module.resolve_project_reference(
            repository_name="AcmeCorp/Payments-API",
            allow_create=True,
        )

        self.assertEqual(project.project_key, "acmecorp-payments-api")
        self.assertEqual(project.display_name, "Payments API")

    def test_active_project_setting_round_trips(self) -> None:
        created = project_service_module.create_project(
            project_key="network-core",
            display_name="Network Core",
        )

        project_service_module.set_active_project(created.id)
        active = project_service_module.get_active_project()

        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active.id, created.id)
        self.assertEqual(active.project_key, "network-core")

    def test_unknown_explicit_project_reference_raises(self) -> None:
        with self.assertRaises(
            project_service_module.ProjectResolutionError
        ) as exc_info:
            project_service_module.resolve_project_reference(project_key="missing")

        self.assertEqual(exc_info.exception.code, "project_not_found")

    def test_conflicting_project_reference_raises(self) -> None:
        first = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        second = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )

        with self.assertRaises(
            project_service_module.ProjectResolutionError
        ) as exc_info:
            project_service_module.resolve_project_reference(
                project_id=first.id,
                project_key=second.project_key,
            )

        self.assertEqual(exc_info.exception.code, "conflicting_project_reference")

    def test_partially_invalid_dual_project_reference_raises(self) -> None:
        created = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

        with self.assertRaises(
            project_service_module.ProjectResolutionError
        ) as exc_info:
            project_service_module.resolve_project_reference(
                project_id=999,
                project_key=created.project_key,
            )

        self.assertEqual(exc_info.exception.code, "project_not_found")

    def test_allow_create_creates_explicit_project_key(self) -> None:
        project = project_service_module.resolve_project_reference(
            project_key="platform-core",
            allow_create=True,
        )

        self.assertEqual(project.project_key, "platform-core")
        self.assertEqual(project.display_name, "Platform Core")

    def test_active_project_selection_flag_tracks_explicit_choice(self) -> None:
        self.assertFalse(project_service_module.has_active_project_selection())

        created = project_service_module.create_project(
            project_key="core",
            display_name="Core",
        )
        project_service_module.set_active_project(created.id)

        self.assertTrue(project_service_module.has_active_project_selection())
