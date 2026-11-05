# Story 16.16: Declared Multi Unit Preflight Planning

Status: done
Preparation: refined
Release: v1.5.0 | Priority: P0, highest-priority feature

## Story

As a platform engineer, I want explicit confirmed unit dependencies and deterministic preflight waves, so that combined evidence is reviewable without confusing collection with provisioning.

## Implementation gates

- Earlier dependencies: 16.3 bounded closed schema, 16.10 canonical target locks and decision binding, 16.14 actual collection/provenance.
- Blocked until Story 16.0 public RFC acceptance and executable identity/fencing/isolation/custody/receiver qualification close the readiness gates; documentation refinement does not satisfy those gates.
- Recheck actual prerequisite records before execution. Downstream release acceptance is not a prerequisite for an earlier owned slice; test-double proofs remain explicitly limited.
- Promote to ready-for-dev only after dependency evidence, final interfaces and packet estimates are independently reviewed. Keep unchecked tasks and backlog until then.

## Acceptance Criteria

1. **Given a human-declared inventory with explicit IDs, source/path, environment/target and prerequisite edges, when validated, then exact affected/prerequisite unit coverage is confirmed and bounded by the 16.0 contract; no inferred identities/edges are introduced.**
2. **Given duplicate/unknown identities, unresolved prerequisites, cycle or excess units/edges, when validation runs, then located errors reject the map before scheduling; no silent skipped scope or deployment-order promise is emitted.**
3. **Given equivalent maps with reordered input, when canonicalized, then deterministic preflight waves and combined evidence digest match; persisted run snapshot contains exact units, edges, source/evidence and map/wave digest.**
4. **Given aliases for one physical target or unknown external work, when units request locks, then canonical identities collide and unknown locks remain held; expiry/cancel cannot release them, and audited operator break never creates authorization.**
5. **Given changed map, evidence/source or infrastructure after upstream external change, when downstream plans are used, then old eligibility/approval cannot authorize the new plan; recollect/reanalyze/reapprove and explicitly call waves collection/review order.**
6. **Given confirmed scoped inventory, when a keyboard operator edits/confirms and reviews /infra-automation/inventory and run waves, then accessible tables show scope/locks/errors with real APIs, axe gates and 1440/760 screenshots.**

### Requirement Traceability

Coverage intent: Delta against released v1.4.0; full canonical mappings below are acceptance obligations, not delivered proof.

| Requirement | Full canonical requirement | Required proof |
| --- | --- | --- |
| IAU15-FR-042 | Canonicalize target lock identities across aliases and retain locks during unknown external work until verified resolution or an audited operator break that does not mint a new authorization. | Alias collision/lock expiry/unknown-work/break tests |
| IAU15-FR-056 | Accept only human-declared unit inventory and dependencies; validate exact unit coverage/cycles/unknown identities, persist deterministic preflight waves and combined evidence digest, and show accessible scope/lock tables without claiming deployment ordering. | Multi-unit exact-cover/cycle/digest tests and accessible table E2E |
| IAU15-NFR-009 | All new React routes must pass the composed-app axe critical/serious violation gate and keyboard-only create/run/review/decision/recovery journeys, using real API-backed seeded data and required screenshots. | Compose production build, Playwright/axe/keyboard results and screenshots |

## Tasks / Subtasks

Execute one bounded packet at a time on the story feature branch. Each packet owns the named paths; coordinate shared paths and do not revert other edits. Re-estimate after 16.0 spikes; split packets into reviewable PRs without renumbering the canonical story.

- [x] Packet 16.1: Exact map and deterministic planner — owner: Domain implementer.
  - Owned write paths: `infra_automation/ unit-map schema/planner; schemas/infra-automation/; tests/test_infra_automation/`.
  - Output: bounded closed map, stable sort/waves, exact-cover checks and versioned canonical digest.
  - Acceptance proof: AC1–3: permutation determinism, cycles, unknown IDs, limits and missing/extra scope tests.
- [x] Packet 16.2: Snapshot and lock integration — owner: Service implementer.
  - Owned write paths: `services/infra_automation_service.py; existing run/lock repositories; tests/test_infra_automation/`.
  - Output: immutable map/evidence binding, canonical alias collision and stale-decision invalidation.
  - Acceptance proof: AC3–5: alias, unknown-work, map/source mutation and downstream replan denial.
