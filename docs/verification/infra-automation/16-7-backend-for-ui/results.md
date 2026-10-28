# Story 16.7 backend-for-UI prerequisite verification

Date: 2026-10-28. Scope: live scoped capability/feature-state discovery only.
Branch: `feature/16-7-backend-for-ui-capabilities`.
Baseline: `57990443112d472187f2e2e68d0cf754568267ed` (merged Story 16.6, PR199).
Status: implementation, independent review and final local verification passed.

## Need and compatibility with Story 16.6

Cross-checked delivered preflight APIs, services, schema and story acceptance.
16.6 supplies authenticated upload admission, durable run/step/log views,
screened artifact references and relational immutable report/evidence status.
It does not expose the caller's effective editor/start permissions. Role
definitions are static; membership lists are administrative; settings reads
require project-wide draft capability. The additive projection fills that gap
without changing those existing contracts or their authority checks.

The new integration case uses the actual 16.6 workflow publication and preflight
admission fixture. It then disables execution and verifies that authorized run
history and report-relation reads remain available, the projection reports
disabled state, and a previously captured request permission cannot start new
work. No report/provenance schema or analysis semantics changes.

## Implementation and tests

`GET /api/v1/infra-automation/capabilities` uses the existing authenticated
AutomationRoute. Its service reserves the existing authorization transaction,
resolves live exact-scope membership and policy, and projects four existing role
permissions. The strict closed response is versioned separately; it validates
ordered unique permissions containing read. Feature state and role permission
remain separate facts. No authority or secret is issued.

Test-first evidence:

- Before implementation: new route/service coverage failed on 404/missing service
  method (28 failed, 2 passed including subtest outcomes).
- Before review correction: four malformed list variants reproduced schema gaps.
- Final focused capability/workflow/preflight/policy regression bundle:
  **68 passed, 130 subtests passed**.
- New tests cover role mapping independent of account-admin/header assertions;
  project/workspace isolation; live policy/membership changes; account disablement,
  expiry, actual session logout/revocation and nonhuman credentials; CSRF separation;
  unavailable/corrupt policy; strict schema/no-store/fixed errors; read-only entity
  persistence and actual 16.6 disabled-mode continuity.

Focused command:

```sh
./.venv/bin/python -m pytest \
  tests/test_api/test_infra_automation_capabilities.py \
  tests/test_infra_automation/test_ui_capabilities.py \
  tests/test_api/test_infra_automation_workflows.py \
  tests/test_api/test_infra_automation_preflight.py \
  tests/test_infra_automation/test_workflow_policy.py -q --tb=short
```

Repository-wide constructor/consumer search found the new response models only
in their schema, adapter and tests. No existing constructor or fixture changed.
The new tests use already registered API/automation directories; no discovery
configuration change is needed. Generated React types remain Story 16.7 Packet 1.

## Independent review

Three fresh native reviewers received no conversation context: blind diff hunter,
edge-case path tracer and acceptance auditor. No authority bypass or prior contract
regression was identified. Three concrete findings were resolved: contradictory
capability lists, missing distinct logout-revocation proof, and documentation still
describing the earlier no-code blocker. Added the storage-failure proof requested
by blind review. All three reviewers rechecked the changed delta: no remaining
actionable introduced findings. The acceptance auditor independently ran the
initial 17-test bundle /38 subtests before hardening.

## Production Python verification

Built the existing Dockerfile from a temporary tracked-source context excluding
local `.env`, data and credentials. The first stdin-context build hit Docker's
`COMPRESSION_ERROR`; extracting the same archive and building from its directory
succeeded. No daemon reset or repository build change was needed.

Image: `sha256:3d6a96631703363152dd0e6ecf9d3fabe066b6f350c8f09cfbae42c0e1286f8f`.
Runtime: Python 3.11.17; non-root; Node absent.

```sh
docker run --rm --network none \
  --mount type=bind,source="$PWD/tests",target=/app/tests,readonly \
  deploywhisper:16-7-bff python -m unittest \
  tests.test_api.test_infra_automation_capabilities \
  tests.test_infra_automation.test_ui_capabilities -q
```

Result: **20 tests passed** in 4.623 seconds. Read-only synthetic test mount only;
the image's database/storage remained ephemeral. Separate container checks verified
the production app's OpenAPI route and closed schema, actual `python app.py`
startup, HTTP health and generic no-store denial on the protected endpoint.
Containers used `--rm` and no host data volume or published port.

## Repository verification and limits

Commands use the repository's existing virtual environment (Python 3.14.3) and
`LLM_API_BASE=http://127.0.0.1:9` for bounded local-only provider fallback:

| Command | Actual result |
| --- | --- |
| `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` | 685 passed, 2,267 subtests passed, one opt-in qualification skipped; 220.43 seconds |
| `bash scripts/ci-local.sh` | Passed: 2,607 tests in all 10 registered directories, prompt-injection 8 tests /96 subtests, skill harness, compile, dependency graph, Ruff and configured security gates |
| `./.venv/bin/python -m unittest discover -q` (final rerun) | Passed: 1,161 tests, two expected skips; 471.705 seconds |
| `./.venv/bin/ruff check .` | Passed |
| `./.venv/bin/ruff format --check .` | Passed, 427 files already formatted |
| Scoped Bandit on the four touched source files, medium severity/confidence | Passed, no findings |
| Repo-wide mypy over the CI targets with `--ignore-missing-imports --no-error-summary` | Existing nonblocking debt remains: exactly 324 diagnostic lines before/after; line-normalized multiset comparison found no added or removed diagnostics |
| `git diff --check` | Passed |

The full medium-threshold Bandit report retains one unchanged B104 medium/medium
finding in `services/sample_incident_pack.py:327`, a comparison allowing the sample
IP literal `0.0.0.0`, rather than a network listener. That file is identical to the
baseline. The configured high-severity/high-confidence gate passed; no suppression
or unrelated code change was added.

The initial `./.venv/bin/python -m unittest discover -q` ran 1,158 tests with two
skips and errored in
`EngineRecoveryTests.test_blocking_handler_does_not_block_tick_or_second_claim`:
one unconfirmed worker termination plus two cleanup retries. No engine code changed.
The exact case subsequently passed once and five more sequential repeats on both
a clean baseline archive and the current tree (six per tree). The original cause
remains unproven. Full local CI's automation directory then passed all 428 tests.
The final root smoke rerun executed after CI with no concurrent build and passed
all 1,161 tests with two expected skips in 471.705 seconds. The initial failure
and unproven cause are retained here rather than represented as a first-run pass.

UI validation not applicable: no rendered React surface, routing, keyboard or
accessibility behavior changes. Full editor/account-entry/Compose/axe/keyboard
acceptance remains in Story 16.7. This is not production-release qualification or
an execution/approval grant. Deliver this support separately with the
`backend-for-ui` label; the UI story remains unimplemented.
