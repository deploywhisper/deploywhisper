"""Fail-closed reference performance qualification contracts."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.benchmark_runner_protocol import reference_failures


class ReferenceBenchmarkHarnessTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            "cgroup_limits": {
                "cpu.max": "400000 100000",
                "memory.max": str(8 * 1024**3),
            },
            "requested_warmups": 100,
            "requested_samples": 1000,
            "runner_processes": 20,
            "measured_samples": 1000,
            "failures": 0,
            "harness_failure": None,
            "p95_ms": 1999.99,
            "source_hashes_unchanged": True,
        }

    def test_exact_reference_claim_profile_qualifies(self):
        with patch(
            "scripts.benchmark_runner_protocol.platform.system", return_value="Linux"
        ):
            self.assertEqual(reference_failures(self.report), [])

    def test_every_reference_dimension_fails_closed(self):
        mutations = {
            "cpu": (
                "cgroup_limits",
                {"cpu.max": "max 100000", "memory.max": str(8 * 1024**3)},
            ),
            "memory": (
                "cgroup_limits",
                {"cpu.max": "400000 100000", "memory.max": "max"},
            ),
            "samples": ("measured_samples", 999),
            "failures": ("failures", 1),
            "p95": ("p95_ms", 2000),
            "source": ("source_hashes_unchanged", False),
        }
        with patch(
            "scripts.benchmark_runner_protocol.platform.system", return_value="Linux"
        ):
            for name, (key, value) in mutations.items():
                changed = deepcopy(self.report)
                changed[key] = value
                with self.subTest(name=name):
                    self.assertTrue(reference_failures(changed))

    def test_workflow_benchmark_cli_fails_when_not_qualified(self):
        from scripts import benchmark_workflow_validation as workflow

        report = {
            "qualified": False,
            "samples": 1000,
            "failures": {"warmup": 0, "measured": 0},
            "p50_ms": 1,
            "p95_ms": 2,
            "p99_ms": 3,
            "qualification_failures": ["wrong hardware"],
        }
        with patch.object(workflow, "run_benchmark", return_value=report):
            self.assertEqual(
                workflow.main(
                    [
                        "--corpus",
                        "unused.json",
                        "--output",
                        "unused-output.json",
                    ]
                ),
                1,
            )


if __name__ == "__main__":
    unittest.main()
