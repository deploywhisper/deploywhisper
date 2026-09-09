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
        mode_section = self._section(
            content, "## Choose the least forceful mode that works"
        )

        self.assertIn(
            "| Effective status | Workflow effect | Appropriate use |", mode_section
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
            self._effective_status_rows(mode_section),
        )
        self.assertIn(
            "`warn` permits effective `advisory` or `warn`; `soft-block` permits effective `advisory`, `warn`, or `soft-block`; and `hard-block` preserves any raw status.",
            self._normalized(mode_section),
        )

    def test_operational_guardrails_are_locked_to_their_sections(self) -> None:
        content = GUARDRAIL_GUIDE.read_text(encoding="utf-8")
        expected_by_section = {
            "## Wire blocking into the protected workflow": (
                "immutable protected workflow",
                "review ownership for workflow changes",
                "must fail when the enforcement step is skipped",
                "bound to the protected commit",
                "checkout ref, artifact selection, `changed-files`, project and workspace scope, and working directory",
                "path and event filters, job-level `if` conditions, dependency skips, and cancellation",
            ),
            "## Review inherited settings before changing scope": (
                "new repository, environment, change class, or other scope",
                "resolved setting source and configured enforcement mode",
                "separate project or integration identity",
                "must complete its own benchmark and guardrail review",
                "Limit policy-setting write access to named operators",
                "approval from a different authorized reviewer",
                "durable before/after audit record",
                "freeze delivery before changing enforcement settings",
            ),
            "## Treat an unavailable decision as an operational failure": (
                "partial intake coverage",
                "submitted artifact manifest",
                "protected commit SHA",
                "PR-head workflow must verify that its tested commit SHA equals the current PR head SHA",
                "merge-ref or merge-queue workflow must bind the report to the current generated merge commit",
                "non-PR consumer must resolve a moving deployment ref to an immutable commit or artifact digest",
                "no atomic settings revision",
                "authenticated transport",
                "trusted server identity",
                "least-privilege credential",
                "exact retained authenticated response bytes",
                "retention period",
                "separation of duties",
                "exact persisted report `submission_manifest`",
                "submitted_artifact_count",
                "accepted_artifact_count",
                "analyzed_artifact_count",
                "analyzed_artifact_count == submitted_artifact_count",
                "every item to be `accepted`",
                "project-scope resolution failure",
                "payload digest proves only the integrity of the retained bytes",
                "append-only audit receipt",
                "automatically revoke the bypass",
                "Do not use policy settings as break glass",
                "deleted or renamed artifact",
                "clean checkout",
                "content hash",
                "current base SHA",
                "bounded timeout",
                "idempotency key",
                "do not provide native idempotent create or check-update semantics",
                "durable external coordinator",
                "trusted identity layer",
                "strips caller-supplied project actor headers",
                "serialize the frozen decision once",
            ),
            "## Set benchmark thresholds before blocking": (
                "actual enforcement consumer revision",
                "outcome-observation window",
                "incident-attribution horizon",
                "endpoint schema",
                "workflow or protection wiring",
                "requires a fresh approval tied to the new immutable revisions",
                "application, corpus, configuration, feature-flag, and context change",
                "False reassurance is a workflow pass followed by an attributable adverse production outcome",
                "benchmark false negative",
                "workflow and protection configuration snapshot",
                "Every allowed evidence form requires a digest",
                "materially changes benchmark inputs or enforcement behavior",
                "attribution method",
                "severity boundary",
                "independent adjudicator",
            ),
            "## Human review remains mandatory": (
                "protected commit SHA",
                "dismiss stale approvals",
                "Baseline human approval",
                "resolved configured enforcement mode is `soft-block` or `hard-block`",
                "including runs whose effective status is only `advisory` or `warn`",
                "Elevated specialist review",
            ),
            "## Rollout checklist": (
                "source-bound required check or job",
                "`continue-on-error`",
                "valid-pass, valid-block, and decision-error smoke cases",
                "complete and partial intake coverage",
                "required project-scope control",
                "`warn_at`, `soft_block_at`, and `hard_block_at`",
                "resolved setting source",
            ),
        }
        for heading, expected_clauses in expected_by_section.items():
            section = self._normalized(self._section(content, heading))
            for expected in expected_clauses:
                with self.subTest(heading=heading, expected=expected):
                    self.assertIn(expected, section)

    def test_guide_entry_conditions_cover_inherited_and_expanding_scope(self) -> None:
        preamble = GUARDRAIL_GUIDE.read_text(encoding="utf-8").split("\n## ", 1)[0]
        normalized = self._normalized(preamble)
        for expected in (
            "onboarding an integration under an inherited blocking default",
            "deleting an override",
            "expanding an existing integration to a new scope",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, normalized)

    def test_acceptance_topics_are_locked_to_their_sections(self) -> None:
        self.assertTrue(GUARDRAIL_GUIDE.exists(), "Enforcement guide is missing.")
        content = GUARDRAIL_GUIDE.read_text(encoding="utf-8")
        expected_by_section = {
            "## Evidence Law is a prerequisite, not an approval": (
                "No high or critical finding may drive enforcement without deterministic evidence.",
                "Blocking thresholds below `high` do not receive an additional Evidence Law guarantee",
                "cannot apply an additional deterministic-evidence gate below `high`",
            ),
            "## Set benchmark thresholds before blocking": (
                "does not define a universal numeric threshold",
                "minimum acceptable precision and recall",
                "maximum acceptable false-reassurance and false-positive rates",
                "zero Evidence Law violations",
                "ground-truth labels",
                "zero-denominator handling",
                "minimum positive and negative sample sizes",
            ),
            "## Blocking does not prove a change is safe": (
                "A passing check can still be false reassurance.",
                "return the integration to `warn` or `advisory`",
            ),
            "## Human review remains mandatory": (
                "No adapter output authorizes autonomous approval, deployment, or remediation.",
                "Configure repository review rules or protected-environment approvals",
            ),
            "## Rollback remains an operator responsibility": (
                "DeployWhisper does not execute, validate, or own the rollback.",
                "Never auto-execute it from an adapter decision.",
            ),
        }
        for heading, expected_clauses in expected_by_section.items():
            section = self._normalized(self._section(content, heading))
            for expected in expected_clauses:
                with self.subTest(heading=heading, expected=expected):
                    self.assertIn(expected, section)

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
            "./project-workspaces.md#guardrails",
        ):
            with self.subTest(expected_target=expected_target):
                self.assertIn(expected_target, links)
                self.assertTrue(
                    (GUARDRAIL_GUIDE.parent / expected_target.split("#", 1)[0])
                    .resolve()
                    .exists()
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
            "no protected scope shares that project/integration key",
            content,
        )
        self.assertIn(
            "create a `github-action` integration-specific `advisory` override", content
        )
        self.assertIn("without downgrading existing consumers", content)
        self.assertIn(
            "Pin the Action to an immutable reviewed commit SHA even for advisory workflows",
            content,
        )
        self.assertIn("persistent integration-specific `advisory` override", content)

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
        self.assertIn("does not subscribe to `merge_group`", content)
        self.assertIn("do not require its check in a merge queue", content)

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
            "synthetic valid-pass, valid-block, unavailable-decision, and malformed-decision cases",
            content,
        )
        self.assertIn(
            "Pin Action revisions for advisory and blocking workflows", content
        )
        self.assertIn("persistent integration-specific `advisory` override", content)
        self.assertIn(
            "steps.deploywhisper.outputs.should-block == 'true'",
            content,
        )
        self.assertIn(
            "fromJSON(steps.deploywhisper.outputs.should-block)",
            content,
        )

    def test_policy_entry_points_explain_inherited_project_defaults(self) -> None:
        for relative_path in (
            "docs/ci-advisory-consumption.md",
            "docs/workflow-adapter-output-contract.md",
            "docs/github-action.md",
        ):
            with self.subTest(relative_path=relative_path):
                content = self._normalized(
                    (REPO_ROOT / relative_path).read_text(encoding="utf-8")
                )
                self.assertIn(
                    "integration override before the inherited project default",
                    content,
                )

    def test_self_hosted_runbook_preserves_narrow_setting_scope(self) -> None:
        content = (REPO_ROOT / "docs" / "github-app-self-hosted-setup.md").read_text(
            encoding="utf-8"
        )
        onboarding = self._normalized(
            self._section(content, "### 7. Establish advisory onboarding state")
        )
        self.assertIn(
            "inspect the setting source and resolved configured enforcement mode",
            onboarding,
        )
        self.assertIn("integration-specific `advisory` override", onboarding)
        self.assertIn(
            "no existing protected scope shares that project/integration key",
            onboarding,
        )
        self.assertIn("use a separate project", onboarding)
        self.assertIn(
            "[Enforcement Guardrails](./enforcement-guardrails.md)", onboarding
        )
        self.assertLess(
            content.index("### 7. Establish advisory onboarding state"),
            content.index("## Installation steps"),
        )
        troubleshooting = self._normalized(
            self._section(
                content, "### Branch protection blocks merge on DeployWhisper"
            )
        )
        self.assertIn("resolved configured enforcement mode", troubleshooting)
        self.assertIn("effective status for the current report", troubleshooting)

    def test_epic_11_closes_when_all_stories_are_done(self) -> None:
        content = (
            REPO_ROOT
            / "_bmad-output"
            / "implementation-artifacts"
            / "sprint-status.yaml"
        ).read_text(encoding="utf-8")
        self.assertRegex(content, r"(?m)^  epic-11: done$")
        for story_key in (
            "11-1-policy-adapter-output-contract",
            "11-2-threshold-and-reporting-defaults-management",
            "11-3-integration-level-enforcement-settings",
            "11-4-enforcement-guardrail-documentation",
        ):
            with self.subTest(story_key=story_key):
                self.assertRegex(content, rf"(?m)^  {re.escape(story_key)}: done$")

    @staticmethod
    def _normalized(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _markdown_links(value: str) -> set[str]:
        return {target for _, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", value)}

    @staticmethod
    def _section(value: str, heading: str) -> str:
        marker = f"{heading}\n"
        if value.count(marker) != 1:
            if marker not in value:
                raise AssertionError(f"Missing section: {heading}")
            raise AssertionError(f"Duplicate section: {heading}")
        section = value.split(marker, 1)[1]
        level = len(heading) - len(heading.lstrip("#"))
        return re.split(rf"\n#{{1,{level}}} ", section, maxsplit=1)[0]

    @staticmethod
    def _effective_status_rows(value: str) -> dict[str, tuple[str, str]]:
        lines = value.splitlines()
        header = "| Effective status | Workflow effect | Appropriate use |"
        try:
            header_index = lines.index(header)
        except ValueError as exc:
            raise AssertionError("Effective-status table header is missing") from exc
        expected_separator = "| --- | --- | --- |"
        if lines[header_index + 1] != expected_separator:
            raise AssertionError("Effective-status table separator is malformed")

        rows: dict[str, tuple[str, str]] = {}
        for line in lines[header_index + 2 :]:
            if not line.startswith("|"):
                break
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) != 3:
                raise AssertionError(f"Malformed effective-status row: {line}")
            if (
                re.fullmatch(r"`(advisory|warn|soft-block|hard-block)`", cells[0])
                is None
            ):
                raise AssertionError(f"Unexpected effective-status row: {line}")
            status = cells[0].strip("`")
            if status in rows:
                raise AssertionError(f"Duplicate effective-status row: {status}")
            rows[status] = (
                cells[1].replace("`", ""),
                cells[2].replace("`", ""),
            )
        return rows
