# Story 16.9: Human Approval Inbox and Decision UX

Status: done
Preparation: refined
Release: v1.5.0

## Story

As a human approver, I want to review the exact evidence and target in an accessible decision inbox, so that my approval or rejection is deliberate, scoped and durably recorded.

## Entry gates and slice boundary

- Release priority: P0 feature work for v1.5.0. **Blocked for implementation** until Story 16.0 has recorded public RFC/CODEOWNERS acceptance, executable identity/fencing/isolation/custody/receiver qualification and final interface decisions; planning adoption alone is not authorization evidence.
- Hard earlier dependencies: **16.7, 16.8**, accepted and verified before advancing this story. These dependency results are currently unresolved; refined preparation does not mean ready-for-dev. No prior implementation learning is available for the new Epic 16 story set.
- Promote only after contract freeze, earlier dependency evidence, bounded task ownership/re-estimation and independent story review. Preserve IDs and backlog status; no feature/release implementation is claimed here.

## Acceptance Criteria

1. **AC1:** Given a verified human with project review permission, when the inbox and review screen open, then immutable evidence, registered target/payload, authorization_kind, source, policy, confidence/blast radius/rollback, freshness and effective deadline are visible before controls.
2. **AC2:** Given shared-mode requester self-approval or nonhuman credentials, when approve/reject is submitted, then the server denies it regardless of headers/UI; authenticated single-operator mode records and labels acknowledgement without a separation-of-duties claim.
3. **AC3:** Given no-go, high/critical severity or typed insufficient_context, when a decision is submitted, then explicit approve/reject and reason are required, with typed confirmation for high/critical; reasons cannot override hard eligibility blocks.
4. **AC4:** Given expiry, tuple mutation, project switch, role revocation, lost response or concurrent decision, when the screen refreshes/submits, then stale controls fail safely, the durable receipt is reloaded before resubmission and no second decision is minted.
5. **AC5:** Given a persisted decision, when scoped audit/export and receipt are viewed, then verified principal/type/role/scope/reason/time and before/after digests are append-only, screened and authorized with DB-admin trust limits documented.
6. **AC6:** Given composed-app real seeded data, when a keyboard user approves, rejects or encounters expiry/self-approval/denial, then focus and confirmation behavior, axe serious/critical gate and screenshots pass.

### Requirement Traceability

Coverage intent: Delta over the v1.4.0 baseline. These exact mapped requirements are acceptance obligations; mapping is not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| IAU15-FR-008 | Enforce distinct requester/approver identities in shared mode; label authenticated single-operator decisions as acknowledgement with no separation-of-duties claim. | Self-approval denial and acknowledgement-mode E2E |
| IAU15-FR-034 | Require an explicit authenticated approve/reject decision and reason when the canonical recommendation is `no-go`, severity is high/critical or the separate typed `insufficient_context` flag is true, with typed confirmation for high/critical. | Reason/confirmation API denial and keyboard decision E2E |
| IAU15-FR-054 | Provide a scoped approval inbox and keyboard-operable decision screen showing exact evidence, target/payload, freshness, policy, confidence, blast radius and rollback context with acknowledgement labeling. | Compose-built approve/reject/self-approval/freshness E2E |
| IAU15-FR-059 | Record append-only application audit events with verified principal/type, role, scope, target, reason, time and before/after digests; expose scoped UI/JSON export without raw artifacts/secrets and document DB-admin trust limits. | Audit event coverage/export authorization and secret corpus |
| IAU15-NFR-009 | All new React routes must pass the composed-app axe critical/serious violation gate and keyboard-only create/run/review/decision/recovery journeys, using real API-backed seeded data and required screenshots. | Compose production build, Playwright/axe/keyboard results and screenshots |

## Tasks / Subtasks and bounded ownership

