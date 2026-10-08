# Story 16.16: Declared Multi Unit Preflight Planning

Status: backlog
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

- [ ] Packet 16.1: Exact map and deterministic planner — owner: Domain implementer.
  - Owned write paths: `infra_automation/ unit-map schema/planner; schemas/infra-automation/; tests/test_infra_automation/`.
  - Output: bounded closed map, stable sort/waves, exact-cover checks and versioned canonical digest.
  - Acceptance proof: AC1–3: permutation determinism, cycles, unknown IDs, limits and missing/extra scope tests.
- [ ] Packet 16.2: Snapshot and lock integration — owner: Service implementer.
  - Owned write paths: `services/infra_automation_service.py; existing run/lock repositories; tests/test_infra_automation/`.
  - Output: immutable map/evidence binding, canonical alias collision and stale-decision invalidation.
  - Acceptance proof: AC3–5: alias, unknown-work, map/source mutation and downstream replan denial.
- [ ] Packet 16.3: Accessible confirmation and evidence — owner: Frontend implementer.
  - Owned write paths: `frontend/src/ inventory and run wave table; frontend/e2e/`.
  - Output: typed manual editor/confirmation with affected/prerequisite distinction and collection-order copy.
  - Acceptance proof: AC1,2,5,6: keyboard cycle/unknown errors, confirmation and lock/wave table Compose flow.
- [ ] Packet 16.4: Documentation and contract proof — owner: Verifier/documenter.
  - Owned write paths: `docs/infra-automation/units.md; tests/test_api/ and tests/test_infra_automation/`.
  - Output: exact scope examples and measured bounded inputs without 200-unit scale promise.
  - Acceptance proof: AC1–6: API/schema/digest parity and documented future-plan invalidation.

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
Planning refinement only; implementation agent records its model at execution.

### Debug Log References
Not executed.

### Completion Notes List
- Story specification prepared; no feature implementation, qualification, public RFC acceptance, release publication or runtime tests performed.
- Implementation and validation commands above are future obligations, not test results.

### File List
- `_bmad-output/implementation-artifacts/16-16-declared-multi-unit-preflight-planning.md` (story specification only).
