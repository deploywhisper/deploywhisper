# Story 16.19: Production Qualification and v1.5.0 Release

Status: backlog
Preparation: refined
Release: v1.5.0 | Priority: P0, highest-priority feature

## Story

As a maintainer, I want qualification of the complete supported release profile, so that operators receive honest safety, compatibility and supply-chain evidence.

## Implementation gates

- Earlier dependencies: All accepted P0 16.0–16.18 stories, completed 12.5 SBOM, applicable original 12.7/12.8 acceptance; reuse delivered 12.6 signing and provenance.
- Blocked until Story 16.0 public RFC acceptance and executable identity/fencing/isolation/custody/receiver qualification close the readiness gates; documentation refinement does not satisfy those gates.
- Recheck actual prerequisite records before execution. Downstream release acceptance is not a prerequisite for an earlier owned slice; test-double proofs remain explicitly limited.
- Promote to ready-for-dev only after dependency evidence, final interfaces and packet estimates are independently reviewed. Keep unchecked tasks and backlog until then.

## Acceptance Criteria

1. **Given all feature slices and declared supported tool/runner/receiver versions, when the integrated real-tool/self-hosted receiver pilot runs, then uploaded advisory and exact-local-plan journeys, shared review and honest acknowledgement, signed intake, declared-unit preflight and unknown-delivery recovery satisfy their requirements; dummy receivers never qualify production support.**
2. **Given crash boundaries and principal/role/project/workspace/action matrices, when fault, authorization and sensitive-data corpora execute, then no committed state is lost, unauthorized/duplicate receiver action and cross-scope access are zero, known-secret corpus leaks are zero and Evidence Law/advisory parity is preserved.**
3. **Given reproducible reference hardware of 4 vCPU/8 GB RAM/local SSD, when 1,000 overhead transitions, 1,000 runner claims and 1,000 50-step validations plus 30-minute saturation run execute, then p95 overhead <1s, claim <2s and validation <500ms hold, with 10 active runs/2 analysis workers/20 runners; publish workload/version/resources/errors and failed limits.**
4. **Given new production React routes and real seeded APIs, when full create/run/review/decision/runner/unit/recovery journeys run against composed FastAPI, then frontend type/unit/build and Playwright/axe/keyboard pass, critical/serious violations are zero and 1440/760 screenshots capture happy/denied/expired/unknown states.**
5. **Given v1.4.0 migration/backup/restore, rotation and restricted-network exercises, when a separate operator uses release-matched docs, then stale grants/leases are invalidated, reconciliation succeeds and schema/API/CLI/support/runbooks/metrics pass link/drift and self-service acceptance.**
6. **Given all mandatory proofs and independent code/security review, when stable release is considered, then unresolved introduced critical/high defects or any missing gate block publication; signed app/runner artifacts, SBOM/checksums/provenance and supported matrix are verified before separately authorized public release writes.**

### Requirement Traceability

Coverage intent: Delta against released v1.4.0; full canonical mappings below are acceptance obligations, not delivered proof.

| Requirement | Full canonical requirement | Required proof |
| --- | --- | --- |
| IAU15-NFR-001 | The declared crash/race corpus must lose no committed run/decision state and produce no unauthorized or duplicate receiver action, including stale attempts, unknown delivery and restore epochs. | Published fault-injection results at every persisted boundary |
| IAU15-NFR-002 | The declared principal × role × project/workspace × object/action matrix must produce zero cross-scope reads or unauthorized mutations. | Published complete authorization matrix results |
| IAU15-NFR-003 | The versioned sensitive-data corpus must yield zero known secret patterns in stored artifacts/logs/metadata/errors/audit or transmitted narrative summaries; no universal-redaction claim follows. | Stored/output corpus scans including chunk boundaries |
| IAU15-NFR-004 | Automation-originated fixture reports must produce zero Evidence Law violations and preserve deterministic/inferred labels and advisory report semantics. | Evidence Law and cross-surface contract CI results |
| IAU15-NFR-005 | Ready-step server orchestration overhead must have p95 <1 second, excluding collection/network/analysis duration, under the reproducible reference workload. | Timestamped 1,000-transition overhead benchmark |
| IAU15-NFR-006 | Enqueue-to-claim latency must have p95 <2 seconds with 20 online compatible runners under the reference workload. | Timestamped 1,000-claim runner benchmark |
| IAU15-NFR-007 | The singleton SQLite profile must sustain 10 active runs with at most 2 concurrent analysis jobs and 20 online runners, with bounded queue/storage and no corrupted transitions. | 30-minute capacity/saturation run with resource and error report |
| IAU15-NFR-008 | Workflow validation must have p95 <500 milliseconds for the declared 50-step workflow corpus under the reference workload. | 1,000-validation timing/correctness benchmark |
| IAU15-NFR-009 | All new React routes must pass the composed-app axe critical/serious violation gate and keyboard-only create/run/review/decision/recovery journeys, using real API-backed seeded data and required screenshots. | Compose production build, Playwright/axe/keyboard results and screenshots |
| IAU15-NFR-010 | Upgrade from a v1.4.0 database copy, interrupted upgrade, coordinated DB/artifact backup/restore, token rotation and restricted-network recovery must preserve auditable state while invalidating outstanding authorization/leases until reconciled. | Recorded upgrade/restore/rotation/offline exercises |
| IAU15-NFR-011 | Publish version-matched schema/API/CLI/operator/security/support-limit docs with CI link/drift checks and secret-free run/queue/step/runner/approval/delivery metrics plus troubleshooting runbooks. | Docs CI and operator self-service installation/recovery pilot |
| IAU15-NFR-012 | Stable v1.5.0 requires signed app/runner artifacts, SBOM/checksums/provenance, named tool/receiver support matrix, full application CI, independent review and supported-profile pilot with no unresolved introduced critical/high defect. | Signed release manifest, CI/security/review/pilot evidence |

