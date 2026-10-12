"""Changed-test feedback selects executable tests without importing fixtures."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/test-changed.sh"


class ChangedTestDiscoveryTests(unittest.TestCase):
    def run_changed(self, paths, *, absent=(), test_exit=0):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binaries = root / "bin"
            binaries.mkdir()
            changes = root / "changes"
            changes.write_text("".join(f"{path}\n" for path in paths))
            capture = root / "python-args"
            for name, body in {
                "git": (
                    '#!/bin/sh\ncase "$1" in\n'
                    "rev-parse) exit 0 ;;\n"
                    'diff) cat "$TEST_CHANGED_PATHS" ;;\n'
                    "*) exit 1 ;;\nesac\n"
                ),
                "python": (
                    '#!/bin/sh\nprintf "%s\\n" "$@" > "$TEST_PYTHON_ARGS"\n'
                    'exit "$TEST_PYTHON_EXIT"\n'
                ),
            }.items():
                executable = binaries / name
                executable.write_text(body)
                executable.chmod(0o755)
            for path in paths:
                if path not in absent:
                    target = root / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("# Synthetic changed file; never imported.\n")
            result = subprocess.run(
                ["/bin/bash", str(SCRIPT)],
                cwd=root,
                env={
                    **os.environ,
                    "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}",
                    "BASE_REF": "test-base",
                    "PYTHON_BIN": "python",
                    "TEST_CHANGED_PATHS": str(changes),
                    "TEST_PYTHON_ARGS": str(capture),
                    "TEST_PYTHON_EXIT": str(test_exit),
                },
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            arguments = capture.read_text().splitlines() if capture.exists() else None
            return result, arguments

    def test_selects_root_and_nested_test_modules_only(self):
        result, arguments = self.run_changed(
            [
                "tests/test_root.py",
                "tests/test_infra/test_qualification.py",
                "tests/fixtures/infra_automation/contracts/action_consumer_probe.py",
                "tests/fixtures/nested/test_synthetic_fixture.py",
                "tests/fixtures/test_fixture.py",
                "tests/helpers.py",
                "tests/test_infra/helpers.py",
                "tests/test_infra/__init__.py",
                "tests/test_infra/test_notes.md",
                "services/test_helper.py",
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            arguments,
            [
                "-m",
                "unittest",
                "-q",
                "tests.test_root",
                "tests.test_infra.test_qualification",
            ],
        )

    def test_empty_and_fixture_or_helper_only_diffs_do_not_run_python(self):
        for paths in (
            [],
            ["tests/fixtures/test_fixture.py"],
            ["tests/fixtures/contracts/action_consumer_probe.py", "tests/helpers.py"],
            ["tests/test_infra/__init__.py", "README.md"],
        ):
            with self.subTest(paths=paths):
                result, arguments = self.run_changed(paths)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIsNone(arguments)
                self.assertIn("No changed test files detected", result.stdout)

    def test_nonexistent_changed_test_is_not_imported(self):
        result, arguments = self.run_changed(
            ["tests/test_missing.py"], absent=["tests/test_missing.py"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(arguments)
        self.assertIn("No existing changed test files detected", result.stdout)

    def test_selected_test_failure_is_propagated(self):
        result, arguments = self.run_changed(["tests/test_failed.py"], test_exit=7)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(arguments, ["-m", "unittest", "-q", "tests.test_failed"])
