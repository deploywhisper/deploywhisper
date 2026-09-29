"""Documentation checks for optional enforcement guardrails."""

from __future__ import annotations

import html
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlparse

import yaml
from markdown_it import MarkdownIt
from markdown_it.token import Token

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


class _LocalHtmlTargetCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        target = values.get("href") if tag == "a" else values.get("src")
        if tag in {"a", "img"} and target:
            self.targets.add(target)


class _HtmlHeadingCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headings: list[tuple[int, str, int, int]] = []
        self._active: tuple[int, int, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        match = re.fullmatch(r"h([1-6])", tag, flags=re.IGNORECASE)
        if match is not None and self._active is None:
            self._active = (int(match.group(1)), self.getpos()[0] - 1, [])

    def handle_data(self, data: str) -> None:
        if self._active is not None:
            self._active[2].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._active is None:
            return
        level, start, parts = self._active
        if tag.lower() != f"h{level}":
            return
        text = re.sub(r"\s+", " ", "".join(parts)).strip()
        self.headings.append((level, text, start, self.getpos()[0]))
        self._active = None


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
                "do not expose deterministic lookup by the pre-submission request identity",
                "accepts and persists the idempotency key",
                "Until that server support exists, keep the consumer non-blocking",
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
                    self._resolved_local_doc_target(source, expected_target)
                    .resolve()
                    .is_file()
                )

    def test_guardrail_guide_outbound_links_resolve(self) -> None:
        content = GUARDRAIL_GUIDE.read_text(encoding="utf-8")
        links = self._markdown_links(content)

        local_links = {
            target
            for target in links
            if not ((parsed := urlparse(target)).scheme or parsed.netloc)
        }
        for target in local_links:
            with self.subTest(local_target=target):
                target_path = self._resolved_local_doc_target(GUARDRAIL_GUIDE, target)
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
                    GUARDRAIL_GUIDE, expected_target
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
        self.assertIn("no other repository or environment shares", content)
        self.assertIn("separate project or integration identity", content)
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
            "These enforcement semantics require an Action release that exposes all five required outputs: `policy-status`, `configured-mode`, `effective-status`, `should-block`, and `failure-kind`, and consumes the enforcement-decision endpoint.",
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
        self.assertIn(
            "Publication of `failure-kind` is best effort when output publication itself fails",
            content,
        )
        self.assertIn(
            "A missing `failure-kind` must fail closed as an operational error",
            content,
        )

    def test_guardrail_guide_discloses_current_app_evidence_limit(self) -> None:
        content = self._normalized(GUARDRAIL_GUIDE.read_text(encoding="utf-8"))

        self.assertIn(
            "An enforcement-capable Action revision must expose all five required outputs: `policy-status`, `configured-mode`, `effective-status`, `should-block`, and `failure-kind`",
            content,
        )
        self.assertIn(
            "The current GitHub App does not publish an `operational-error` classification, failing stage, or stable error code",
            content,
        )
        self.assertIn(
            "Keep the GitHub App check non-blocking until that evidence contract is implemented and validated",
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
        with self.assertRaisesRegex(AssertionError, "exactly one Markdown table"):
            self._effective_status_rows(duplicate)

        with self.assertRaisesRegex(AssertionError, "exactly one Markdown table"):
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
                "./guide%20with%20spaces.md",
                "./guide_(v3).md",
            },
            self._markdown_links(content),
        )

    def test_markdown_links_follow_commonmark_forms(self) -> None:
        for malformed_text in (
            "[Bad angle](<./bad.md>junk)",
            "[Bad title](./bad-title.md invalid)",
        ):
            with self.subTest(malformed_text=malformed_text):
                self.assertEqual(set(), self._markdown_links(malformed_text))
        self.assertEqual(
            {"./enforcement-guardrails.md"},
            self._markdown_links(
                "[Guide][guardrail]\n\n[guardrail]: ./enforcement-guardrails.md"
            ),
        )

    def test_markdown_contract_uses_rendered_commonmark_nodes(self) -> None:
        self.assertEqual(
            set(),
            self._markdown_links("> ```markdown\n> [Hidden](./missing.md)\n> ```"),
        )
        self.assertEqual(
            {"./missing.md"},
            self._markdown_links(
                "```text\n<!-- literal comment marker -->\n```\n[Visible](./missing.md)"
            ),
        )
        for rendered_link in (
            "[guardrail [details]](./missing.md)",
            '<a href="./missing.md">Missing</a>',
            "<a href=./missing.md>Missing</a>",
            "[Root local](/docs/missing.md)",
        ):
            with self.subTest(rendered_link=rendered_link):
                self.assertEqual(
                    {"/docs/missing.md"}
                    if rendered_link.startswith("[Root")
                    else {"./missing.md"},
                    self._markdown_links(rendered_link),
                )

        section = """\
## Target
[short label](./required-hidden-phrase.md)
- list item

      hidden list code requirement
"""
        visible = self._normalized(
            self._visible_prose(self._section(section, "## Target"))
        )
        self.assertEqual("short label list item", visible)
        self.assertNotIn("required-hidden-phrase", visible)
        self.assertNotIn("hidden list code requirement", visible)

        two_spans = "`soft-block` requires review before `hard-block`"
        self.assertIn(two_spans, "".join(self._rendered_markdown_lines(two_spans)))

        raw_heading = "## Target\ninside\n<h2>Boundary</h2>\noutside\n"
        self.assertEqual(
            "inside", self._normalized(self._section(raw_heading, "## Target"))
        )

        self.assertIn(
            "`<!--` literal opener",
            "".join(self._rendered_markdown_lines("`<!--` literal opener")),
        )
        for malformed in ("```text\nunclosed fence", "<!-- unclosed comment"):
            with self.subTest(malformed=malformed):
                with self.assertRaises(AssertionError):
                    self._rendered_markdown_lines(malformed)

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

        section = self._normalized(
            self._visible_prose(self._section(content, "## Target"))
        )

        self.assertIn("visible requirement with `an identifier`", section)
        self.assertIn("hidden normative requirement", section)
        self.assertIn("hidden indented requirement", section)
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

        with self.assertRaisesRegex(AssertionError, "Unclosed YAML workflow fence"):
            self._documented_workflow(real_workflow.removesuffix("```\n"))

    def test_raw_html_headings_follow_rendered_markdown_boundaries(self) -> None:
        content = """\
```html
<h2>Hidden fence boundary</h2>
```
<!--
<h2>Hidden comment boundary</h2>
-->
<h2
 class="scope-boundary">
Target <em>scope</em>
</h2>
inside target
<h2 data-boundary="next">Next scope</h2>
outside target
"""

        self.assertEqual(
            {"target-scope", "next-scope"},
            self._markdown_heading_anchors(content),
        )
        self.assertEqual(
            "inside target",
            self._normalized(self._section(content, "## Target scope")),
        )

    def test_documented_workflow_accepts_yaml_info_attributes_and_longer_close(
        self,
    ) -> None:
        content = """\
```yaml title="protected workflow"
jobs:
  deploywhisper:
    steps: []
````
"""

        self.assertEqual(
            {"jobs": {"deploywhisper": {"steps": []}}},
            self._documented_workflow(content),
        )

    def test_effective_status_rows_require_code_formatted_statuses(self) -> None:
        section = self._section(
            GUARDRAIL_GUIDE.read_text(encoding="utf-8"),
            "## Choose the least forceful mode that works",
        )

        malformed = section.replace("| `advisory` |", "| advisory |", 1)

        with self.assertRaisesRegex(AssertionError, "inline code"):
            self._effective_status_rows(malformed)

    def test_fragment_only_link_resolves_to_the_source_document(self) -> None:
        self.assertEqual(
            GUARDRAIL_GUIDE.resolve(),
            self._resolved_local_doc_target(
                GUARDRAIL_GUIDE,
                "#choose-the-least-forceful-mode-that-works",
            ),
        )

    @staticmethod
    def _normalized(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _markdown_tokens(value: str) -> list[Token]:
        return (
            MarkdownIt("commonmark")
            .enable("table")
            .enable("strikethrough")
            .parse(value)
        )

    @staticmethod
    def _inline_visible_text(
        token: Token, *, preserve_code_markers: bool = False
    ) -> str:
        parts: list[str] = []
        for child in token.children or []:
            if child.type == "text":
                parts.append(child.content)
            elif child.type == "code_inline":
                parts.append(
                    f"`{child.content}`" if preserve_code_markers else child.content
                )
            elif child.type in {"softbreak", "hardbreak"}:
                parts.append(" ")
            elif child.type == "image":
                parts.append(child.content)
        return "".join(parts)

    @staticmethod
    def _visible_prose(value: str) -> str:
        parts = [
            EnforcementGuardrailDocumentationTests._inline_visible_text(
                token, preserve_code_markers=True
            )
            for token in EnforcementGuardrailDocumentationTests._markdown_tokens(value)
            if token.type == "inline"
        ]
        return html.unescape(" ".join(part for part in parts if part))

    @staticmethod
    def _markdown_links(value: str) -> set[str]:
        targets: set[str] = set()
        html_collector = _LocalHtmlTargetCollector()
        for token in EnforcementGuardrailDocumentationTests._markdown_tokens(value):
            if token.type in {"html_block", "html_inline"}:
                html_collector.feed(token.content)
            for child in token.children or []:
                if child.type == "link_open":
                    target = child.attrGet("href")
                    if target:
                        targets.add(target)
                elif child.type == "image":
                    target = child.attrGet("src")
                    if target:
                        targets.add(target)
                elif child.type == "html_inline":
                    html_collector.feed(child.content)
        targets.update(html_collector.targets)
        return targets

    @staticmethod
    def _heading_records(value: str) -> list[tuple[int, str, int, int]]:
        records: list[tuple[int, str, int, int]] = []
        tokens = EnforcementGuardrailDocumentationTests._markdown_tokens(value)
        for index, token in enumerate(tokens):
            if token.type != "heading_open" or token.map is None:
                continue
            inline = tokens[index + 1]
            records.append(
                (
                    int(token.tag[1:]),
                    EnforcementGuardrailDocumentationTests._inline_visible_text(inline),
                    token.map[0],
                    token.map[1],
                )
            )
        for token in tokens:
            if token.type != "html_block" or token.map is None:
                continue
            collector = _HtmlHeadingCollector()
            collector.feed(token.content)
            records.extend(
                (level, text, token.map[0] + start, token.map[0] + end)
                for level, text, start, end in collector.headings
            )
        return sorted(records, key=lambda record: record[2])

    @staticmethod
    def _markdown_heading_anchors(value: str) -> set[str]:
        anchors: set[str] = set()
        duplicate_counts: dict[str, int] = {}
        for _, heading, _, _ in EnforcementGuardrailDocumentationTests._heading_records(
            value
        ):
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
        match = re.fullmatch(r"(#{1,6})\s+(.+)", heading)
        if match is None:
            raise AssertionError(f"Invalid ATX section heading: {heading}")
        level = len(match.group(1))
        target_text = match.group(2).strip()
        records = EnforcementGuardrailDocumentationTests._heading_records(value)
        matches = [record for record in records if record[:2] == (level, target_text)]
        if not matches:
            raise AssertionError(f"Missing section: {heading}")
        if len(matches) > 1:
            raise AssertionError(f"Duplicate section: {heading}")
        _, _, _, start = matches[0]
        end = len(value.splitlines())
        for candidate_level, _, candidate_start, _ in records:
            if candidate_start >= start and candidate_level <= level:
                end = candidate_start
                break
        lines = value.splitlines(keepends=True)
        section = "".join(lines[start:end])
        return "".join(
            EnforcementGuardrailDocumentationTests._rendered_markdown_lines(
                section, keepends=True
            )
        )

    @staticmethod
    def _documented_workflow(value: str) -> dict[str, object]:
        workflows: list[dict[str, object]] = []
        lines = value.splitlines()
        for token in EnforcementGuardrailDocumentationTests._markdown_tokens(value):
            info_name = token.info.split(maxsplit=1)[0].lower() if token.info else ""
            if token.type != "fence" or info_name not in {"yaml", "yml"}:
                continue
            if (
                token.map is None
                or not EnforcementGuardrailDocumentationTests._fence_is_closed(
                    lines, token
                )
            ):
                raise AssertionError("Unclosed YAML workflow fence")
            payload = yaml.safe_load(token.content)
            if isinstance(payload, dict) and "jobs" in payload:
                workflows.append(payload)
        if len(workflows) != 1:
            raise AssertionError(
                f"Expected exactly one documented workflow, found {len(workflows)}"
            )
        return workflows[0]

    @staticmethod
    def _fence_is_closed(lines: list[str], token: Token) -> bool:
        if token.map is None or token.map[1] <= token.map[0] + 1:
            return False
        closing = lines[token.map[1] - 1]
        closing = re.sub(r"^(?: {0,3}>[ \t]?)+", "", closing)
        marker = token.markup[0]
        return (
            re.fullmatch(
                rf" {{0,3}}{re.escape(marker)}{{{len(token.markup)},}}[ \t]*",
                closing,
            )
            is not None
        )

    @staticmethod
    def _effective_status_rows(value: str) -> dict[str, tuple[str, str]]:
        expected_header = ["Effective status", "Workflow effect", "Appropriate use"]
        tables: list[list[list[str]]] = []
        current_table: list[list[str]] | None = None
        current_row: list[str] | None = None
        in_cell = False
        for token in EnforcementGuardrailDocumentationTests._markdown_tokens(value):
            if token.type == "table_open":
                current_table = []
            elif token.type == "tr_open" and current_table is not None:
                current_row = []
            elif token.type in {"th_open", "td_open"}:
                in_cell = True
            elif token.type == "inline" and in_cell and current_row is not None:
                current_row.append(
                    EnforcementGuardrailDocumentationTests._inline_visible_text(
                        token, preserve_code_markers=len(current_row) == 0
                    )
                )
            elif token.type in {"th_close", "td_close"}:
                in_cell = False
            elif token.type == "tr_close" and current_table is not None:
                if current_row is not None:
                    current_table.append(current_row)
                current_row = None
            elif token.type == "table_close" and current_table is not None:
                tables.append(current_table)
                current_table = None
        if len(tables) != 1:
            raise AssertionError(
                "Effective-status section must contain exactly one Markdown table"
            )
        table = tables[0]
        if not table or table[0] != expected_header:
            raise AssertionError(
                "Effective-status table header is missing or malformed"
            )
        rows: dict[str, tuple[str, str]] = {}
        for cells in table[1:]:
            if len(cells) != 3:
                raise AssertionError(f"Malformed effective-status row: {cells}")
            status_match = re.fullmatch(
                r"`(advisory|warn|soft-block|hard-block)`", cells[0]
            )
            if status_match is None:
                raise AssertionError(
                    "Effective-status row label must be a single inline code span: "
                    f"{cells[0]}"
                )
            status = status_match.group(1)
            if status not in {"advisory", "warn", "soft-block", "hard-block"}:
                raise AssertionError(f"Unexpected effective-status row: {cells}")
            if status in rows:
                raise AssertionError(f"Duplicate effective-status row: {status}")
            rows[status] = (
                cells[1],
                cells[2],
            )
        return rows

    @staticmethod
    def _rendered_markdown_lines(value: str, *, keepends: bool = False) -> list[str]:
        excluded_lines: set[int] = set()
        source_lines = value.splitlines()
        for token in EnforcementGuardrailDocumentationTests._markdown_tokens(value):
            if token.map is None:
                continue
            if (
                token.type == "fence"
                and not EnforcementGuardrailDocumentationTests._fence_is_closed(
                    source_lines, token
                )
            ):
                raise AssertionError("Unclosed fenced code block")
            if (
                token.type == "html_block"
                and token.content.lstrip().startswith("<!--")
                and "-->" not in token.content
            ):
                raise AssertionError("Unclosed HTML comment")
            if token.type in {"fence", "code_block"} or (
                token.type == "html_block" and token.content.lstrip().startswith("<!--")
            ):
                excluded_lines.update(range(token.map[0], token.map[1]))
        lines = value.splitlines(keepends=keepends)
        return [line for index, line in enumerate(lines) if index not in excluded_lines]

    @staticmethod
    def _resolved_local_doc_target(source: Path, target: str) -> Path:
        parsed = urlparse(target)
        if parsed.scheme or parsed.netloc:
            raise AssertionError(
                f"Expected a repository-local documentation link: {target}"
            )
        decoded_path = unquote(parsed.path)
        if not decoded_path:
            candidate = source.resolve()
        elif decoded_path.startswith("/"):
            candidate = (REPO_ROOT / decoded_path.lstrip("/")).resolve()
        else:
            candidate = (source.parent / decoded_path).resolve()
        repository_root = REPO_ROOT.resolve()
        if not candidate.is_relative_to(repository_root):
            raise AssertionError(f"Documentation link escapes repository: {target}")
        if not candidate.is_file():
            raise AssertionError(f"Documentation link is not a file: {target}")
        return candidate
