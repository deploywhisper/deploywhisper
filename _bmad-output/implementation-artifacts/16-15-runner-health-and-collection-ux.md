# Story 16.15: Runner Health and Collection UX

Status: in-progress
Preparation: refined
Release: v1.5.0 | Priority: P0, highest-priority feature

## Story

As an operator, I want runner health, collection state and bounded redacted logs, so that unavailable, expired and cancelled collections are recoverable without guessing.

## Implementation gates

- Earlier dependencies: 16.7 accepted workflow/run UI and 16.14 real isolated collection-to-receiver path.
- Blocked until Story 16.0 public RFC acceptance and executable identity/fencing/isolation/custody/receiver qualification close the readiness gates; documentation refinement does not satisfy those gates.
- Recheck actual prerequisite records before execution. Downstream release acceptance is not a prerequisite for an earlier owned slice; test-double proofs remain explicitly limited.
- Promote to ready-for-dev only after dependency evidence, final interfaces and packet estimates are independently reviewed. Keep unchecked tasks and backlog until then.

## Acceptance Criteria

1. **Given scoped runner health responses, when /infra-automation/runners loads, then rows show last heartbeat, supported versions/profile, active attempt and online/stale/offline state; connectivity is distinct from qualification/trust.**
2. **Given no eligible runner, mismatched tags/profile/version or finite wait expiry, when a collection is requested, then UI reports a specific correction and no silent fallback; enrollment/revocation remains administrator-scoped.**
3. **Given a one-time enrollment response, when shown/closed/expired or project/authorization changes, then the secret is transient and cleared; no URL, local storage, audit/log payload or automatic clipboard copy carries it.**
4. **Given real collection, lease loss, capped/truncated logs or network loss, when the run timeline updates, then source pinning/screening/upload/analysis and sequence gaps are accurate, focus stays stable and only meaningful stage changes are announced.**
5. **Given cancellation before or after external acceptance/unknown state, when requested, then the UI distinguishes owned-process termination, cancellation request and external stop confirmation; unknown work retains locks and offers reconciliation without blind resend.**
6. **Given an authenticated real isolated runner and seeded APIs, when composed-browser run-to-report, enrollment and recovery journeys run, then keyboard and axe critical/serious gates pass at 1440/760 widths with required screenshots and denied/disabled/error states.**

### Requirement Traceability

Coverage intent: Delta against released v1.4.0; full canonical mappings below are acceptance obligations, not delivered proof.

| Requirement | Full canonical requirement | Required proof |
| --- | --- | --- |
| IAU15-FR-021 | Record cancellation durably and terminate the owned runner process tree; explain that cancellation cannot undo accepted external work. | Cancellation/dispatch races and process-tree termination tests |
| IAU15-FR-046 | Route collection to eligible runner tags with no silent fallback; fail clearly when none qualify or enforce an explicit finite wait, and expose last-seen/version/task health. | No-runner/tag-mismatch/wait-timeout and health tests |
| IAU15-FR-055 | Expose runner health, collection/cancel progress and unknown/reconciliation state with advisory copy that never claims Tier 0/1 deploys infrastructure. | Real-runner composed E2E and unknown-state copy checks |
| IAU15-NFR-009 | All new React routes must pass the composed-app axe critical/serious violation gate and keyboard-only create/run/review/decision/recovery journeys, using real API-backed seeded data and required screenshots. | Compose production build, Playwright/axe/keyboard results and screenshots |

## Tasks / Subtasks

Execute one bounded packet at a time on the story feature branch. Each packet owns the named paths; coordinate shared paths and do not revert other edits. Re-estimate after 16.0 spikes; split packets into reviewable PRs without renumbering the canonical story.

- [ ] Packet 15.1: Health contract integration — owner: API implementer.
  - Owned write paths: `api/routes/infra_automation.py and tests/test_api/`.
  - Output: bounded scoped health/tag/status fields, versioned errors; additive backend-for-UI PR.
  - Acceptance proof: AC1,2: permission/profile/tag/finite-wait contract tests.
  - [x] Additive backend implementation, generated contract, independent review and tests complete on local backend branch `db73571`.
  - [ ] Publish the separate labeled backend-for-UI PR during authorized closeout.
