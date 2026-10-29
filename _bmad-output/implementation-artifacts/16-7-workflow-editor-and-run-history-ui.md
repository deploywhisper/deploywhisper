# Story 16.7: Workflow Editor and Run History UI

Status: done
Preparation: refined
Release: v1.5.0

## Story

As a workflow author, I want to create validated workflows and inspect immutable runs in the React app, so that I can follow real preflight progress and open the permanent briefing.

## Entry gates and slice boundary

- Earlier Stories 16.0–16.6 are accepted/done. RFC/qualification and workflow v2 contracts are delivered; earlier unresolved-dependency text is superseded by current evidence.
- The separately reviewed backend-for-UI prerequisite [PR200](https://github.com/deploywhisper/deploywhisper/pull/200) is merged into `develop` at `bf464ef`. Its [capabilities contract](../../docs/infra-automation/ui-capabilities.md) resolves the prior concrete blocker. The maintainer explicitly authorized full UI implementation after merge.
- Independent native readiness review confirmed existing workspace discovery, lifecycle/preflight/session APIs and relational report provenance support this slice. Preserve all six ACs and stable Story16.7 ID; no future approval/runner/receiver or Settings-administration functionality is included.
- One UI branch/PR: `feature/16-7-workflow-editor-run-history-ui`, based on merged `develop`. Root owns integration, workflow editor, routes/navigation, story and final validation. Bounded native owners may implement typed adapters, identity entry and run views under explicit file ownership; shared-file edits remain root-owned. Relative estimates: adapters medium; editor large; run views medium; browser proof large; identity medium. Each packet requires tests before acceptance.

## Acceptance Criteria

1. **AC1:** Given an authorized project author and supported template, when a draft is edited and validated, then field/step errors are accessible, saving is distinct from publishing, and only a permitted immutable published revision can start an uploaded-artifact run.
2. **AC2:** Given a completed uploaded preflight, when run detail or its report link opens, then actual timeline, screened bounded logs, artifact digests, uncertainty and permanent `/reports/{id}` provenance render without changing canonical report semantics.
3. **AC3:** Given feature-off, denied, empty, loading, failed or degraded responses, when workflow/run views load, then actual state and permitted next action are accessible; disabled mode retains authorized historical reads without new starts.
4. **AC4:** Given a project switch, stale revision or connection loss, when queries refresh or a mutation is attempted, then previous project forms/eligibility clear, conflicts reload server state and consequential controls remain disabled until fresh authorization.
5. **AC5:** Given the composed production app, when a keyboard user creates, validates, publishes, starts and reviews a real seeded workflow, then focus/error/tab semantics, axe gates and screenshots pass; Dashboard information budget and global search remain sanctioned.

6. **AC6:** Given the qualified local-account APIs from 16.1/16.2, when an operator signs in/out, returns from an expired session or follows account-recovery guidance, then the browser uses the verified session, CSRF/Origin contract and a screened return path; failed or revoked credentials cannot reveal protected workflow data. Recovery does not invent an email/SSO provider or expose bootstrap secrets.

### Requirement Traceability

Coverage intent: Delta over the v1.4.0 baseline. These exact mapped requirements are acceptance obligations; mapping is not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| IAU15-FR-027 | Link runs to immutable reports through a compatible versioned optional provenance contract; retain permanent report URLs and existing report consumers. | Serializer/constructor/legacy-consumer contract tests |
| IAU15-FR-052 | Provide sanctioned React navigation, validated templates/YAML draft/publish controls and scoped workflow/run lists using actual APIs and existing design primitives without changing Dashboard information budget. | Compose-built workflow creation and scoped-list keyboard/a11y E2E |
| IAU15-FR-053 | Show immutable run timeline, screened logs, artifact digests, linked briefing, uncertainty and permanent report provenance links with loading/empty/error/disabled/degraded states. | Compose-built run/history/report states and real-data E2E |
| IAU15-NFR-009 | All new React routes must pass the composed-app axe critical/serious violation gate and keyboard-only create/run/review/decision/recovery journeys, using real API-backed seeded data and required screenshots. | Compose production build, Playwright/axe/keyboard results and screenshots |

## Tasks / Subtasks and bounded ownership

- [x] **Packet 1 — UI owner: typed resource adapter (AC 1–4).** Owned output: `frontend/src/api/infraAutomation.ts (planned), using frontend/src/api/client.ts and generated schema.d.ts`.
  - [x] Freeze list pagination, capabilities, draft validation/publish, run timeline and report-provenance responses from earlier APIs; add client error/conflict tests.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 2 — UI owner: workflow/editor surfaces (AC 1,3,4).** Owned output: `frontend/src/screens/InfraAutomation*.tsx (planned), frontend/src/main.tsx and existing shell/navigation`.
  - [x] Implement project-scoped list and accessible YAML textarea, supported templates, server validation summary and immutable revision controls; API fixtures prove missing permissions and revision conflicts.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 3 — UI owner: run/report surfaces (AC 2–4).** Owned output: `new automation run screen, frontend/src/screens/Report.tsx and frontend/src/api/report.ts only for additive provenance rendering`.
  - [x] Render real ordered steps/log cursor/digests and permanent briefing link, with uncertainty and stale/empty/error states; preserve legacy report fixtures and consumers.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 4 — Test/documentation owner: production-browser proof (AC 1–5).** Owned output: `frontend/e2e, docs/infra-automation/ and story record`.
  - [x] Seed authorized real API data; capture full journey and denied/disabled/error states, keyboard/axe and 1440/760 screenshots; record unchanged Dashboard budget.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.

- [x] **Packet 5 — UI identity-entry owner: named account access (AC6).** Owned output: `frontend/src/screens/` supported local-account entry/logout/expired-session views, typed authentication adapter using existing `frontend/src/api/client.ts`, root routing and `frontend/e2e`.
  - [x] Use the 16.0-frozen local account/session API and 16.1/16.2 backend; do not implement authentication logic in the browser or trust role headers. Restrict return destinations to permitted local routes; clear stale project data and eligibility on login/logout/revocation.
  - [x] Provide labeled username/password fields, protected cookie/CSRF handling, readable failed-login/expired-session state and operator-held recovery instructions; never persist passwords/bootstrap/session secrets in browser storage or logs. No new SMTP/SSO dependency or account-governance scope is added.
  - [x] Prove actual browser sign-in → scoped workflow → logout → denied entry, expiry/revocation, bad Origin/CSRF and unsafe return-target cases against the composed API. Existing backend-only tests or preseeded browser cookies do not replace this UI proof. Use a separately labeled backend-for-UI PR for any additive support gap.

Each packet is a bounded review unit under this stable story ID; split large packets after 16.0 estimation instead of silently broadening scope. One story branch follows Git Flow; coordinate shared-file edits and do not revert other work.

### Resolved review follow-ups (AI)

- [x] [Review][P1] Remount protected report consumers on account expiry/revocation; the mounted-report browser case proves the old briefing and relation disappear.
- [x] [Review][P2] Require a successful current-session read before mutation, even if a later capability read succeeds.
- [x] [Review][P2] Preserve explicit project-wide scope through navigation and reload without silently selecting a workspace.
- [x] [Review][P2] Refresh screened logs and final attempts/evidence while retaining keyboard focus on the same attempt.
- [x] [Review][P2] Treat an uncertain preflight transport result as unknown, distinct from a local file decode error; do not replay it automatically.
- [x] [Review][P2] Keep run details hidden until denied-access recovery verifies the current account and all required reads.
- [x] [Review][P2] Request the server's evidence state once when a deadline has elapsed; never invent a local freshness verdict.
- [x] [Review][P2] Preserve report-ID feedback invalidation when the report query also keys by identity epoch.
- [x] [Review][High] Resolve the browser fixture file race reported by CodeQL: open with `O_NOFOLLOW`, verify with `fstat`, and read through the same descriptor.

### Review Findings

BMad code review, 2026-10-28:

- [x] [Review][Patch] Reconcile project and workspace URL changes after browser Back/Forward without rendering the old scope; preserve user scope selections as history entries (`frontend/src/screens/InfraAutomationShared.tsx`).
- [x] [Review][Patch] Permit the exact workflow/runs tab in the screened account return URL (`frontend/src/api/identity.ts`).
- [x] [Review][Patch] Repeat bounded server reads when the evidence deadline passes but the server still reports available (`frontend/src/screens/InfraAutomationRun.tsx`).
- [x] [Review][Patch] Retain unknown mutation outcome after Reload server state or same-session route remount so a lost publish response cannot enable a duplicate request (`frontend/src/screens/InfraAutomation.tsx`).
- [x] [Review][Patch] Do not show an empty workflow or run list alongside an initial load error (`frontend/src/screens/InfraAutomation.tsx`).
- [x] [Review][Patch] Verify the live disposable Docker target before browser fixtures mutate it (`frontend/e2e/infra-automation.spec.ts`).
- [x] [Review][Patch] Prove editor and upload control Tab order and state the native file-picker test boundary precisely (`frontend/e2e/infra-automation.spec.ts`).

The proposed feature-off navigation change was dismissed: the approved UX contract explicitly hides normal Automation navigation while preserving authorized direct-route history (`docs/design/infra-automation-ux.md`).

## Dev Notes

Supporting identity UX obligations: IAU15-FR-002..004 and FR-007/008 remain backend-owned by 16.1/16.2; this story owns browser entry/logout/expired-session and recovery guidance using those earlier APIs. It does not require future approval or runner handlers.


- Current HTTP contracts are implemented in `api/routes/infra_automation.py`, `api/schemas.py` and `docs/infra-automation/{workflows,preflight,ui-capabilities}.md`; consume these actual responses. Root SPA routes follow `/infra-automation`, `/infra-automation/workflows/{id}` and `/infra-automation/runs/{id}`; add actual BrowserRouter entries in frontend/src/main.tsx rather than assuming a separate router module.
- Reuse frontend/src/screens/Phase6Shell.tsx and projectSelection.ts, React Query, API client and existing UI/theme tokens. Existing gallery demoProjects is not production automation data. No secondary global search, chart library, visual DAG editor, deploy/apply control or new Dashboard KPIs.
- 16.6 delivered relational run/report provenance through `/runs/{id}/reports`, independently versioned uploaded provenance/evidence status. Report v2 has no promised automation block or reverse relation. Render an optional run context on a report link only after the live relation proves the exact report ID; preserve canonical `/reports/{id}` paths and legacy consumers. Never promise report v2.1. Do not mark the not-yet-delivered runner/decision/receiver views functional.
- Use v3 mockup exact values, local fonts and lucide-react; accessible labels/table captions/field-linked errors and keyboard tab behavior need explicit tests. Backend-for-UI behavior, if needed, ships in its own labeled PR and must not be buried in the UI PR.

### Concrete UI implementation guardrails — refreshed after PR200

- `GET /projects/{project_key}/workspaces` already filters authorized workspaces. Require an actual selected workspace for uploaded starts and workspace-limited capability reads; null workspace permits only authorized project-wide authoring.
- Ship the executable two-step workflow-v2 upload/analysis template. YAML candidates stay transient; validate on the server, save with `expected_version`, publish separately with an idempotency key, and start only an immutable selected revision. Do not replay ambiguous mutations automatically. A conflict clears validation/eligibility and reloads current server state.
- Keep account access in the Settings composition (`/settings/account`), with a screened local return path. Login/rotation CSRF stays in memory. GET session restores reads only; a reload requires fresh sign-in for mutations. Clear protected query/mutation caches, files/forms and eligibility on identity changes/revocation. Preserve nonsecret same-scope edits only during ordinary connection loss.
- Run views render actual attempt states, `created_at`/deadlines and cancellation request time where available. Step start/finish and per-log timestamps are absent from current APIs: explicitly show timing unavailable rather than treating deadline/lease as completion time. Use server ordering/attempt numbers and bounded cursors, with gap/truncation indicators. Artifact output/upload digests differ from workflow/input/snapshot digests.
- Hide normal Automation navigation when execution is off; a direct route retains authorized workflow/history reads and an adjacent disabled-start reason. No permissions derive from global account-admin flags or old role headers.
- Visual thesis: a calm operational workspace using the approved light v3 shell, typography, spacing and one action accent. Content plan: scoped workflow/run tabs → focused editor or durable run summary → evidence/log details. Interaction thesis: keyboard tab/field focus, deliberate server validation, quiet polling with no focus theft. No decorative hero, new Dashboard budget, mock data, secondary search or image assets.
- Reuse existing primitives; add roving tab focus, arrow/Home/End behavior and associated panels only where the new tabs require it, preserving other screens. Query keys include identity/project/workspace; consume AbortSignals, remove stale data on identity changes and disable consequential actions until current session/capability reads succeed.
- Pinned React18/TanStack Query5/router versions remain unchanged. Technical references: [QueryClient](https://tanstack.com/query/latest/docs/framework/react/reference/classes/QueryClient) for cancel/remove/clear semantics and [WAI tabs](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/) for keyboard/panel semantics. No dependency upgrade is authorized by this refresh.

### Project Structure Notes

- Planned modules are additions under the established Python/service/API/repository and React boundaries, not present-day implementation claims. Reuse `api/errors.py` ApiRoute/ApiError, `api/schemas.py`, `models/database.py`, `models/tables.py`, repositories and `migrations/versions/`; inspect head before allocation.
- Introduce only entities necessary for this slice; never precreate all automation tables. Keep deterministic findings in the shared analysis core, optional AI downstream and privileged execution outside FastAPI. No new dependencies without a recorded approved decision.
- Interface names/resources are the delivered earlier contracts; do not invent new route/schema contracts. Add docs and tests with behavior; do not defer slice coverage to 16.19.

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

Codex; full UI implementation resumed after maintainer-confirmed PR200 merge. Root integrates bounded native packet owners and final Compose/browser/review evidence.

### Implementation Plan

1. Use generated OpenAPI types and a bounded adapter over the merged workflow, run, report-relation, capability and local-account APIs. Preserve fixed error envelopes and current backend authorization.
2. Add sanctioned root SPA routes with one project/workspace selection, server-backed workflow-v2 upload template, YAML validation, separate draft save/publish and immutable revision start controls.
3. Render actual server-ordered run attempts, logs, available times, artifact digests, durable uncertainty and a report-v2 permalink with optional exact relational provenance.
4. Keep account CSRF in memory, screen return routes, clear identity-scoped caches and forms on definite loss, and retain only same-scope nonsecret draft edits through transient network loss.
5. Verify legacy and authenticated composed-app lanes, screenshots, axe/keyboard, all repository gates and independent review. The production coordinator correction is delivered separately as PR #201.

### Debug Log References

Historical preparation note: application/Compose/browser qualification had not been executed for the UI. Current command results are recorded below as implementation proceeds.

- 2026-10-28: Requested dev-story entry assessment found earlier Stories 16.0–16.6 accepted/done; the original unresolved-dependency preparation text is historical. See [scoped readiness assessment](../planning-artifacts/implementation-readiness-report-2026-10-28-story-16-7.md).
- Historical initial blocker (resolved by merged PR200): no API supplied the verified caller's live scoped automation capabilities and feature state. Static role definitions, admin-only membership reads and draft-only settings reads cannot establish AC3/AC4 eligibility. AGENTS.md and Packet 5 require separate backend-for-UI delivery for additive support; no permission inference or speculative backend contract was implemented.

### Completion Notes List

- Completed the React workflow editor, scoped workflow/run lists, run evidence and report provenance, and named account entry/logout/recovery guidance. Only actual server data is rendered; Dashboard card budget and global search remain unchanged.
- Browser proof: 14 authenticated Compose Playwright cases passed with real named accounts, workflow publication, uploaded preflight, worker completion, report URL, scope/feature-off/denial/conflict/network/expiry states, keyboard focus and axe gates. The default-profile legacy lane passed 15 tests; its 16 skips are 14 identity-only scenarios tested separately and two existing opt-ins.
- Visual QA: approved v3 shell/account 94/100, workflow/run/report 92/100 at 1440px and 760px; 12 final composed screenshots recorded in `docs/verification/infra-automation/16-7/screenshots/`.
- Validation: `npm run ui:typecheck`, `npm run ui:test` (158 passed), `npm run ui:build`, repo-wide `ruff check .` and `ruff format --check .` (428 files), `unittest discover -q` (1,161 tests/two skips), exact API/CLI/infra pytest shard (685 passed/2,267 subtests/one skip), and `BASE_URL=http://localhost:8080 RUN_UI_A11Y=1 bash scripts/ci-local.sh` (2,607 Python tests/all ten directories and 15 baseline browser tests) passed. `git diff --check` passed.
- Three native AI review layers completed and their eight initial findings above were corrected and rechecked. The old incident-leak test's whole-JSON numeric assertion was narrowed to incident references and made deterministic against public timestamp digits; no backend behavior changed in this UI PR.
- GitHub CodeQL flagged a high-severity race in the initial browser-only credential fixture reader. It now opens the 0600 file once with `O_NOFOLLOW`, verifies type/owner/mode/size through the descriptor and reads that same descriptor. The authenticated Compose suite was rerun after this fix: 14/14 passed. This did not change application credential handling.
- A real preflight exposed the existing coordinator's expiring-session bug. Separate [backend-for-UI PR #201](https://github.com/deploywhisper/deploywhisper/pull/201) fixed it, passed 248 engine/API tests plus production Compose browser integration here, and merged into `develop` on 2026-10-28. This UI branch contains no coordinator runtime patch.
- The disposable Compose project/volume and private synthetic credential fixture were removed. Original `deploywhisper-deploywhisper-1` was restarted with its original ID; health returned HTTP 200. No human review, external receiver, production TLS pilot or release qualification is claimed.
- BMad code review of UI PR #202 used blind, edge-case and acceptance layers. Seven patch findings were fixed and one feature-off navigation suggestion dismissed against the approved UX contract. The refreshed frontend suite passed 176 tests, production build and typecheck passed, Ruff lint/format and diff checks passed, the root Python smoke passed 1,161 tests/two expected skips, and the 14-case authenticated composed browser suite passed with scope history, lost publish response, file fixture guard, empty/error state and keyboard control order checks. The disposable stack was removed and the original local app restored healthy.



- Historical preparation snapshot: refined/backlog before dependency acceptance. Current gates are cleared by the refreshed entry section; UI acceptance remains unchecked until implementation proof.
- UI validation: Required at implementation; not executed.
- Independent review, actual command results, residual risks and release qualification evidence must be recorded during implementation.
- 2026-10-28: Independent readiness review cleared the earlier dependency evidence but confirmed the capability/feature-state contract gap. Status remains backlog; tasks remain unchecked pending separate support-contract resolution. This is a readiness finding, not feature completion. BMad Help recommends resolving that prerequisite, refreshing the story context and then resuming dev-story.
- Verification: `git diff --check` passed for the readiness documentation. No application code/config changed; implementation and required UI validation were not run.
- Subsequent maintainer instruction, 2026-10-28: implement and verify the necessary prerequisite in a separate backend-for-UI workstream. See [prerequisite specification](spec-16-7-backend-for-ui-capabilities.md) and [API contract](../../docs/infra-automation/ui-capabilities.md) for the current implementation/review/validation record. The earlier no-code/blocker notes describe the initial assessment. Full UI tasks remain unchecked; backend support does not establish browser acceptance.
- Prerequisite completion: the read-only scoped capability/feature-state API reuses live human/membership/policy checks. Actual Story 16.6 admission/history/report-relation continuity is covered; existing mutation/report contracts remain intact. Three review layers and re-review cleared the change. Final validation passed: focused 68 tests /130 subtests; full local CI 2,607 tests; final root smoke 1,161 tests /two expected skips; exact affected shard 685 tests /2,267 subtests /one opt-in skip; production Python 3.11 new tests 20 passed and actual app startup/health/OpenAPI/protected denial passed. Ruff/repo-wide formatting/scoped Bandit/diff checks passed. See [verification record](../../docs/verification/infra-automation/16-7-backend-for-ui/results.md) for initial recovery-test failure, successful rerun and unchanged existing static-analysis debt. UI validation not applicable to the separate backend slice; full UI story remains backlog.

### File List

Historical preparation record: the paths above were plans before the UI implementation.

2026-10-28 readiness assessment changes only:
- `_bmad-output/implementation-artifacts/16-7-workflow-editor-and-run-history-ui.md`
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-28-story-16-7.md`

The separate backend-for-UI prerequisite's complete file list is maintained in
`spec-16-7-backend-for-ui-capabilities.md`; it does not claim any planned UI path
above has been implemented.

### UI implementation file list

- `README.md`
- `_bmad-output/implementation-artifacts/16-7-workflow-editor-and-run-history-ui.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `docs/design/infra-automation-ux.md`
- `docs/infra-automation/browser-ui.md`
- `docs/verification/infra-automation/16-7/results.md`
- `docs/verification/infra-automation/16-7/screenshots/account-unavailable-1440.png`
- `docs/verification/infra-automation/16-7/screenshots/account-unavailable-760.png`
- `docs/verification/infra-automation/16-7/screenshots/briefing-1440.png`
- `docs/verification/infra-automation/16-7/screenshots/briefing-760.png`
- `docs/verification/infra-automation/16-7/screenshots/execution-disabled-1440.png`
- `docs/verification/infra-automation/16-7/screenshots/execution-disabled-760.png`
- `docs/verification/infra-automation/16-7/screenshots/readonly-1440.png`
- `docs/verification/infra-automation/16-7/screenshots/readonly-760.png`
- `docs/verification/infra-automation/16-7/screenshots/run-1440.png`
- `docs/verification/infra-automation/16-7/screenshots/run-760.png`
- `docs/verification/infra-automation/16-7/screenshots/workflow-1440.png`
- `docs/verification/infra-automation/16-7/screenshots/workflow-760.png`
- `frontend/e2e/infra-automation.spec.ts`
- `frontend/src/api/client.test.ts`
- `frontend/src/api/client.ts`
- `frontend/src/api/identity.test.ts`
- `frontend/src/api/identity.ts`
- `frontend/src/api/infraAutomation.test.ts`
- `frontend/src/api/infraAutomation.ts`
- `frontend/src/api/report.ts`
- `frontend/src/api/schema.d.ts`
- `frontend/src/components/ui/SegmentedTabs.tsx`
- `frontend/src/components/ui/__snapshots__/primitives.test.tsx.snap`
- `frontend/src/components/ui/badges.tsx`
- `frontend/src/main.tsx`
- `frontend/src/screens/AccountAccess.test.tsx`
- `frontend/src/screens/AccountAccess.tsx`
- `frontend/src/screens/AutomationNavigation.tsx`
- `frontend/src/screens/Dashboard.tsx`
- `frontend/src/screens/History.tsx`
- `frontend/src/screens/IdentitySession.test.tsx`
- `frontend/src/screens/IdentitySession.tsx`
- `frontend/src/screens/InfraAutomation.test.tsx`
- `frontend/src/screens/InfraAutomation.tsx`
- `frontend/src/screens/InfraAutomationRun.test.tsx`
- `frontend/src/screens/InfraAutomationRun.tsx`
- `frontend/src/screens/InfraAutomationShared.test.tsx`
- `frontend/src/screens/InfraAutomationShared.tsx`
- `frontend/src/screens/Phase6Shell.tsx`
- `frontend/src/screens/Report.test.tsx`
- `frontend/src/screens/Report.tsx`
- `frontend/src/screens/ReportAutomationContext.test.tsx`
- `frontend/src/screens/ReportAutomationContext.tsx`
- `frontend/src/screens/Settings.tsx`
- `frontend/src/screens/account-access.css`
- `frontend/src/screens/infra-automation.css`
- `frontend/src/screens/phase6.css`
- `frontend/src/screens/report.css`
- `scripts/seed_infra_automation_ui.py`
- `tests/test_services/test_linked_authorization.py`

## Change Log

- 2026-10-28: Refreshed story context after PR200 merge; earlier dependencies cleared, actual API/identity/provenance contracts and bounded ownership recorded. Ready for UI development; no implementation/browser acceptance claimed by preparation.

- 2026-10-28: Independent refreshed-story review found no implementation blocker; development started on the UI branch.

- 2026-10-28: Implemented full Story 16.7 UI, passed composed dual-profile browser/CI gates and native review, and set status done. Runtime coordinator fix merged separately in PR #201; human approval of UI PR #202 and later release qualification remain open.
- 2026-10-28: BMad code review resolved seven actionable findings, dismissed one UX-contract mismatch, reran the focused production browser and frontend/static gates, and retained status done.
