# Story 16.18: Operator Recovery, Retention and Network Readiness

Status: backlog
Preparation: refined
Release: v1.5.0 | Priority: P0, highest-priority feature

## Story

As a self-hosted operator, I want tested upgrade, backup, restore, retention and restricted-network procedures, so that old authorizations never revive and uncertain external work remains recoverable.

## Implementation gates

- Earlier dependencies: Incremental packet preparation from accepted 16.5; final integration after 16.16 and 16.17; 16.0 RFC/spikes gate applies to all implementation.
- Blocked until Story 16.0 public RFC acceptance and executable identity/fencing/isolation/custody/receiver qualification close the readiness gates; documentation refinement does not satisfy those gates.
- Recheck actual prerequisite records before execution. Downstream release acceptance is not a prerequisite for an earlier owned slice; test-double proofs remain explicitly limited.
- Promote to ready-for-dev only after dependency evidence, final interfaces and packet estimates are independently reviewed. Keep unchecked tasks and backlog until then.

## Acceptance Criteria

1. **Given privileged configuration of enablement/quotas/TTL/retention/credential lifetimes, when changed, then permissions, safety floors and append-only audit apply; pending evidence is protected or its decision is invalidated before atomic deletion, with manifest/tombstone kept.**
2. **Given quotas, concurrent runs, abandoned staging and disk exhaustion, when capacity saturates, then bounded backlog/storage/analysis workers return actionable backpressure and cleanup does not corrupt state or release unknown locks.**
3. **Given a quiesced coordinated DB/artifact/custody backup and v1.4.0 database copy, when upgraded/interrupted/restored, then auditable history survives, restore epoch changes, sessions/machine/task credentials and leases invalidate, unconsumed grants cannot revive and consumed unknown operations reconcile before outbound work.**
4. **Given evidence/custody expiry, feature/member/runner revocation or unknown delivery, when recovery runs, then reads/reconciliation remain possible but no new action consumes stale authority; audited operator break acknowledges uncertainty and does not mint authorization.**
5. **Given operator-managed pinned tools/caches and restricted egress/DNS, when installation/collection/recovery is exercised, then documented allowed hosts/cache limits and credential rotation work without server-side provider credentials or silently widening the network profile.**
6. **Given an operator following version-matched runbooks, when bootstrap/recovery/upgrade/retention/network/incident exercises and 30-minute 10-run/2-analysis/20-runner saturation execute, then metrics/results/limits are recorded; automation contributions to 12.7/12.8 are explicit and do not close unmet original ACs.**

7. **Given an authenticated administrator and earlier configuration/target APIs, when enablement, target, quota, retention, TTL or credential-lifetime settings are saved in `/settings`, then real typed values and validation/conflict errors render, forbidden reductions deny, disabling invalidates pending authority while preserving reconciliation, and a nonadmin cannot mutate settings. No infrastructure credentials are entered or persisted by this form.**

### Requirement Traceability

Coverage intent: Delta against released v1.4.0; full canonical mappings below are acceptance obligations, not delivered proof.

| Requirement | Full canonical requirement | Required proof |
| --- | --- | --- |
| IAU15-FR-003 | Bootstrap the first local operator through an operator-held one-use setup credential with no default account/password; provide a documented secured account-recovery procedure. | Bootstrap replay/default-credential tests and recovery exercise |
| IAU15-FR-017 | Disable, revoke or restore epoch changes must invalidate unconsumed grants and prevent new run starts, collection claims, dispatch or grant consumption while preserving read and reconciliation for accepted external work. | Disable/revoke/restore-before-dispatch-or-consume race matrix |
| IAU15-FR-022 | Bound per-workflow/project concurrency, backlog, analysis workers and storage usage with explicit quota/backpressure errors. | Saturation, queue-cap and storage-exhaustion tests |
| IAU15-FR-059 | Record append-only application audit events with verified principal/type, role, scope, target, reason, time and before/after digests; expose scoped UI/JSON export without raw artifacts/secrets and document DB-admin trust limits. | Audit event coverage/export authorization and secret corpus |
| IAU15-FR-060 | Let authorized operators configure feature enablement, targets, quotas, retention, TTL and credential lifetimes; reject unsafe reductions, protect pending evidence or invalidate its decision before deletion, and audit each change. | Configuration permissions, pending-retention and floor-change tests |
| IAU15-NFR-007 | The singleton SQLite profile must sustain 10 active runs with at most 2 concurrent analysis jobs and 20 online runners, with bounded queue/storage and no corrupted transitions. | 30-minute capacity/saturation run with resource and error report |
| IAU15-NFR-010 | Upgrade from a v1.4.0 database copy, interrupted upgrade, coordinated DB/artifact backup/restore, token rotation and restricted-network recovery must preserve auditable state while invalidating outstanding authorization/leases until reconciled. | Recorded upgrade/restore/rotation/offline exercises |
| IAU15-NFR-011 | Publish version-matched schema/API/CLI/operator/security/support-limit docs with CI link/drift checks and secret-free run/queue/step/runner/approval/delivery metrics plus troubleshooting runbooks. | Docs CI and operator self-service installation/recovery pilot |

