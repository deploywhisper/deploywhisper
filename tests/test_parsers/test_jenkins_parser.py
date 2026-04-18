"""Tests for Jenkins parser normalization behavior."""

from __future__ import annotations

import unittest

from parsers.jenkins_parser import parse_jenkins


class JenkinsParserTests(unittest.TestCase):
    def test_parse_jenkins_returns_empty_list_when_content_missing(self) -> None:
        self.assertEqual(parse_jenkins("Jenkinsfile", None), [])

    def test_parse_jenkins_extracts_each_stage_name(self) -> None:
        raw = b"""
pipeline {
  stages {
    stage('Build') { steps { echo 'build' } }
    stage("Deploy") { steps { echo 'deploy' } }
  }
}
"""

        changes = parse_jenkins("Jenkinsfile", raw)

        self.assertEqual(
            [change.resource_id for change in changes], ["stage/Build", "stage/Deploy"]
        )
        self.assertIn("Jenkins stage Build", changes[0].summary)

    def test_parse_jenkins_falls_back_to_pipeline_change_when_no_stages_found(
        self,
    ) -> None:
        raw = b"pipeline { agent any }"

        changes = parse_jenkins("Jenkinsfile", raw)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].resource_id, "pipeline")
        self.assertIn("pipeline included in analysis set", changes[0].summary)


if __name__ == "__main__":
    unittest.main()
