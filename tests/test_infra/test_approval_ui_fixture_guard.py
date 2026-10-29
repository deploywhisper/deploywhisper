"""Disposable approval harness refuses operator storage and private exports."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def harness_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "approval_ui_fixture.py"
    spec = spec_from_file_location("approval_ui_fixture_guard_subject", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApprovalUiFixtureGuardTests(unittest.TestCase):
    def setUp(self):
        self.harness = harness_module()

    def test_host_execution_refuses_before_loading_application_configuration(self):
        with (
            patch.object(self.harness.Path, "is_file", return_value=False),
            patch.object(self.harness.os, "umask") as umask,
            self.assertRaises(RuntimeError),
        ):
            self.harness.guard()
        umask.assert_not_called()

    def test_non_tmpfs_storage_refuses_before_any_write_or_configuration_import(self):
        environment = {
            "APPROVAL_UI_DISPOSABLE": "1",
            "DEPLOYWHISPER_IDENTITY_PROFILE": "local-development",
            "DEPLOYWHISPER_IDENTITY_ORIGIN": self.harness.ORIGIN,
            "DEPLOYWHISPER_AUTHORIZATION_PROFILE": "verified",
            "DEPLOYWHISPER_IDENTITY_DECISION_MODE": "shared",
            "DATABASE_URL": self.harness.DATABASE,
            "APP_BASE_URL": self.harness.ORIGIN,
        }
        with (
            patch.dict(self.harness.os.environ, environment, clear=True),
            patch.object(self.harness.os, "geteuid", return_value=999),
            patch.object(self.harness.Path, "is_file", return_value=True),
            patch.object(self.harness.Path, "is_symlink", return_value=False),
            patch.object(self.harness.Path, "cwd", return_value=Path("/app")),
            patch.object(
                self.harness.Path,
                "read_text",
                return_value="1 0 8:1 / /app/data rw - ext4 /dev/sda rw\n",
            ),
            patch.object(self.harness.os, "umask") as umask,
            self.assertRaises(RuntimeError),
        ):
            self.harness.guard()
        umask.assert_not_called()

    def test_browser_export_excludes_service_credentials_and_material_authority(self):
        exported = self.harness.browser_fixture(
            {
                "version": 1,
                "profile": "shared",
                "accounts": {},
                "projects": {},
                "cases": {},
                "requesterSession": {"token": "private", "csrf": "private"},
                "materials": {"binding": "server-only"},
            }
        )
        self.assertEqual(
            set(exported), {"version", "profile", "accounts", "projects", "cases"}
        )
        self.assertNotIn("private", json.dumps(exported))
        self.assertNotIn("server-only", json.dumps(exported))

    def test_private_reader_rejects_symlinks_and_broad_file_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            path.write_text('{"version":1}')
            path.chmod(0o644)
            with self.assertRaises(RuntimeError):
                self.harness.read_private(path)
            path.chmod(0o600)
            self.assertEqual(self.harness.read_private(path), {"version": 1})
            link = Path(directory) / "link.json"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                self.harness.read_private(link)
