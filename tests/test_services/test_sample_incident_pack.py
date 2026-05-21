"""Tests for the safe sample incident pack."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.incident_service as incident_service_module
import services.project_service as project_service_module
import services.sample_incident_pack as sample_incident_pack_module


class SampleIncidentPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "sample-incidents.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        reload(incident_service_module)
        reload(sample_incident_pack_module)
        database_module.init_db()
        self.project = project_service_module.create_project(
            project_key="demo",
            display_name="Demo",
        )

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_sample_pack_inspection_passes_safety_contract(self) -> None:
        inspection = sample_incident_pack_module.inspect_sample_incident_pack()

        self.assertTrue(inspection.safe, inspection.errors)
        self.assertEqual(inspection.pack_id, "safe-sample-incidents-v1")
        self.assertFalse(inspection.loaded_by_default)
        self.assertGreaterEqual(len(inspection.records), 3)
        self.assertTrue(inspection.provenance)
        self.assertTrue(inspection.limitations)
        for record in inspection.records:
            self.assertTrue(record.sample)
            self.assertTrue(record.provenance)
            self.assertTrue(record.permission)
            self.assertFalse(record.contains_real_customer_data)
            self.assertFalse(record.contains_real_organization_names)
            self.assertFalse(record.contains_non_public_postmortem)

    def test_sample_pack_inspection_rejects_unsafe_demo_content(self) -> None:
        inspection = sample_incident_pack_module.inspect_sample_incident_documents(
            {
                "unsafe.md": (
                    "# Sample incident: unsafe\n"
                    "Sample data: yes\n"
                    "Provenance: Synthetic scenario authored for this sample pack.\n"
                    "Permission: Original synthetic documentation content.\n"
                    "Contains real customer data: no\n"
                    "Contains real organization names: no\n"
                    "Contains non-public postmortem content: no\n\n"
                    "The outage affected Google and alice@gmail.com from 8.8.8.8."
                )
            }
        )

        self.assertFalse(inspection.safe)
        self.assertTrue(
            any("real organization" in error.lower() for error in inspection.errors),
            inspection.errors,
        )
        self.assertTrue(
            any("email" in error.lower() for error in inspection.errors),
            inspection.errors,
        )
        self.assertTrue(
            any("ip address" in error.lower() for error in inspection.errors),
            inspection.errors,
        )

    def test_sample_pack_inspection_rejects_project_name_in_record_content(
        self,
    ) -> None:
        inspection = sample_incident_pack_module.inspect_sample_incident_documents(
            {
                "unsafe.md": (
                    "# Sample incident: unsafe\n"
                    "Sample data: yes\n"
                    "Provenance: Synthetic scenario authored for DeployWhisper.\n"
                    "Permission: Original synthetic documentation content.\n"
                    "Contains real customer data: no\n"
                    "Contains real organization names: no\n"
                    "Contains non-public postmortem content: no\n\n"
                    "A synthetic rollout failed."
                )
            }
        )

        self.assertFalse(inspection.safe)
        self.assertTrue(
            any("deploywhisper" in error.lower() for error in inspection.errors),
            inspection.errors,
        )

    def test_sample_pack_inspection_rejects_vendor_toolchain_names(self) -> None:
        inspection = sample_incident_pack_module.inspect_sample_incident_documents(
            {
                "unsafe.md": (
                    "# Sample incident: unsafe\n"
                    "Sample data: yes\n"
                    "Provenance: Synthetic scenario authored for this sample pack.\n"
                    "Permission: Original synthetic documentation content.\n"
                    "Contains real customer data: no\n"
                    "Contains real organization names: no\n"
                    "Contains non-public postmortem content: no\n\n"
                    "Limitations:\n"
                    "- Synthetic demo record.\n\n"
                    "A Terraform change updated aws_security_group_rule.example."
                )
            }
        )

        self.assertFalse(inspection.safe)
        self.assertTrue(
            any("terraform" in error.lower() for error in inspection.errors),
            inspection.errors,
        )
        self.assertTrue(
            any(
                "aws_security_group_rule" in error.lower()
                for error in inspection.errors
            ),
            inspection.errors,
        )

    def test_sample_pack_inspection_rejects_project_name_in_manifest_metadata(
        self,
    ) -> None:
        pack_dir = Path(self.tempdir.name) / "unsafe-pack"
        pack_dir.mkdir()
        (pack_dir / "manifest.json").write_text(
            """{
  "pack_id": "unsafe-pack",
  "title": "Unsafe Pack",
  "sample": true,
  "loaded_by_default": false,
  "provenance": "Original synthetic incidents authored for DeployWhisper.",
  "limitations": ["Only for demos."],
  "records": [{"source_file": "incident.md"}]
}""",
            encoding="utf-8",
        )
        (pack_dir / "incident.md").write_text(
            "# Sample incident: safe declarations\n"
            "Sample data: yes\n"
            "Provenance: Synthetic scenario authored for this sample pack.\n"
            "Permission: Original synthetic documentation content.\n"
            "Contains real customer data: no\n"
            "Contains real organization names: no\n"
            "Contains non-public postmortem content: no\n\n"
            "Limitations:\n"
            "- Synthetic demo record.\n",
            encoding="utf-8",
        )

        inspection = sample_incident_pack_module.inspect_sample_incident_pack(pack_dir)

        self.assertFalse(inspection.safe)
        self.assertTrue(
            any("deploywhisper" in error.lower() for error in inspection.errors),
            inspection.errors,
        )

    def test_sample_pack_loads_only_by_explicit_project_scope(self) -> None:
        load_result = sample_incident_pack_module.load_safe_sample_incident_pack(
            project_id=self.project.id
        )

        records = incident_service_module.get_incident_records(
            project_id=self.project.id
        )
        self.assertEqual(load_result["loaded"], len(load_result["records"]))
        self.assertEqual(len(records), load_result["loaded"])
        self.assertGreaterEqual(len(records), 3)
        self.assertTrue(
            all(record["title"].startswith("Sample incident:") for record in records)
        )
        self.assertTrue(
            all("Sample data: yes" in record["content"] for record in records)
        )

    def test_sample_pack_load_requires_project_scope(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            sample_incident_pack_module.load_safe_sample_incident_pack()

        self.assertIn("Project scope is required", str(ctx.exception))

    def test_sample_pack_documentation_explains_provenance_and_limitations(
        self,
    ) -> None:
        docs = Path("docs/sample-incident-pack.md").read_text(encoding="utf-8")

        self.assertIn("Provenance", docs)
        self.assertIn("not copied from customer data", docs)
        self.assertIn("not loaded by default", docs)
        self.assertIn("Limitations", docs)


if __name__ == "__main__":
    unittest.main()
