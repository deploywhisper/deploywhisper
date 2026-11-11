"""Qualification inventories fail closed on missing, stale or substituted proof."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from scripts import qualification_manifest as manifest


class ReleaseQualificationManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        catalog = self.root / manifest.CATALOG
        catalog.parent.mkdir(parents=True)
        catalog.write_bytes((manifest.ROOT / manifest.CATALOG).read_bytes())
        self.value = manifest.template(self.root, "a" * 40)

    def complete(self):
        self.value["build"]["image_digest"] = "sha256:" + "b" * 64
        (self.root / "proof.json").write_text('{"test": "synthetic proof"}')
        proof = {
            "path": "proof.json",
            "sha256": manifest.digest((self.root / "proof.json").read_bytes()),
            "command": "synthetic-check",
            "exit_code": 0,
            "scope": "synthetic validator test, not real qualification",
            "verified_by": "synthetic reviewer",
            **self.value["build"],
        }
        for row in self.value["requirements"] + self.value["gates"]:
            row.update(status="passed", evidence=[deepcopy(proof)])

    def test_template_keeps_all_requirements_and_gates_unexecuted(self):
        result = manifest.validate(self.value, self.root)
        self.assertEqual(len(result["blockers"]), 82)
        self.assertFalse(result["inventory_complete"])
        self.assertFalse(result["publication_authorized"])

    def test_complete_inventory_never_authorizes_publication(self):
        self.complete()
        result = manifest.validate(self.value, self.root)
        self.assertTrue(result["inventory_complete"])
        self.assertFalse(result["publication_authorized"])

    def test_missing_duplicate_unknown_requirement_or_gate_rejects(self):
        for section in ("requirements", "gates"):
            for mutation in ("missing", "duplicate", "unknown"):
                value = deepcopy(self.value)
                if mutation == "missing":
                    value[section].pop()
                elif mutation == "duplicate":
                    value[section][-1] = value[section][0]
                else:
                    value[section][-1]["id"] = "unknown"
                with self.subTest(section=section, mutation=mutation):
                    with self.assertRaises(ValueError):
                        manifest.validate(value, self.root)

    def test_file_presence_or_status_alone_does_not_pass(self):
        (self.root / "proof.json").write_text("present")
        self.value["requirements"][0]["status"] = "passed"
        with self.assertRaises(ValueError):
            manifest.validate(self.value, self.root)

    def test_tampered_or_missing_evidence_rejects(self):
        self.complete()
        (self.root / "proof.json").write_text("tampered")
        with self.assertRaises(ValueError):
            manifest.validate(self.value, self.root)
        (self.root / "proof.json").unlink()
        with self.assertRaises(ValueError):
            manifest.validate(self.value, self.root)

    def test_changed_catalog_rejects(self):
        path = self.root / manifest.CATALOG
        path.write_text(path.read_text() + "\n")
        with self.assertRaises(ValueError):
            manifest.validate(self.value, self.root)

    def test_wrong_build_failed_command_or_missing_attribution_rejects(self):
        self.complete()
        for key, value in (
            ("source_commit", "c" * 40),
            ("image_digest", "sha256:" + "d" * 64),
            ("exit_code", 1),
            ("exit_code", False),
            ("verified_by", ""),
            ("scope", ""),
            ("command", ""),
        ):
            changed = deepcopy(self.value)
            changed["requirements"][0]["evidence"][0][key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    manifest.validate(changed, self.root)

    def test_absolute_traversal_and_symlink_evidence_reject(self):
        self.complete()
        (self.root / "alias.json").symlink_to(self.root / "proof.json")
        for path in (
            str(self.root / "proof.json"),
            "../proof.json",
            "./proof.json",
            "alias.json",
        ):
            changed = deepcopy(self.value)
            changed["requirements"][0]["evidence"][0]["path"] = path
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    manifest.validate(changed, self.root)

    def test_duplicate_json_keys_reject(self):
        path = self.root / "bad.json"
        path.write_text('{"status":"failed","status":"passed"}')
        with self.assertRaises(ValueError):
            manifest.read_json(path)

    def test_failed_gate_keeps_otherwise_complete_inventory_blocked(self):
        self.complete()
        self.value["gates"][0]["status"] = "failed"
        self.assertEqual(
            manifest.validate(self.value, self.root)["blockers"], [manifest.GATES[0]]
        )

    def test_serialized_template_round_trip(self):
        path = self.root / "manifest.json"
        path.write_text(json.dumps(self.value))
        self.assertEqual(manifest.read_json(path), self.value)
