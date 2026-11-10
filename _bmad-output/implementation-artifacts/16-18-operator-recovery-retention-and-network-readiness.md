# Story 16.18: Operator Recovery, Retention and Network Readiness

Status: in-progress
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

- [x] Packet 18.1: Retention and bounded storage — owner: Persistence implementer.
  - Owned write paths: `infra_automation/ retention service; models/repositories/ artifact manifests; config.py; tests/test_infra_automation/`.
  - Output: atomic upload/deletion staging, decision invalidation, digest tombstones and floors; no raw artifact in audit.
  - Acceptance proof: AC1,2: pending-evidence deletion races, abandoned upload/disk-full/quota corpus.
- [x] Packet 18.2: Quiesced backup, upgrade and restore epoch — owner: Persistence/operator implementer.
  - Owned write paths: `scripts/ automation backup/restore tooling; migrations/versions/ next inspected head; tests/test_models/ and tests/test_infra_automation/`.
  - Output: coordinated manifest/checkpoint and epoch reset with credential/lease/grant invalidation; never assume copied SQLite alone is complete.
  - Acceptance proof: AC3: v1.4.0-copy migration, interrupted upgrade, restored consumed/unconsumed operation races.
- [x] Packet 18.3: Expiry and uncertain-operation recovery — owner: Domain implementer.
  - Owned write paths: `infra_automation/ reconciliation and existing target locks; tests/test_infra_automation/`.
  - Output: distinct content/authority/lease expiry, retained unknown locks and reasoned audited break.
  - Acceptance proof: AC3,4: no resurrection after restore/revoke/expiry; receiver receipts reconcile same operation.
- [x] Packet 18.4: Restricted network and tool caches — owner: Runner/operator implementer.
  - Owned write paths: `infra_automation/runner/ config; docs/infra-automation/network.md; tests/test_infra_automation/`.
  - Output: allowlisted DNS/egress, bounded pinned caches, separate identities and rotation procedures.
  - Acceptance proof: AC5: denied egress/DNS, offline cache install, rotation and recovery exercise.
- [ ] Packet 18.5: Operator runbooks and observable limits — owner: Documentation/operations verifier.
  - Owned write paths: `docs/infra-automation/operations.md and recovery/security/support docs; config.py metrics; tests/test_docs/`.
  - Output: bootstrap/account recovery, configuration, restore, incident, retention and unknown-lock runbooks; secret-free bounded metrics and original 12.7/12.8 contribution matrix.
  - Acceptance proof: AC1–6: self-service pilot, docs/drift checks, 30-minute capacity/resource/error record.

- [x] Packet 18.6: Automation settings browser integration — owner: Frontend/operator UI implementer (AC7 and AC1/4).
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
Codex (GPT-6), with bounded native implementation and independent review lanes.

### Implementation Plan
- Reuse existing authorization, policy epochs, audit, target locks, shared analysis and receiver contracts; add no dependencies.
- Preserve immutable evidence identity through tombstones and an exact one-use storage debit; protect pending decisions and uncertain external work.
- Coordinate private database/artifact/custody backups under participating-writer locks and an outside-backup generation ledger; make interrupted publication and completion resumable without reviving authority.
- Reconcile a consumed historical receiver operation using current-generation status/terminal-only credentials and completed local evidence; never repeat an action or restore a grant.
- Bind the approved settings and registered-target inspection UI to real APIs in a separate dependent branch; verify the production-built composed app.
- Keep unexecuted human and broader production-profile qualification explicit. Packet 18.5 remains open for its independent human self-service pilot.

### Debug Log References
- [Entry and concrete interface review](../../docs/verification/infra-automation/16-18/readiness.md).
- [Independent findings and repairs](../../docs/verification/infra-automation/16-18/review.md).
- [Retention proof](../../docs/verification/infra-automation/16-18/retention-results.md).
- [Restore proof](../../docs/verification/infra-automation/16-18/restore-results.md).
- [Receiver recovery proof](../../docs/verification/infra-automation/16-18/receiver-recovery-results.md) and [completed receiver/CLI proof](../../docs/verification/infra-automation/16-18/receiver-runtime-recovery-results.md).
- [Actual operator exercise](../../docs/verification/infra-automation/16-18/operator-exercise.md):28 normal checks plus 2 completion-resume cases.
- [Authentic v1.4.0-copy upgrade](../../docs/verification/infra-automation/16-18/upgrade-results.json): schema 028 → 042, 37 original report columns preserved, source unchanged, integrity OK/FK0.
- [Offline archive installation and network-none recovery](../../docs/verification/infra-automation/16-18/offline-install-results.md), [cache](../../docs/verification/infra-automation/16-18/cache-results.json) and [DNS](../../docs/verification/infra-automation/16-18/network-results.md).
- [Full capacity result](../../docs/verification/infra-automation/16-18/capacity-results.md) and [reproducible command](../../docs/verification/infra-automation/16-18/capacity-command.md).
- [Composed browser proof](../../docs/verification/infra-automation/16-18/ui-results.md), source inventory, 24 screenshots and visual verdict 94 on the dependent UI branch.
- [Final commands/log digests/results](../../docs/verification/infra-automation/16-18/validation-summary.json) and [acceptance audit](../../docs/verification/infra-automation/16-18/acceptance-audit.md).

