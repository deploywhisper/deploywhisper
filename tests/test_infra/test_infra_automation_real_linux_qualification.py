"""Fail-closed admission and opt-in actual Linux/tool/custody qualification."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

MODULE = (
    Path(__file__).resolve().parents[1]
    / "fixtures/infra_automation/qualification/16_0/isolation/harness.py"
)
spec = importlib.util.spec_from_file_location("real_linux_qualification", MODULE)
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


class RealLinuxQualificationTests(unittest.TestCase):
    def test_rejects_unadmitted_sources_paths_and_catalog(self):
        baseline = ["protected_revision", "source/main.tf", "a" * 40, ["plan"]]
        self.assertTrue(harness.admit(*baseline))
        for index, value in (
            (0, "untrusted_pr"),
            (1, "../outside"),
            (1, "symlink/main.tf"),
            (2, "HEAD"),
            (3, ["apply"]),
            (3, ["plan", "-var-file=/secrets"]),
        ):
            changed = baseline.copy()
            changed[index] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                harness.admit(*changed)

    def test_actual_symlink_and_hostile_git_config_do_not_admit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outside = root / "outside"
            outside.write_text("synthetic")
            (root / "main.tf").symlink_to(outside)
            with self.assertRaises(ValueError):
                harness.source_admission(root, "main.tf")
            hostile = root / "gitconfig"
            hostile.write_text("invalid git config would fail if inherited")
            previous = os.environ.get("GIT_CONFIG_GLOBAL")
            os.environ["GIT_CONFIG_GLOBAL"] = str(hostile)
            try:
                revision, digest = harness.admitted_source()
                self.assertEqual(len(revision), 40)
                self.assertEqual(len(digest), 64)
            finally:
                if previous is None:
                    os.environ.pop("GIT_CONFIG_GLOBAL")
                else:
                    os.environ["GIT_CONFIG_GLOBAL"] = previous

    @unittest.skipUnless(
        os.environ.get("DW16_REAL_LINUX") == "1",
        "explicit disposable Docker qualification required",
    )
    def test_real_tool_containment_and_custody(self):
        result = harness.qualify()
        harness.validate(result)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["plan"]["uid"], 10001)
        self.assertTrue(
            all(
                value == "True"
                for key, value in result["plan"]["provider_probe"].items()
                if key != "uid"
            )
        )
        self.assertNotEqual(
            result["plan"]["raw_digest"], result["plan"]["sanitized_digest"]
        )
        self.assertEqual(result["custody"]["uid"], 10002)
        self.assertEqual(result["plan"]["raw_digest"], result["restart"]["raw_digest"])
        self.assertTrue(result["collector"]["custody_denied"])
        self.assertTrue(all(result["custody_attacks"].values()))
        self.assertTrue(result["disk"]["disk_denied"])
        self.assertTrue(result["disk"]["partial_removed"])
        self.assertTrue(result["pids"]["pids_denied"])
        self.assertTrue(result["memory"]["oom_killed"])
        self.assertTrue(
            all(
                item["stopped"] and item["processes_before"] >= 2
                for item in result["descendants"].values()
            )
        )
