"""End-to-end shared-core regressions for submitted credential boundaries."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from services.analysis_service import build_analysis_artifacts

RUNTIME = {
    "provider": "openai",
    "model": "gpt-4.1-mini",
    "api_base": "https://api.openai.com/v1",
    "api_key": "synthetic-provider-key",
    "local_mode": False,
}


class AnalysisContentBoundaryTests(unittest.TestCase):
    def test_sensitive_confidence_output_retains_an_explicit_warning(self):
        from llm.providers import SENSITIVE_RESPONSE_NOTICE

        captured = []

        def completion(**kwargs):
            payload = json.loads(kwargs["messages"][-1]["content"])["untrusted_data"]
            captured.append(payload)
            if "interactions" in payload:
                return json.dumps(
                    {"confidences": [], "debug": "PASSWORD=synthetic-sensitive-output"}
                )
            if "findings" in payload:
                return json.dumps(
                    {
                        "opening_sentence": payload["recommendation"].upper()
                        + ": review the change.",
                        "explanation": "Verify the deployment.",
                        "guidance": [],
                    }
                )
            return json.dumps({"change_scores": []})

        with (
            patch(
                "analysis.risk_scorer.resolve_provider_runtime", return_value=RUNTIME
            ),
            patch(
                "services.analysis_service.resolve_provider_runtime",
                return_value=RUNTIME,
            ),
            patch("llm.narrator.resolve_provider_runtime", return_value=RUNTIME),
        ):
            result = build_analysis_artifacts(
                [
                    ("main.tf", b'resource "aws_instance" "payments" {}'),
                    (
                        "Jenkinsfile",
                        b'pipeline { stages { stage("payments") { steps { echo "safe" } } } }',
                    ),
                ],
                completion_client=completion,
                include_topology_context=False,
                include_incident_context=False,
            )
        self.assertEqual(len(captured), 3)
        self.assertTrue(
            any(
                SENSITIVE_RESPONSE_NOTICE in warning
                for warning in result.assessment.warnings
            )
        )
        self.assertNotIn("synthetic-sensitive-output", result.model_dump_json())

    def test_credential_bearing_artifact_name_is_excluded_before_parsing(self):
        from services.intake_service import build_pending_analysis, build_parse_batch
        from services.artifact_snapshot_service import save_report_artifacts
        from pathlib import Path
        from types import SimpleNamespace
        import tempfile

        name = "password=synthetic-name.tf"
        files = [(name, b'resource "aws_instance" "web" {}')]
        pending = build_pending_analysis(files)
        self.assertEqual(pending.items[0].status, "sensitive")
        self.assertEqual(build_parse_batch(files).files, [])
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "services.artifact_snapshot_service.settings",
                SimpleNamespace(artifact_snapshot_dir=directory),
            ),
        ):
            save_report_artifacts(1, dict(files))
            for path in Path(directory).rglob("*"):
                if path.is_file():
                    self.assertNotIn("synthetic-name", path.read_text())

    def test_every_hosted_call_screens_values_from_failed_and_excluded_inputs(self):
        for name, raw in (
            (
                "broken.tf",
                b'password="synthetic-opaque-value"\nresource "aws_instance" "broken" {',
            ),
            (".env", b'PASSWORD="synthetic-opaque-value"'),
        ):
            with self.subTest(name=name):
                self._assert_input_secret_protected(name, raw)

    def test_standard_multiline_secret_cannot_leak_through_sibling_artifact(self):
        self._assert_input_secret_protected(
            "secret.yaml",
            b"apiVersion: v1\nkind: Secret\nmetadata:\n  name: sample\nstringData:\n  opaque: |\n    synthetic-opaque-value\n",
        )

    def _assert_input_secret_protected(self, name: str, raw: bytes):
        secret = "synthetic-opaque-value"
        captured = []

        def completion(**kwargs):
            captured.append(kwargs["messages"])
            return json.dumps(
                {
                    "change_scores": [],
                    "opening_sentence": "CAUTION: review the change.",
                    "explanation": "Verify the deployment.",
                    "guidance": [],
                }
            )

        playbook = f"hosts: all\ntasks:\n  - name: Review {secret}\n    debug:\n      msg: safe\n".encode()
        with (
            patch(
                "analysis.risk_scorer.resolve_provider_runtime", return_value=RUNTIME
            ),
            patch("llm.narrator.resolve_provider_runtime", return_value=RUNTIME),
            patch(
                "services.analysis_service.resolve_provider_runtime",
                return_value=RUNTIME,
            ),
        ):
            result = build_analysis_artifacts(
                [(name, raw), ("playbook.yaml", playbook)],
                completion_client=completion,
                include_topology_context=False,
                include_incident_context=False,
            )
        self.assertGreaterEqual(len(captured), 2)
        for messages in captured:
            self.assertNotIn(secret, json.dumps(messages))
        self.assertNotIn(secret, result.model_dump_json())
        self.assertEqual(
            result.submission_manifest.items[0].redaction_status,
            "sensitive_blocked" if name == ".env" else "redacted",
        )

    def test_large_benign_supported_submission_retains_valid_report_structure(self):
        count = 300
        raw = (
            "hosts: all\ntasks:\n"
            + "".join(
                f"  - name: task-{index}\n    debug:\n      msg: safe\n"
                for index in range(count)
            )
        ).encode()
        result = build_analysis_artifacts(
            [("playbook.yaml", raw)],
            include_narrative=False,
            include_topology_context=False,
            include_incident_context=False,
            allow_llm_assistance=False,
        )
        self.assertEqual(len(result.assessment.contributors), count)
        self.assertEqual(len(result.evidence_items), count)
        self.assertTrue(result.rollback_plan.steps)


if __name__ == "__main__":
    unittest.main()