## Tasks / Subtasks

Execute one bounded packet at a time on the story feature branch. Each packet owns the named paths; coordinate shared paths and do not revert other edits. Re-estimate after 16.0 spikes; split packets into reviewable PRs without renumbering the canonical story.

- [ ] Packet 18.1: Retention and bounded storage — owner: Persistence implementer.
  - Owned write paths: `infra_automation/ retention service; models/repositories/ artifact manifests; config.py; tests/test_infra_automation/`.
  - Output: atomic upload/deletion staging, decision invalidation, digest tombstones and floors; no raw artifact in audit.
  - Acceptance proof: AC1,2: pending-evidence deletion races, abandoned upload/disk-full/quota corpus.
- [ ] Packet 18.2: Quiesced backup, upgrade and restore epoch — owner: Persistence/operator implementer.
  - Owned write paths: `scripts/ automation backup/restore tooling; migrations/versions/ next inspected head; tests/test_models/ and tests/test_infra_automation/`.
  - Output: coordinated manifest/checkpoint and epoch reset with credential/lease/grant invalidation; never assume copied SQLite alone is complete.
  - Acceptance proof: AC3: v1.4.0-copy migration, interrupted upgrade, restored consumed/unconsumed operation races.
- [ ] Packet 18.3: Expiry and uncertain-operation recovery — owner: Domain implementer.
  - Owned write paths: `infra_automation/ reconciliation and existing target locks; tests/test_infra_automation/`.
  - Output: distinct content/authority/lease expiry, retained unknown locks and reasoned audited break.
  - Acceptance proof: AC3,4: no resurrection after restore/revoke/expiry; receiver receipts reconcile same operation.
- [ ] Packet 18.4: Restricted network and tool caches — owner: Runner/operator implementer.
  - Owned write paths: `infra_automation/runner/ config; docs/infra-automation/network.md; tests/test_infra_automation/`.
  - Output: allowlisted DNS/egress, bounded pinned caches, separate identities and rotation procedures.
  - Acceptance proof: AC5: denied egress/DNS, offline cache install, rotation and recovery exercise.
- [ ] Packet 18.5: Operator runbooks and observable limits — owner: Documentation/operations verifier.
  - Owned write paths: `docs/infra-automation/operations.md and recovery/security/support docs; config.py metrics; tests/test_docs/`.
  - Output: bootstrap/account recovery, configuration, restore, incident, retention and unknown-lock runbooks; secret-free bounded metrics and original 12.7/12.8 contribution matrix.
  - Acceptance proof: AC1–6: self-service pilot, docs/drift checks, 30-minute capacity/resource/error record.

- [ ] Packet 18.6: Automation settings browser integration — owner: Frontend/operator UI implementer (AC7 and AC1/4).
  - Owned write paths: `frontend/src/screens/Settings.tsx` and scoped settings components/client adapters, `frontend/e2e`, and feature operator documentation.
  - Output: explicit admin feature-enablement, registered-target selection/details, quota/retention/TTL/credential-lifetime controls backed by earlier 16.4/16.10 APIs; receiver credentials remain configured by protected operator mechanisms, never pasted into reusable UI persistence.
  - Acceptance proof: composed API-backed admin save/validation/conflict, nonadmin denial, feature-off history/reconciliation, disable-after-approval and stale-scope cache cases; full keyboard/axe and 1440/760 screenshots. Register actual browser tests and record commands/results. Backend support gaps use their own labeled backend-for-UI PR; no Vite acceptance.

## Dev Notes

- Reuse: Reuse models/database.py, existing Alembic/migrations and configuration patterns; tests/test_models temp-database isolation and existing operator docs. Restore and receiver admission must reuse shared epoch/authority services from 16.4/10/11. Do not introduce HA, PostgreSQL or another backup framework.
- Owned entities: Extend manifests/tombstones, epoch/config/audit and operation relations only for current packet; custody backup remains operator-local. Append-only APIs do not protect against host/DB administrators.
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
- `_bmad-output/implementation-artifacts/16-18-operator-recovery-retention-and-network-readiness.md` (story specification only).
