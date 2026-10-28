# Story 16.7 workflow editor and run history verification

Date: 2026-10-28. Branch: `feature/16-7-workflow-editor-run-history-ui`.
Story: [`16-7-workflow-editor-and-run-history-ui.md`](../../../../_bmad-output/implementation-artifacts/16-7-workflow-editor-and-run-history-ui.md).
Design authority: [`deploywhisper-redesign-v3.jsx`](../../../design/deploywhisper-redesign-v3.jsx)
and [`infra-automation-ux.md`](../../../design/infra-automation-ux.md).

## Delivery boundary

This React slice uses the merged Story 16.1–16.6 APIs and the merged
[backend-for-UI capability contract](../../../infra-automation/ui-capabilities.md)
from PR #200. It does not change any API, analysis, data model, or credential
contract. Actual composed uploaded preflight revealed an earlier coordinator
bug: the production session expires scheduling candidates on commit, while the
earlier tests used nonexpiring sessions. The narrow fix and its expiring-session
regression are in separate [backend-for-UI PR #201](https://github.com/deploywhisper/deploywhisper/pull/201).
Composed browser proof builds the UI source with the exact coordinator source from
that PR in a disposable Docker build context. PR #201 must merge before the UI PR
can deliver a working uploaded run on `develop`. No operator database was used.

## Browser proof

The production image is built by `docker compose up -d --build` with the existing
Dockerfile. The default public-compatibility lane and the separate
`local-development` identity lane each use an isolated Compose project and volume.
The latter seeds only synthetic accounts and protected projects inside its
disposable container, writes its test-only credentials to a private 0600 file,
and signs in through the actual browser form. No test uses preseeded browser
cookies or mocked success responses for the main journey.

The authenticated suite covers keyboard sign-in → actual workflow-v2 template →
server validation → draft save → immutable publish → uploaded file admission →
durable run and attempts → screened logs/digests → permanent briefing with a
verified relational run link → browser logout and denied return. It also covers
safe return paths, failed credentials, real feature-off historical reads, project
switching, read-only/unassigned roles, bad Origin/CSRF, stale version conflict,
network loss and same-scope draft retention, revocation and server expiry while a
protected report remains mounted. Keyboard focus and axe critical/serious gates
are checked on the new account, workflow and run screens. The report's tab
Arrow/Home/End and panel relationship checks are part of the final browser pass.

Screenshots from the composed app use root SPA routes and actual API data:

| State | 1440px | 760px |
| --- | --- | --- |
| Account unavailable | [desktop](screenshots/account-unavailable-1440.png) | [tablet](screenshots/account-unavailable-760.png) |
| Published workflow | [desktop](screenshots/workflow-1440.png) | [tablet](screenshots/workflow-760.png) |
| Uploaded run | [desktop](screenshots/run-1440.png) | [tablet](screenshots/run-760.png) |
| Permanent briefing | [desktop](screenshots/briefing-1440.png) | [tablet](screenshots/briefing-760.png) |
| Read-only scope | [desktop](screenshots/readonly-1440.png) | [tablet](screenshots/readonly-760.png) |
| Feature disabled | [desktop](screenshots/execution-disabled-1440.png) | [tablet](screenshots/execution-disabled-760.png) |

Visual-verdict iterations: account page 82 → 93 after restoring the approved
Settings containment; workflow/run/report 87 → 91 after removing duplicate
evidence and output rows and giving publication a neutral notice. The final
keyboard enhancement changes tab semantics and hidden panel references, without
changing the visible composition. The structured verdict is in
`.omx/state/16-7-ui/ralph-progress.json` (local ignored runtime state).

## Validation record

| Command / gate | Actual result |
| --- | --- |
| `npm run ui:typecheck` | Passed after the final report-tab and contrast changes. |
| `npm run ui:test` | 158 passed. The verdict-chip snapshot was updated only for its new semantic `data-verdict` attribute. |
| `npm run ui:build` | Passed; the existing Dockerfile also built the React assets and served them from FastAPI. |
| `./.venv/bin/python -m unittest discover -q` | 1,161 tests, two expected skips, passed. |
| `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` | 685 passed, 2,267 subtests, one opt-in qualification skipped. |
| `bash scripts/ci-local.sh` | Passed all 10 registered Python directories, 2,607 tests total, plus Ruff, repo-wide formatting, prompt-injection and configured security gates. |
| Identity-enabled Compose/Playwright (new suite) | 14/14 passed, real browser accounts, APIs and worker. No success routes were mocked. |
| Existing Compose/Playwright baseline suite | 15 passed; 14 identity-only tests and two older opt-in tests skipped in the default identity-disabled profile. The new authenticated suite above establishes this story's browser proof. |
| Visual verdict and screenshots | Account 94/100; workflow, run and briefing 92/100, all from composed 1440/760 routes. |
| `git diff --check` and repo-wide `./.venv/bin/ruff format --check .` | Passed after code/test changes. |

The final `BASE_URL=http://localhost:8080 RUN_UI_A11Y=1 bash scripts/ci-local.sh`
run passed on a fresh baseline Compose volume: 2,607 Python tests across all ten
directories, configured static/security gates, then 15 browser tests passed with
16 documented skips (14 require the separate authenticated fixture/profile and
two are older opt-in cases). All 14 new authenticated cases passed in their actual
profile. The disposable container and volume were removed. The original user
container `deploywhisper-deploywhisper-1` was restarted with the same ID,
`e2ab5e554166…`; its health endpoint returned HTTP 200. The private test fixture
file was removed after proof collection.

The first broad local CI run exposed an existing test's false positive: it searched
the entire serialized backtest for the private incident ID's digits, which can
also occur in a public project timestamp. The test now puts those digits in that
timestamp deliberately and checks every incident reference structurally; the
private title is still absent. The focused regression and complete CI rerun passed.
No production backend contract changed in this UI PR.

Three native AI review layers found and rechecked corrections for project-wide
scope round-tripping, log refresh, fresh account checks before mutations, uncertain
start responses, denied-run recovery, evidence-deadline refresh, protected report
cache invalidation, and retained feedback refresh behavior. The report remains v2;
run provenance is verified through the separate relation. The newer browser checks
also covered report tab Arrow/Home/End behavior, focus after actions, semantic
error summaries and axe critical/serious gates. No unresolved introduced review
finding is recorded. Independent human approval is not claimed.

Remaining boundary: PR #201 is open and must merge before this UI can run durable
preflights on `develop`. Production identity TLS/proxy qualification and the later
approval, runner, receiver and operations screens remain their owning stories.
