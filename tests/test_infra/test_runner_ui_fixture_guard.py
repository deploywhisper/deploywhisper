"""Runner browser fixture refuses non-disposable or unsafe credential storage."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def load_harness():
    path = Path(__file__).resolve().parents[2] / "scripts/runner_ui_fixture.py"
    spec = spec_from_file_location("runner_ui_guard_subject", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RunnerUiFixtureGuardTests(unittest.TestCase):
    def setUp(self):
        self.harness = load_harness()

    def test_host_refuses_before_configuration_import_or_write(self):
        with (
            patch.object(self.harness.Path, "is_file", return_value=False),
            patch.object(self.harness.os, "umask") as umask,
            self.assertRaises(RuntimeError),
        ):
            self.harness.guard()
        umask.assert_not_called()

    def test_persistent_mount_refuses_before_configuration_import_or_write(self):
        environment = self.harness.required_environment()
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

    def test_https_configuration_is_not_silently_enabled_by_http_harness(self):
        environment = self.harness.required_environment() | {
            "DEPLOYWHISPER_IDENTITY_PROFILE": "https"
        }
        with (
            patch.dict(self.harness.os.environ, environment, clear=True),
            patch.object(self.harness.Path, "is_file", return_value=True),
            patch.object(self.harness.os, "geteuid", return_value=999),
            self.assertRaises(RuntimeError),
        ):
            self.harness.guard()

    def test_private_reader_rejects_broad_permissions_and_links(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture.json"
            path.write_text('{"version":1}')
            path.chmod(0o644)
            with self.assertRaises(RuntimeError):
                self.harness.read_private(path)
            path.chmod(0o600)
            self.assertEqual(self.harness.read_private(path), {"version": 1})
            link = Path(folder) / "linked.json"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                self.harness.read_private(link)

    def test_browser_export_drops_any_server_session_or_authority(self):
        exported = self.harness.browser_fixture(
            {
                "accounts": {},
                "operatorPool": [],
                "projects": {},
                "token": "private-server-token",
                "requesterSession": {"csrf": "private"},
            }
        )
        self.assertEqual(
            set(exported),
            {"version", "origin", "lane", "accounts", "operatorPool", "projects"},
        )
        self.assertNotIn("private", str(exported))
