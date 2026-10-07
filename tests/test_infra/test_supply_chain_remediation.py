"""Guard dependency-update coverage and least-privilege delivery boundaries."""

from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import yaml

from scripts.refresh_skill_analytics import (
    fetch_active_issue_counts,
    fetch_popularity_metrics,
)


class SupplyChainRemediationTests(unittest.TestCase):
    def workflow(self, name):
        return yaml.load(
            Path(f".github/workflows/{name}.yml").read_text(), Loader=yaml.BaseLoader
        )

    def test_dependency_updates_cover_all_manifests_and_target_develop(self):
        data = yaml.load(
            Path(".github/dependabot.yml").read_text(), Loader=yaml.BaseLoader
        )
        updates = data["updates"]
        self.assertEqual(
            {(u["package-ecosystem"], u["directory"]) for u in updates},
            {
                ("pip", "/"),
                ("npm", "/"),
                ("npm", "/frontend"),
                ("github-actions", "/"),
                ("docker", "/"),
                ("docker", "/.clusterfuzzlite"),
                ("pip", "/.clusterfuzzlite"),
            },
        )
        for update in updates:
            self.assertEqual(update["target-branch"], "develop")
            self.assertEqual(update["schedule"]["interval"], "weekly")

    def test_release_write_scopes_are_limited_to_publishers(self):
        data = self.workflow("release")
        self.assertEqual(data["permissions"], {"contents": "read"})
        for name, job in data["jobs"].items():
            permissions = job.get("permissions", data["permissions"])
            expected = {"contents": "read"}
            if name == "docker":
                expected = {
                    "contents": "read",
                    "packages": "write",
                    "id-token": "write",
                    "attestations": "write",
                    "artifact-metadata": "write",
                }
            elif name == "release":
                expected = {"contents": "write", "packages": "write"}
            elif name == "artifacts":
                expected = {
                    "contents": "read",
                    "id-token": "write",
                    "attestations": "write",
                    "artifact-metadata": "write",
                }
            with self.subTest(job=name):
                self.assertEqual(permissions, expected)

    def test_ci_requires_no_write_token_and_audits_both_npm_graphs(self):
        data = self.workflow("ci")
        self.assertEqual(data["permissions"], {"contents": "read"})
        for job in data["jobs"].values():
            self.assertNotIn("write", job.get("permissions", {}).values())
        scripts = "\n".join(s.get("run", "") for s in data["jobs"]["frontend"]["steps"])
        self.assertIn("npm audit --audit-level=low", scripts)
        self.assertIn("npm audit --prefix frontend --audit-level=low", scripts)

    def test_analytics_defaults_read_only_and_limits_committed_paths(self):
        data = self.workflow("refresh-skill-analytics")
        self.assertEqual(data["permissions"], {"contents": "read"})
        self.assertEqual(
            data["jobs"]["refresh"]["permissions"],
            {"contents": "write", "issues": "read"},
        )
        scripts = "\n".join(s.get("run", "") for s in data["jobs"]["refresh"]["steps"])
        self.assertIn("git add data/skill-analytics.json", scripts)
        self.assertIn("git diff --quiet -- data/skill-analytics.json", scripts)

    def test_popularity_feed_never_receives_github_token(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {"skills": {}}
        ).encode()
        with patch(
            "scripts.refresh_skill_analytics.request.urlopen", return_value=response
        ) as call:
            fetch_popularity_metrics(
                "https://metrics.example.test/feed.json", token="synthetic-test-marker"
            )
        self.assertNotIn("Authorization", dict(call.call_args.args[0].header_items()))

    def test_github_issue_lookup_retains_authorization(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"total_count": 2}'
        with patch(
            "scripts.refresh_skill_analytics.request.urlopen", return_value=response
        ) as call:
            self.assertEqual(
                fetch_active_issue_counts(
                    ["terraform"], repo="example/project", token="synthetic-test-marker"
                ),
                {"terraform": 2},
            )
        self.assertEqual(
            call.call_args.args[0].get_header("Authorization"),
            "Bearer synthetic-test-marker",
        )


if __name__ == "__main__":
    unittest.main()
