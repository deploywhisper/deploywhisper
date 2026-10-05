"""Public-surface regressions using isolated database and snapshot fixtures."""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from cli.analyze import main
from services.analysis_service import build_analysis_artifacts
from services.artifact_snapshot_service import load_report_artifact
from tests.test_api import test_analyses as analyses_tests

SAFE_PLAYBOOK = (
    b"hosts: all\ntasks:\n  - name: Review deployment\n    debug:\n      msg: safe\n"
)


class PublicAnalysisBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = analyses_tests.AnalysesApiTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        self.project_key = self.fixture.persisted["project"]["project_key"]

        def deterministic(files, **kwargs):
            kwargs.update(
                include_narrative=False,
                allow_llm_assistance=False,
                include_topology_context=False,
                include_incident_context=False,
            )
            return build_analysis_artifacts(files, **kwargs)

        override = patch(
            "services.analysis_service.build_analysis_artifacts",
            side_effect=deterministic,
        )
        override.start()
        self.addCleanup(override.stop)

    def submit(self, files, **headers):
        response = self.fixture.client.post(
            "/api/v1/analyses",
            data={"project_key": self.project_key},
            headers=headers,
            files=[
                ("files", (name, raw, "application/octet-stream"))
                for name, raw in files
            ],
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    def test_api_and_cli_intake_do_not_echo_detected_sensitive_names(self):
        name = "password=synthetic-filename-secret.tf"
        data = self.submit(
            [
                (name, b'resource "aws_instance" "web" {}'),
                ("playbook.yaml", SAFE_PLAYBOOK),
            ]
        )
        self.assertNotIn("synthetic-filename-secret", json.dumps(data))
        self.assertEqual(data["intake"]["items"][0]["status"], "sensitive")
        paths = [
            Path(self.fixture.tempdir.name) / name,
            Path(self.fixture.tempdir.name) / "playbook.yaml",
        ]
        paths[0].write_bytes(b'resource "aws_instance" "web" {}')
        paths[1].write_bytes(SAFE_PLAYBOOK)
        output = io.StringIO()
        with (
            redirect_stdout(output),
            patch.object(
                sys,
                "argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    self.project_key,
                    *map(str, paths),
                ],
            ),
        ):
            with self.assertRaises(SystemExit) as result:
                main()
        self.assertEqual(result.exception.code, 0)
        self.assertNotIn("synthetic-filename-secret", output.getvalue())

    def test_excluded_credentials_cannot_return_through_audit_or_provenance(self):
        secret = "synthetic-excluded-audit-secret"
        data = self.submit(
            [(".env", f"PASSWORD={secret}".encode()), ("playbook.yaml", SAFE_PLAYBOOK)],
            **{"X-DeployWhisper-Actor": secret},
        )
        self.assertNotIn(secret, json.dumps(data))
        detail = self.fixture.client.get(
            f"/api/v1/analyses/{data['persisted_report']['id']}"
        )
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn(secret, detail.text)

    def test_aliases_keep_accepted_files_and_snapshot_lookup_consistent(self):
        secret = b'PASSWORD="playbook.yaml"'
        data = self.submit([(".env", secret), ("playbook.yaml", SAFE_PLAYBOOK)])
        report = data["persisted_report"]
        names = [item["name"] for item in report["submission_manifest"]["items"]]
        self.assertNotIn("playbook.yaml", names)
        self.assertEqual(
            [item["status"] for item in report["submission_manifest"]["items"]],
            ["sensitive", "accepted"],
        )
        self.assertEqual(data["intake"]["items"][1]["name"], names[1])
        self.assertEqual(data["parse_batch"]["files"][0]["file_name"], names[1])
        snapshot = load_report_artifact(report["id"], names[1])
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.content, SAFE_PLAYBOOK.decode())

    def test_encoded_evidence_and_sibling_snapshot_remain_redacted(self):
        secret = "synthetic value"
        source = f'PASSWORD="{secret}"'.encode()
        sibling = f"hosts: all\ntasks:\n  - name: Review {secret}\n    debug:\n      msg: safe\n".encode()
        data = self.submit([(".env", source), ("playbook.yaml", sibling)])
        encoded = json.dumps(data)
        self.assertNotIn(secret, encoded)
        self.assertNotIn("synthetic%20value", encoded)
        report = data["persisted_report"]
        evidence = next(
            item
            for item in report["evidence_items"]
            if item["artifact"] == "playbook.yaml"
        )
        self.assertEqual(evidence["redaction_status"], "redacted")
        self.assertEqual(
            report["submission_manifest"]["items"][1]["redaction_status"], "redacted"
        )
        snapshot = load_report_artifact(report["id"], "playbook.yaml")
        self.assertNotIn(secret, snapshot.content)


if __name__ == "__main__":
    unittest.main()
