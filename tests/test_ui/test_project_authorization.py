"""Tests for lightweight UI project authorization helpers."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path
from unittest.mock import patch

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.project_service as project_service_module
import ui.project_authorization as ui_project_authorization_module


class UIProjectAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ui-project-auth.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        reload(ui_project_authorization_module)
        database_module.init_db()

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("DEPLOYWHISPER_PROJECT_ROLE", None)
        os.environ.pop("DEPLOYWHISPER_PROJECT_KEYS", None)
        self.tempdir.cleanup()

    def test_list_authorized_ui_projects_filters_to_actor_scope(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        os.environ["DEPLOYWHISPER_PROJECT_ROLE"] = "read-only"
        os.environ["DEPLOYWHISPER_PROJECT_KEYS"] = "payments"

        projects = ui_project_authorization_module.list_authorized_ui_projects()

        self.assertEqual([project.project_key for project in projects], ["payments"])

    def test_load_authorized_ui_projects_returns_error_for_missing_scope(self) -> None:
        os.environ["DEPLOYWHISPER_PROJECT_ROLE"] = "read-only"

        projects, error = ui_project_authorization_module.load_authorized_ui_projects()

        self.assertEqual(projects, [])
        self.assertEqual(error, "Caller role requires an explicit project scope.")

    def test_clear_unauthorized_active_project_removes_stale_selection(self) -> None:
        forbidden = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        project_service_module.set_active_project(forbidden.id)

        cleared = ui_project_authorization_module.clear_unauthorized_active_project(
            forbidden,
            projects=[],
        )

        self.assertTrue(cleared)
        self.assertFalse(project_service_module.has_active_project_selection())

    def test_clear_unauthorized_active_project_preserves_selection_on_auth_error(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        project_service_module.set_active_project(project.id)

        cleared = ui_project_authorization_module.clear_unauthorized_active_project(
            project,
            projects=[],
            authorization_error="Caller role requires an explicit project scope.",
        )

        self.assertFalse(cleared)
        self.assertTrue(project_service_module.has_active_project_selection())

    def test_resolve_active_selection_hides_project_on_auth_error_without_clearing(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        project_service_module.set_active_project(project.id)

        has_selection, active_project = (
            ui_project_authorization_module.resolve_authorized_active_project_selection(
                has_saved_selection=True,
                active_project=project,
                projects=[],
                authorization_error="Caller role requires an explicit project scope.",
            )
        )

        self.assertFalse(has_selection)
        self.assertIsNone(active_project)
        self.assertTrue(project_service_module.has_active_project_selection())

    def test_resolve_authorized_ui_active_project_uses_auth_error_safe_selection(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        project_service_module.set_active_project(project.id)
        os.environ["DEPLOYWHISPER_PROJECT_ROLE"] = "read-only"

        has_selection, active_project, error = (
            ui_project_authorization_module.resolve_authorized_ui_active_project()
        )

        self.assertFalse(has_selection)
        self.assertIsNone(active_project)
        self.assertEqual(error, "Caller role requires an explicit project scope.")
        self.assertTrue(project_service_module.has_active_project_selection())

    def test_resolve_active_selection_keeps_visible_default_without_saved_selection(
        self,
    ) -> None:
        project = project_service_module.get_active_project()

        has_selection, active_project = (
            ui_project_authorization_module.resolve_authorized_active_project_selection(
                has_saved_selection=False,
                active_project=project,
                projects=[project],
            )
        )

        self.assertFalse(has_selection)
        self.assertEqual(active_project.project_key, "unassigned")

    def test_set_authorized_ui_project_rejects_project_outside_visible_list(
        self,
    ) -> None:
        allowed = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        forbidden = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )

        with self.assertRaisesRegex(PermissionError, "not authorized"):
            ui_project_authorization_module.set_authorized_ui_project(
                forbidden.id,
                [allowed],
            )

        self.assertFalse(project_service_module.has_active_project_selection())

    def test_set_authorized_ui_project_handles_stale_selected_project(self) -> None:
        allowed = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        project_service_module.set_active_project(allowed.id)

        with (
            patch.object(
                ui_project_authorization_module,
                "set_active_project",
                side_effect=ValueError("Project workspace not found."),
            ),
            self.assertRaisesRegex(PermissionError, "no longer available"),
        ):
            ui_project_authorization_module.set_authorized_ui_project(
                allowed.id,
                [allowed],
            )

        self.assertFalse(project_service_module.has_active_project_selection())

    def test_create_authorized_ui_project_denies_role_without_manage_capability(
        self,
    ) -> None:
        os.environ["DEPLOYWHISPER_PROJECT_ROLE"] = "read-only"
        os.environ["DEPLOYWHISPER_PROJECT_KEYS"] = "payments"

        with self.assertRaises(project_service_module.ProjectAuthorizationError):
            ui_project_authorization_module.create_authorized_ui_project(
                project_key="payments",
                display_name="Payments",
            )


if __name__ == "__main__":
    unittest.main()
