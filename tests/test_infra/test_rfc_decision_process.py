"""Guardrails for the public RFC and decision process."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
RFC_PROCESS = ROOT / "docs" / "rfcs" / "README.md"
RFC_TEMPLATE = ROOT / "docs" / "rfcs" / "0000-template.md"
GOVERNANCE = ROOT / "GOVERNANCE.md"

REQUIRED_PROCESS_TERMS = (
    "architecture",
    "governance",
    "security",
    "roadmap",
)

REQUIRED_TEMPLATE_HEADINGS = (
    "## Summary",
    "## Motivation",
    "## PRD and Architecture Links",
    "## Detailed Design",
    "## Security and Privacy",
    "## Compatibility and Migration",
    "## Alternatives Considered",
    "## Review Plan",
    "## Decision Record",
)

REQUIRED_DECISION_STATES = ("proposed", "accepted", "rejected", "withdrawn")


def _normalized(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8").lower())


class RfcDecisionProcessTests(unittest.TestCase):
    """Verify major public decisions stay traceable to planning artifacts."""

    def test_rfc_process_and_template_exist(self) -> None:
        self.assertTrue(RFC_PROCESS.is_file())
        self.assertTrue(RFC_TEMPLATE.is_file())

    def test_rfc_process_defines_when_rfc_is_required(self) -> None:
        content = _normalized(RFC_PROCESS)

        missing_terms = [term for term in REQUIRED_PROCESS_TERMS if term not in content]

        self.assertEqual([], missing_terms)
        self.assertIn("major", content)
        self.assertIn("rfc", content)

    def test_rfc_template_defines_required_sections(self) -> None:
        content = RFC_TEMPLATE.read_text(encoding="utf-8")
        missing_headings = [
            heading for heading in REQUIRED_TEMPLATE_HEADINGS if heading not in content
        ]

        self.assertEqual([], missing_headings)

    def test_review_expectations_and_decision_recording_are_explicit(self) -> None:
        content = _normalized(RFC_PROCESS)
        missing_states = [
            state for state in REQUIRED_DECISION_STATES if state not in content
        ]

        self.assertEqual([], missing_states)
        self.assertIn("codeowners", content)
        self.assertIn("review window", content)
        self.assertIn("decision record", content)

    def test_accepted_decisions_must_link_to_prd_or_architecture(self) -> None:
        content = _normalized(RFC_PROCESS)

        self.assertRegex(content, r"accepted.{0,160}prd")
        self.assertRegex(content, r"accepted.{0,160}architecture")

    def test_governance_links_to_rfc_process(self) -> None:
        content = GOVERNANCE.read_text(encoding="utf-8")

        self.assertIn("docs/rfcs/README.md", content)


if __name__ == "__main__":
    unittest.main()