- [x] Packet 16.3: Accessible confirmation and evidence — owner: Frontend implementer.
  - Owned write paths: `frontend/src/ inventory and run wave table; frontend/e2e/`.
  - Output: typed manual editor/confirmation with affected/prerequisite distinction and collection-order copy.
  - Acceptance proof: AC1,2,5,6: keyboard cycle/unknown errors, confirmation and lock/wave table Compose flow.
- [x] Packet 16.4: Documentation and contract proof — owner: Verifier/documenter.
  - Owned write paths: `docs/infra-automation/units.md; tests/test_api/ and tests/test_infra_automation/`.
  - Output: exact scope examples and measured bounded inputs without 200-unit scale promise.
  - Acceptance proof: AC1–6: API/schema/digest parity and documented future-plan invalidation.

### Review Findings

- [x] [Review][Patch] Bound direct dictionary keys before canonical serialization and include inventory retention in shared quotas.
- [x] [Review][Patch] Resolve exact latest-attempt evidence and enforce whole-bundle freshness with independent expiry assertions.
- [x] [Review][Patch] Reject undeclared cross-unit analysis ordering and external handoff ancestors.
- [x] [Review][Patch] Refresh same-version unit evidence and reject duplicate/incomplete available-evidence responses.
- [x] [Review][Patch] Recover late/lost saves through observable settlement and exact verified revision adoption; permit explicitly confirmed new preflights.
- [x] [Review][Patch] Validate genuine keyboard navigation and allow the exact Inventory account return route.
- [x] [Review][Patch] Update current migration-head expectations and isolate receiver contention proof from the existing macOS cold-file race.

### Formal review follow-ups — 2026-11-05

- [x] [Review][Patch][High] R1: Reject approval-before-collection dependency deadlocks at admission (`services/infra_automation_units.py`).
- [x] [Review][Patch][Medium] R2: Return the original admitted run on exact idempotent replay after inventory supersession.
- [x] [Review][Patch][Medium] R3: Recover lost start responses with an explicit same-identity retry; never strand the form or create a fresh request implicitly.
- [x] [Review][Patch][Medium] R4: Freeze workflow/revision pagination while admission is pending.
- [x] [Review][Patch][Medium] R5: Align browser source-path validation with backend Unicode character semantics.
- [x] [Review][Patch][Medium] R6: Associate located errors with their actual controls and provide keyboard links from the summary.
- [x] [Review][Patch][Medium] R7: Expose bounded revision history so a lost save can be recovered after a later revision supersedes it.

- [x] [Review][Defer] D1: Existing medium brace-expansion advisory in unchanged root package-lock.json; see deferred-work.md.

## Dev Notes

- Reuse: Reuse 16.3 validator/DAG/canonicalization ports and 16.10 target lock/binding service; frontend/src/components/ui primitives and API client. Do not duplicate dependency planning in frontend or reuse topology inference as declared authority.
- Owned entities: Only unit-map revision/snapshot relations and required existing decision/run linkage; target locks stay in the canonical shared registry.
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
Codex with bounded native domain, service, UI, browser and independent review lanes.

### Debug Log References
- [Formal review and repairs](../../docs/verification/infra-automation/16-16/formal-code-review.md), [fresh validation](../../docs/verification/infra-automation/16-16/review-validation-summary.json), and [review browser proof](../../docs/verification/infra-automation/16-16/review-browser-proof.md).
- [Full implementation and validation record](../../docs/verification/infra-automation/16-16/results.md).
- [Layered review and resolved findings](../../docs/verification/infra-automation/16-16/code-review.md).
- [Actual composed keyboard/axe/browser proof](../../docs/verification/infra-automation/16-16/browser-proof.md), [screenshots](../../docs/verification/infra-automation/16-16/screenshots.json) and [visual verdict](../../docs/verification/infra-automation/16-16/visual-verdict.json).
- [Structured results and log hashes](../../docs/verification/infra-automation/16-16/validation-summary.json).

