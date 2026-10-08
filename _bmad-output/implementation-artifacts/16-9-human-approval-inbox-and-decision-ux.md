# Story 16.9: Human Approval Inbox and Decision UX

Status: backlog
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

- [ ] **Packet 1 — UI owner: inbox and immutable packet (AC 1,2,4).** Owned output: `frontend/src/screens/InfraAutomationApprovals.tsx (planned), existing automation run screen and API client`.
  - [ ] Implement scoped pending/expired/decided list, exact evidence/action summary and permanent report links with absolute timezone/deadline, explicit advisory_request versus exact_plan and acknowledgement labels.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 2 — UI owner: decision submission (AC 2–4,6).** Owned output: `typed frontend API adapter and confirmation/reason form`.
  - [ ] Use verified sessions/CSRF and current server eligibility; accessible typed confirmation, reason validation and durable receipt recovery before retry; focus summary or receipt on outcome.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 3 — Service/test owner: audit and authorization verification (AC 2–5).** Owned output: `existing 16.8 decision API, models/repositories audit boundary and tests/test_api`.
  - [ ] Prove malicious actor/role headers, service/runner credentials, self-approval, tuple mutation and concurrent submissions deny; add screened scoped JSON audit export if not delivered earlier in its own backend PR.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 4 — Test/documentation owner: browser proof (AC 1–6).** Owned output: `frontend/e2e, docs/infra-automation and record`.
  - [ ] Capture keyboard approve/reject/acknowledgement and stale/lost-response/denied journeys, audit export and 1440/760 screenshots using actual API-backed data.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.

Each packet is a bounded review unit under this stable story ID; split large packets after 16.0 estimation instead of silently broadening scope. One story branch follows Git Flow; coordinate shared-file edits and do not revert other work.

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