- [ ] Packet 15.2: Runner screen and transient enrollment — owner: Frontend implementer.
  - Owned write paths: `frontend/src/ automation runner view and API adapter; frontend/src/ tests`.
  - Output: real health table, explicit qualification, transient one-time reveal/revoke/rotate UI.
  - Acceptance proof: AC1–3: component tests plus secret-state clearing and administrator denial.
  - [x] Runner screen/adapters and transient-state implementation pass unit and composed component fault-model tests.
  - [ ] Complete positive same-origin HTTPS enrollment/rotation/revocation browser proof.
- [ ] Packet 15.3: Collection timeline and cancellation — owner: Frontend implementer.
  - Owned write paths: `frontend/src/ automation run view; frontend/e2e/ automation tests`.
  - Output: cursor logs, gap/truncation states, actual cancellation/unknown copy, stable focus.
  - Acceptance proof: AC4,5: real runner E2E with lease loss, log limits and accepted/unknown dispatch.
  - [x] Durable observations, routing, cancellation, late-response and network/focus implementation plus unit/fault-model checks complete.
  - [ ] Complete authenticated real isolated-runner browser collection/recovery proof under the approved HTTPS lane.
- [ ] Packet 15.4: Compose acceptance and help — owner: UI verifier/documenter.
  - Owned write paths: `frontend/e2e/; docs/infra-automation/runners.md`.
  - Output: screenshots and keyboard/axe evidence tied to real API-backed data.
  - Acceptance proof: AC6: composed 1440/760 runner-to-report and recovery paths.
  - [x] Required HTTP lane, uploaded-flow compatibility, operator help and safe1440/760 captures verified.
  - [ ] Resolve the pending HTTPS verification-contract choice and capture the positive runner/enrollment acceptance states.

## Dev Notes

- Reuse: Reuse frontend/src/api/client.ts, ProjectSwitcher, Card, Button, Skeleton, SegmentedTabs, badges and theme/tokens.css; validate tabs/focus semantics rather than assuming primitive reuse proves accessibility. Use existing permanent report route and avoid Dashboard additions.
- Owned entities: Reuse runner/task/run/log DTOs from 16.12/14. Add only additive health fields if absent; never persist enrollment secrets in browser storage.
- Respect Python 3.10-compatible code/3.11 runtime, Pydantic 2, SQLAlchemy 2 and current lockfiles. No dependency installation is authorized by this story. Inspect migration head before allocating changes.
- No apply/destroy/remediation, arbitrary shell/plugins, automatic approval, new AI Composer, Ansible/Kubernetes/Helm collectors, Git sync, PostgreSQL/HA or broad infrastructure engine. Existing reports remain advisory with `should_block=False`.
- OpenTofu/Terraform licenses remain independent; operator supplies pinned tools. Do not bundle proprietary binaries or claim MIT relicensing. Never commit/transport real state, credentials or saved binary plans; test files are synthetic and protected local real-tool custody is disposable.
- Prior-story intelligence: preceding Epic 16 capabilities are planned dependencies, not claimed implemented. Read their actual Dev Agent Records and contracts before coding. Recent release commits emphasize independently verified artifact identity, signing and separate security regression checks; reuse that evidence discipline.

### Testing requirements

- Before changing constructors/schema, search the entire repository for direct instantiations/fixtures; update affected contracts and run `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` plus the automation shard registered in CI.
- Register `tests/test_infra_automation/` explicitly in `scripts/ci-local.sh` and affected GitHub shards; root discovery skips some directories. Run `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh`, `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`. Keep deterministic fixtures separate from real tool/receiver acceptance.
- UI task/gate: run `npm run ui:gen-api` for API changes, `npm run ui:typecheck`, `npm run ui:test`, `npm run ui:build`; then `docker compose up -d --build`, wait for `http://localhost:8080/api/v1/health`, seed synthetic authorized API data and run expanded `BASE_URL=http://localhost:8080 npm run test:ui-review` and `BASE_URL=http://localhost:8080 RUN_UI_A11Y=1 bash scripts/ci-local.sh` as applicable. Capture 1440/760 screenshots, axe and keyboard evidence, then `docker compose down`.
- All browser URLs are root SPA routes on composed FastAPI, including `/infra-automation`; Vite/dev server and legacy prefixes are not verification. Backend-for-UI behavior uses a separate labeled PR.