### Completion Notes List
- Formal BMad review completed: seven findings repaired and independently verified; existing dependency alert D1 deferred outside the story diff. Fresh root1,866tests/3skips; API754passed/1skip/2,358subtests; automation1,063passed/1skip/3,081subtests; UI438tests+2compat/typecheck/build; actual Compose4passed45.4s,18screenshots,axe0,visual94. Current real collection49checks and integrity9tests73subtests pass. Separate backend/UI branches are prepared for required remote review closure.
- Earlier dependency/interface review passed using actual16.0/16.3/16.10/16.14 proof. Current collection/isolation integrity:9tests73subtests pass; real collection49checks pass with unit integration added to source-hash coverage. Existing qualified offline ARM64/OpenTofu profile remains the support boundary.
- AC1–3: closed25unit/200edge/128KiB declarations, exact affected/prerequisite closure, located rejection, canonical ordering and immutable revision/run snapshots. Permutations and complete two-unit shared analysis are exercised. Local maximum-length ASCII corpus59,416input/62,951result bytes;1000validations p50/p95/p99=6.073/6.312/6.564ms (diagnostic only).
- AC3–5: existing canonical target locks, unknown-work retention and exact intake/analysis/source linkage; persisted server-derived combined evidence and current revision/whole-bundle deadlines checked at decision admission. Uploaded/mixed bundles remain advisory; collected association requires repository root and actual admitted provenance for every unit. External handoff ancestors cannot masquerade as collection order.
- AC6: actual composed Inventory edit/unknown/cycle/confirmation/start/review journey produced two reports; mounted evidence supersession observed without run-version change. Keyboard traversal, zero axe critical/serious violations, ten1440/760screenshots and94/100visual verdict pass. Original application restored healthy; disposable resources/private credentials removed.
- Validation: root1862tests/3skips; exact API/CLI/infra753passed/1skip/2358subtests; automation1060passed/1skip/3081subtests; all ten local-CI directory targets verified after stale migration-head assertions and an existing macOS test-fixture race were repaired. Full logs preserve initial failures rather than hiding them.
- Frontend432tests plus2compatibilitychecks, typecheck and production build pass. Ruff lint and repo-wide formatting565files pass. Scoped Bandit/full-CI high gate pass. CI mypy retains318existing-code diagnostics, zero on changed lines.
- Independent review repairs cover pre-serialization bounds, quotas, retry lineage, whole-bundle freshness, exact dependency order, live evidence refresh, exact response coverage, new-preflight recovery and verified lost-save reconciliation. Composed proof additionally repaired the Inventory account return-route allowlist. No unresolved introduced review findings remain.
- Development handoff to formal code review is complete. Planning scope, advisory reports and shared analysis remain unchanged; release/pilot qualification remains owned by later stories.

