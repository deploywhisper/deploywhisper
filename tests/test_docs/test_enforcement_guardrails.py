"""Documentation checks for optional enforcement guardrails."""

from __future__ import annotations

import html
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
                    "The policy decision does not request Action failure; after all runtime work succeeds, the Action exits 0. The GitHub App reports success for GO and neutral otherwise.",
                    "Default, initial rollout, incomplete context, or an uncalibrated project.",
                ),
                "warn": (
                    "The policy decision does not request Action failure; after all runtime work succeeds, the Action exits 0. The GitHub App reports neutral.",
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
                "non-PR consumer must resolve a moving deployment ref to an immutable commit or an algorithm-qualified SHA-256 digest",
                "algorithm-qualified SHA-256 digest over the exact deployed artifact bytes",
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
                "every retry of one unknown outcome reuses the same key",
                "pre-submission request identity",
                "must not depend on report ID or validated decision digest",
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
                "longest exception, compliance-audit, and incident-attribution horizon",
                "complete decision identity",
                "retained manifest snapshot",
                "retained material-context snapshot",
                "versioned material-context record",
                "deterministic UTF-8 JSON",
                "material-context SHA-256 digest",
                "manifest snapshot digest",
                "settings snapshot digest",
                "canonical unique normalized path-to-content-hash mapping",
                "exact set equality",
                "case-folding behavior",
                "symlink/alias handling",
                "generated or build-produced artifact",
                "immutable producer attestation",
                "producer revision, build-run identity, protected source commit",
                "`operational-error` classification",
                "validated hard-block",
                "check summary",
            ),
            "## Set benchmark thresholds before blocking": (
                "actual enforcement consumer revision",
                "decision-level enforcement false negative",
                "expected and actual `effective-status` and `should-block`",
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
                "immutable application/server revision",
                "dependency-lock identity",
                "endpoint-contract version",
                "validated decision digest",
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
                "always-triggered terminal context",
                "independent cancellation and timeout watchdog",
                "base-branch update or merge-result trigger",
                "complete decision identity",
                "repository and environment",
                "integration and project scope",
                "protected-target identity",
                "external approval record or independently enforced approval check",
                "Lower-than-`high` blocking remains prohibited",
                "ruleset or emergency-workflow ID",
                "provider audit-event identifier",
                "one active exception at a time",
            ),
        }
        for heading, expected_clauses in expected_by_section.items():
            section = self._normalized(
                self._visible_prose(self._section(content, heading))
            )
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
            section = self._normalized(
                self._visible_prose(self._section(content, heading))
            )
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

        local_links = {
            target
            for target in links
            if not (
                (parsed := urlparse(target)).scheme
                or parsed.netloc
                or parsed.path.startswith("/")
            )
        }
        for target in local_links:
            with self.subTest(local_target=target):
                target_path = self._resolved_local_doc_target(
                    GUARDRAIL_GUIDE.parent, target
                )
                if "#" in target:
                    fragment = target.split("#", 1)[1]
                    self.assertIn(
                        fragment,
                        self._markdown_heading_anchors(
                            target_path.read_text(encoding="utf-8")
                        ),
                    )

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
            "A valid non-blocking policy decision does not itself request failure; the enforcement-capable Action exits `0` only when all remaining runtime work also succeeds.",
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
        self.assertIn("classify the candidate SHA in the capability registry", content)
        self.assertIn("manifest and enforcement-decision endpoint evidence", content)
        self.assertIn(
            "allowed values for `policy-status`, `configured-mode`, and `effective-status`",
            content,
        )
        self.assertIn("configured-mode ceiling", content)
        self.assertIn(
            "`should-block` is `true` if and only if `effective-status` is `soft-block` or `hard-block`",
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
        self.assertIn(
            "no existing scope shares that project/integration key", ci_guidance
        )
        self.assertIn("separate project or integration identity", ci_guidance)

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
        self.assertIn(
            "no other scope shares the project/integration key", troubleshooting
        )
        self.assertIn("separate project or integration identity", troubleshooting)

    def test_adapter_docs_distinguish_policy_and_enforcement_endpoints(self) -> None:
        content = self._normalized(
            (REPO_ROOT / "docs" / "workflow-adapter-output-contract.md").read_text(
                encoding="utf-8"
            )
        )

        self.assertIn(
            "`/policy-adapter` is the raw configured-policy inspection endpoint",
            content,
        )
        self.assertIn(
            "`/enforcement-decision` is the canonical integration-enforcement endpoint",
            content,
        )
        self.assertIn(
            "configured ceiling, effective status, and blocking invariant", content
        )

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
            content.replace(
                "| `warn` |",
                "   `warn` | Contradictory effect | Contradictory use |",
            ),
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

        formatted_content = """\
### [Guardrails](./wrong-target.md) &amp; `Safety`
### <span>Scoped</span> *Review*
"""
        self.assertEqual(
            {"guardrails--safety", "scoped-review"},
            self._markdown_heading_anchors(formatted_content),
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

        duplicate_with_closing_hashes = """\
## Target
required clause
## Target ##
contradiction
"""
        with self.assertRaisesRegex(AssertionError, "Duplicate section"):
            self._section(duplicate_with_closing_hashes, "## Target")

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

        competing_header = duplicate.replace(
            "| Effective status | Workflow effect | Appropriate use |",
            "| Status | Effect | Use |",
            1,
        )
        with self.assertRaisesRegex(AssertionError, "exactly one Markdown table"):
            self._effective_status_rows(competing_header)

    def test_markdown_links_ignore_non_rendered_content_and_resolve_safely(
        self,
    ) -> None:
        content = r"""
<!-- [Hidden](./hidden.md) -->
```markdown
[Fenced](./fenced.md)
```
    [Indented](./indented.md)
`[Inline](./inline.md)`
[Parentheses](./guide_(v2).md)
[Angle](<./guide with spaces.md>)
[Escaped](./guide_\(v3\).md)
<!-- [Hidden tail](./unclosed.md) -->
"""
        self.assertEqual(
            {
                "./guide_(v2).md",
                "./guide with spaces.md",
                "./guide_(v3).md",
            },
            self._markdown_links(content),
        )

    def test_markdown_links_reject_malformed_and_reference_style_forms(self) -> None:
        for malformed in (
            "[Bad angle](<./bad.md>junk)",
            "[Bad title](./bad-title.md invalid)",
            "[Guide][guardrail]\n\n[guardrail]: ./enforcement-guardrails.md",
        ):
            with self.subTest(malformed=malformed):
                with self.assertRaises(AssertionError):
                    self._markdown_links(malformed)

    def test_markdown_contract_rejects_unsupported_rendering_constructs(self) -> None:
        for unsupported in (
            "> ```markdown\n> [Hidden](./missing.md)\n> ```",
            "```text\n<!-- literal comment marker -->\n```\n[Visible](./missing.md)",
            "- item\n\n      ```text\n      hidden requirement\n      ```",
            "<h2>Rendered boundary</h2>\nhidden requirement",
            "`<!--` literal opener",
            "```text\nunclosed fence",
            "<!-- unclosed comment",
        ):
            with self.subTest(unsupported=unsupported):
                with self.assertRaises(AssertionError):
                    self._rendered_markdown_lines(unsupported)

        for unsupported_link in (
            "[guardrail [details]](./missing.md)",
            '<a href="./missing.md">Missing</a>',
            "<a href=./missing.md>Missing</a>",
            "[Root local](/docs/missing.md)",
        ):
            with self.subTest(unsupported_link=unsupported_link):
                with self.assertRaises(AssertionError):
                    self._markdown_links(unsupported_link)

        section = """\
## Target
[short label](./required-hidden-phrase.md)
- list item

      hidden list code requirement
"""
        visible = self._normalized(
            self._visible_prose(self._section(section, "## Target"))
        )
        self.assertEqual("short label - list item", visible)
        self.assertNotIn("required-hidden-phrase", visible)
        self.assertNotIn("hidden list code requirement", visible)

        two_spans = "`soft-block` requires review before `hard-block`"
        self.assertIn(two_spans, "".join(self._rendered_markdown_lines(two_spans)))

    def test_rendered_markdown_hides_unclosed_comments_and_code_only_prose(
        self,
    ) -> None:
        content = """\
## Target
visible requirement with `an identifier`
`hidden normative requirement`
    hidden indented requirement
<!-- hidden comment requirement -->
"""

        section = self._normalized(self._section(content, "## Target"))

        self.assertIn("visible requirement with `an identifier`", section)
        self.assertNotIn("hidden normative requirement", section)
        self.assertNotIn("hidden indented requirement", section)
        self.assertNotIn("hidden comment requirement", section)

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

        with self.assertRaisesRegex(AssertionError, "Unclosed fenced code block"):
            self._documented_workflow(real_workflow.removesuffix("```\n"))

    @staticmethod
    def _normalized(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _visible_prose(value: str) -> str:
        visible = "".join(
            EnforcementGuardrailDocumentationTests._rendered_markdown_lines(
                value, keepends=True
            )
        )
        EnforcementGuardrailDocumentationTests._markdown_links(visible)
        visible = re.sub(
            r"!\[([^\]]*)\]\((?:<[^>]*>|(?:\\.|[^)])*)\)",
            r"\1",
            visible,
        )
        visible = re.sub(
            r"\[([^\]]+)\]\((?:<[^>]*>|(?:\\.|[^)])*)\)",
            r"\1",
            visible,
        )
        visible = re.sub(r"<[^>]+>", "", visible)
        return html.unescape(visible)

    @staticmethod
    def _markdown_links(value: str) -> set[str]:
        visible = "".join(
            EnforcementGuardrailDocumentationTests._rendered_markdown_lines(
                value, keepends=True
            )
        )
        visible = EnforcementGuardrailDocumentationTests._strip_inline_code_spans(
            visible
        )
        if re.search(r"(?<![!\\])\[[^\]\n]*\[[^\n]*\]\]\(", visible):
            raise AssertionError("Nested Markdown link labels are unsupported")
        if re.search(
            r"(?is)<a\b[^>]*\bhref\s*=\s*(?:['\"](?:\.?\.?/)[^'\"]*['\"]|(?:\.?\.?/)[^\s>]+)[^>]*>",
            visible,
        ):
            raise AssertionError("Repository-local raw HTML links are unsupported")
        if re.search(r"(?<![!\\])\[[^\]\n]+\]\[[^\]\n]*\]", visible) or re.search(
            r"(?m)^ {0,3}\[[^\]\n]+\]:", visible
        ):
            raise AssertionError(
                "Reference-style Markdown links are unsupported by this contract parser"
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
                if target.startswith("/"):
                    raise AssertionError(
                        "Repository-root-relative Markdown links are unsupported"
                    )
                targets.add(target)
                cursor = link_end
            else:
                raise AssertionError(
                    f"Malformed inline Markdown link near: {visible[label_start : label_end + 1]}"
                )
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
            heading = EnforcementGuardrailDocumentationTests._rendered_heading_text(
                heading
            )
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
    def _rendered_heading_text(value: str) -> str:
        rendered = html.unescape(value)
        rendered = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", rendered)
        rendered = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", rendered)
        rendered = re.sub(r"`+([^`]*)`+", r"\1", rendered)
        rendered = re.sub(r"<[^>]+>", "", rendered)
        return re.sub(r"[*_~]", "", rendered)

    @staticmethod
    def _section(value: str, heading: str) -> str:
        target = EnforcementGuardrailDocumentationTests._atx_heading(heading)
        if target is None:
            raise AssertionError(f"Invalid ATX section heading: {heading}")
        level, target_text = target
        lines = EnforcementGuardrailDocumentationTests._rendered_markdown_lines(
            value, keepends=True
        )
        matches: list[int] = []
        for index, line_with_ending in enumerate(lines):
            line = line_with_ending.rstrip("\r\n")
            parsed_heading = EnforcementGuardrailDocumentationTests._atx_heading(line)
            if parsed_heading == (level, target_text):
                matches.append(index)

        if not matches:
            raise AssertionError(f"Missing section: {heading}")
        if len(matches) > 1:
            raise AssertionError(f"Duplicate section: {heading}")

        start = matches[0] + 1
        end = len(lines)
        for index in range(start, len(lines)):
            line = lines[index].rstrip("\r\n")
            parsed_heading = EnforcementGuardrailDocumentationTests._atx_heading(line)
            if parsed_heading is not None and parsed_heading[0] <= level:
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
    def _atx_heading(line: str) -> tuple[int, str] | None:
        match = re.fullmatch(r" {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*", line)
        if match is None:
            return None
        heading = (match.group(2) or "").strip()
        heading = re.sub(r"[ \t]+#+[ \t]*$", "", heading).strip()
        return len(match.group(1)), heading

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
        EnforcementGuardrailDocumentationTests._validate_supported_markdown(value)
        comment_free = EnforcementGuardrailDocumentationTests._strip_html_comments(
            value
        )
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
                if index >= len(lines):
                    raise AssertionError("Unclosed YAML workflow fence")
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
        lines = EnforcementGuardrailDocumentationTests._rendered_markdown_lines(value)
        expected_header = ["Effective status", "Workflow effect", "Appropriate use"]
        header_indices = [
            index
            for index, line in enumerate(lines)
            if EnforcementGuardrailDocumentationTests._markdown_table_cells(line)
            == expected_header
        ]
        if len(header_indices) != 1:
            raise AssertionError("Effective-status table must appear exactly once")
        header_index = header_indices[0]
        if header_index + 1 >= len(lines):
            raise AssertionError("Effective-status table separator is missing")
        separator_cells = EnforcementGuardrailDocumentationTests._markdown_table_cells(
            lines[header_index + 1]
        )
        if len(separator_cells) != 3 or not all(
            re.fullmatch(r":?-{3,}:?", cell) for cell in separator_cells
        ):
            raise AssertionError("Effective-status table separator is malformed")

        table_starts = [
            index
            for index in range(len(lines) - 1)
            if len(
                EnforcementGuardrailDocumentationTests._markdown_table_cells(
                    lines[index]
                )
            )
            >= 2
            and (
                candidate_separator
                := EnforcementGuardrailDocumentationTests._markdown_table_cells(
                    lines[index + 1]
                )
            )
            and all(re.fullmatch(r":?-{3,}:?", cell) for cell in candidate_separator)
        ]
        if len(table_starts) != 1:
            raise AssertionError(
                "Effective-status section must contain exactly one Markdown table"
            )

        rows: dict[str, tuple[str, str]] = {}
        for line in lines[header_index + 2 :]:
            if "|" not in line:
                break
            cells = EnforcementGuardrailDocumentationTests._markdown_table_cells(line)
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
    def _markdown_table_cells(line: str) -> list[str]:
        value = line.strip()
        if value.startswith("|"):
            value = value[1:]
        if value.endswith("|"):
            value = value[:-1]
        return [cell.strip() for cell in value.split("|")]

    @staticmethod
    def _rendered_markdown_lines(value: str, *, keepends: bool = False) -> list[str]:
        EnforcementGuardrailDocumentationTests._validate_supported_markdown(value)
        comment_free = EnforcementGuardrailDocumentationTests._strip_html_comments(
            value
        )
        rendered: list[str] = []
        fence_character: str | None = None
        fence_length = 0
        list_content_indent: int | None = None
        for line_with_ending in comment_free.splitlines(keepends=keepends):
            line = line_with_ending.rstrip("\r\n")
            if fence_character is None:
                opening = EnforcementGuardrailDocumentationTests._opening_fence(line)
                if opening is not None:
                    fence_character = opening[0]
                    fence_length = len(opening)
                    continue
                list_item = re.match(r"^ {0,3}(?:[-+*]|\d+[.)])[ \t]+", line)
                if list_item is not None:
                    list_content_indent = list_item.end()
                elif re.match(r"^(?: {4,}|\t)", line):
                    leading_spaces = len(line) - len(line.lstrip(" "))
                    if (
                        list_content_indent is None
                        or leading_spaces < list_content_indent
                        or leading_spaces >= list_content_indent + 4
                    ):
                        continue
                elif line.strip():
                    list_content_indent = None
                if EnforcementGuardrailDocumentationTests._is_code_only_line(line):
                    continue
                rendered.append(line_with_ending)
            elif EnforcementGuardrailDocumentationTests._is_closing_fence(
                line, fence_character, fence_length
            ):
                fence_character = None
                fence_length = 0
        return rendered

    @staticmethod
    def _validate_supported_markdown(value: str) -> None:
        fence_character: str | None = None
        fence_length = 0
        html_comment_open = False
        for line in value.splitlines():
            if html_comment_open:
                if "-->" in line:
                    html_comment_open = False
                continue
            if fence_character is None:
                if re.match(r"^ {0,3}>[ \t]?(?:`{3,}|~{3,})", line):
                    raise AssertionError("Blockquoted fenced code is unsupported")
                if re.match(r"^ {4,}(?:`{3,}|~{3,})", line):
                    raise AssertionError("List-nested fenced code is unsupported")
                if re.match(r"^ {0,3}<h[1-6]\b", line, flags=re.IGNORECASE):
                    raise AssertionError("Raw HTML headings are unsupported")
                if re.search(r"`+[^`\n]*(?:<!--|-->)[^`\n]*`+", line):
                    raise AssertionError(
                        "HTML comment markers inside inline code are unsupported"
                    )
                sanitized = line
                while "<!--" in sanitized:
                    opening_index = sanitized.index("<!--")
                    closing_index = sanitized.find("-->", opening_index + 4)
                    if closing_index < 0:
                        html_comment_open = True
                        sanitized = sanitized[:opening_index]
                        break
                    sanitized = (
                        sanitized[:opening_index] + sanitized[closing_index + 3 :]
                    )
                if "-->" in sanitized:
                    raise AssertionError("Unmatched HTML comment closer")
                opening = EnforcementGuardrailDocumentationTests._opening_fence_info(
                    sanitized
                )
                if opening is not None:
                    fence_character = opening[0][0]
                    fence_length = len(opening[0])
            else:
                if "<!--" in line or "-->" in line:
                    raise AssertionError(
                        "HTML comment markers inside fenced code are unsupported"
                    )
                if EnforcementGuardrailDocumentationTests._is_closing_fence(
                    line, fence_character, fence_length
                ):
                    fence_character = None
                    fence_length = 0
        if fence_character is not None:
            raise AssertionError("Unclosed fenced code block")
        if html_comment_open:
            raise AssertionError("Unclosed HTML comment")

    @staticmethod
    def _is_code_only_line(line: str) -> bool:
        value = line.strip()
        if not value.startswith("`"):
            return False
        marker_length = len(value) - len(value.lstrip("`"))
        marker = "`" * marker_length
        if not value.endswith(marker) or len(value) <= marker_length * 2:
            return False
        body = value[marker_length:-marker_length]
        return marker not in body

    @staticmethod
    def _strip_html_comments(value: str) -> str:
        return re.sub(
            r"<!--.*?(?:-->|\Z)",
            lambda match: "\n" * match.group(0).count("\n"),
            value,
            flags=re.DOTALL,
        )

    @staticmethod
    def _strip_inline_code_spans(value: str) -> str:
        characters = list(value)
        index = 0
        while index < len(value):
            if value[index] != "`":
                index += 1
                continue
            run_end = index
            while run_end < len(value) and value[run_end] == "`":
                run_end += 1
            marker = value[index:run_end]
            closing = value.find(marker, run_end)
            if closing < 0:
                index = run_end
                continue
            for offset in range(index, closing + len(marker)):
                if characters[offset] not in "\r\n":
                    characters[offset] = " "
            index = closing + len(marker)
        return "".join(characters)

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
            link_end = EnforcementGuardrailDocumentationTests._parse_link_suffix(
                value, end + 1
            )
            if link_end is None:
                return None, start
            return value[start + 1 : end], link_end

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
                link_end = EnforcementGuardrailDocumentationTests._parse_link_suffix(
                    value, index
                )
                if link_end is None:
                    return None, start
                return "".join(target).strip(), link_end
            else:
                target.append(character)
            index += 1
        return None, start

    @staticmethod
    def _parse_link_suffix(value: str, start: int) -> int | None:
        index = start
        while index < len(value) and value[index] in " \t\r\n":
            index += 1
        if index >= len(value):
            return None
        if value[index] == ")":
            return index + 1
        if value[index] not in {'"', "'", "("}:
            return None
        opening = value[index]
        closing_character = ")" if opening == "(" else opening
        closing = EnforcementGuardrailDocumentationTests._find_unescaped(
            value, closing_character, index + 1
        )
        if closing < 0:
            return None
        index = closing + 1
        while index < len(value) and value[index] in " \t\r\n":
            index += 1
        if index >= len(value) or value[index] != ")":
            return None
        return index + 1

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