### Completion Notes List
- Backend branch: `feature/16-18-operator-recovery-retention`; dependent UI branch: `feature/16-18-automation-settings-ui`. Local preparation preserves separate backend and UI review units.
- Implemented migrations040–042, typed scoped purge, immutable retention receipts, conservative quota reclamation, protected cache verification, coordinated backup/restore, generation invalidation and recovery barriers, completed-only receiver reconciliation, and approved settings/target-selection-details UI.
- Reused existing services and wire contracts; no new dependency, infrastructure action, automatic approval, general machine issuer or target-editing form was introduced.
- Independent reviews and composed/real operator exercises caught and repaired: full-schema debit rejection; exact retry after purge; lost post-backup external history; missing schema guards; raw SQLite descriptor lock loss; expired reconciliation-token revival; inert audit-identity generation assumption; and interrupted completion with expired sessions. Initial failures/interrupted measurements remain explicitly unqualified evidence.
- Final root smoke: `./.venv/bin/python -m unittest discover -q` — 2048 tests, 3 skips, exit 0. Full `bash scripts/ci-local.sh` — 3523 tests across all 10 directories, exit 0; includes lint, repo-wide formatting 611 files, dependency consistency, Bandit, compile and skill/prompt checks. Exact API/CLI/infra pytest shard — 812 passed, 1 skipped, 2442 subtests.
- Fresh real isolation 172 checks and collection 49 checks passed with source integrity. Final Linux/Python 3.11.17 production-image capacity ran 1800.767 real seconds: 3600 samples, 10 active runs throughout, 2 spawned synthetic analysis workers, 20 authenticated persisted runner ports, 72000 polls, 40 rotations, zero errors, explicit 429 backpressure and identical 338-file source witnesses.
- UI validation APPLICABLE and passed: 493 frontend tests plus 2 compatibility checks, typecheck/build, 2 actual composed browser journeys, 24 screenshots at 1440/760, zero critical/serious axe findings, visual 94. Settings saves/409/422/403 and stale-scope cases, real purge/retained history, post-approval disable and feature-off reconciliation ran at root SPA routes on localhost8080. Original application was restored healthy; all disposable resources and credentials were removed.
- Offline installation proof uses a complete verified 229869568-byte/21-layer current image archive on an already installed/cached Docker host, then fresh private schema 042 state and 28 CLI/API checks under network none. This is not cold OS/Docker/dependency installation or a production human pilot.
- Remaining mandatory gate: independent human self-service pilot. Broader production HTTPS/remote receiver credential transfer, unmanaged writers, other tools/providers and host-power-loss qualification remain unclaimed support/release gates. Original 12.7/12.8 acceptance remains open. Story stays **in-progress**; Packet 18.5 is not falsely checked.
- Combined workspace after local branch integration: frontend493 tests/2 compatibility checks, typecheck/build,3 fixture guards and repository-wide Ruff613 files passed.
- BMad Help recheck: complete the remaining operator qualification, then run formal `bmad-code-review` in fresh context before review/done advancement. Do not promote release readiness or close 12.7/12.8 from these bounded contributions.

### File List
The following list covers the backend branch and dependent UI branch together;
private databases, plans, credentials and image archives are excluded.