### File List
- `README.md`
- `_bmad-output/implementation-artifacts/16-16-declared-multi-unit-preflight-planning.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/project-context.md`
- `api/routes/infra_automation_units.py`
- `app.py`
- `docs/infra-automation/browser-ui.md`
- `docs/infra-automation/units.md`
- `docs/verification/infra-automation/16-14/results.json`
- `docs/verification/infra-automation/16-16/browser-initial-navigation-failure.txt`
- `docs/verification/infra-automation/16-16/browser-native-select-failure.txt`
- `docs/verification/infra-automation/16-16/browser-proof.md`
- `docs/verification/infra-automation/16-16/browser-test-label-failure.txt`
- `docs/verification/infra-automation/16-16/browser-test-reload-failure.txt`
- `docs/verification/infra-automation/16-16/browser-verified.txt`
- `docs/verification/infra-automation/16-16/code-review.md`
- `docs/verification/infra-automation/16-16/formal-code-review.md`
- `docs/verification/infra-automation/16-16/results.md`
- `docs/verification/infra-automation/16-16/review-browser-before-retry-hardening.txt`
- `docs/verification/infra-automation/16-16/review-browser-interrupted.txt`
- `docs/verification/infra-automation/16-16/review-browser-proof.md`
- `docs/verification/infra-automation/16-16/review-browser-source.json`
- `docs/verification/infra-automation/16-16/review-browser-verified.txt`
- `docs/verification/infra-automation/16-16/review-screenshots.json`
- `docs/verification/infra-automation/16-16/review-screenshots/inventory-confirmation-1440.png`
- `docs/verification/infra-automation/16-16/review-screenshots/inventory-confirmation-760.png`
- `docs/verification/infra-automation/16-16/review-screenshots/inventory-editor-1440.png`
- `docs/verification/infra-automation/16-16/review-screenshots/inventory-editor-760.png`
- `docs/verification/infra-automation/16-16/review-screenshots/inventory-unknown-1440.png`
- `docs/verification/infra-automation/16-16/review-screenshots/inventory-unknown-760.png`
- `docs/verification/infra-automation/16-16/review-screenshots/review-historical-save-adoption-1440.png`
- `docs/verification/infra-automation/16-16/review-screenshots/review-historical-save-adoption-760.png`
- `docs/verification/infra-automation/16-16/review-screenshots/review-pending-pagination-1440.png`
- `docs/verification/infra-automation/16-16/review-screenshots/review-pending-pagination-760.png`
- `docs/verification/infra-automation/16-16/review-screenshots/review-replayed-superseded-run-1440.png`
- `docs/verification/infra-automation/16-16/review-screenshots/review-replayed-superseded-run-760.png`
- `docs/verification/infra-automation/16-16/review-screenshots/review-retry-rate-rejected-1440.png`
- `docs/verification/infra-automation/16-16/review-screenshots/review-retry-rate-rejected-760.png`
- `docs/verification/infra-automation/16-16/review-screenshots/run-review-required-1440.png`
- `docs/verification/infra-automation/16-16/review-screenshots/run-review-required-760.png`
- `docs/verification/infra-automation/16-16/review-screenshots/run-unit-evidence-1440.png`
- `docs/verification/infra-automation/16-16/review-screenshots/run-unit-evidence-760.png`
- `docs/verification/infra-automation/16-16/review-validation-summary.json`
- `docs/verification/infra-automation/16-16/review-visual-verdict.json`
- `docs/verification/infra-automation/16-16/screenshots.json`
- `docs/verification/infra-automation/16-16/screenshots/inventory-confirmation-1440.png`
- `docs/verification/infra-automation/16-16/screenshots/inventory-confirmation-760.png`
- `docs/verification/infra-automation/16-16/screenshots/inventory-editor-1440.png`
- `docs/verification/infra-automation/16-16/screenshots/inventory-editor-760.png`
- `docs/verification/infra-automation/16-16/screenshots/inventory-unknown-1440.png`
- `docs/verification/infra-automation/16-16/screenshots/inventory-unknown-760.png`
- `docs/verification/infra-automation/16-16/screenshots/run-review-required-1440.png`
- `docs/verification/infra-automation/16-16/screenshots/run-review-required-760.png`
- `docs/verification/infra-automation/16-16/screenshots/run-unit-evidence-1440.png`
- `docs/verification/infra-automation/16-16/screenshots/run-unit-evidence-760.png`
- `docs/verification/infra-automation/16-16/validation-summary.json`
- `docs/verification/infra-automation/16-16/visual-verdict.json`
- `frontend/e2e/infra-automation-units.spec.ts`
- `frontend/src/api/identity.test.ts`
- `frontend/src/api/identity.ts`
- `frontend/src/api/infraAutomationUnits.test.ts`
- `frontend/src/api/infraAutomationUnits.ts`
- `frontend/src/api/schema.d.ts`
- `frontend/src/main.tsx`
- `frontend/src/screens/InfraAutomationInventory.test.tsx`
- `frontend/src/screens/InfraAutomationInventory.tsx`
- `frontend/src/screens/InfraAutomationRun.test.tsx`
- `frontend/src/screens/InfraAutomationRun.tsx`
- `frontend/src/screens/InfraAutomationShared.tsx`
- `frontend/src/screens/infra-automation.css`
- `infra_automation/claims.py`
- `infra_automation/unit_contracts.py`
- `infra_automation/unit_map.py`
- `migrations/versions/038_add_declared_unit_maps.py`
- `models/database.py`
- `models/repositories/infra_automation_units.py`
- `models/tables.py`
- `schemas/infra-automation/unit-map-v1.json`
- `scripts/compose-story16-16.yaml`
- `scripts/qualify_collection.py`
- `scripts/unit_ui_fixture.py`
- `services/infra_automation_decisions.py`
- `services/infra_automation_units.py`
- `tests/test_api/test_infra_automation_units.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_identity_migration.py`
- `tests/test_infra/test_infra_automation_engine_migration.py`
- `tests/test_infra/test_infra_automation_handoff_migration.py`
- `tests/test_infra/test_infra_automation_workflow_migration.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_infra/test_project_membership_migration.py`
- `tests/test_infra/test_receiver_reconciliation_migration.py`
- `tests/test_infra/test_runner_enrollment_migration.py`
- `tests/test_infra_automation/test_collection_qualification.py`
- `tests/test_infra_automation/test_preflight_repository.py`
- `tests/test_infra_automation/test_receiver_runtime.py`
- `tests/test_infra_automation/test_unit_map.py`
- `tests/test_infra_automation/test_units_service.py`

## Change Log
- 2026-11-05: Implemented all four bounded packets, resolved independent and composed-browser findings, completed required verification, and advanced to review.
- 2026-11-05: Formal review repaired R1–R7, recorded D1 separately, reran affected full suites and composed proof, and advanced to done.
