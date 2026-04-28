"""Tests for lightweight project/workspace service behavior."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path

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
