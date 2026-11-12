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
        groups = self.root / manifest.EVIDENCE_GROUPS
        groups.parent.mkdir(parents=True, exist_ok=True)
        groups.write_bytes((manifest.ROOT / manifest.EVIDENCE_GROUPS).read_bytes())
        owners = self.root / ".github/CODEOWNERS"
        owners.parent.mkdir(parents=True)
        owners.write_text("* @reviewer\n")
        self.value = manifest.template(self.root, "a" * 40)
        self.first_proof = None

    def complete(self):
        self.value["build"]["image_digest"] = "sha256:" + "b" * 64
        requirement_paths = manifest.requirement_evidence(self.root)

        def proof(path, *, waiver=False):
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_text('{"test":"synthetic proof"}\n')
            self.first_proof = self.first_proof or target
            return {
                "path": path,
                "sha256": manifest.digest(target.read_bytes()),
                "command": "synthetic-check",
                "exit_code": 0,
                "scope": (
                    "waiver_kind=accountable-maintainer synthetic-test"
                    if waiver
                    else "synthetic validator test, not real qualification"
                ),
                "verified_by": (
                    "accountable-maintainer:psaho01" if waiver else "synthetic reviewer"
                ),
                **self.value["build"],
            }

        for row in self.value["requirements"]:
            row.update(
                status="passed",
                evidence=[proof(sorted(requirement_paths[row["id"]])[0])],
            )
        for row in self.value["gates"]:
            path = sorted(manifest.GATE_EVIDENCE[row["id"]])[0]
            row.update(
                status="passed",
                evidence=[
                    proof(
                        path,
                        waiver=row["id"] == "operator-pilot-or-maintainer-waiver",
                    )
                ],
            )

    def approval(self, **changes):
        value = {
            "repository": "example/deploywhisper",
            "source_commit": "c" * 40,
            "pull_request": 123,
            "reviewer_login": "reviewer",
            "review_state": "APPROVED",
            "codeowners_sha256": manifest.digest(
                (self.root / ".github/CODEOWNERS").read_bytes()
            ),
            "collected_by": "github-actions",
        }
        value.update(changes)
        return value

    def test_template_keeps_all_requirements_and_gates_unexecuted(self):
        self.assertIn("operator-pilot-or-maintainer-waiver", manifest.GATES)
        self.assertNotIn("independent-human-pilot", manifest.GATES)
        result = manifest.validate(self.value, self.root)
        self.assertEqual(len(result["blockers"]), 82)
        self.assertFalse(result["inventory_complete"])
        self.assertFalse(result["publication_authorized"])

    def test_complete_inventory_never_authorizes_publication(self):
        self.complete()
        result = manifest.validate(self.value, self.root)
        self.assertTrue(result["inventory_complete"])
        self.assertFalse(result["release_gate_passed"])
        self.assertFalse(result["publication_authorized"])

    def test_trusted_workflow_finalization_binds_source_image_and_approval(self):
        self.complete()
        final = manifest.finalize(
            self.value,
            self.root,
            source_commit="c" * 40,
            image_digest="sha256:" + "d" * 64,
            repository="example/deploywhisper",
            workflow_ref="refs/tags/v1.5.0",
            run_id="1234",
            codeowners_approval=self.approval(),
            changed_paths=(),
        )
        result = manifest.validate(
            final,
            self.root,
            expected_source_commit="c" * 40,
            expected_image_digest="sha256:" + "d" * 64,
            require_final=True,
            changed_paths=(),
        )
        self.assertTrue(result["release_gate_passed"])
        self.assertFalse(result["publication_authorized"])
        self.assertTrue(
            all(
                item["source_commit"] == "a" * 40
                and item["image_digest"] == "sha256:" + "b" * 64
                for row in final["requirements"] + final["gates"]
                for item in row["evidence"]
            )
        )

    def test_finalization_rejects_untrusted_or_wrong_codeowner_receipt(self):
        self.complete()
        for changes in (
            {"reviewer_login": "outsider"},
            {"review_state": "CHANGES_REQUESTED"},
            {"source_commit": "e" * 40},
            {"collected_by": "local-shell"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                manifest.finalize(
                    self.value,
                    self.root,
                    source_commit="c" * 40,
                    image_digest="sha256:" + "d" * 64,
                    repository="example/deploywhisper",
                    workflow_ref="refs/tags/v1.5.0",
                    run_id="1234",
                    codeowners_approval=self.approval(**changes),
                    changed_paths=(),
                )

    def test_finalization_refuses_open_qualification_blockers(self):
        self.complete()
        self.value["requirements"][0]["status"] = "failed"
        with self.assertRaisesRegex(ValueError, "blockers"):
            manifest.finalize(
                self.value,
                self.root,
                source_commit="c" * 40,
                image_digest="sha256:" + "d" * 64,
                repository="example/deploywhisper",
                workflow_ref="refs/tags/v1.5.0",
                run_id="1234",
                codeowners_approval=self.approval(),
                changed_paths=(),
            )

    def test_finalization_rejects_runtime_changes_after_evidence_source(self):
        self.complete()
        with self.assertRaisesRegex(ValueError, "Runtime source changed"):
            manifest.finalize(
                self.value,
                self.root,
                source_commit="c" * 40,
                image_digest="sha256:" + "d" * 64,
                repository="example/deploywhisper",
                workflow_ref="refs/tags/v1.5.0",
                run_id="1234",
                codeowners_approval=self.approval(),
                changed_paths=("services/infra_automation_material_authority.py",),
            )

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
        self.first_proof.write_text("tampered")
        with self.assertRaises(ValueError):
            manifest.validate(self.value, self.root)
        self.first_proof.unlink()
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
        (self.root / "alias.json").symlink_to(self.first_proof)
        for path in (
            str(self.first_proof),
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

    def test_waiver_gate_rejects_generic_self_assertion(self):
        self.complete()
        waiver = next(
            row
            for row in self.value["gates"]
            if row["id"] == "operator-pilot-or-maintainer-waiver"
        )
        waiver["evidence"][0]["verified_by"] = "generic branch author"
        with self.assertRaises(ValueError):
            manifest.validate(self.value, self.root)

    def test_serialized_template_round_trip(self):
        path = self.root / "manifest.json"
        path.write_text(json.dumps(self.value))
        self.assertEqual(manifest.read_json(path), self.value)