## Tasks / Subtasks

Execute one bounded packet at a time on the story feature branch. Each packet owns the named paths; coordinate shared paths and do not revert other edits. Re-estimate after 16.0 spikes; split packets into reviewable PRs without renumbering the canonical story.

- [ ] Packet 19.1: Qualification manifest and full CI — owner: Quality implementer/verifier.
  - Owned write paths: `tests/test_infra_automation/ harness; scripts/ci-local.sh; .github/workflows/ affected test shards; docs/infra-automation/qualification.md`.
  - Output: versioned gate manifest mapping all 72 requirements and actual commands/results to immutable build identity.
  - Acceptance proof: AC1–6: existing nine test directories plus new automation directory, constructor fixture search, affected pytest shard and repo-wide Ruff.
- [ ] Packet 19.2: Integrated safety and compatibility — owner: Security/domain verifier.
  - Owned write paths: `tests/test_infra_automation/ fault/auth/redaction/receiver real-profile harness; synthetic fixtures`.
  - Output: persisted-boundary crash matrix, exact-byte custody/receiver pilot and principal×role×scope matrix.
  - Acceptance proof: AC1,2: real supported-tool profile, zero unauthorized/duplicate action and known-pattern leaks.
- [ ] Packet 19.3: Performance and operations — owner: Performance/operator verifier.
  - Owned write paths: `tests/test_infra_automation/ benchmark harness and docs/infra-automation/qualification.md`.
  - Output: named 4vCPU/8GB/localSSD workload, 1,000 samples per latency gate and recorded 30-minute saturation/restore exercises.
  - Acceptance proof: AC3,5: timestamped reproducible p95/capacity/error/resource results and self-service runbooks.
- [ ] Packet 19.4: Composed browser qualification — owner: UI verifier.
  - Owned write paths: `frontend/e2e/ automation journeys; docs/infra-automation/qualification.md screenshot evidence`.
  - Output: real seeded production-route E2E, keyboard/axe and widths 1440/760.
  - Acceptance proof: AC4: all new routes, denial/stale/unknown states, frontend type/unit/build and Compose evidence.
- [ ] Packet 19.5: Supply chain and release decision — owner: Release maintainer.
  - Owned write paths: `existing .github/workflows/ release assets; docs/infra-automation/support.md and release notes`.
  - Output: reuse 12.5 SBOM and 12.6 signing/provenance; independently verified app/runner manifests and signed hashes, defects/support matrix.
  - Acceptance proof: AC6: signature/SBOM/provenance verification, independent review and separately authorized publication; no fabricated release outcome.

## Dev Notes

- Reuse: Reuse scripts/ci-local.sh and scripts/run-test-targets.sh, existing nine-directory CI topology, frontend/playwright.config.ts and e2e fixtures, released 12.6 signing/provenance and separate 12.5 SBOM work. This story aggregates earlier slice proof rather than postponing feature tests to release.
- Owned entities: Qualification manifests and synthetic fixtures only unless a failing gate requires a bounded fix with owned tests; no speculative production entities or new framework.
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
- `_bmad-output/implementation-artifacts/16-19-production-qualification-and-v1-5-0-release.md` (story specification only).
