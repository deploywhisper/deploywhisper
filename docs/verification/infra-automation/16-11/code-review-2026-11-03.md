# Story 16.11 re-review — 2026-11-03

Outcome: **changes requested; story remains in progress**.

## Scope and method

Reviewed the ten tracked/untracked files listed in the story, including the
complete current Packet 1 implementation and tests, against baseline `0e197ce`
on `feature/16-11-github-receiver-reconciliation`. The input contained 1,598 diff
lines, including new files. Existing local review claims were rechecked.

Three independent native review layers completed: blind adversarial review,
edge-case path tracing and acceptance audit. Initial role-configured launches
failed because their configured model was unavailable; replacement native
agents using the session default completed all three layers. No review layer
remains missing. Edge-case and acceptance layers returned no actionable
findings. The blind layer's single finding was independently reproduced.

## P2: Effective tag protection split across rulesets is rejected

Location: `integrations/github/infra_automation_adapter.py:192`.

The adapter checks `{"update", "deletion"}.issubset(kinds)` independently for
each ruleset. Given two active applicable tag rulesets with empty bypass lists,
one containing `update` and the other `deletion`, the tag has both protections
but qualification fails. This denies valid protected-tag dispatch under AC1.
It is an availability/compatibility defect, not an unsafe admission.

[GitHub's rule-layering contract](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets#about-rule-layering)
aggregates applicable rules across rulesets targeting the same branch or tag.

Reproduction used the existing `GithubAdapterTests` fixture in a temporary
in-memory Python invocation: replaced the branch metadata with a commit tag;
provided two active exact-match rulesets without bypasses, IDs 1 and 2, with
`update` and `deletion` respectively. Actual result:
`github_target_unqualified`. Moving both rules into ruleset 1 admitted the same
SHA (`a` repeated 40 times). No network requests or production edits occurred.

Action: aggregate qualified applicable rule kinds before requiring both
protections. Add split-ruleset regression coverage and retain fail-closed
handling for missing protection, bypass actors and unsupported conditions.
The action item is recorded unchecked in the story; no fix was applied during
this review. Triage: 0 decisions, 1 patch, 0 deferred, 0 dismissed findings.

## Validation rerun

- `./.venv/bin/python -m unittest tests.test_infra_automation.test_github_adapter tests.test_infra_automation.test_target_transport -q` — 46 tests passed.
- `./.venv/bin/ruff check .` — passed.
- `./.venv/bin/ruff format --check .` — 477 files already formatted.
- `./.venv/bin/mypy --follow-imports=silent --ignore-missing-imports infra_automation/github_contracts.py infra_automation/target_transport.py integrations/github/infra_automation_adapter.py` — passed, 3 source files.
- `./.venv/bin/bandit -q integrations/github/infra_automation_adapter.py infra_automation/github_contracts.py infra_automation/target_transport.py --severity-level medium --confidence-level medium` — passed.
- `git diff --check` — passed before review documentation and rerun afterward.

The current [GitHub dispatch documentation](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
was rechecked: API `2026-03-10` uses the implemented ref/inputs request and HTTP
200 acceptance response with run ID and URLs. No live dispatch was attempted.

Full root discovery, API/CLI/infra shard and local CI were not repeated in this
review; prior implementation results remain in `packet-1-review.md`. No Python
or UI code changed. UI validation not applicable to this adapter-only review.

## Acceptance and next workflow

Live sandbox qualification is still missing and Packets 2–5 are unimplemented.
These are acknowledged scope gates, not concealed completion claims. Passing
local adapter tests cannot close AC2–6 or whole-story acceptance. Story and
sprint status remain `in-progress`. No commit/push/PR was performed because
review follow-up and qualification work remain open.

BMad help routing: return to `bmad-dev-story` for the recorded patch and Packet 1
sandbox gate, then re-run `bmad-code-review`; do not advance to the next story
or claim story closure.

## Follow-up resolution

The P2 finding was fixed and verified on 2026-11-03. See
[review-fixes-2026-11-03.md](review-fixes-2026-11-03.md) for red/green regression,
independent review and final broad test results. The original review above is
retained as history; whole-story qualification remains outstanding.
