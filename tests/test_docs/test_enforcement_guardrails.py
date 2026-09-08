"""Documentation checks for optional enforcement guardrails."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
GUARDRAIL_GUIDE = REPO_ROOT / "docs" / "enforcement-guardrails.md"
ENTRY_POINTS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "workflow-adapter-output-contract.md",
    REPO_ROOT / "docs" / "ci-advisory-consumption.md",
    REPO_ROOT / "docs" / "github-action.md",
    REPO_ROOT / "docs" / "github-app.md",
    REPO_ROOT / "docs" / "github-app-self-hosted-setup.md",
)


class EnforcementGuardrailDocumentationTests(unittest.TestCase):
    def test_guardrail_guide_covers_required_safety_decisions(self) -> None:
        self.assertTrue(GUARDRAIL_GUIDE.exists(), "Enforcement guide is missing.")
        content = self._normalized(GUARDRAIL_GUIDE.read_text(encoding="utf-8"))

        expected_clauses = (
            "## Evidence Law is a prerequisite, not an approval",
            "No high or critical finding may drive enforcement without deterministic evidence.",
            "## Set benchmark thresholds before blocking",
            "DeployWhisper does not define a universal numeric threshold for enabling blocking modes.",
            "The current benchmark runner emits scenario-level results and honest-failure categories; it does not emit a universal enforcement-readiness score or precomputed precision, recall, false-reassurance, or false-positive rates.",
            "document the formulas and denominators",
            "minimum acceptable precision and recall",
            "maximum acceptable false-reassurance and false-positive rates",
            "minimum evidence coverage",
            "zero Evidence Law violations",
            "unsupported-scenario limit",
            "regression-stability tolerance",
            "Project-level settings are inherited by every integration that has no integration-specific override.",
            "Deleting an integration override immediately exposes the project default",
            "A mode-table row describes runtime behavior, not sufficient readiness criteria.",
            "GitHub Action exits nonzero",
            "GitHub App check conclusion is `action_required`",
            "GitHub App check conclusion is `failure`",
            "must never be reported as a pass",
            "require documented human disposition",
            "## Blocking does not prove a change is safe",
            "A passing check can still be false reassurance.",
            "## Human review remains mandatory",
            "No adapter output authorizes autonomous approval, deployment, or remediation.",
            "## Rollback remains an operator responsibility",
            "DeployWhisper does not execute, validate, or own the rollback.",
            "keep the integration in `advisory` or `warn`",
            "soft-block",
            "hard-block",
            "break-glass",
        )
        for expected in expected_clauses:
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

    def test_enforcement_entry_points_link_to_guardrail_guide(self) -> None:
        for source in ENTRY_POINTS:
            with self.subTest(source=source.relative_to(REPO_ROOT).as_posix()):
                content = source.read_text(encoding="utf-8")
                links = self._markdown_links(content)
                expected_target = (
                    "./docs/enforcement-guardrails.md"
                    if source == REPO_ROOT / "README.md"
                    else "./enforcement-guardrails.md"
                )
                self.assertIn(expected_target, links)
                self.assertTrue((source.parent / expected_target).resolve().exists())

    @staticmethod
    def _normalized(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _markdown_links(value: str) -> set[str]:
        return {target for _, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", value)}
