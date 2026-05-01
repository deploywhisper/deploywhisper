"""Guardrails for public governance and community documentation."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]

REQUIRED_COMMUNITY_FILES = (
    "GOVERNANCE.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "SUPPORT.md",
    "ROADMAP.md",
)

FORBIDDEN_POSTURE_CLAIMS = (
    "saas-only",
    "hosted-only",
    "open core",
    "open-core",
    "enterprise-only",
    "paid feature",
    "proprietary plugin required",
    "commercial edition required",
)


class GovernanceFilesTests(unittest.TestCase):
    """Verify repository-level community files stay present and open."""

    def test_required_community_files_exist(self) -> None:
        missing = [
            name for name in REQUIRED_COMMUNITY_FILES if not (ROOT / name).is_file()
        ]

        self.assertEqual([], missing)

    def test_community_files_do_not_imply_feature_gating(self) -> None:
        violations: list[tuple[str, str]] = []

        for name in REQUIRED_COMMUNITY_FILES:
            path = ROOT / name
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8").lower()
            for phrase in FORBIDDEN_POSTURE_CLAIMS:
                if phrase in content:
                    violations.append((name, phrase))

        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
