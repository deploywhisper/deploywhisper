"""Regression tests for prompt-injection CI and release enforcement."""

from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import sys
import unittest

import yaml

PROMPT_INJECTION_TEST = "tests/test_llm/test_prompt_injection.py"
PROMPT_INJECTION_COMMAND = (
    "python -m pytest tests/test_llm/test_prompt_injection.py -v --tb=short"
)


class PromptInjectionReleaseGateTests(unittest.TestCase):
    def test_local_ci_runs_prompt_injection_suite_before_full_targets(self) -> None:
        script = Path("scripts/ci-local.sh").read_text(encoding="utf-8")
        commands = [line.strip() for line in script.splitlines()]

        prompt_gate = commands.index(
            '"$PYTHON_BIN" -m pytest tests/test_llm/test_prompt_injection.py -q'
        )
        full_targets = next(
            index
            for index, command in enumerate(commands)
            if command.startswith('PYTHON_BIN="$PYTHON_BIN" bash ')
            and "scripts/run-test-targets.sh" in command
        )

        self.assertLess(prompt_gate, full_targets)

    def test_ci_llm_shard_blocks_summary_when_prompt_suite_fails(self) -> None:
        workflow = yaml.load(
            Path(".github/workflows/ci.yml").read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )
        jobs = workflow["jobs"]
        test_matrix = jobs["test"]["strategy"]["matrix"]["include"]
        llm_shards = [
            shard for shard in test_matrix if shard.get("targets") == "tests/test_llm"
        ]

        self.assertEqual(len(llm_shards), 1)
        self.assertIn("test", jobs["report"]["needs"])
        gate = next(
            step
            for step in jobs["report"]["steps"]
            if step["name"] == "Determine overall CI result"
        )
        program = gate["run"].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        needs = {
            name: {"result": "success"}
            for name in (
                "quality",
                "security",
                "frontend",
                "test",
                "docker",
                "migration",
                "changed-tests",
            )
        }
        needs["test"]["result"] = "failure"
        result = subprocess.run(
            [sys.executable, "-c", program],
            env={
                **os.environ,
                "NEEDS_JSON": json.dumps(needs),
                "EVENT_NAME": "pull_request",
            },
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('"test": "failure"', result.stdout)

    def test_release_runs_prompt_injection_gate_before_full_suite(self) -> None:
        workflow = yaml.load(
            Path(".github/workflows/release.yml").read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )
        steps = workflow["jobs"]["test"]["steps"]
        step_names = [step.get("name") for step in steps]
        prompt_gate = step_names.index("Run prompt-injection release gate")
        full_suite = step_names.index("Run full test suite")

        self.assertEqual(steps[prompt_gate]["run"], PROMPT_INJECTION_COMMAND)
        self.assertLess(prompt_gate, full_suite)


if __name__ == "__main__":
    unittest.main()