- `README.md`
- `_bmad-output/implementation-artifacts/16-18-operator-recovery-retention-and-network-readiness.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/project-context.md`
- `api/routes/infra_automation.py`
- `api/schemas.py`
- `app.py`
- `cli/automation_operations.py`
- `cli/identity.py`
- `config.py`
- `docs/infra-automation/network.md`
- `docs/infra-automation/operations.md`
- `docs/verification/infra-automation/16-13/results.json`
- `docs/verification/infra-automation/16-14/results.json`
- `docs/verification/infra-automation/16-18/acceptance-audit.md`
- `docs/verification/infra-automation/16-18/cache-results.json`
- `docs/verification/infra-automation/16-18/capacity-before-completion-resume/capacity-progress.json`
- `docs/verification/infra-automation/16-18/capacity-before-completion-resume/capacity-start.json`
- `docs/verification/infra-automation/16-18/capacity-before-completion-resume/container-profile.json`
- `docs/verification/infra-automation/16-18/capacity-before-completion-resume/interruption.json`
- `docs/verification/infra-automation/16-18/capacity-before-completion-resume/operator-capacity-failure.json`
- `docs/verification/infra-automation/16-18/capacity-before-fixture-clock-fix/capacity-progress.json`
- `docs/verification/infra-automation/16-18/capacity-before-fixture-clock-fix/capacity-start.json`
- `docs/verification/infra-automation/16-18/capacity-before-fixture-clock-fix/container-profile.json`
- `docs/verification/infra-automation/16-18/capacity-before-fixture-clock-fix/interruption.json`
- `docs/verification/infra-automation/16-18/capacity-before-fixture-clock-fix/operator-capacity-failure.json`
- `docs/verification/infra-automation/16-18/capacity-before-receiver-recovery/capacity-progress.json`
- `docs/verification/infra-automation/16-18/capacity-before-receiver-recovery/capacity-start.json`
- `docs/verification/infra-automation/16-18/capacity-before-receiver-recovery/interruption.json`
- `docs/verification/infra-automation/16-18/capacity-before-receiver-recovery/operator-capacity-failure.json`
- `docs/verification/infra-automation/16-18/capacity-command.md`
- `docs/verification/infra-automation/16-18/capacity-interrupted/capacity-progress.json`
- `docs/verification/infra-automation/16-18/capacity-interrupted/capacity-start.json`
- `docs/verification/infra-automation/16-18/capacity-interrupted/interruption.json`
- `docs/verification/infra-automation/16-18/capacity-interrupted/operator-capacity-failure.json`
- `docs/verification/infra-automation/16-18/capacity-results.md`
- `docs/verification/infra-automation/16-18/capacity/capacity-progress.json`
- `docs/verification/infra-automation/16-18/capacity/capacity-start.json`
- `docs/verification/infra-automation/16-18/capacity/capacity.json`
- `docs/verification/infra-automation/16-18/capacity/container-profile.json`
- `docs/verification/infra-automation/16-18/capacity/operator-capacity.json`
- `docs/verification/infra-automation/16-18/changed-files.json`
- `docs/verification/infra-automation/16-18/final-source-hashes.json`
- `docs/verification/infra-automation/16-18/isolation-first-attempt.json`
- `docs/verification/infra-automation/16-18/linux-smoke/capacity-progress.json`
- `docs/verification/infra-automation/16-18/linux-smoke/capacity-start.json`
- `docs/verification/infra-automation/16-18/linux-smoke/capacity.json`
- `docs/verification/infra-automation/16-18/linux-smoke/container-profile.json`
- `docs/verification/infra-automation/16-18/linux-smoke/operator-capacity.json`
- `docs/verification/infra-automation/16-18/network-results.json`
- `docs/verification/infra-automation/16-18/network-results.md`
- `docs/verification/infra-automation/16-18/offline-install-results.json`
- `docs/verification/infra-automation/16-18/offline-install-results.md`
- `docs/verification/infra-automation/16-18/operator-exercise.json`
- `docs/verification/infra-automation/16-18/operator-exercise.md`
- `docs/verification/infra-automation/16-18/readiness.md`
- `docs/verification/infra-automation/16-18/receiver-recovery-design.md`
- `docs/verification/infra-automation/16-18/receiver-recovery-results.md`
- `docs/verification/infra-automation/16-18/receiver-runtime-recovery-results.md`
- `docs/verification/infra-automation/16-18/recovery-results.md`
- `docs/verification/infra-automation/16-18/restore-design.md`
- `docs/verification/infra-automation/16-18/restore-results.md`
- `docs/verification/infra-automation/16-18/restore-source-hashes.json`
- `docs/verification/infra-automation/16-18/retention-design.md`
- `docs/verification/infra-automation/16-18/retention-results.md`
- `docs/verification/infra-automation/16-18/review.md`
- `docs/verification/infra-automation/16-18/screenshots.json`
- `docs/verification/infra-automation/16-18/screenshots/settings-after-approval-disabled-1440.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-after-approval-disabled-760.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-conflict-1440.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-conflict-760.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-conflict-outcome-1440.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-conflict-outcome-760.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-disabled-1440.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-disabled-760.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-disabled-outcome-1440.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-disabled-outcome-760.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-feature-off-reconciled-1440.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-feature-off-reconciled-760.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-integrated-history-1440.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-integrated-history-760.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-nonadmin-1440.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-nonadmin-760.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-saved-1440.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-saved-760.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-saved-outcome-1440.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-saved-outcome-760.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-target-1440.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-target-760.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-target-outcome-1440.png`
- `docs/verification/infra-automation/16-18/screenshots/settings-target-outcome-760.png`
- `docs/verification/infra-automation/16-18/ui-integrated-sources.json`
- `docs/verification/infra-automation/16-18/ui-results.md`
- `docs/verification/infra-automation/16-18/upgrade-initial041-results.json`
- `docs/verification/infra-automation/16-18/upgrade-results.json`
- `docs/verification/infra-automation/16-18/validation-summary.json`
- `docs/verification/infra-automation/16-18/visual-verdict.json`
- `frontend/e2e/infra-automation-settings-outcomes.spec.ts`
- `frontend/e2e/infra-automation-settings.spec.ts`
- `frontend/src/api/infraAutomationSettings.test.ts`
- `frontend/src/api/infraAutomationSettings.ts`
- `frontend/src/api/schema.d.ts`
- `frontend/src/screens/AutomationSettingsSection.test.tsx`
- `frontend/src/screens/AutomationSettingsSection.tsx`
- `frontend/src/screens/Settings.tsx`
- `infra_automation/operator_recovery.py`
- `infra_automation/receiver_recovery.py`
- `infra_automation/receiver_runtime.py`
- `infra_automation/retention.py`
- `infra_automation/runner/cache.py`
- `migrations/versions/040_add_manifest_retention.py`
- `migrations/versions/041_add_operator_recovery.py`
- `migrations/versions/042_add_receiver_recovery.py`
- `models/database.py`
- `models/operator_recovery.py`
- `models/receiver_recovery.py`
- `models/repositories/infra_automation_reports.py`
- `models/tables.py`
- `scripts/compose-story16-18-outcomes.yaml`
- `scripts/compose-story16-18.yaml`
- `scripts/qualify_collection.py`
- `scripts/qualify_operator_capacity.py`
- `scripts/settings_ui_fixture.py`
- `services/content_security.py`
- `services/identity_service.py`
- `services/infra_automation_collection_views.py`
- `services/infra_automation_engine_support.py`
- `services/infra_automation_handoffs.py`
- `services/infra_automation_policy.py`
- `services/infra_automation_preflight.py`
- `services/infra_automation_receiver_recovery.py`
- `services/infra_automation_retention.py`
- `services/infra_automation_runner_tasks.py`
- `services/infra_automation_runners.py`
- `services/infra_automation_snapshots.py`
- `services/project_service.py`
- `tests/test_api/test_infra_automation_retention.py`
- `tests/test_cli/test_receiver_recovery.py`
- `tests/test_docs/test_automation_operations_docs.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_identity_migration.py`
- `tests/test_infra/test_infra_automation_engine_migration.py`
- `tests/test_infra/test_infra_automation_handoff_migration.py`
- `tests/test_infra/test_infra_automation_workflow_migration.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_infra/test_project_membership_migration.py`
- `tests/test_infra/test_receiver_reconciliation_migration.py`
- `tests/test_infra/test_runner_enrollment_migration.py`
- `tests/test_infra/test_settings_ui_fixture_guard.py`
- `tests/test_infra/test_trigger_migration.py`
- `tests/test_infra_automation/test_collection_qualification.py`
- `tests/test_infra_automation/test_engine_identity.py`
- `tests/test_infra_automation/test_operator_backup.py`
- `tests/test_infra_automation/test_operator_cache.py`
- `tests/test_infra_automation/test_operator_capacity.py`
- `tests/test_infra_automation/test_operator_recovery.py`
- `tests/test_infra_automation/test_preflight_repository.py`
- `tests/test_infra_automation/test_receiver_completed_recovery.py`
- `tests/test_infra_automation/test_receiver_recovery.py`
- `tests/test_infra_automation/test_receiver_recovery_redaction.py`
- `tests/test_infra_automation/test_recovery_barrier.py`
- `tests/test_infra_automation/test_retention.py`
- `tests/test_models/test_receiver_recovery_migration.py`
- `tests/test_models/test_retention_migration.py`

## Change Log

- 2026-11-10: Implemented and independently reviewed owned local contracts; completed unit/local CI, authentic upgrade, real isolation/collection, composed UI, offline installation and 30-minute configured Linux capacity proof. Preserved the independent human pilot and broader release/support gates; status remains in-progress.