### Completion and integration boundary

- Attach exact command/results, source/build/tool versions and proof artifact locations per AC and mapped requirement. Independent review resolves findings before review/done advancement.
- A slice may close only its owned contract; future integration or production support claims wait for their explicit real-profile gates. Any missing mandatory proof keeps the relevant status blocked/backlog or in progress. Public GitHub writes, real credential setup and release publication require authority for those actions unless already explicitly authorized in the session; do not request the same authority again.

### References

- [Canonical feature PRD](../planning-artifacts/prd-infra-automation.md)
- [Requirement text and proof map](../planning-artifacts/infra-automation-requirement-dispositions.json)
- [Epic 16 story](../planning-artifacts/epics.md)
- [Architecture Section 25](../planning-artifacts/architecture.md)
- [Feature UX contract](../../docs/design/infra-automation-ux.md)
- [Readiness report](../planning-artifacts/implementation-readiness-report-2026-10-07-infra-automation-v1.5.0.md)
- [Project implementation context](../project-context.md)

## Dev Agent Record

### Agent Model Used
Codex with native agents for independent readiness, bounded backend/UI implementation and verification.

### Debug Log References
2026-11-05: Prerequisites and final bounded interfaces independently reviewed. PR211 merged8095877 with passing remote checks. Implementation proceeds on separate backend-for-UI and UI branches; the supplemental HTTPS browser verification amendment is pending user clarification. See docs/verification/infra-automation/16-15/readiness.md.

