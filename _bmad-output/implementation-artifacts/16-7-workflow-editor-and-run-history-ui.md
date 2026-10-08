# Story 16.7: Workflow Editor and Run History UI

Status: backlog
Preparation: refined
Release: v1.5.0

## Story

As a workflow author, I want to create validated workflows and inspect immutable runs in the React app, so that I can follow real preflight progress and open the permanent briefing.

## Entry gates and slice boundary

- Release priority: P0 feature work for v1.5.0. **Blocked for implementation** until Story 16.0 has recorded public RFC/CODEOWNERS acceptance, executable identity/fencing/isolation/custody/receiver qualification and final interface decisions; planning adoption alone is not authorization evidence.
- Hard earlier dependencies: **16.4, 16.6**, accepted and verified before advancing this story. These dependency results are currently unresolved; refined preparation does not mean ready-for-dev. No prior implementation learning is available for the new Epic 16 story set.
- Promote only after contract freeze, earlier dependency evidence, bounded task ownership/re-estimation and independent story review. Preserve IDs and backlog status; no feature/release implementation is claimed here.

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

- [ ] **Packet 1 — UI owner: typed resource adapter (AC 1–4).** Owned output: `frontend/src/api/infraAutomation.ts (planned), using frontend/src/api/client.ts and generated schema.d.ts`.
  - [ ] Freeze list pagination, capabilities, draft validation/publish, run timeline and report-provenance responses from earlier APIs; add client error/conflict tests.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 2 — UI owner: workflow/editor surfaces (AC 1,3,4).** Owned output: `frontend/src/screens/InfraAutomation*.tsx (planned), frontend/src/main.tsx and existing shell/navigation`.
  - [ ] Implement project-scoped list and accessible YAML textarea, supported templates, server validation summary and immutable revision controls; API fixtures prove missing permissions and revision conflicts.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 3 — UI owner: run/report surfaces (AC 2–4).** Owned output: `new automation run screen, frontend/src/screens/Report.tsx and frontend/src/api/report.ts only for additive provenance rendering`.
  - [ ] Render real ordered steps/log cursor/digests and permanent briefing link, with uncertainty and stale/empty/error states; preserve legacy report fixtures and consumers.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 4 — Test/documentation owner: production-browser proof (AC 1–5).** Owned output: `frontend/e2e, docs/infra-automation/ and story record`.
  - [ ] Seed authorized real API data; capture full journey and denied/disabled/error states, keyboard/axe and 1440/760 screenshots; record unchanged Dashboard budget.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.

- [ ] **Packet 5 — UI identity-entry owner: named account access (AC6).** Owned output: `frontend/src/screens/` supported local-account entry/logout/expired-session views, typed authentication adapter using existing `frontend/src/api/client.ts`, root routing and `frontend/e2e`.
  - [ ] Use the 16.0-frozen local account/session API and 16.1/16.2 backend; do not implement authentication logic in the browser or trust role headers. Restrict return destinations to permitted local routes; clear stale project data and eligibility on login/logout/revocation.
  - [ ] Provide labeled username/password fields, protected cookie/CSRF handling, readable failed-login/expired-session state and operator-held recovery instructions; never persist passwords/bootstrap/session secrets in browser storage or logs. No new SMTP/SSO dependency or account-governance scope is added.
  - [ ] Prove actual browser sign-in → scoped workflow → logout → denied entry, expiry/revocation, bad Origin/CSRF and unsafe return-target cases against the composed API. Existing backend-only tests or preseeded browser cookies do not replace this UI proof. Use a separately labeled backend-for-UI PR for any additive support gap.

Each packet is a bounded review unit under this stable story ID; split large packets after 16.0 estimation instead of silently broadening scope. One story branch follows Git Flow; coordinate shared-file edits and do not revert other work.

## Dev Notes

Supporting identity UX obligations: IAU15-FR-002..004 and FR-007/008 remain backend-owned by 16.1/16.2; this story owns browser entry/logout/expired-session and recovery guidance using those earlier APIs. It does not require future approval or runner handlers.


