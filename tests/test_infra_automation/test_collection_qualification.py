"""Evidence integrity checks; recorded real runs do not qualify an arbitrary host."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "docs/verification/infra-automation/16-14/results.json"


class CollectionQualificationTests(unittest.TestCase):
    def setUp(self):
        self.record = json.loads(RECORD.read_text())

    def test_real_matrix_has_all_successful_checks(self):
        self.assertIs(self.record["qualified"], True)
        self.assertEqual(self.record["failed_checks"], [])
        self.assertTrue(all(self.record["checks"].values()))
        cases = {case["case"]: case for case in self.record["cases"]}
        self.assertEqual(
            set(cases),
            {
                "no-change",
                "change",
                "error",
                "sensitive",
                "credential-reflection",
                "credential-key-reflection",
                "output-limit",
                "cancel-at-finalization",
            },
        )
        self.assertEqual(self.record["tool"], "opentofu")
        self.assertEqual(self.record["tool_version"], "1.13.1")
        self.assertTrue(cases["change"]["local_service_acceptance"]["shared_analysis"])
        self.assertTrue(cases["change"]["receiver_receipt"]["real_saved_plan_receipt"])
        self.assertTrue(
            cases["change"]["receiver_receipt"]["canonical_registered_payload"]
        )
        self.assertTrue(cases["change"]["receiver_receipt"]["same_report_identity"])
        for name in (
            "error",
            "sensitive",
            "credential-reflection",
            "credential-key-reflection",
            "cancel-at-finalization",
        ):
            with self.subTest(case=name):
                self.assertFalse(cases[name]["finalizable"])
                self.assertFalse(cases[name]["custody_published"])
                self.assertIsNone(cases[name]["screened_output_digest"])

    def test_changed_runtime_requires_real_requalification(self):
        self.assertTrue(self.record["source_hashes"])
        self.assertTrue(
            {
                "infra_automation/unit_map.py",
                "infra_automation/unit_contracts.py",
                "services/infra_automation_units.py",
                "models/repositories/infra_automation_units.py",
                "infra_automation/trigger_contracts.py",
                "infra_automation/trigger_signing.py",
                "infra_automation/lifecycle.py",
                "infra_automation/state.py",
                "services/infra_automation_trigger_authority.py",
                "services/infra_automation_triggers.py",
                "services/infra_automation_policy.py",
                "infra_automation/operator_recovery.py",
                "infra_automation/retention.py",
                "models/operator_recovery.py",
                "models/receiver_recovery.py",
                "infra_automation/receiver_recovery.py",
                "services/infra_automation_receiver_recovery.py",
                "services/infra_automation_handoffs.py",
                "models/database.py",
                "models/tables.py",
                "migrations/versions/040_add_manifest_retention.py",
                "migrations/versions/041_add_operator_recovery.py",
                "migrations/versions/042_add_receiver_recovery.py",
                "services/identity_service.py",
                "services/infra_automation_snapshots.py",
                "services/infra_automation_engine_service.py",
                "services/infra_automation_engine_support.py",
                "services/project_service.py",
                "models/repositories/infra_automation_triggers.py",
                "config.py",
            }.issubset(self.record["source_hashes"])
        )
        for relative, expected in self.record["source_hashes"].items():
            with self.subTest(source=relative):
                self.assertEqual(
                    "sha256:"
                    + hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(),
                    expected,
                )

    def test_evidence_contains_only_screened_facts(self):
        raw = RECORD.read_bytes()
        for marker in (
            b"synthetic-sensitive-marker",
            b"synthetic-collector-sentinel",
            b"synthetic-public-value",
            b"never-store-grant",
        ):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, raw)
        self.assertTrue(
            any(
                "Terraform" in item and "not qualified" in item
                for item in self.record["limitations"]
            )
        )
