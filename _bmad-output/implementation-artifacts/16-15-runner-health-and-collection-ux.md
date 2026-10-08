# Story 16.15: Runner Health and Collection UX

Status: backlog
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
- [ ] Packet 15.2: Runner screen and transient enrollment — owner: Frontend implementer.
  - Owned write paths: `frontend/src/ automation runner view and API adapter; frontend/src/ tests`.
  - Output: real health table, explicit qualification, transient one-time reveal/revoke/rotate UI.
  - Acceptance proof: AC1–3: component tests plus secret-state clearing and administrator denial.
- [ ] Packet 15.3: Collection timeline and cancellation — owner: Frontend implementer.
  - Owned write paths: `frontend/src/ automation run view; frontend/e2e/ automation tests`.
  - Output: cursor logs, gap/truncation states, actual cancellation/unknown copy, stable focus.
  - Acceptance proof: AC4,5: real runner E2E with lease loss, log limits and accepted/unknown dispatch.
- [ ] Packet 15.4: Compose acceptance and help — owner: UI verifier/documenter.
  - Owned write paths: `frontend/e2e/; docs/infra-automation/runners.md`.
  - Output: screenshots and keyboard/axe evidence tied to real API-backed data.
  - Acceptance proof: AC6: composed 1440/760 runner-to-report and recovery paths.

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
Planning refinement only; implementation agent records its model at execution.

### Debug Log References
Not executed.

### Completion Notes List
- Story specification prepared; no feature implementation, qualification, public RFC acceptance, release publication or runtime tests performed.
- Implementation and validation commands above are future obligations, not test results.

### File List
- `_bmad-output/implementation-artifacts/16-15-runner-health-and-collection-ux.md` (story specification only).