### Completion Notes List
- All planned UI/backend implementation is present and reviewed; the story remains in-progress because positive HTTPS enrollment and actual isolated-runner browser acceptance are not yet authorized/qualified. No mocked component result is counted as that acceptance.
- Fresh validation: root unittest1794tests/3skips exit0; full localCI3240executions across10directories exit0; API/CLI/infra745passed/1skip/2356subtests; UI377tests and typecheck/build pass; composed19new tests (3realHTTP +16syntheticcomponent fault models) and14realuploaded compatibility tests pass; tested1440/760 keyboard/axe gates pass.
- Integrated BMad review findings were repaired: pre-send validation, late verified outcome settlement, membership-stable mutation continuity, bounded late-read correction, same-scope draft/focus retention on read failures, and precise lease/evidence recovery. Independent repair verification found no residual implementation finding.
- Visual verdict93 forcapturedHTTP/compatibilitystates. PopulatedHTTPSrunner/enrollment views remain unqualified. The original app container and data volume were restored unchanged; private browser credential exports were destroyed.
- Current details, proof tiers and limits: `docs/verification/infra-automation/16-15/results.md`; pending verification amendment: `docs/verification/infra-automation/16-15/readiness.md`.
- Python mypy retains320diagnostics outsidechangedfiles (includingmissingPyYAMLstubs); no changed-file errors. Configuredsecuritygatepasses withthe unchangedsample-IP mediumBandit finding disclosed. No dependencies or migrations added.
- Backend packet implemented and independently reviewed: scoped runner health/capabilities and durable collection/readiness projections, typed transient admin responses, existing HTTPS/production-identity gates preserved. Focused backend review31tests/20subtests and existing runner API/enrollment21tests/22subtests passed; generated frontend schema typechecks and314 existing UI tests pass. Refreshed16.14 collector qualification49checks passed with current hashes. Full story/browser acceptance remains in progress.
- UI work is isolated in `/tmp/deploywhisper-story16-15-ui` on its own feature branch. Positive HTTPS enrollment/real-run browser evidence remains pending the explicit verification-lane decision.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/16-15-runner-health-and-collection-ux.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `api/routes/infra_automation_collection_views.py`
- `api/routes/infra_automation_runner_admin.py`
- `api/routes/infra_automation_runner_views.py`
- `app.py`
- `docs/infra-automation/runners.md`
- `docs/verification/infra-automation/16-14/results.json`
- `docs/verification/infra-automation/16-15/code-review.md`
- `docs/verification/infra-automation/16-15/readiness.md`
- `docs/verification/infra-automation/16-15/results.md`
- `docs/verification/infra-automation/16-15/screenshots/http-initial-1440.png`
- `docs/verification/infra-automation/16-15/screenshots/http-initial-760.png`
- `docs/verification/infra-automation/16-15/screenshots/runners-disabled-1440.png`
- `docs/verification/infra-automation/16-15/screenshots/runners-disabled-760.png`
- `docs/verification/infra-automation/16-15/screenshots/runners-http-unavailable-1440.png`
- `docs/verification/infra-automation/16-15/screenshots/runners-http-unavailable-760.png`
- `docs/verification/infra-automation/16-15/screenshots/runners-reader-unavailable-1440.png`
- `docs/verification/infra-automation/16-15/screenshots/runners-reader-unavailable-760.png`
- `docs/verification/infra-automation/16-15/screenshots/upload-briefing-1440.png`
- `docs/verification/infra-automation/16-15/screenshots/upload-briefing-760.png`
- `docs/verification/infra-automation/16-15/screenshots/upload-execution-disabled-1440.png`
- `docs/verification/infra-automation/16-15/screenshots/upload-execution-disabled-760.png`
- `docs/verification/infra-automation/16-15/screenshots/upload-readonly-1440.png`
- `docs/verification/infra-automation/16-15/screenshots/upload-readonly-760.png`
- `docs/verification/infra-automation/16-15/screenshots/upload-run-1440.png`
- `docs/verification/infra-automation/16-15/screenshots/upload-run-760.png`
- `docs/verification/infra-automation/16-15/screenshots/upload-workflow-1440.png`
- `docs/verification/infra-automation/16-15/screenshots/upload-workflow-760.png`
- `docs/verification/infra-automation/16-15/visual-verdict.json`
- `frontend/e2e/infra-automation-runner-component.spec.ts`
- `frontend/e2e/infra-automation-runners.spec.ts`
- `frontend/e2e/infra-automation.spec.ts`
- `frontend/src/api/identity.test.ts`
- `frontend/src/api/identity.ts`
- `frontend/src/api/infraAutomation.ts`
- `frontend/src/api/infraAutomationCollection.test.ts`
- `frontend/src/api/infraAutomationCollection.ts`
- `frontend/src/api/infraAutomationRunners.test.ts`
- `frontend/src/api/infraAutomationRunners.ts`
- `frontend/src/api/schema.d.ts`
- `frontend/src/main.tsx`
- `frontend/src/screens/InfraAutomation.test.tsx`
- `frontend/src/screens/InfraAutomation.tsx`
- `frontend/src/screens/InfraAutomationRun.test.tsx`
- `frontend/src/screens/InfraAutomationRun.tsx`
- `frontend/src/screens/InfraAutomationRunners.test.tsx`
- `frontend/src/screens/InfraAutomationRunners.tsx`
- `frontend/src/screens/InfraAutomationShared.tsx`
- `frontend/src/screens/runnerMutationState.test.ts`
- `frontend/src/screens/runnerMutationState.ts`
- `scripts/compose-story16-15.yaml`
- `scripts/runner_ui_fixture.py`
- `services/infra_automation_collection_views.py`
- `services/infra_automation_runners.py`
- `tests/test_api/test_collection_views.py`
- `tests/test_api/test_runner_health_ui.py`
- `tests/test_infra/test_runner_ui_fixture_guard.py`
- `tests/test_infra_automation/test_collection_views.py`
- `tests/test_infra_automation/test_runner_health_ui.py`

## Change Log

- 2026-11-05: Implemented separate backend/UI packets, repaired independent review/browser findings, completed Python/UI/HTTP-browser validation and restored the original app. Positive HTTPS/real-run browser gates remain open pending the user decision.