- [x] **Packet 1 — UI owner: inbox and immutable packet (AC 1,2,4).** Owned output: `frontend/src/screens/InfraAutomationApprovals.tsx (planned), existing automation run screen and API client`.
  - [x] Implement scoped pending/expired/decided list, exact evidence/action summary and permanent report links with absolute timezone/deadline, explicit advisory_request versus exact_plan and acknowledgement labels.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 2 — UI owner: decision submission (AC 2–4,6).** Owned output: `typed frontend API adapter and confirmation/reason form`.
  - [x] Use verified sessions/CSRF and current server eligibility; accessible typed confirmation, reason validation and durable receipt recovery before retry; focus summary or receipt on outcome.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 3 — Service/test owner: audit and authorization verification (AC 2–5).** Owned output: `existing 16.8 decision API, models/repositories audit boundary and tests/test_api`.
  - [x] Prove malicious actor/role headers, service/runner credentials, self-approval, tuple mutation and concurrent submissions deny; add screened scoped JSON audit export if not delivered earlier in its own backend PR.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 4 — Test/documentation owner: browser proof (AC 1–6).** Owned output: `frontend/e2e, docs/infra-automation and record`.
  - [x] Capture keyboard approve/reject/acknowledgement and stale/lost-response/denied journeys, audit export and 1440/760 screenshots using actual API-backed data.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.

Each packet is a bounded review unit under this stable story ID; split large packets after 16.0 estimation instead of silently broadening scope. One story branch follows Git Flow; coordinate shared-file edits and do not revert other work.

### Review Findings

- [x] [Review][Patch] Show retained collection/source and redaction metadata [frontend/src/screens/InfraAutomationApprovals.tsx:247] — AC1 / UX Evidence row: collection time, source/trust flags and redaction version are retained but not rendered.
- [x] [Review][Patch] Show current freshness deadlines and elapsed validity [frontend/src/screens/InfraAutomationApprovals.tsx:114] — AC1/AC4: expose evidence/approval deadlines and remaining validity before controls; account for request transit and monotonic elapsed time.
- [x] [Review][Patch] Keep an ambiguous submission blocked on unchanged pending reads [frontend/src/screens/InfraAutomationApprovals.tsx:21] — AC4: pending equal-version recovery is not a terminal outcome. Retain uncertainty until a later terminal receipt; distinguish definite server rejection and test both paths.
- [x] [Review][Patch] Reject contradictory terminal receipts and attribution [frontend/src/api/infraAutomation.ts:279] — Reject same-version conflicting outcomes and approved/rejected service attribution; preserve independent reason screening, audit clocks and legitimate legacy values.
- [x] [Review][Patch] Label unavailable decision models without claiming independent review [frontend/src/screens/InfraAutomationApprovals.tsx:237] — AC2: null mode must stay unknown; provide a safe generic explanation when blocked guidance arrays are empty.
- [x] [Review][Patch] Stop repeated approval pagination cursors [frontend/src/screens/InfraAutomationApprovals.tsx:79] — Reject already consumed cursors and duplicate receipt pages instead of appending indefinitely.
- [x] [Review][Patch] Do not label audit exports complete when pages report gaps [frontend/src/screens/InfraAutomationApprovals.tsx:229] — AC5: complete must include each page gap/truncation flags, not only cursor exhaustion.
- [x] [Review][Patch] Focus newly rendered errors after React commits them [frontend/src/screens/InfraAutomationApprovals.tsx:164] — AC6: microtask focus can precede mounting the summary; use committed message state and assert focus in browser.

## Dev Notes

- Use the delivered decision API with seeded typed target/custody packets. Remote dispatch remains unavailable until 16.10/16.11; no forward receiver dependency for UX acceptance.
- Human credential classification establishes authorized account type, not proof a physical person clicked. No claim that scripted human credentials are technically impossible. Session principal, server memberships and CSRF establish the boundary; never caller role headers.
- Packet is immutable; display full digests accessibly on demand and target/action/earliest deadline immediately. Do not show approval grants, raw plan/state/download paths or secrets as evidence. Canonical recommendations remain go/caution/no-go; typed insufficient_context is separate.
- Reuse frontend/src/screens/Phase6Shell.tsx, projectSelection.ts, main.tsx routes, api/client.ts and theme/primitives. Do not assume SegmentedTabs already meets keyboard panel semantics. Clear transient decision state on project/auth changes; fresh server eligibility controls actions.
- Backend-for-UI behavior requires its own labeled PR. Audit is application append-only, not tamper-proof against DB/host administrators. Existing report links need the earlier protected read boundary.

