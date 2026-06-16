"""Guardrails for maintainer ownership and CODEOWNERS coverage."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
CODEOWNERS = ROOT / ".github" / "CODEOWNERS"
MAINTAINERS = ROOT / "MAINTAINERS.md"

MAJOR_REPOSITORY_AREAS = {
    ".agents": "/.agents/",
    "_bmad": "/_bmad/",
    "_bmad-output": "/_bmad-output/",
    ".github": "/.github/",
    "api": "/api/",
    "analysis": "/analysis/",
    "cli": "/cli/",
    "data": "/data/",
    "docs": "/docs/",
    "evidence": "/evidence/",
    "frontend": "/frontend/",
    "integrations": "/integrations/",
    "llm": "/llm/",
    "migrations": "/migrations/",
    "models": "/models/",
    "parsers": "/parsers/",
    "samples": "/samples/",
    "schemas": "/schemas/",
    "scripts": "/scripts/",
    "services": "/services/",
    "skills": "/skills/",
    "tests": "/tests/",
}

REQUIRED_MAINTAINERS_SECTIONS = (
    "## Current Maintainers",
    "## Maintainer Responsibilities",
    "## Maintainer Areas",
    "## Known Coverage Gaps",
    "## Ownership Updates",
)


def _codeowners_rules() -> dict[str, tuple[str, ...]]:
    rules: dict[str, tuple[str, ...]] = {}
    for line in CODEOWNERS.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        pattern, *owners = stripped.split()
        rules[pattern] = tuple(owners)
    return rules


class MaintainerOwnershipTests(unittest.TestCase):
    """Verify public maintainer ownership stays actionable."""

    def test_codeowners_routes_major_repository_areas(self) -> None:
        rules = _codeowners_rules()
        missing = [
            area
            for area, pattern in MAJOR_REPOSITORY_AREAS.items()
            if pattern not in rules or not rules[pattern]
        ]

        self.assertEqual([], missing)

    def test_maintainers_document_exists_and_explains_process(self) -> None:
        self.assertTrue(MAINTAINERS.is_file())

        content = MAINTAINERS.read_text(encoding="utf-8")
        missing_sections = [
            section
            for section in REQUIRED_MAINTAINERS_SECTIONS
            if section not in content
        ]

        self.assertEqual([], missing_sections)
        self.assertIn("@pramodksahoo", content)
        self.assertRegex(content.lower(), r"\breview\b")
        self.assertRegex(content.lower(), r"\bsecurity\b")
        self.assertRegex(content.lower(), r"\bcoverage gap")

    def test_maintainers_document_maps_codeowners_areas(self) -> None:
        content = MAINTAINERS.read_text(encoding="utf-8")
        missing = [
            area
            for area in MAJOR_REPOSITORY_AREAS
            if not re.search(rf"`{re.escape(area)}`|`/{re.escape(area)}/`", content)
        ]

        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
