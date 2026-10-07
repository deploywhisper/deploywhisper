"""Protect the untrusted-PR boundary and visibility of baseline security scans."""

from __future__ import annotations

from pathlib import Path
import json
import re
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[2]


class SupplyChainWorkflowTests(unittest.TestCase):
    def load_workflow(self, name):
        text = (ROOT / ".github" / "workflows" / f"{name}.yml").read_text()
        return yaml.load(text, Loader=yaml.BaseLoader), text

    def test_scans_run_for_prs_long_lived_branches_and_weekly(self):
        expected = {
            "codeql": {"push", "pull_request", "schedule", "workflow_dispatch"},
            "scorecard": {"pull_request"},
            "scorecard-publish": {"push", "schedule", "workflow_dispatch"},
        }
        for name, events in expected.items():
            with self.subTest(workflow=name):
                workflow, _ = self.load_workflow(name)
                self.assertEqual(
                    set(workflow["on"]),
                    events,
                )
                for event in ("push", "pull_request"):
                    if event not in events:
                        continue
                    self.assertEqual(
                        set(workflow["on"][event]["branches"]), {"main", "develop"}
                    )
                    self.assertNotIn("paths", workflow["on"][event])
                if "schedule" in events:
                    self.assertEqual(len(workflow["on"]["schedule"]), 1)
                    self.assertRegex(
                        workflow["on"]["schedule"][0]["cron"], r"^\d+ \d+ \* \* [0-6]$"
                    )

    def test_scans_limit_permissions_and_pin_external_code(self):
        for name in ("codeql", "scorecard", "scorecard-publish"):
            with self.subTest(workflow=name):
                workflow, text = self.load_workflow(name)
                self.assertEqual(workflow["permissions"], {"contents": "read"})
                self.assertNotIn("secrets.", text)
                self.assertNotIn("env", workflow)
                for job in workflow["jobs"].values():
                    permissions = {"contents": "read", "security-events": "write"}
                    if name == "scorecard-publish":
                        permissions["id-token"] = "write"
                    self.assertEqual(
                        job["permissions"],
                        permissions,
                    )
                    self.assertGreater(int(job["timeout-minutes"]), 0)
                    self.assertNotIn("continue-on-error", job)
                    self.assertNotIn("env", job)
                    for step in job["steps"]:
                        self.assertNotIn("continue-on-error", step)
                        if "uses" in step:
                            self.assertRegex(step["uses"], r"^[\w./-]+@[a-f0-9]{40}$")
                        self.assertNotIn("env", step)
                        self.assertNotIn("token", step.get("with", {}))
                        self.assertNotIn("repo_token", step.get("with", {}))
                        if step.get("uses", "").startswith("actions/checkout@"):
                            self.assertEqual(
                                step["with"]["persist-credentials"], "false"
                            )
                            self.assertNotIn("token", step["with"])

    def test_codeql_scans_all_languages_without_running_repository_code(self):
        workflow, _ = self.load_workflow("codeql")
        job = workflow["jobs"]["analyze"]
        self.assertEqual(
            set(job["strategy"]["matrix"]["language"]),
            {"python", "javascript-typescript", "actions"},
        )
        self.assertEqual(job["strategy"]["fail-fast"], "false")
        self.assertFalse(any("run" in step for step in job["steps"]))
        init = next(s for s in job["steps"] if "/init@" in s.get("uses", ""))
        self.assertEqual(init["with"]["build-mode"], "none")
        self.assertEqual(init["with"]["queries"], "security-extended")
        analyze = next(s for s in job["steps"] if "/analyze@" in s.get("uses", ""))
        self.assertIn("matrix.language", analyze["with"]["category"])
        self.assertTrue(analyze["with"]["output"])

    def test_sarif_artifacts_remain_visible_on_failure(self):
        for name in ("codeql", "scorecard", "scorecard-publish"):
            with self.subTest(workflow=name):
                workflow, _ = self.load_workflow(name)
                for job in workflow["jobs"].values():
                    upload = next(
                        s
                        for s in job["steps"]
                        if s.get("uses", "").startswith("actions/upload-artifact@")
                    )
                    self.assertIn("always()", upload["if"])
                    self.assertIn("hashFiles(", upload["if"])
                    self.assertGreaterEqual(int(upload["with"]["retention-days"]), 14)
                    self.assertLessEqual(int(upload["with"]["retention-days"]), 90)
                    self.assertEqual(upload["with"]["if-no-files-found"], "error")
                    self.assertIn("sarif", upload["with"]["path"])

    def test_scorecard_limits_default_branch_scans_and_external_publication(self):
        workflow, _ = self.load_workflow("scorecard")
        job = workflow["jobs"]["scorecard"]
        self.assertIn("github.event_name == 'pull_request'", job["if"])
        self.assertIn("github.event.repository.fork == false", job["if"])
        score = next(s for s in job["steps"] if s.get("uses", "").startswith("ossf/"))
        self.assertEqual(score["with"]["publish_results"], "false")
        self.assertEqual(score["with"]["results_format"], "sarif")
        sarif = next(s for s in job["steps"] if "/upload-sarif@" in s.get("uses", ""))
        self.assertEqual(sarif["with"]["sarif_file"], score["with"]["results_file"])
        self.assertIn("always()", sarif["if"])
        self.assertIn("hashFiles(", sarif["if"])

    def test_badge_publisher_is_single_restricted_default_branch_job(self):
        workflow, text = self.load_workflow("scorecard-publish")
        self.assertEqual(set(workflow["jobs"]), {"publish"})
        self.assertNotIn("pull_request", workflow["on"])
        self.assertNotIn("pull_request_target", workflow["on"])
        self.assertNotIn("env", workflow)
        self.assertNotIn("defaults", workflow)
        job = workflow["jobs"]["publish"]
        self.assertIn("github.event.repository.fork == false", job["if"])
        self.assertIn("github.event.repository.default_branch", job["if"])
        self.assertIn("github.ref == format('refs/heads/{0}'", job["if"])
        for forbidden in ("env", "defaults", "container", "services"):
            self.assertNotIn(forbidden, job)
        allowed = (
            "actions/checkout@",
            "ossf/scorecard-action@",
            "actions/upload-artifact@",
            "github/codeql-action/upload-sarif@",
        )
        for step in job["steps"]:
            self.assertNotIn("run", step)
            self.assertTrue(step.get("uses", "").startswith(allowed))
        score = next(step for step in job["steps"] if step["uses"].startswith("ossf/"))
        self.assertEqual(score["with"]["publish_results"], "true")
        readme = (ROOT / "README.md").read_text()
        self.assertIn(
            "https://api.scorecard.dev/projects/github.com/deploywhisper/deploywhisper/badge",
            readme,
        )
        self.assertIn(
            "https://scorecard.dev/viewer/?uri=github.com/deploywhisper/deploywhisper",
            readme,
        )

    def test_scorecard_summary_uses_trusted_literal_text_only(self):
        workflow, _ = self.load_workflow("scorecard")
        scripts = [
            s["run"] for s in workflow["jobs"]["scorecard"]["steps"] if "run" in s
        ]
        self.assertEqual(len(scripts), 1)
        script = scripts[0]
        self.assertNotIn("${{", script)
        self.assertNotIn("$(", script)
        self.assertNotIn("`", script)
        self.assertTrue(
            script.startswith("cat >> \"$GITHUB_STEP_SUMMARY\" <<'SUMMARY'\n")
        )
        self.assertTrue(script.endswith("SUMMARY\n"))
        self.assertFalse(
            re.search(r"\b(?:python|node|npm|pip|bash|source|curl|wget)\b", script)
        )
        self.assertIn("docs/security/supply-chain-scanning.md", script)
        self.assertIn("PR local", script)
        self.assertIn("default-branch", script)
        self.assertIn("GITHUB_STEP_SUMMARY", script)

    def test_baseline_high_priority_findings_have_owned_followups(self):
        evidence = json.loads(
            (ROOT / "docs/verification/story-12-4/scorecard-baseline.json").read_text()
        )
        ledger = (ROOT / "docs/security/supply-chain-findings.md").read_text()
        high_priority = {
            "Dangerous-Workflow",
            "Webhooks",
            "Binary-Artifacts",
            "Branch-Protection",
            "Code-Review",
            "Dependency-Update-Tool",
            "Maintained",
            "Signed-Releases",
            "Token-Permissions",
            "Vulnerabilities",
        }
        for check in evidence["checks"]:
            if check["name"] in high_priority and check["score"] < 10:
                with self.subTest(check=check["name"]):
                    row = next(
                        (
                            line
                            for line in ledger.splitlines()
                            if line.startswith("| " + check["name"] + ",")
                        ),
                        None,
                    )
                    self.assertIsNotNone(
                        row, f"Missing disposition for {check['name']}"
                    )
                    self.assertIn("@pramodksahoo", row)
                    self.assertIn(
                        "https://github.com/deploywhisper/deploywhisper/issues/", row
                    )
                    self.assertRegex(row, r"\d{4}-\d{2}-\d{2}")
        guide = (ROOT / "docs/security/supply-chain-scanning.md").read_text()
        self.assertIn("scorecard-sarif", guide)
        self.assertIn("publish_results: false", guide)
        self.assertIn("publish_results: true", guide)
        self.assertIn("first default-branch publishing run", guide)
        self.assertIn("private disclosure", guide)
        self.assertIn("recorded after integration", guide)

    def test_critical_failures_without_dispositions_are_rejected(self):
        baseline_path = ROOT / "docs/verification/story-12-4/scorecard-baseline.json"
        original_read = Path.read_text
        baseline = json.loads(baseline_path.read_text())
        for critical in ("Dangerous-Workflow", "Webhooks"):
            for score in (0, -1):
                with self.subTest(check=critical, score=score):
                    evidence = {
                        **baseline,
                        "checks": [
                            *baseline["checks"],
                            {"name": critical, "score": score},
                        ],
                    }

                    def read(path, *args, **kwargs):
                        if path == baseline_path:
                            return json.dumps(evidence)
                        return original_read(path, *args, **kwargs)

                    with patch.object(Path, "read_text", read):
                        result = unittest.TestResult()
                        SupplyChainWorkflowTests(
                            "test_baseline_high_priority_findings_have_owned_followups"
                        ).run(result)
                    self.assertFalse(
                        result.wasSuccessful(),
                        "Critical failure/unknown check needs an owned disposition",
                    )
                    self.assertFalse(result.errors)
                    self.assertTrue(result.failures)
                    self.assertIn(
                        "Missing disposition for " + critical, result.failures[0][1]
                    )

    def test_critical_failures_with_owned_dispositions_are_accepted(self):
        baseline_path = ROOT / "docs/verification/story-12-4/scorecard-baseline.json"
        ledger_path = ROOT / "docs/security/supply-chain-findings.md"
        original_read = Path.read_text
        baseline = json.loads(baseline_path.read_text())
        evidence = {
            **baseline,
            "checks": [
                *baseline["checks"],
                {"name": "Dangerous-Workflow", "score": 0},
                {"name": "Webhooks", "score": -1},
            ],
        }
        ledger = (
            ledger_path.read_text()
            + "\n"
            + "\n".join(
                f"| {name}, 0/10 | Critical | synthetic fixture | @pramodksahoo | Open follow-up | https://github.com/deploywhisper/deploywhisper/issues/131 | 2026-10-13 |"
                for name in ("Dangerous-Workflow", "Webhooks")
            )
        )

        def read(path, *args, **kwargs):
            if path == baseline_path:
                return json.dumps(evidence)
            if path == ledger_path:
                return ledger
            return original_read(path, *args, **kwargs)

        with patch.object(Path, "read_text", read):
            result = unittest.TestResult()
            SupplyChainWorkflowTests(
                "test_baseline_high_priority_findings_have_owned_followups"
            ).run(result)
        self.assertTrue(result.wasSuccessful(), str(result.failures + result.errors))


if __name__ == "__main__":
    unittest.main()
