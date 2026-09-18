"""Documentation checks for optional enforcement guardrails."""

from __future__ import annotations

from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlparse

import yaml

from integrations.github import init_service


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
                "independent watchdog",
                "cannot rely on `if: always()`",
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
                "unknown submission outcome",
                "reconcile the original request before retrying",
                "out-of-band alert",
                "independent delivery freeze",
                "trusted identity layer",
                "strips caller-supplied project actor headers",
                "serialize the frozen decision once",
                "immutable exception identifier",
                "organization-approved maximum TTL",
                "new independent approval",
                "one active exception at a time",
                "per-exception bypass capability",
                "encrypted immutable raw response",
                "separate redacted reviewer view",
            ),
            "## Set benchmark thresholds before blocking": (
                "actual enforcement consumer revision",
                "outcome-observation window",
                "incident-attribution horizon",
                "endpoint schema",
                "workflow or protection wiring",
                "requires a fresh approval tied to the new immutable revisions",
                "application, corpus, configuration, feature-flag, and context change",
                "Deployment-backed false reassurance is a workflow pass followed by an attributable adverse production outcome",
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
                "report ID, manifest, settings snapshot, material context, consumer revision, or workflow changes",
                "external approval record",
                "complete decision identity",
            ),
            "## Rollout checklist": (
                "source-bound required check or job",
                "`continue-on-error`",
                "valid-pass, valid-block, and decision-error smoke cases",
                "complete and partial intake coverage",
                "required project-scope control",
                "`warn_at`, `soft_block_at`, and `hard_block_at`",
                "resolved setting source",
                "trusted identity/proxy boundary",
                "durable external idempotency coordinator",
                "Settings-change serialization",
                "deterministic diff-coverage control for deletions and renames",
                "A non-blocking disposition does not satisfy blocking readiness",
                "maximum expiry timestamp",
                "fails closed",
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
                self.assertTrue(
                    self._resolved_local_doc_target(source.parent, expected_target)
                    .resolve()
                    .is_file()
                )

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
                target_path = self._resolved_local_doc_target(
                    GUARDRAIL_GUIDE.parent, expected_target
                )
                self.assertTrue(target_path.is_file())
                if "#" in expected_target:
                    fragment = expected_target.split("#", 1)[1]
                    self.assertIn(
                        fragment,
                        self._markdown_heading_anchors(
                            target_path.read_text(encoding="utf-8")
                        ),
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
            "no existing scope shares that project/integration key",
            content,
        )
        self.assertIn(
            "create a `github-action` integration-specific `advisory` override", content
        )
        self.assertIn("without downgrading existing consumers", content)
        self.assertIn(
            "Pin the Action and checkout dependencies to reviewed full commit SHAs even for advisory workflows",
            content,
        )
        self.assertIn(
            "server-side advisory override cannot make mutable third-party code trustworthy",
            content,
        )
        self.assertIn(
            "tag object `f2e36cef443129e85c55882b9dafc1f20d409284`",
            content,
        )
        action_section = self._normalized(
            self._section(
                (REPO_ROOT / "README.md").read_text(encoding="utf-8"),
                "### DeployWhisper Analyze Action",
            )
        )
        self.assertNotIn(
            "exits `0` when analysis succeeds, regardless of risk verdict",
            action_section,
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
        self.assertIn("does not subscribe to `merge_group`", content)
        self.assertIn("Do not require either check in a merge queue", content)

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
        self.assertIn(
            "server-side advisory override does not make mutable Action code trustworthy",
            content,
        )
        self.assertIn(
            "actions/checkout `v4` is a lightweight tag that resolved to commit `11d5960a326750d5838078e36cf38b85af677262`",
            content,
        )
        self.assertIn(
            "resolve and review the checkout candidate independently",
            content,
        )
        self.assertIn(
            "peel an annotated tag to the executed commit",
            content,
        )
        self.assertIn("- id: deploywhisper", content)
        self.assertIn(
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262", content
        )
        self.assertIn(
            "deploywhisper/analyze-action@3b37ed72bfb2d201030bef873268f2170794b160",
            content,
        )
        self.assertIn(
            "steps.deploywhisper.outputs.should-block == 'true'",
            content,
        )
        self.assertIn(
            "fromJSON(steps.deploywhisper.outputs.should-block)",
            content,
        )
        self.assertIn(
            'reject any `should-block` value other than the exact strings `"true"` and `"false"`',
            content,
        )

    def test_documented_workflow_pins_match_scaffold_constants(self) -> None:
        for relative_path in ("README.md", "docs/github-action.md"):
            content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
            workflow = self._documented_workflow(content)
            steps = workflow["jobs"]["deploywhisper"]["steps"]
            checkout_steps = [
                step
                for step in steps
                if str(step.get("uses", "")).startswith("actions/checkout@")
            ]
            action_steps = [
                step
                for step in steps
                if str(step.get("uses", "")).startswith("deploywhisper/analyze-action@")
            ]
            with self.subTest(relative_path=relative_path):
                self.assertEqual(1, len(checkout_steps))
                self.assertEqual(1, len(action_steps))
                self.assertEqual(
                    f"actions/checkout@{init_service.CHECKOUT_ACTION_PINNED_SHA}",
                    checkout_steps[0]["uses"],
                )
                self.assertEqual(
                    f"deploywhisper/analyze-action@{init_service.ANALYZE_ACTION_PINNED_SHA}",
                    action_steps[0]["uses"],
                )
                self.assertEqual("deploywhisper", action_steps[0].get("id"))

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

        ci_guidance = self._normalized(
            (REPO_ROOT / "docs" / "ci-advisory-consumption.md").read_text(
                encoding="utf-8"
            )
        )
        self.assertNotIn("until the team explicitly opts into", ci_guidance)
        self.assertIn("inspect the resolved setting source", ci_guidance)

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
            "no existing scope shares that project/integration key",
            onboarding,
        )
        self.assertIn("use a separate project", onboarding)
        self.assertIn(
            "grant staged repository access while the check remains non-required",
            onboarding,
        )
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
        payload = yaml.safe_load(
            (
                REPO_ROOT
                / "_bmad-output"
                / "implementation-artifacts"
                / "sprint-status.yaml"
            ).read_text(encoding="utf-8")
        )
        statuses = payload["development_status"]
        story_statuses = {
            key: value
            for key, value in statuses.items()
            if re.fullmatch(r"11-\d+-.+", str(key))
        }
        required_story_keys = {
            "11-1-policy-adapter-output-contract",
            "11-2-threshold-and-reporting-defaults-management",
            "11-3-integration-level-enforcement-settings",
            "11-4-enforcement-guardrail-documentation",
        }
        self.assertTrue(
            required_story_keys.issubset(story_statuses),
            f"Epic 11 is missing required stories: {sorted(required_story_keys - story_statuses.keys())}",
        )
        all_stories_done = all(status == "done" for status in story_statuses.values())
        self.assertEqual(
            all_stories_done,
            statuses.get("epic-11") == "done",
            "Epic 11 and its complete discovered story set must reach done together",
        )

    def test_mode_table_parser_rejects_malformed_rows(self) -> None:
        content = self._section(
            GUARDRAIL_GUIDE.read_text(encoding="utf-8"),
            "## Choose the least forceful mode that works",
        )
        for malformed in (
            content.replace("| --- | --- | --- |", "| advisory | bad | row |"),
            content.replace("| `warn` |", "| warn |"),
            content.replace("| `warn` |", "| `warn` | extra |"),
        ):
            with self.subTest(malformed=malformed.splitlines()[1:4]):
                with self.assertRaises(AssertionError):
                    self._effective_status_rows(malformed)

    def test_markdown_heading_anchors_ignore_fences_and_suffix_duplicates(
        self,
    ) -> None:
        content = """\
```markdown
```not-a-close
### Fake
```
### Guardrails
### Guardrails
"""
        self.assertEqual(
            {"guardrails", "guardrails-1"},
            self._markdown_heading_anchors(content),
        )

        collision_content = """\
### Guardrails
### Guardrails-1
### Guardrails
```invalid`info
### Not hidden by an invalid fence
"""
        collision_anchors = self._markdown_heading_anchors(collision_content)
        self.assertEqual(4, len(collision_anchors))
        self.assertIn("guardrails-2", collision_anchors)
        self.assertIn("not-hidden-by-an-invalid-fence", collision_anchors)

        hidden_content = """\
<!--
## Hidden comment heading
-->
````markdown
```yaml
## Hidden nested fence heading
```
````
Visible Setext Heading
----------------------
"""
        self.assertEqual(
            {"visible-setext-heading"},
            self._markdown_heading_anchors(hidden_content),
        )

    def test_section_extraction_ignores_fenced_pseudo_headings(self) -> None:
        content = """\
## Target
required clause
```markdown
## Fake next section
```
still required
## Real next section
outside target
"""
        self.assertEqual(
            "required clause\nstill required\n",
            self._section(content, "## Target"),
        )

        commented_and_setext = """\
  ## Target
visible requirement
<!-- hidden requirement -->
```text
hidden fenced requirement
```
Next Section
------------
later requirement
"""
        self.assertEqual(
            "visible requirement",
            self._normalized(self._section(commented_and_setext, "## Target")),
        )

    def test_effective_status_parser_rejects_duplicate_tables(self) -> None:
        section = self._section(
            GUARDRAIL_GUIDE.read_text(encoding="utf-8"),
            "## Choose the least forceful mode that works",
        )
        table_start = "| Effective status | Workflow effect | Appropriate use |"
        duplicate = f"{section}\n{section[section.index(table_start) :]}"
        with self.assertRaisesRegex(AssertionError, "exactly once"):
            self._effective_status_rows(duplicate)

        with self.assertRaisesRegex(AssertionError, "separator is missing"):
            self._effective_status_rows(table_start)

    def test_markdown_links_ignore_non_rendered_content_and_resolve_safely(
        self,
    ) -> None:
        content = r"""
<!-- [Hidden](./hidden.md) -->
```markdown
[Fenced](./fenced.md)
```
[Parentheses](./guide_(v2).md)
[Angle](<./guide with spaces.md>)
[Escaped](./guide_\(v3\).md)
"""
        self.assertEqual(
            {
                "./guide_(v2).md",
                "./guide with spaces.md",
                "./guide_(v3).md",
            },
            self._markdown_links(content),
        )

    def test_documented_workflow_ignores_nested_and_commented_fences(self) -> None:
        real_workflow = """\
```yaml
jobs:
  deploywhisper:
    steps: []
```
"""
        hidden_workflows = """\
<!--
```yaml
jobs:
  hidden-comment: {}
```
-->
````markdown
```yaml
jobs:
  hidden-nested: {}
```
````
"""
        self.assertEqual(
            {"jobs": {"deploywhisper": {"steps": []}}},
            self._documented_workflow(f"{hidden_workflows}{real_workflow}"),
        )

    @staticmethod
    def _normalized(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _markdown_links(value: str) -> set[str]:
        visible = "".join(
            EnforcementGuardrailDocumentationTests._rendered_markdown_lines(
                value, keepends=True
            )
        )
        targets: set[str] = set()
        cursor = 0
        while cursor < len(visible):
            label_start = visible.find("[", cursor)
            if label_start < 0:
                break
            if label_start > 0 and visible[label_start - 1] in {"!", "\\"}:
                cursor = label_start + 1
                continue
            label_end = EnforcementGuardrailDocumentationTests._find_unescaped(
                visible, "]", label_start + 1
            )
            if label_end < 0 or label_end + 1 >= len(visible):
                break
            if visible[label_end + 1] != "(":
                cursor = label_end + 1
                continue

            target_start = label_end + 2
            while target_start < len(visible) and visible[target_start] in " \t":
                target_start += 1
            target, link_end = (
                EnforcementGuardrailDocumentationTests._parse_link_destination(
                    visible, target_start
                )
            )
            if target is not None:
                targets.add(target)
                cursor = link_end
            else:
                cursor = label_end + 1
        return targets

    @staticmethod
    def _markdown_heading_anchors(value: str) -> set[str]:
        anchors: set[str] = set()
        duplicate_counts: dict[str, int] = {}

        lines = EnforcementGuardrailDocumentationTests._rendered_markdown_lines(value)
        for index, line in enumerate(lines):
            heading_match = re.match(r"^ {0,3}#{1,6}\s+(.+?)\s*$", line)
            if heading_match is not None:
                heading = re.sub(r"\s+#+\s*$", "", heading_match.group(1))
            elif (
                index + 1 < len(lines)
                and line.strip()
                and re.fullmatch(r" {0,3}(=+|-+)[ \t]*", lines[index + 1])
            ):
                heading = line.strip()
            else:
                continue
            base_anchor = re.sub(r"[^\w\- ]", "", heading.lower())
            base_anchor = re.sub(r"\s", "-", base_anchor)
            duplicate_number = duplicate_counts.get(base_anchor, 0)
            anchor = base_anchor
            while anchor in anchors:
                duplicate_number += 1
                anchor = f"{base_anchor}-{duplicate_number}"
            duplicate_counts[base_anchor] = duplicate_number
            anchors.add(anchor)
        return anchors

    @staticmethod
    def _section(value: str, heading: str) -> str:
        level = len(heading) - len(heading.lstrip("#"))
        lines = EnforcementGuardrailDocumentationTests._rendered_markdown_lines(
            value, keepends=True
        )
        matches: list[int] = []
        for index, line_with_ending in enumerate(lines):
            line = line_with_ending.rstrip("\r\n")
            if line.lstrip(" ") == heading and len(line) - len(line.lstrip(" ")) <= 3:
                matches.append(index)

        if not matches:
            raise AssertionError(f"Missing section: {heading}")
        if len(matches) > 1:
            raise AssertionError(f"Duplicate section: {heading}")

        start = matches[0] + 1
        end = len(lines)
        for index in range(start, len(lines)):
            line = lines[index].rstrip("\r\n")
            heading_match = re.match(r"^ {0,3}(#{1,6})\s+", line)
            if heading_match is not None and len(heading_match.group(1)) <= level:
                end = index
                break
            if (
                index + 1 < len(lines)
                and line.strip()
                and (
                    setext_match := re.fullmatch(
                        r" {0,3}(=+|-+)[ \t]*",
                        lines[index + 1].rstrip("\r\n"),
                    )
                )
                is not None
            ):
                setext_level = 1 if setext_match.group(1).startswith("=") else 2
                if setext_level <= level:
                    end = index
                    break
        return "".join(lines[start:end])

    @staticmethod
    def _opening_fence(line: str) -> str | None:
        result = EnforcementGuardrailDocumentationTests._opening_fence_info(line)
        return result[0] if result is not None else None

    @staticmethod
    def _opening_fence_info(line: str) -> tuple[str, str] | None:
        match = re.match(r"^ {0,3}(?P<marker>`{3,}|~{3,})(?P<info>.*)$", line)
        if match is None:
            return None
        marker = match.group("marker")
        if marker.startswith("`") and "`" in match.group("info"):
            return None
        return marker, match.group("info").strip()

    @staticmethod
    def _is_closing_fence(line: str, character: str, length: int) -> bool:
        match = re.fullmatch(r" {0,3}(`{3,}|~{3,})[ \t]*", line)
        if match is None:
            return False
        marker = match.group(1)
        return marker[0] == character and len(marker) >= length

    @staticmethod
    def _documented_workflow(value: str) -> dict[str, object]:
        workflows: list[dict[str, object]] = []
        comment_free = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
        lines = comment_free.splitlines()
        index = 0
        while index < len(lines):
            opening = EnforcementGuardrailDocumentationTests._opening_fence_info(
                lines[index]
            )
            if opening is None:
                index += 1
                continue
            marker, info = opening
            fence_character = marker[0]
            fence_length = len(marker)
            body: list[str] = []
            index += 1
            while index < len(lines) and not (
                EnforcementGuardrailDocumentationTests._is_closing_fence(
                    lines[index], fence_character, fence_length
                )
            ):
                body.append(lines[index])
                index += 1
            if info.lower() in {"yaml", "yml"}:
                payload = yaml.safe_load("\n".join(body))
                if isinstance(payload, dict) and "jobs" in payload:
                    workflows.append(payload)
            index += 1
        if len(workflows) != 1:
            raise AssertionError(
                f"Expected exactly one documented workflow, found {len(workflows)}"
            )
        return workflows[0]

    @staticmethod
    def _effective_status_rows(value: str) -> dict[str, tuple[str, str]]:
        lines = value.splitlines()
        header = "| Effective status | Workflow effect | Appropriate use |"
        if lines.count(header) != 1:
            raise AssertionError("Effective-status table must appear exactly once")
        try:
            header_index = lines.index(header)
        except ValueError as exc:
            raise AssertionError("Effective-status table header is missing") from exc
        expected_separator = "| --- | --- | --- |"
        if header_index + 1 >= len(lines):
            raise AssertionError("Effective-status table separator is missing")
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

    @staticmethod
    def _rendered_markdown_lines(value: str, *, keepends: bool = False) -> list[str]:
        comment_free = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
        rendered: list[str] = []
        fence_character: str | None = None
        fence_length = 0
        for line_with_ending in comment_free.splitlines(keepends=keepends):
            line = line_with_ending.rstrip("\r\n")
            if fence_character is None:
                opening = EnforcementGuardrailDocumentationTests._opening_fence(line)
                if opening is not None:
                    fence_character = opening[0]
                    fence_length = len(opening)
                    continue
                rendered.append(line_with_ending)
            elif EnforcementGuardrailDocumentationTests._is_closing_fence(
                line, fence_character, fence_length
            ):
                fence_character = None
                fence_length = 0
        return rendered

    @staticmethod
    def _find_unescaped(value: str, character: str, start: int) -> int:
        escaped = False
        for index in range(start, len(value)):
            if escaped:
                escaped = False
                continue
            if value[index] == "\\":
                escaped = True
                continue
            if value[index] == character:
                return index
        return -1

    @staticmethod
    def _parse_link_destination(value: str, start: int) -> tuple[str | None, int]:
        if start >= len(value):
            return None, start
        if value[start] == "<":
            end = EnforcementGuardrailDocumentationTests._find_unescaped(
                value, ">", start + 1
            )
            if end < 0:
                return None, start
            closing = value.find(")", end + 1)
            if closing < 0:
                return None, start
            return value[start + 1 : end], closing + 1

        target: list[str] = []
        depth = 1
        index = start
        while index < len(value):
            character = value[index]
            if character == "\\" and index + 1 < len(value):
                target.append(value[index + 1])
                index += 2
                continue
            if character == "(":
                depth += 1
                target.append(character)
            elif character == ")":
                depth -= 1
                if depth == 0:
                    return "".join(target).strip(), index + 1
                target.append(character)
            elif character in " \t\r\n" and depth == 1:
                closing = value.find(")", index)
                if closing < 0:
                    return None, start
                return "".join(target).strip(), closing + 1
            else:
                target.append(character)
            index += 1
        return None, start

    @staticmethod
    def _resolved_local_doc_target(base: Path, target: str) -> Path:
        parsed = urlparse(target)
        if parsed.scheme or parsed.netloc or parsed.path.startswith("/"):
            raise AssertionError(
                f"Expected a repository-local documentation link: {target}"
            )
        candidate = (base / unquote(parsed.path)).resolve()
        repository_root = REPO_ROOT.resolve()
        if not candidate.is_relative_to(repository_root):
            raise AssertionError(f"Documentation link escapes repository: {target}")
        if not candidate.is_file():
            raise AssertionError(f"Documentation link is not a file: {target}")
        return candidate
