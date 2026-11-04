"""Frozen evidence drift guard; this does not execute or qualify a live host in CI."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/infra_automation/qualification/16_13"
RECORD = ROOT / "docs/verification/infra-automation/16-13/results.json"
CORE = ("bootstrap", "catalog", "source", "sandbox", "execution", "execution_profile")
REQUIRED_CASES = {
    "invalid-image-pin",
    "unsupported-host-profile",
    "receiver-identity-denied",
    "receiver-environment-denied",
    "real-provider",
    "vendored-tofu-provider",
    "tool-version",
    "environment",
    "watchdog-defenses",
    "cancel-at-finalization",
    "cpu-cap",
    "memory-cap",
    "pid-cap",
    "disk-cap",
    "output-cap",
    "partial-evidence",
    "cancel-descendants",
    "lease-descendants",
    "timeout-descendants",
}


def checksum(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class RunnerIsolationQualificationTests(unittest.TestCase):
    def setUp(self):
        self.record = json.loads(RECORD.read_text())

    def test_complete_record_has_only_passing_required_evidence(self):
        record = self.record
        self.assertIs(record["qualified"], True)
        self.assertIs(record["source_hashes_unchanged"], True)
        self.assertEqual(record["failed_checks"], [])
        self.assertTrue(record["checks"])
        self.assertTrue(all(value is True for value in record["checks"].values()))
        cases = [case["case"] for case in record["cases"]]
        self.assertEqual(len(cases), len(set(cases)))
        self.assertTrue(REQUIRED_CASES <= set(cases))
        for key in (
            "operator_death",
            "operator_death_under_load",
            "operator_death_delayed_setup",
        ):
            with self.subTest(key=key):
                proof = record[key]
                self.assertIs(proof["qualified"], True)
                self.assertEqual(proof["controller_exit"], -9)
                self.assertIs(proof["expired_without_host"], True)
                self.assertEqual(
                    proof["container_state_before_recovery"]["ExitCode"], 124
                )
                self.assertIs(proof["container_removed"], True)

    def test_durable_cancellation_distinguishes_host_kill_and_watchdog_expiry(self):
        cases = {item["case"]: item for item in self.record["cases"]}
        for name in ("cancel-descendants", "lease-descendants"):
            with self.subTest(case=name):
                self.assertIs(cases[name]["cancel_persisted_before_kill"], True)
                self.assertIs(cases[name]["cancel_persisted_before_removal"], True)
        timeout = cases["timeout-descendants"]
        self.assertEqual(timeout["result"]["state"], "timed_out")
        self.assertIs(timeout["result"]["finalizable"], False)
        self.assertIsNone(timeout["result"]["output_digest"])
        self.assertIs(timeout["cancel_persisted_before_removal"], True)
        if timeout["cancel_persisted_before_kill"] is None:
            self.assertEqual(timeout["last_state"]["ExitCode"], 124)
            self.assertIs(timeout["last_state"]["Running"], False)
        else:
            self.assertIs(timeout["cancel_persisted_before_kill"], True)

    def test_core_source_drift_requires_real_requalification(self):
        for name in CORE:
            relative = f"infra_automation/runner/{name}.py"
            with self.subTest(source=relative):
                self.assertEqual(
                    self.record["source_hashes"][relative], checksum(ROOT / relative)
                )

    def test_built_image_pins_match_current_bootstrap_and_fixture_bytes(self):
        paths = {
            "/opt/deploywhisper/bootstrap.py": ROOT
            / "infra_automation/runner/bootstrap.py",
            **{
                f"/opt/deploywhisper/{name}": FIXTURE / name
                for name in ("probe.py", "provider_probe.py", "tofurc")
            },
            **{
                f"/opt/deploywhisper/source/{name}": FIXTURE / "source" / name
                for name in ("main.tf", ".terraform.lock.hcl", "source.lock")
            },
        }
        pins = {
            item["path"]: item["sha256"] for item in self.record["catalog"]["files"]
        }
        self.assertEqual(self.record["catalog"]["image_id"], self.record["image_id"])
        for target, path in paths.items():
            with self.subTest(image_path=target):
                self.assertIs(self.record["image_source_pin_checks"][target], True)
                self.assertEqual(pins[target], checksum(path))

    def test_review_admission_and_every_advertised_command_have_evidence(self):
        required = {
            "tofu-outside",
            "tofu-remote",
            "tofu-oversize",
            "tofu-json-outside",
            "tofu-json-remote",
            "tofu-json-oversize",
            "public-staging-parent",
            "removed-provider-command",
        }
        cases = {item["case"]: item for item in self.record["admission"]}
        self.assertTrue(required <= set(cases))
        for name in required:
            with self.subTest(admission=name):
                self.assertIs(cases[name]["denied"], True)
                self.assertEqual(cases[name]["credential_resolver_calls"], 0)
        self.assertIs(
            cases["public-staging-parent"]["staging_empty_after_denial"], True
        )
        self.assertEqual(
            set(self.record["advertised_commands"]),
            {"qualification_probe", "tool_version"},
        )
        successful = {
            item.get("command")
            for item in self.record["cases"]
            if item["result"]["state"] == "succeeded"
        }
        self.assertTrue(set(self.record["advertised_commands"]) <= successful)
        vendor = next(
            item
            for item in self.record["cases"]
            if item["case"] == "vendored-tofu-provider"
        )
        self.assertIn(
            "module.local.terraform_data.vendored",
            vendor["evidence"]["module_resources"],
        )
        self.assertIs(
            self.record["r4_ambiguous_creation"]["real_late_daemon_commit_reproduced"],
            False,
        )

    def test_delayed_setup_cannot_restart_the_original_execution_budget(self):
        proof = self.record["operator_death_delayed_setup"]
        self.assertEqual(proof["profile"]["timeout_seconds"], 6)
        self.assertEqual(proof["create_delay_seconds"], 3)
        self.assertEqual(proof["lease_seconds"], 60)
        self.assertEqual(proof["credential_resolver_calls"], 1)
        self.assertGreaterEqual(
            proof["controller_killed_seconds_after_original_start"], 3
        )
        self.assertLessEqual(proof["observation_tolerance_seconds"], 0.75)
        self.assertAlmostEqual(
            proof["original_deadline_monotonic"],
            proof["timings"]["execute_entered_monotonic"] + 6,
            places=6,
        )
        self.assertLessEqual(
            proof["stop_observed_monotonic"],
            proof["original_deadline_monotonic"]
            + proof["observation_tolerance_seconds"],
        )
        self.assertIs(proof["stopped_within_original_deadline"], True)
        self.assertIs(proof["running_beyond_original_bound"], False)