### Project Structure Notes

- Planned modules are additions under the established Python/service/API/repository and React boundaries, not present-day implementation claims. Reuse `api/errors.py` ApiRoute/ApiError, `api/schemas.py`, `models/database.py`, `models/tables.py`, repositories and `migrations/versions/`; inspect head before allocation.
- Introduce only entities necessary for this slice; never precreate all automation tables. Keep deterministic findings in the shared analysis core, optional AI downstream and privileged execution outside FastAPI. No new dependencies without a recorded approved decision.
- Interface names/resources are design obligations pending 16.0 freeze, not permission to invent final route/schema contracts. Add docs and tests with behavior; do not defer slice coverage to 16.19.

## Required implementation verification

- [x] Register new `tests/test_infra_automation` directories in `scripts/ci-local.sh` and affected GitHub discovery/shards; root discovery alone skips non-package test directories.
- [x] For every Pydantic/schema/dataclass/constructor change, use repository-wide `rg` searches for direct instantiations/fixtures and update all consumers, including CLI/agent/action/report compatibility where affected.
- [x] Run `./.venv/bin/python -m unittest discover -q`, story-focused tests and exactly `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` for affected API/CLI/infra contracts.
- [x] Run `./.venv/bin/ruff check .`, **`./.venv/bin/ruff format --check .` repo-wide**, `bash scripts/ci-local.sh` and `git diff --check`; add applicable static/security/type checks. Record commands and actual results rather than assumed passes.
- [x] Run `npm run ui:typecheck`, `npm run ui:test`, `npm run ui:build`; then `docker compose up -d --build`, wait for `http://localhost:8080/api/v1/health`, seed synthetic authorized API data and run `BASE_URL=http://localhost:8080 npm run test:ui-review` with new journey coverage.
- [x] Run `BASE_URL=http://localhost:8080 RUN_UI_A11Y=1 bash scripts/ci-local.sh` for keyboard/axe critical/serious coverage; capture required 1440/760-width screenshots from root SPA routes and permanent `/reports/{id}` links, then `docker compose down`.
- [x] Record browser commands/results/screenshots before review. Vite dev server, legacy prefixed routes and existing report tests alone do not establish this story's browser acceptance. Backend-for-UI behavior requires a separate labeled PR.

## References