- HTTP resources are conceptual until 16.0 freezes final routes/enums/errors. Root SPA routes follow `/infra-automation`, `/infra-automation/workflows/{id}` and `/infra-automation/runs/{id}`; add actual BrowserRouter entries in frontend/src/main.tsx rather than assuming a separate router module.
- Reuse frontend/src/screens/Phase6Shell.tsx and projectSelection.ts, React Query, API client and existing UI/theme tokens. Existing gallery demoProjects is not production automation data. No secondary global search, chart library, visual DAG editor, deploy/apply control or new Dashboard KPIs.
- 16.6 owns report relation/provenance compatibility; verify optional provenance_version 1 tolerance across API/UI/CLI/agent/action constructors before rendering it. Never promise report v2.1. Do not mark the not-yet-delivered runner/decision/receiver views functional.
- Use v3 mockup exact values, local fonts and lucide-react; accessible labels/table captions/field-linked errors and keyboard tab behavior need explicit tests. Backend-for-UI behavior, if needed, ships in its own labeled PR and must not be buried in the UI PR.

### Project Structure Notes

- Planned modules are additions under the established Python/service/API/repository and React boundaries, not present-day implementation claims. Reuse `api/errors.py` ApiRoute/ApiError, `api/schemas.py`, `models/database.py`, `models/tables.py`, repositories and `migrations/versions/`; inspect head before allocation.
- Introduce only entities necessary for this slice; never precreate all automation tables. Keep deterministic findings in the shared analysis core, optional AI downstream and privileged execution outside FastAPI. No new dependencies without a recorded approved decision.
- Interface names/resources are design obligations pending 16.0 freeze, not permission to invent final route/schema contracts. Add docs and tests with behavior; do not defer slice coverage to 16.19.

## Required implementation verification

- [ ] Register new `tests/test_infra_automation` directories in `scripts/ci-local.sh` and affected GitHub discovery/shards; root discovery alone skips non-package test directories.
- [ ] For every Pydantic/schema/dataclass/constructor change, use repository-wide `rg` searches for direct instantiations/fixtures and update all consumers, including CLI/agent/action/report compatibility where affected.
- [ ] Run `./.venv/bin/python -m unittest discover -q`, story-focused tests and exactly `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` for affected API/CLI/infra contracts.
- [ ] Run `./.venv/bin/ruff check .`, **`./.venv/bin/ruff format --check .` repo-wide**, `bash scripts/ci-local.sh` and `git diff --check`; add applicable static/security/type checks. Record commands and actual results rather than assumed passes.
- [ ] Run `npm run ui:typecheck`, `npm run ui:test`, `npm run ui:build`; then `docker compose up -d --build`, wait for `http://localhost:8080/api/v1/health`, seed synthetic authorized API data and run `BASE_URL=http://localhost:8080 npm run test:ui-review` with new journey coverage.
- [ ] Run `BASE_URL=http://localhost:8080 RUN_UI_A11Y=1 bash scripts/ci-local.sh` for keyboard/axe critical/serious coverage; capture required 1440/760-width screenshots from root SPA routes and permanent `/reports/{id}` links, then `docker compose down`.
- [ ] Record browser commands/results/screenshots before review. Vite dev server, legacy prefixed routes and existing report tests alone do not establish this story's browser acceptance. Backend-for-UI behavior requires a separate labeled PR.

## References

- [Canonical feature PRD](../planning-artifacts/prd-infra-automation.md), [exact requirement registry](../planning-artifacts/infra-automation-requirement-dispositions.json) and [Epic 16](../planning-artifacts/epics.md).
- [Architecture §25](../planning-artifacts/architecture.md#25-v150-infrastructure-automation-architecture-amendment), especially slice qualification §25.12; [mandatory project context](../project-context.md).
- [Readiness gates IR-01–IR-06](../planning-artifacts/implementation-readiness-report-2026-10-07-infra-automation-v1.5.0.md) and [release sequencing](../planning-artifacts/infra-automation-v1.5.0-release-plan.md).
- [Feature UX contract](../../docs/design/infra-automation-ux.md), [UX authority](../planning-artifacts/ux-design-specification.md), [v3 visual authority](../../docs/design/deploywhisper-redesign-v3.jsx) and [RFC 0001](../../docs/rfcs/0001-infra-automation-preflight-and-handoff.md).

## Dev Agent Record

### Agent Model Used

Documentation preparation only; implementation agent/version to be recorded when gates open.

### Debug Log References

Not executed: application, runner, receiver, Compose, browser, fault/load or production qualification. This preparation records obligations, not passing results.

### Completion Notes List

- Preparation: refined. Status remains backlog. All implementation tasks unchecked; Story 16.0 and earlier dependency acceptance remain unresolved.
- UI validation: Required at implementation; not executed.
- Independent review, actual command results, residual risks and release qualification evidence must be recorded during implementation.

### File List

This story specification only; planned ownership paths above are not implemented files.
