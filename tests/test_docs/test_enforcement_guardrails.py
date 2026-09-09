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
    def test_effective_status_table_locks_behavior_and_prerequisites(self) -> None:
        content = GUARDRAIL_GUIDE.read_text(encoding="utf-8")

        self.assertIn(
            "| Effective status | Workflow effect | Appropriate use |", content
        )
        self.assertEqual(
            {
                "advisory": (
                    "GitHub Action exits 0 after a valid decision; GitHub App reports success for GO and neutral otherwise.",
                    "Default, initial rollout, incomplete context, or an uncalibrated project.",
                ),
                "warn": (
                    "GitHub Action exits 0 after a valid decision; GitHub App reports neutral.",
                    "Teams have reviewed signal quality and want consistent reviewer attention.",
                ),
                "soft-block": (
                    "GitHub Action exits nonzero; GitHub App reports action_required.",
                    "Every blocking prerequisite below is satisfied, and a human-owned exception path has been exercised.",
                ),
                "hard-block": (
                    "GitHub Action exits nonzero; GitHub App reports failure.",
                    "Every blocking prerequisite below is satisfied, and the organization has approved strict enforcement for this scope.",
                ),
            },
            self._effective_status_rows(content),
        )
        self.assertIn(
            "`warn` permits effective `advisory` or `warn`; `soft-block` permits effective `advisory`, `warn`, or `soft-block`; and `hard-block` preserves any raw status.",
            self._normalized(content),
        )

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
            "must never be reported as a pass",
            "require documented human disposition",
            "An installed Action ref must expose the `policy-status`, `configured-mode`, `effective-status`, and `should-block` outputs",
            "Blocking thresholds below `high` do not receive an additional Evidence Law guarantee",
            "Create an integration-specific `advisory` override before onboarding a new consumer",
            "must be a required status check or required job",
            "bound to the expected GitHub App or workflow source",
            "must not use `continue-on-error: true`",
            "pin the Action to an immutable reviewed commit SHA",
            "synthetic fail-closed smoke test",
            "must identify the corpus and immutable application and Action revisions evaluated",
            "Rerun the benchmark gate after behavior-affecting changes",
            "HTTP or transport failure, non-JSON or missing data, unsupported contract or status values, report or integration mismatch, and any decision-invariant failure",
            "The current contract exposes no report or settings revision token",
            "complete nested `applied_settings` snapshot",
            "SHA-256 digest of its canonical serialization",
            "Sensitive, unsupported, or otherwise excluded artifacts do not produce a policy decision.",
            "must not be accepted as an enforcement pass",
            "The current GitHub App reports `neutral` when intake has no analyzable artifact",
            "add a separate required intake-coverage control that fails on a missing decision",
            "A protection-layer bypass does not change the DeployWhisper decision",
            "Prefer a report- and integration-scoped protection bypass",
            "freeze other deliveries in the affected scope",
            "require fresh protected results for every open commit",
            "For a protection-layer bypass, record the protected-delivery or bypass event; for a temporary settings change, record the replacement workflow run.",
            "## Blocking does not prove a change is safe",
            "A passing check can still be false reassurance.",
            "## Human review remains mandatory",
            "No adapter output authorizes autonomous approval, deployment, or remediation.",
            "Configure repository review rules or protected-environment approvals",
            "## Rollback remains an operator responsibility",
            "DeployWhisper does not execute, validate, or own the rollback.",
            "The current shared decision contract cannot apply an additional deterministic-evidence gate below `high`.",
            "minimum positive and negative sample sizes for every covered change class",
            "statistical confidence method",
            "ground-truth labels",
            "zero-denominator handling",
            "Verify that the deployed application and Action revisions match those evaluated artifacts",
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

    def test_guardrail_guide_outbound_links_resolve(self) -> None:
        content = GUARDRAIL_GUIDE.read_text(encoding="utf-8")
        links = self._markdown_links(content)

        for expected_target in (
            "./workflow-adapter-output-contract.md",
            "./benchmarks/corpus.md",
            "./outcome-linking.md",
        ):
            with self.subTest(expected_target=expected_target):
                self.assertIn(expected_target, links)
                self.assertTrue(
                    (GUARDRAIL_GUIDE.parent / expected_target).resolve().exists()
                )

    def test_readme_describes_enforcement_capability_without_exit_contradiction(
        self,
    ) -> None:
        content = self._normalized(
            (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        )

        self.assertIn(
            "An enforcement-capable Action ref exits `0` after a valid non-blocking decision, exits nonzero when validated `should-block` is `true`, and also exits nonzero when the enforcement decision cannot be retrieved or validated.",
            content,
        )
        self.assertIn(
            "Older Action refs that do not expose enforcement outputs remain advisory-only",
            content,
        )
        self.assertIn(
            "Pin a required enforcement workflow to an immutable reviewed commit SHA",
            content,
        )
        self.assertNotIn(
            "exits `0` when analysis succeeds, regardless of risk verdict",
            content,
        )

    def test_github_app_guide_explains_project_default_inheritance(self) -> None:
        content = self._normalized(
            (REPO_ROOT / "docs" / "github-app.md").read_text(encoding="utf-8")
        )

        self.assertIn(
            "An integration without an override inherits its project-level enforcement mode",
            content,
        )
        self.assertNotIn(
            "New and existing integrations remain advisory unless an operator explicitly opts into a blocking mode",
            content,
        )
        self.assertIn(
            "An effective `advisory` status reports `success` for `GO` and `neutral` for other recommendations; effective `warn` reports `neutral`",
            content,
        )
        self.assertIn(
            "Effective `soft-block` and `hard-block` statuses produce `action_required` and `failure` conclusions respectively, regardless of which configured ceiling permitted that effective status",
            content,
        )

    def test_github_action_guide_conditions_blocking_on_runtime_capability(
        self,
    ) -> None:
        content = self._normalized(
            (REPO_ROOT / "docs" / "github-action.md").read_text(encoding="utf-8")
        )

        self.assertIn(
            "These enforcement semantics require an Action release that exposes `policy-status`, `configured-mode`, `effective-status`, and `should-block` and consumes the enforcement-decision endpoint.",
            content,
        )
        self.assertIn(
            "Older Action refs that do not expose enforcement outputs remain advisory-only",
            content,
        )
        self.assertIn(
            "also fails with an operational error when that decision cannot be retrieved or validated",
            content,
        )
        self.assertIn(
            "Pin a required enforcement workflow to an immutable reviewed commit SHA",
            content,
        )
        self.assertIn(
            "synthetic valid-pass, valid-block, unavailable-decision, and malformed-decision cases",
            content,
        )

    @staticmethod
    def _normalized(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _markdown_links(value: str) -> set[str]:
        return {target for _, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", value)}

    @staticmethod
    def _effective_status_rows(value: str) -> dict[str, tuple[str, str]]:
        rows: dict[str, tuple[str, str]] = {}
        for line in value.splitlines():
            if not line.startswith("| `"):
                continue
            cells = [
                cell.strip().replace("`", "") for cell in line.strip("|").split("|")
            ]
            if len(cells) == 3:
                rows[cells[0]] = (cells[1], cells[2])
        return rows
