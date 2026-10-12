"""Qualification evidence cannot omit proofs or hide completed output overruns."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
MODULE = (
    ROOT / "tests/fixtures/infra_automation/qualification/16_0/isolation/harness.py"
)
spec = importlib.util.spec_from_file_location("qualification_gate", MODULE)
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)
EVIDENCE = ROOT / "docs/verification/infra-automation/16-0"
BASELINE = {
    **json.loads((EVIDENCE / "wp4-containment-results.json").read_text()),
    **json.loads((EVIDENCE / "wp5-real-custody-results.json").read_text()),
}


def evidence_maps():
    """Walk proof maps only; manifest annotations are outside the gate contract."""
    sections = (
        "plan",
        "local_traffic",
        "custody",
        "restart",
        "collector",
        "custody_attacks",
        "finalization_faults",
        "receiver_faults",
        "replan",
        "disk",
        "pids",
        "memory",
        "cpu",
        "output_cap",
        "time_cap",
        "descendants",
        "store_disk",
        "controls",
        "catalog_digests",
    )

    def walk(value, path):
        yield path, value
        for key, child in value.items():
            if isinstance(child, dict):
                yield from walk(child, (*path, key))

    for section in sections:
        yield from walk(BASELINE[section], (section,))


def changed(path, value, *, remove=False):
    result = deepcopy(BASELINE)
    parent = result
    for part in path[:-1]:
        parent = parent[part]
    if remove:
        del parent[path[-1]]
    else:
        parent[path[-1]] = value
    return result


class QualificationGateTests(unittest.TestCase):
    def test_finalization_fault_proofs_are_mandatory(self):
        result = deepcopy(BASELINE)
        result.pop("finalization_faults", None)
        with self.assertRaises(ValueError):
            harness.validate(result)

    def test_recorded_complete_evidence_passes(self):
        harness.validate(deepcopy(BASELINE))

    def test_each_proof_map_is_required_and_must_be_a_nonempty_object(self):
        for path, _ in evidence_maps():
            for bad in ({}, [], None, True, "True"):
                with self.subTest(path=path, bad=bad), self.assertRaises(ValueError):
                    harness.validate(changed(path, bad))
            with self.subTest(missing=path), self.assertRaises(ValueError):
                harness.validate(changed(path, None, remove=True))

    def test_partial_and_undeclared_cases_fail_closed(self):
        for path, value in evidence_maps():
            for key in value:
                # CPU statistics are diagnostics, not a separate mandatory probe.
                if path == ("cpu",) and key == "cpu_stat":
                    continue
                with self.subTest(missing=(*path, key)), self.assertRaises(ValueError):
                    harness.validate(changed((*path, key), None, remove=True))
            with self.subTest(extra=path), self.assertRaises(ValueError):
                harness.validate(changed((*path, "undeclared_probe"), True))

    def test_boolean_and_numeric_proofs_require_exact_types(self):
        for path, value in evidence_maps():
            for key, leaf in value.items():
                if type(leaf) is bool:
                    invalid = (not leaf, int(leaf), str(leaf), None)
                elif type(leaf) is int:
                    invalid = (True, str(leaf), float(leaf), None)
                elif type(leaf) is str and leaf == "True":
                    invalid = (True, 1, "False", None)
                elif type(leaf) is str:
                    invalid = (True, 1, [], None)
                elif type(leaf) is list:
                    invalid = (True, {}, [], tuple(leaf), None)
                else:
                    continue
                for bad in invalid:
                    with (
                        self.subTest(path=(*path, key), bad=bad),
                        self.assertRaises(ValueError),
                    ):
                        harness.validate(changed((*path, key), bad))

    def test_each_fault_requires_its_exact_state_and_action_count(self):
        for point, record in BASELINE["receiver_faults"]["faults"].items():
            path = ("receiver_faults", "faults", point)
            for bad in (-1, 1 - record["action_count"], 2):
                with (
                    self.subTest(point=point, count=bad),
                    self.assertRaises(ValueError),
                ):
                    harness.validate(changed((*path, "action_count"), bad))
            wrong_state = (
                "delivery_unknown"
                if record["state"] == "action_completed"
                else "action_completed"
            )
            with (
                self.subTest(point=point, state=wrong_state),
                self.assertRaises(ValueError),
            ):
                harness.validate(changed((*path, "state"), wrong_state))

    def test_contradictory_identity_digest_limits_and_exit_status_fail(self):
        cases = (
            (("plan", "provider_probe", "uid"), "0"),
            (("local_traffic", "uid"), "0"),
            (("custody", "raw_digest"), "0" * 64),
            (("plan", "raw_digest"), "invalid"),
            (("custody", "expiry"), -1),
            (("custody", "tool"), "unqualified"),
            (("controls", "uid"), "0:0"),
            (("controls", "memory"), 0),
            (("controls", "nano_cpus"), 0),
            (("controls", "pids_limit"), 0),
            (("controls", "mount_destinations"), [[], {}]),
            (("controls", "mount_destinations"), ["/custody", "/custody"]),
            (("controls", "mount_destinations"), ["/custody", "/staging", "/host"]),
            (("disk", "exit_code"), 1),
            (("pids", "exit_code"), 1),
            (("cpu", "exit_code"), 1),
            (("memory", "exit_code"), 0),
            (("descendants", "cancel", "exit_code"), 0),
            (("descendants", "cancel", "processes_before"), 1),
        )
        for path, bad in cases:
            with self.subTest(path=path), self.assertRaises(ValueError):
                harness.validate(changed(path, bad))

    def test_malformed_top_level_is_a_validation_error(self):
        for bad in ({}, [], None, True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                harness.validate(bad)

    def test_source_digest_is_required_and_must_match_executed_source(self):
        for bad in (None, True, 1, [], "invalid", "0" * 64):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                harness.validate(changed(("source_content_sha256",), bad))
        with self.assertRaises(ValueError):
            harness.validate(changed(("source_content_sha256",), None, remove=True))

    def test_cpu_diagnostics_are_optional(self):
        harness.validate(changed(("cpu", "cpu_stat"), None, remove=True))


class QualificationOutputCapTests(unittest.TestCase):
    def run_task(self, stdout_bytes, stderr_bytes, *, running=False):
        experiment = harness.Qualification.__new__(harness.Qualification)
        experiment.prefix = "dw16-output-regression"
        experiment.containers = []
        experiment.volumes = ["staging", "custody"]
        experiment.image = "test-image"
        process = Mock(returncode=0)
        process.poll.return_value = None if running else 0

        def launch(_args, *, stdout, stderr):
            stdout.write(b"x" * stdout_bytes)
            stderr.write(b"x" * stderr_bytes)
            stdout.flush()
            stderr.flush()
            return process

        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(harness.tempfile, "gettempdir", return_value=temp),
            patch.object(harness.subprocess, "Popen", side_effect=launch),
            patch.object(harness, "command") as command,
            patch.object(harness.time, "monotonic", side_effect=[0, 2]),
        ):
            _, code, output = experiment.task("output", deadline=1)
            diagnostic = (
                Path(temp) / "dw16-output-regression-0.private-stderr"
            ).read_bytes()
        return code, output, diagnostic, command

    def test_completed_stdout_stderr_and_combined_boundaries(self):
        for stdout, stderr in (
            (65535, 0),
            (65536, 0),
            (65537, 0),
            (0, 65535),
            (0, 65536),
            (0, 65537),
            (32768, 32767),
            (32768, 32768),
            (32768, 32769),
            (100000, 0),
        ):
            with self.subTest(stdout=stdout, stderr=stderr):
                code, output, diagnostic, command = self.run_task(stdout, stderr)
                self.assertEqual(code, 124 if stdout + stderr > 65536 else 0)
                self.assertEqual(len(output), min(stdout, 65536))
                self.assertEqual(len(diagnostic), min(stderr, 65536))
                command.assert_not_called()

    def test_live_output_overrun_and_deadline_still_kill(self):
        for stdout in (0, 65537):
            with self.subTest(stdout=stdout):
                code, _, _, command = self.run_task(stdout, 0, running=True)
                self.assertEqual(code, 124)
                command.assert_called_once_with(
                    [harness.DOCKER, "kill", "dw16-output-regression-0"]
                )