- [Canonical feature PRD](../planning-artifacts/prd-infra-automation.md), [exact requirement registry](../planning-artifacts/infra-automation-requirement-dispositions.json) and [Epic 16](../planning-artifacts/epics.md).
- [Architecture §25](../planning-artifacts/architecture.md#25-v150-infrastructure-automation-architecture-amendment), especially slice qualification §25.12; [mandatory project context](../project-context.md).
- [Readiness gates IR-01–IR-06](../planning-artifacts/implementation-readiness-report-2026-10-07-infra-automation-v1.5.0.md) and [release sequencing](../planning-artifacts/infra-automation-v1.5.0-release-plan.md).
- [Feature UX contract](../../docs/design/infra-automation-ux.md), [UX authority](../planning-artifacts/ux-design-specification.md), [v3 visual authority](../../docs/design/deploywhisper-redesign-v3.jsx) and [RFC 0001](../../docs/rfcs/0001-infra-automation-preflight-and-handoff.md).

## Dev Agent Record

### Agent Model Used

Codex — BMad dev-story with bounded native API, screen, browser-fixture and independent review agents; root owns integration and final verification.

### Implementation Plan

- Deliver the approved immutable review/current-context/confirmation prerequisite in its own backend-for-UI PR, then base the separate UI branch on the accepted result.
- Reuse existing scoped sessions, CSRF, API transport, query keys, automation frame, report reads, audit export and approved v3 primitives. No new dependencies or production backend behavior in the UI branch.
- Present exact report/action/source/policy/deadline context before controls; use native accessible confirmation and server-selected acknowledgement. Recover the exact durable receipt before retry, with no automatic mutation replay.
- Qualify actual composed production assets with protected synthetic fixtures in shared and fresh one-human profiles, keyboard/axe, 1440/760 screenshots and independent source review. Dispose only the test project and restore the exact operator container.

### Debug Log References

- Approved prerequisite: [spec](spec-16-9-backend-for-ui-review-packet.md), [readiness assessment](../planning-artifacts/implementation-readiness-report-2026-10-29-story-16-9.md), [PR204](https://github.com/deploywhisper/deploywhisper/pull/204), merged `7ecec1f`. Backend qualification is recorded in `docs/verification/infra-automation/16-9-backend-for-ui/results.md`.
- UI evidence, acceptance mapping, actual commands, fixture boundaries, independent findings and screenshots: `docs/verification/infra-automation/16-9/results.md`.
- Corrected initial stale-read controls, read regression, terminal modal/focus, protected report link, sign-in return allowlist, native focus wrapping/dialog margins, long project label containment and contrast findings. Independent rechecks found no remaining source blockers.
- Corrected a stale concurrent-test expectation to require the closed dialog and focused existing receipt; focused receipt/acknowledgement screenshots now show the actual recorded state.

### Completion Notes List

- Earlier unresolved dependency/backlog preparation notes are superseded by accepted Stories16.7/16.8 and merged prerequisite PR204. The maintainer explicitly approved the prerequisite first and then continuation of this story.
- UI branch: `feature/16-9-human-approval-inbox-decision-ux`, baseline `7ecec1f`. Inbox filters loaded recorded states; exact review is scoped by approval/run/project/workspace and identity epoch. Immutable evidence precedes controls. Full fingerprints and deadline components remain accessible.
- Explicit reason and high/critical typed phrases use current server context. Canonical no-go remains advisory; hard evidence/policy/authority failures cannot be overridden. Single-operator mode labels authenticated acknowledgement without an independent-review claim.
- Failed refreshes disable stale controls; authorization denial removes protected data. Project/identity change clears local forms. Expiry retains the local reason. Lost response recovers by exact-ID read without automatic POST replay; concurrent terminal refresh closes confirmation and focuses the retained receipt.
- Scoped audit export reuses the administrator-only endpoint and bounded pagination/completeness flag. Receipts retain actual principal/type/role/scope/reason/time and before/after state digests. Application append-only audit retains DB/host-admin trust limits.
- No new test directory or discovery registration was required: the four fixture guards live in existing `tests/test_infra`, already included by local CI and the exact GitHub shard. All production schema/constructor work shipped in the separately reviewed prerequisite; the UI branch adds strict TypeScript wire guards rather than changing Python constructors.
- `npm run ui:typecheck`, `npm run ui:test` (241 tests), `npm run ui:build`: pass. Composed shared profile: seven journeys pass; fresh single-operator profile: one journey passes with exactly one enabled human. Profile-inapplicable tests are excluded in each run, with all eight active across the two profiles.
- Browser command: `BASE_URL=http://localhost:8080 APPROVAL_UI_CONTAINER=deploywhisper-story16-9-deploywhisper-1 APPROVAL_UI_FIXTURE=<owned-mode0600-file> npm run test:ui-review -- infra-automation-approvals.spec.ts`, after `docker compose -p deploywhisper-story16-9 -f docker-compose.approval-ui.yml up -d --build`, health and real seed/export. Keyboard confirmation/focus, approve/reject/acknowledge, expiry, CSRF/self/denial, project/revocation, tuple/unavailable/hard blocks, concurrent/lost-response recovery, audit and protected report navigation pass the axe serious/critical gate. Screenshots at both widths are retained under `docs/verification/infra-automation/16-9/screenshots/`; visual verdict 94/100 against v3/WP6 and accepted16.7 captures.
- `LLM_API_BASE=http://127.0.0.1:1 ./.venv/bin/python -m unittest discover -q`: 1,278 run, two skips, OK. Exact `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: 697 pass, one opt-in skip, 2,279 subtests. Focused guard tests: four pass. Ruff lint/repo-wide format (447 files), Python compile, Docker Compose config, frontend checks and high/high Bandit pass.
- Full `BASE_URL=http://localhost:8080 RUN_UI_A11Y=1 bash scripts/ci-local.sh` completed every Python/static gate: all10 directories OK (2,724 run, two skips), plus eight prompt-injection tests/96 subtests. Its initial browser phase failed safely because the existing report seed helper selected the stopped default Compose project. The entire browser lane then passed with `BASE_URL=http://localhost:8080 COMPOSE_PROJECT_NAME=deploywhisper-story16-9 COMPOSE_FILE=/tmp/story16-9-ui-fixture/regression-compose.yaml npm run test:ui-review`: 15 pass, 24 fixture-inapplicable exclusions (eight approval cases actively verified above,16 earlier workflow/identity cases). The combined initial command was nonzero; the corrected browser rerun exited0. Unaffected Python gates were not repeated and no test/production bypass was added.
- Disposable Compose projects were removed after proof. The exact original operator container/image/persistent volume were restored and verified healthy with HTTP200. Private browser credential exports were removed. The actual runtime image was verified to contain no Node executable.
- Enhanced dev-story definition of done: PASS. All ACs have mapped API/unit/browser evidence, all tasks are checked, only permitted story sections changed, the complete file list is recorded, and story/sprint status is review. Post-workflow `bmad-help` routing selects [CR] Code Review (`bmad-code-review`) next in a fresh context.
- No production collector/registry/custody or remote receiver is qualified/enabled by this UI proof. Repository mypy retains the prerequisite's 312 pre-existing findings. The guarded fixture's five medium Bandit fixed-tmp-path diagnostics were reviewed with owned mode0600/no-follow/atomic-write safeguards; no suppressions were added.
- Formal `bmad-code-review` completed on2026-10-30: eight findings resolved (one high, seven medium), four candidates dismissed with evidence, no deferred/decision-needed or remaining findings. See `docs/verification/infra-automation/16-9/code-review.md`. Fresh layer rechecks are clear.
- Review correction validation: 256 frontend tests; typecheck/build;11 shared and1 fresh one-human approval journeys;15 existing browser regressions; serious/critical axe and both-width screenshots; repo-wide Ruff/format447; root1,278 run/two skips/OK. Actual new regressions cover equal-version pending recovery, definite422 retry, late409 receipt focus and response transit past expiry. Login pacing preserves the real account limit. The exact original operator container/image/volume are restored healthy and private exports removed.
- Simplifications retain existing transport/auth, theme primitives and backend contracts. No production Python service, schema, migration or dependency changed. Source/validation evidence supports done status; Git Flow remote/PR closure is recorded below.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/16-9-human-approval-inbox-and-decision-ux.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-29-story-16-9.md`
- `_bmad-output/project-context.md`
- `docker-compose.approval-ui.yml`
- `docs/infra-automation/approval-review.md`
- `docs/verification/infra-automation/16-9-backend-for-ui/results.md`
- `docs/verification/infra-automation/16-9/code-review.md`
- `docs/verification/infra-automation/16-9/results.md`
- `docs/verification/infra-automation/16-9/screenshots/acknowledgement-receipt-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/acknowledgement-receipt-760.png`
- `docs/verification/infra-automation/16-9/screenshots/acknowledgement-review-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/acknowledgement-review-760.png`
- `docs/verification/infra-automation/16-9/screenshots/audit-attribution-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/audit-attribution-760.png`
- `docs/verification/infra-automation/16-9/screenshots/changed-binding-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/changed-binding-760.png`
- `docs/verification/infra-automation/16-9/screenshots/confirmation-acknowledgement-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/confirmation-acknowledgement-760.png`
- `docs/verification/infra-automation/16-9/screenshots/confirmation-high-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/confirmation-high-760.png`
- `docs/verification/infra-automation/16-9/screenshots/decision-controls-high-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/decision-controls-high-760.png`
- `docs/verification/infra-automation/16-9/screenshots/evidence-high-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/evidence-high-760.png`
- `docs/verification/infra-automation/16-9/screenshots/expired-confirmation-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/expired-confirmation-760.png`
- `docs/verification/infra-automation/16-9/screenshots/freshness-window-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/freshness-window-760.png`
- `docs/verification/infra-automation/16-9/screenshots/hard-eligibility-block-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/hard-eligibility-block-760.png`
- `docs/verification/infra-automation/16-9/screenshots/inbox-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/inbox-760.png`
- `docs/verification/infra-automation/16-9/screenshots/linked-permanent-report-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/linked-permanent-report-760.png`
- `docs/verification/infra-automation/16-9/screenshots/receipt-approved-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/receipt-approved-760.png`
- `docs/verification/infra-automation/16-9/screenshots/receipt-recovered-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/receipt-recovered-760.png`
- `docs/verification/infra-automation/16-9/screenshots/receipt-rejected-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/receipt-rejected-760.png`
- `docs/verification/infra-automation/16-9/screenshots/requester-self-denied-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/requester-self-denied-760.png`
- `docs/verification/infra-automation/16-9/screenshots/response-unconfirmed-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/response-unconfirmed-760.png`
- `docs/verification/infra-automation/16-9/screenshots/review-high-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/review-high-760.png`
- `docs/verification/infra-automation/16-9/screenshots/revoked-reviewer-1440.png`
- `docs/verification/infra-automation/16-9/screenshots/revoked-reviewer-760.png`
- `frontend/e2e/infra-automation-approvals.spec.ts`
- `frontend/src/api/identity.test.ts`
- `frontend/src/api/identity.ts`
- `frontend/src/api/infraAutomation.test.ts`
- `frontend/src/api/infraAutomation.ts`
- `frontend/src/main.tsx`
- `frontend/src/screens/InfraAutomationApprovals.test.tsx`
- `frontend/src/screens/InfraAutomationApprovals.tsx`
- `frontend/src/screens/InfraAutomationRun.tsx`
- `frontend/src/screens/InfraAutomationShared.tsx`
- `frontend/src/screens/dashboard.css`
- `frontend/src/screens/infra-automation.css`
- `scripts/approval_ui_fixture.py`
- `tests/test_infra/test_approval_ui_fixture_guard.py`

### Change Log

- 2026-10-30: Completed layered code review, fixed eight findings with regressions, verified all current checks, restored the operator runtime and marked story/sprint done; Git Flow push/PR closure follows.
- 2026-10-29: Delivered and merged the approved backend prerequisite separately as PR204, then implemented the scoped approval inbox/review/confirmation/receipt/audit UI, strict adapters, protected return/report navigation, disposable browser proof and documentation. Completed full Python gates, corrected composed browser regression, both approval profiles, visual/a11y proof and exact operator restoration; status review.


## Senior Developer Review (AI)

- Date:2026-10-30. Outcome: **Approve after fixes**. Three fresh BMad review layers
  completed; no layer failed. All six ACs are covered by source, focused regressions
  and actual composed keyboard/axe/profile evidence. No HIGH/MEDIUM item remains.
- Eight patch findings are checked in Tasks/Subtasks; four candidates were
  dismissed with backend/profile evidence. Independent rechecks of the final
  acceptance and edge paths are clear. Details and exact commands are in
  `docs/verification/infra-automation/16-9/code-review.md`.
- Git Flow branch: `feature/16-9-human-approval-inbox-decision-ux`, based on accepted
  develop prerequisite `7ecec1f`; review corrections are committed and the branch
  is pushed with a PR targeting develop as the final closure action. Maintainer
  PR approval/merge remains distinct from this automated story review.
- BMad help: assess/refine Story16.10 after16.9 integration; production target,
  custody/registry and receiver qualification remains with its owning stories.
