"""Guardrails for requirements traceability documentation."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
PRD = ROOT / "_bmad-output" / "planning-artifacts" / "prd.md"
MATRIX = (
    ROOT / "_bmad-output" / "planning-artifacts" / "requirements-traceability-matrix.md"
)

REQUIREMENT_ID = re.compile(r"\*\*([A-Z][A-Z0-9]+(?:-[A-Z]+)?)-\d{2}\*\*")
MATRIX_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|")
ARTIFACT_PATH = re.compile(r"`(_bmad-output/implementation-artifacts/[^`]+\.md)`")


def _prd_requirement_families() -> set[str]:
    return set(REQUIREMENT_ID.findall(PRD.read_text(encoding="utf-8")))


def _matrix_rows() -> list[list[str]]:
    rows: list[list[str]] = []
    for line in MATRIX.read_text(encoding="utf-8").splitlines():
        if not MATRIX_ROW.match(line):
            continue
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


class RequirementsTraceabilityMatrixTests(unittest.TestCase):
    """Verify PRD requirement families stay mapped to implementation epics."""

    def test_matrix_exists_with_required_sections(self) -> None:
        self.assertTrue(MATRIX.is_file())

        content = MATRIX.read_text(encoding="utf-8")
        self.assertIn("## Requirements Family Matrix", content)
        self.assertIn("## Gap, Deferred, and Cross-Cutting Register", content)
        self.assertIn("## Source Documents", content)

    def test_every_prd_requirement_family_has_matrix_row(self) -> None:
        prd_families = _prd_requirement_families()
        matrix_families = {
            row[0].removeprefix("`").removesuffix("`").removesuffix("-*")
            for row in _matrix_rows()
        }

        self.assertEqual(set(), prd_families - matrix_families)

    def test_matrix_rows_map_to_epics_and_classify_status(self) -> None:
        rows = _matrix_rows()
        self.assertNotEqual([], rows)

        missing_epic = []
        missing_artifact = []
        missing_status = []
        missing_notes = []
        for row in rows:
            family = row[0]
            epic_coverage = row[2] if len(row) > 2 else ""
            artifact_coverage = row[3] if len(row) > 3 else ""
            status = row[4] if len(row) > 4 else ""
            notes = row[5] if len(row) > 5 else ""

            if "Epic " not in epic_coverage:
                missing_epic.append(family)
            artifact_paths = ARTIFACT_PATH.findall(artifact_coverage)
            if not artifact_paths:
                missing_artifact.append(family)
            for artifact_path in artifact_paths:
                artifact_file = ROOT / artifact_path
                if not artifact_file.is_file():
                    missing_artifact.append(f"{family}: {artifact_path}")
            if not status:
                missing_status.append(family)
            if not notes:
                missing_notes.append(family)

        self.assertEqual([], missing_epic)
        self.assertEqual([], missing_artifact)
        self.assertEqual([], missing_status)
        self.assertEqual([], missing_notes)

    def test_gap_deferred_and_cross_cutting_terms_are_explicit(self) -> None:
        content = MATRIX.read_text(encoding="utf-8").lower()

        self.assertIn("gap", content)
        self.assertIn("deferred", content)
        self.assertIn("cross-cutting", content)


if __name__ == "__main__":
    unittest.main()
