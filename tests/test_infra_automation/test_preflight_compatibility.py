"""Legacy consumers ignore descriptive provenance without changing advisory output."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from api.schemas import PersistedReportData
from infra_automation.preflight_contracts import UploadedProvenance
from services.agent_interface_service import build_agent_report_data
from services.analysis_service import build_share_summary
from services.report_service import (
    REPORT_SCHEMA_VERSION,
    build_share_report_link,
    can_read_report_schema,
    normalize_report_schema_version,
)
from tests.test_api import test_schemas as schema_tests

ROOT = Path(__file__).resolve().parents[2]


class PreflightCompatibilityTests(unittest.TestCase):
    def report_fixture(self, version):
        # Reuse the existing public API schema fixture without inheriting its tests.
        value = schema_tests.ApiSchemaTests()._persisted_report_payload()
        value.update(confidence=0.52, report_schema_version=version)
        return value

    def test_v1_v2_consumers_keep_output_for_absent_known_and_future_provenance(self):
        provenance_cases = (
            None,
            UploadedProvenance().model_dump(mode="json"),
            {"version": 99, "deployment_approval": True, "should_block": True},
        )
        with patch.dict("os.environ", {"APP_BASE_URL": "https://preflight.invalid"}):
            for version in ("v1", "v2"):
                original = self.report_fixture(version)
                expected_report = PersistedReportData.model_validate(
                    original
                ).model_dump(mode="json")
                expected_agent = build_agent_report_data(original).model_dump(
                    mode="json"
                )
                expected_share = build_share_summary(original).model_dump(mode="json")
                for provenance in provenance_cases:
                    with self.subTest(report_version=version, provenance=provenance):
                        report = copy.deepcopy(original)
                        if provenance is not None:
                            report["infra_automation_provenance"] = copy.deepcopy(
                                provenance
                            )
                        before = copy.deepcopy(report)
                        public = PersistedReportData.model_validate(report).model_dump(
                            mode="json"
                        )
                        agent = build_agent_report_data(report).model_dump(mode="json")
                        shared = build_share_summary(report).model_dump(mode="json")
                        self.assertEqual(public, expected_report)
                        self.assertEqual(agent, expected_agent)
                        self.assertEqual(shared, expected_share)
                        self.assertEqual(report, before)
                        self.assertNotIn("infra_automation_provenance", public)
                        self.assertNotIn("infra_automation_provenance", agent)
                        self.assertFalse(public["advisory"]["should_block"])
                        self.assertFalse(agent["deployment_approval"])
                        self.assertTrue(agent["human_decision_required"])
                        self.assertEqual(agent["schema_version"], "v1")
                        self.assertEqual(agent["report_schema_version"], version)
                        self.assertEqual(
                            shared["json_payload"]["report_link"],
                            "https://preflight.invalid/reports/17",
                        )
                        self.assertEqual(
                            build_share_report_link(public["id"]),
                            shared["json_payload"]["report_link"],
                        )

    def test_schema_readers_keep_legacy_default_without_minor_report_bump(self):
        self.assertEqual(REPORT_SCHEMA_VERSION, "v2")
        for stored in (None, "", "v1", " v1 ", "v2"):
            with self.subTest(stored=stored):
                expected = "v2" if stored == "v2" else "v1"
                self.assertEqual(normalize_report_schema_version(stored), expected)
                self.assertTrue(can_read_report_schema("v2", stored))
        self.assertTrue(can_read_report_schema("v1", None))
        self.assertFalse(can_read_report_schema("v1", "v2"))
        self.assertFalse(can_read_report_schema("v2", "v99"))
        self.assertFalse(can_read_report_schema("v2", "v2.1"))

    def test_frozen_protocol_manifests_and_every_referenced_byte_are_unchanged(self):
        manifests = {
            "frozen-v1.json": "c833be7385dd410b04561f581c8747b211ff1b071818302037fa64a0b1a44332",
            "workflow-v2-manifest.json": "d4c66007fc16779927c0ce0b1c12a52bde0ea5839c53ab04323a7968f713d687",
        }
        for name, expected_manifest_digest in manifests.items():
            path = ROOT / "schemas/infra-automation" / name
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), expected_manifest_digest
            )
            manifest = json.loads(path.read_text())
            for relative_path, expected in manifest["files"].items():
                with self.subTest(manifest=name, path=relative_path):
                    self.assertEqual(
                        "sha256:"
                        + hashlib.sha256(
                            (ROOT / relative_path).read_bytes()
                        ).hexdigest(),
                        expected,
                    )
        self.assertEqual(manifest["independent_protocol_versions"]["provenance"], 1)
        self.assertEqual(manifest["independent_protocol_versions"]["report"], 2)

    def test_existing_cli_json_and_agent_probes_keep_all_six_metadata_vectors(self):
        # Run the frozen actual-CLI consumer probe in its own process: its existing
        # temporary DB/config reload fixtures must not leak into this test process.
        probe = (
            ROOT
            / "tests/fixtures/infra_automation/qualification/16_0/contracts/cli_consumer_probe.py"
        )
        result = subprocess.run(
            [sys.executable, str(probe)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertTrue(evidence["passed"])
        self.assertEqual(evidence["cases"], 6)
