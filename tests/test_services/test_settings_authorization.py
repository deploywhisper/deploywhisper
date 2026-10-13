"""Settings boundaries require live project and global administration authority."""

import unittest
from unittest.mock import patch

from models.tables import AppSetting, Project
from services import project_service as auth
from services import settings_service as settings
from tests.test_services import test_project_authorization as fixtures


class SettingsAuthorizationTests(unittest.TestCase):
    setUp = fixtures.ProjectAuthorizationTests.setUp
    tearDown = fixtures.ProjectAuthorizationTests.tearDown
    principal = fixtures.ProjectAuthorizationTests.principal
    member = fixtures.ProjectAuthorizationTests.member
    context = fixtures.ProjectAuthorizationTests.context

    def test_project_policy_denies_anonymous_before_validation(self):
        with patch.object(settings, "SessionLocal", self.factory):
            for operation in (
                lambda: settings.get_policy_adapter_settings(project_key="project-1"),
                lambda: settings.save_policy_adapter_settings(
                    project_key="project-1", integration="invalid / label"
                ),
                lambda: settings.delete_policy_adapter_settings(
                    project_key="project-1"
                ),
            ):
                with (
                    self.subTest(operation=operation),
                    self.assertRaises(auth.TrustedAuthorizationError),
                ):
                    operation()

    def test_policy_read_write_role_and_csrf(self):
        with patch.object(settings, "SessionLocal", self.factory):
            self.member("read-only")
            with self.context():
                self.assertEqual(
                    settings.get_policy_adapter_settings(
                        project_key="project-1"
                    ).source,
                    "built-in",
                )
                with self.assertRaises(auth.TrustedAuthorizationError):
                    settings.save_policy_adapter_settings(project_key="project-1")
            self.member("admin")
            with self.context():
                with self.assertRaises(auth.TrustedAuthorizationError):
                    settings.save_policy_adapter_settings(project_key="project-1")
            with self.context(mutation=True):
                self.assertEqual(
                    settings.save_policy_adapter_settings(
                        project_key="project-1"
                    ).source,
                    "project",
                )
                self.assertEqual(
                    settings.delete_policy_adapter_settings(
                        project_key="project-1"
                    ).source,
                    "built-in",
                )

    def test_global_configuration_requires_membership_in_every_protected_project(self):
        with patch.object(settings, "SessionLocal", self.factory):
            self.member()
            with self.context(mutation=True):
                with self.assertRaises(auth.TrustedAuthorizationError):
                    settings.save_topology_drift_check_interval_hours(6)
            self.member(project=2)
            with self.context(mutation=True):
                self.assertEqual(
                    settings.save_topology_drift_check_interval_hours(6), 6
                )

    def test_provider_admin_read_denied_but_runtime_read_works(self):
        self.member("read-only")
        with patch.object(settings, "SessionLocal", self.factory), self.context():
            with self.assertRaises(auth.TrustedAuthorizationError):
                settings.get_provider_settings()
            self.assertIn("provider", settings.resolve_provider_runtime())
            self.assertIsNotNone(settings.get_provider_health_snapshot())

    def test_legacy_settings_without_protected_projects_remain_available(self):
        with self.factory.begin() as db:
            for project in db.query(Project):
                project.authorization_required = False
        with patch.object(settings, "SessionLocal", self.factory):
            self.assertEqual(settings.save_topology_drift_check_interval_hours(6), 6)
            self.assertEqual(
                settings.save_policy_adapter_settings(
                    project_key="legacy-fixture"
                ).source,
                "project",
            )

    def test_denied_write_never_persists(self):
        with patch.object(settings, "SessionLocal", self.factory):
            with self.assertRaises(auth.TrustedAuthorizationError):
                settings.save_topology_drift_check_interval_hours(6)
        with self.factory() as db:
            self.assertIsNone(db.get(AppSetting, "topology_drift_check_interval_hours"))

    def test_admin_can_read_without_mutation_credentials(self):
        self.member()
        self.member(project=2)
        with patch.object(settings, "SessionLocal", self.factory), self.context():
            self.assertIsNotNone(settings.get_provider_settings())

    def test_workspace_admin_cannot_change_projectwide_or_global_settings(self):
        self.member(workspace=1)
        self.member(project=2)
        with (
            patch.object(settings, "SessionLocal", self.factory),
            self.context(mutation=True),
        ):
            for operation in (
                lambda: settings.save_policy_adapter_settings(project_key="project-1"),
                lambda: settings.save_topology_drift_check_interval_hours(6),
            ):
                with (
                    self.subTest(operation=operation),
                    self.assertRaises(auth.TrustedAuthorizationError),
                ):
                    operation()

    def test_global_admin_flag_does_not_replace_memberships_or_vice_versa(self):
        self.member()
        self.member(project=2)
        from models.tables import IdentityAccount

        with self.factory.begin() as db:
            db.get(IdentityAccount, "human-a").is_admin = False
        with (
            patch.object(settings, "SessionLocal", self.factory),
            self.context(mutation=True),
        ):
            with self.assertRaises(auth.TrustedAuthorizationError):
                settings.save_topology_drift_check_interval_hours(6)

    def test_global_guard_denies_unknown_namespace_when_protected_projects_exist(self):
        with patch.object(settings, "SessionLocal", self.factory):
            with self.assertRaises(auth.TrustedAuthorizationError):
                settings.save_policy_adapter_settings(project_key="invented")

    def test_strict_profile_denies_unowned_legacy_namespace(self):
        import config

        with (
            patch.object(settings, "SessionLocal", self.factory),
            patch.object(config.settings, "authorization_profile", "verified"),
        ):
            with self.assertRaises(auth.TrustedAuthorizationError):
                settings.get_policy_adapter_settings(project_key="project-3")

    def test_settings_write_shares_operation_transaction_and_rolls_back(self):
        self.member()
        with (
            patch.object(settings, "SessionLocal", self.factory),
            self.context(mutation=True),
        ):
            with (
                self.assertRaises(RuntimeError),
                auth.authorized_session(self.factory) as db,
            ):
                settings.save_policy_adapter_settings(project_key="project-1")
                self.assertIsNotNone(
                    db.get(AppSetting, "policy_adapter_defaults::project-1::project")
                )
                raise RuntimeError("rollback whole operation")
        with self.factory() as db:
            self.assertIsNone(
                db.get(AppSetting, "policy_adapter_defaults::project-1::project")
            )

    def test_identity_context_ignores_spoofed_legacy_headers(self):
        from api.routes.settings import _authorization_context

        with self.context():
            self.assertEqual(
                _authorization_context("admin", "project-2"),
                {"role": None, "allowed_project_keys": None},
            )

    def test_custom_skill_write_denied_before_validation_and_filesystem_changes(self):
        from llm.skill_context import save_custom_skill
        from pathlib import Path

        destination = Path(self.temp.name) / "custom"
        with (
            patch.object(auth, "SessionLocal", self.factory),
            patch("llm.skill_context.CUSTOM_DIR", destination),
        ):
            with self.assertRaises(auth.TrustedAuthorizationError):
                save_custom_skill("wrong.txt", "content")
        self.assertFalse(destination.exists())

    def test_workspace_reader_can_resolve_inherited_policy_only_for_own_workspace(self):
        self.member("read-only", workspace=1)
        with patch.object(settings, "SessionLocal", self.factory), self.context():
            self.assertEqual(
                settings.get_policy_adapter_settings(
                    project_key="project-1", workspace_id=1
                ).source,
                "built-in",
            )
            for project, workspace in (
                ("project-1", 2),
                ("project-1", None),
                ("project-2", 1),
            ):
                with (
                    self.subTest(project=project, workspace=workspace),
                    self.assertRaises(auth.TrustedAuthorizationError),
                ):
                    settings.get_policy_adapter_settings(
                        project_key=project, workspace_id=workspace
                    )

    def test_disabled_live_membership_denies_settings_after_context_was_bound(self):
        self.member()
        with (
            patch.object(settings, "SessionLocal", self.factory),
            self.context(mutation=True),
        ):
            with self.factory.begin() as db:
                auth.membership_repository.revoke_membership(
                    db, principal_id="human-a", project_id=1
                )
            with self.assertRaises(auth.TrustedAuthorizationError):
                settings.save_policy_adapter_settings(project_key="project-1")

    def test_api_protected_settings_reject_forged_roles_and_missing_csrf(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.settings import settings_router
        import config

        app = FastAPI()
        app.include_router(settings_router)
        origin = "https://identity.invalid"
        self.member("read-only")
        with (
            patch.object(auth, "SessionLocal", self.factory),
            patch.object(settings, "SessionLocal", self.factory),
            patch("api.dependencies.identity_service", return_value=self.service),
            patch.object(config.settings, "identity_profile", "https"),
            patch.object(config.settings, "identity_origin", origin),
            TestClient(app, base_url=origin) as client,
        ):
            forged = {
                "X-DeployWhisper-Project-Role": "admin",
                "X-DeployWhisper-Project-Keys": "project-1",
            }
            response = client.get(
                "/api/v1/settings/policy-adapter?project_key=project-1", headers=forged
            )
            self.assertEqual(response.status_code, 403, response.text)
            self.assertIn("correlation_id", response.json()["error"]["details"])
            headers = {
                **forged,
                "Cookie": f"__Host-dw-session={self.token}",
                "Origin": origin,
            }
            response = client.get(
                "/api/v1/settings/policy-adapter?project_key=project-1", headers=headers
            )
            self.assertEqual(response.status_code, 200, response.text)
            response = client.put(
                "/api/v1/settings/policy-adapter",
                headers=headers,
                json={"project_key": "project-1"},
            )
            self.assertEqual(response.status_code, 403, response.text)
            self.assertIn("correlation_id", response.json()["error"]["details"])
            for path in (
                "/api/v1/settings/custom-skills",
                "/api/v1/settings?project_key=project-1",
            ):
                self.assertEqual(client.get(path, headers=headers).status_code, 403)

    def test_skill_installer_denies_before_network_or_private_validation(self):
        from services import skill_installer_service as installer

        from pathlib import Path

        with (
            patch.object(auth, "SessionLocal", self.factory),
            patch.object(installer, "CUSTOM_DIR", Path(self.temp.name) / "custom"),
            patch.object(installer, "fetch_configured_skill_content") as fetch,
        ):
            for operation in (installer.install_skill, installer.update_skill):
                for skill in ("private-skill", "../invalid"):
                    with (
                        self.subTest(operation=operation, skill=skill),
                        self.assertRaises(auth.TrustedAuthorizationError),
                    ):
                        operation(skill)
            fetch.assert_not_called()

    def test_skill_remove_and_metadata_read_do_not_bypass_global_authority(self):
        from pathlib import Path
        from services import skill_installer_service as installer
        from llm import skill_context

        custom = Path(self.temp.name) / "custom"
        custom.mkdir()
        destination = custom / "private-skill.md"
        destination.write_text("# Private guidance", encoding="utf-8")
        with (
            patch.object(auth, "SessionLocal", self.factory),
            patch.object(installer, "CUSTOM_DIR", custom),
            patch.object(skill_context, "CUSTOM_DIR", custom),
        ):
            for operation in (
                lambda: installer.remove_skill("private-skill"),
                installer.list_installed_skills,
                skill_context.get_custom_skill_statuses,
            ):
                with (
                    self.subTest(operation=operation),
                    self.assertRaises(auth.TrustedAuthorizationError),
                ):
                    operation()
        self.assertEqual(destination.read_text(encoding="utf-8"), "# Private guidance")

    def test_skill_install_reauthorizes_after_download_and_preserves_files_on_revocation(
        self,
    ):
        from pathlib import Path
        from services import skill_installer_service as installer
        from tests.test_services.test_skill_installer_service import (
            SkillInstallerServiceTests,
        )

        self.member()
        self.member(project=2)
        content = SkillInstallerServiceTests._local_skill_content()
        source = installer._validate_source_content(
            "helm", content, source_url="https://registry.invalid/helm"
        )
        custom = Path(self.temp.name) / "custom"

        def revoke_after_download(_):
            with self.factory.begin() as db:
                auth.membership_repository.revoke_membership(
                    db, principal_id="human-a", project_id=1
                )
            return source

        with (
            patch.object(auth, "SessionLocal", self.factory),
            patch.object(installer, "CUSTOM_DIR", custom),
            patch.object(
                installer,
                "fetch_configured_skill_content",
                side_effect=revoke_after_download,
            ),
            self.context(mutation=True),
        ):
            with self.assertRaises(auth.TrustedAuthorizationError):
                installer.install_skill("helm")
        self.assertFalse(custom.exists())

    def test_global_admin_can_install_list_update_and_remove_custom_skill(self):
        from pathlib import Path
        from services import skill_installer_service as installer
        from llm import skill_context
        from tests.test_services.test_skill_installer_service import (
            SkillInstallerServiceTests,
        )

        self.member()
        self.member(project=2)
        content = SkillInstallerServiceTests._local_skill_content()
        source = installer._validate_source_content(
            "helm", content, source_url="https://registry.invalid/helm"
        )
        custom = Path(self.temp.name) / "custom"
        with (
            patch.object(auth, "SessionLocal", self.factory),
            patch.object(installer, "CUSTOM_DIR", custom),
            patch.object(skill_context, "CUSTOM_DIR", custom),
            patch.object(
                installer, "fetch_configured_skill_content", return_value=source
            ),
        ):
            with self.context(mutation=True):
                self.assertEqual(installer.install_skill("helm").action, "installed")
                self.assertEqual(installer.update_skill("helm").action, "unchanged")
            with self.context():
                self.assertEqual(
                    [entry.id for entry in installer.list_installed_skills()], ["helm"]
                )
                self.assertEqual(
                    [entry.name for entry in skill_context.get_custom_skill_statuses()],
                    ["helm"],
                )
            with self.context(mutation=True):
                self.assertEqual(installer.remove_skill("helm").action, "removed")
        self.assertFalse((custom / "helm.md").exists())

    def test_cli_skill_administration_denials_are_generic_without_private_output(self):
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO
        from pathlib import Path
        from cli import analyze
        from services import skill_installer_service as installer
        from llm import skill_context

        custom = Path(self.temp.name) / "custom"
        custom.mkdir()
        (custom / "private-skill.md").write_text("# Private guidance", encoding="utf-8")
        with (
            patch.object(auth, "SessionLocal", self.factory),
            patch.object(installer, "CUSTOM_DIR", custom),
            patch.object(skill_context, "CUSTOM_DIR", custom),
            patch.object(installer, "fetch_configured_skill_content") as fetch,
        ):
            for operation in (
                analyze._run_skills,
                analyze._run_skill_list,
                lambda: analyze._run_skill_remove("private-skill"),
                lambda: analyze._run_skill_install("private-skill"),
                lambda: analyze._run_skill_update("private-skill"),
            ):
                output, errors = StringIO(), StringIO()
                with (
                    self.subTest(operation=operation),
                    redirect_stdout(output),
                    redirect_stderr(errors),
                ):
                    self.assertEqual(operation(), 2)
                self.assertEqual(output.getvalue(), "")
                self.assertIn("Operation unavailable.", errors.getvalue())
                self.assertNotIn("private-skill", errors.getvalue())
            fetch.assert_not_called()
        self.assertTrue((custom / "private-skill.md").exists())
