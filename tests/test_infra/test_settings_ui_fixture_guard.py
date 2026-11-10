"""The operator browser fixture cannot seed ordinary or persistent deployments."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


class SettingsUIFixtureGuardTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "settings_ui_fixture_guarded",
            Path(__file__).parents[2] / "scripts" / "settings_ui_fixture.py",
        )
        assert spec is not None and spec.loader is not None
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_host_invocation_rejects_before_loading_other_fixture_code(self):
        with (
            patch.dict(self.module.os.environ, {}, clear=True),
            patch.object(self.module.runpy, "run_path") as load,
            self.assertRaises(RuntimeError),
        ):
            self.module.main()
        load.assert_not_called()

    def test_persistent_container_data_is_not_a_disposable_target(self):
        with (
            patch.dict(self.module.os.environ, {"SETTINGS_UI_DISPOSABLE": "1"}),
            patch.object(self.module.os, "geteuid", return_value=10001),
            patch.object(Path, "cwd", return_value=Path("/app")),
            patch.object(Path, "is_file", return_value=True),
            patch.object(
                Path,
                "read_text",
                return_value="1 2 0:1 / /app/data rw - ext4 disk rw\n",
            ),
            patch.object(self.module.runpy, "run_path") as load,
            self.assertRaises(RuntimeError),
        ):
            self.module.main()
        load.assert_not_called()

    def test_root_container_never_seeds(self):
        with (
            patch.dict(self.module.os.environ, {"SETTINGS_UI_DISPOSABLE": "1"}),
            patch.object(Path, "is_file", return_value=True),
            patch.object(self.module.os, "geteuid", return_value=0),
            patch.object(self.module.runpy, "run_path") as load,
            self.assertRaises(RuntimeError),
        ):
            self.module.main()
        load.assert_not_called()
