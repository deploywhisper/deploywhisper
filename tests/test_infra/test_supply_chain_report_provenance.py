"""Reject checkout and prior-run SARIF while retaining fresh publisher output."""

from __future__ import annotations

from pathlib import Path
import json
import re
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
CONTEXT = {"sha": "a" * 40, "run_id": "12345", "run_attempt": "2"}
REPORT = (
    "scorecard-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}.sarif"
)
FRESH = "scorecard-{sha}-{run_id}-{run_attempt}.sarif".format(**CONTEXT)
HASH = "hashFiles(format('scorecard-{0}-{1}-{2}.sarif', github.sha, github.run_id, github.run_attempt)) != ''"
SARIF = json.dumps(
    {
        "version": "2.1.0",
        "runs": [
            {"tool": {"driver": {"name": "Scorecard", "rules": []}}, "results": []}
        ],
    }
)


def permits_upload(condition, workspace, outcome):
    """Model only the workflow's bounded guards, rejecting unknown expressions."""
    terms = condition.split(" && ")
    if terms.pop(0) != "always()":
        raise AssertionError("Uploads must run independently of earlier step failures")
    allowed = True
    for term in terms:
        if term == "steps.scorecard.outcome == 'success'":
            allowed = allowed and outcome == "success"
            continue
        if term == HASH:
            filename = FRESH
        else:
            legacy = re.fullmatch(r"hashFiles\('([^']+)'\) != ''", term)
            if not legacy:
                raise AssertionError(f"Unsupported guard: {term}")
            filename = legacy.group(1)
        allowed = allowed and (workspace / filename).is_file()
    return allowed


class SupplyChainReportProvenanceTests(unittest.TestCase):
    def steps(self, workflow):
        data = yaml.load(
            (ROOT / ".github/workflows" / f"{workflow}.yml").read_text(),
            Loader=yaml.BaseLoader,
        )
        return next(iter(data["jobs"].values()))["steps"]

    def consumers(self, workflow):
        return [
            step
            for step in self.steps(workflow)
            if step.get("uses", "").startswith(
                ("actions/upload-artifact@", "github/codeql-action/upload-sarif@")
            )
        ]

    def test_report_path_binds_producer_and_consumers_to_checkout_and_run(self):
        for workflow in ("scorecard", "scorecard-publish"):
            with self.subTest(workflow=workflow):
                steps = self.steps(workflow)
                checkout = next(
                    s for s in steps if s["uses"].startswith("actions/checkout@")
                )
                self.assertNotIn("ref", checkout.get("with", {}))
                self.assertNotIn("repository", checkout.get("with", {}))
                score = next(s for s in steps if s.get("uses", "").startswith("ossf/"))
                self.assertEqual(score["id"], "scorecard")
                self.assertEqual(score["with"]["results_file"], REPORT)
                for consumer in self.consumers(workflow):
                    key = "path" if "path" in consumer["with"] else "sarif_file"
                    self.assertEqual(consumer["with"][key], REPORT)
                    self.assertIn(HASH, consumer["if"])

    def test_failure_before_output_cannot_upload_seeded_or_previous_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            for filename in (
                "results.sarif",
                FRESH.replace("-2.sarif", "-1.sarif"),
                FRESH.replace("-12345-", "-12344-"),
                FRESH.replace("a" * 40, "b" * 40),
            ):
                (workspace / filename).write_text(SARIF)
            for workflow in ("scorecard", "scorecard-publish"):
                for consumer in self.consumers(workflow):
                    with self.subTest(workflow=workflow, consumer=consumer["name"]):
                        self.assertFalse(
                            permits_upload(consumer["if"], workspace, "failure")
                        )
                        self.assertFalse(
                            permits_upload(consumer["if"], workspace, "skipped")
                        )
                        self.assertFalse(
                            permits_upload(consumer["if"], workspace, "success")
                        )

    def test_fresh_pr_report_requires_successful_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / FRESH).write_text(SARIF)
            for consumer in self.consumers("scorecard"):
                with self.subTest(consumer=consumer["name"]):
                    self.assertTrue(
                        permits_upload(consumer["if"], workspace, "success")
                    )
                    self.assertFalse(
                        permits_upload(consumer["if"], workspace, "failure")
                    )
                    self.assertFalse(
                        permits_upload(consumer["if"], workspace, "skipped")
                    )

    def test_publisher_retains_fresh_report_after_publication_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / FRESH).write_text(SARIF)
            for consumer in self.consumers("scorecard-publish"):
                with self.subTest(consumer=consumer["name"]):
                    self.assertTrue(
                        permits_upload(consumer["if"], workspace, "failure")
                    )
                    self.assertTrue(
                        permits_upload(consumer["if"], workspace, "success")
                    )


if __name__ == "__main__":
    unittest.main()
