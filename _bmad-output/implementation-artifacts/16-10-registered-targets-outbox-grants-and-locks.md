# Story 16.10: Registered Targets, Outbox, Grants and Locks

Status: done
Preparation: refined
Release: v1.5.0

## Story

As a platform administrator, I want to register exact targets and retain durable locked handoff intents, so that destination changes, replay and uncertain work cannot silently release another action.

## Entry gates and slice boundary

- Release priority: P0 feature work for v1.5.0. **Blocked for implementation** until Story 16.0 has recorded public RFC/CODEOWNERS acceptance, executable identity/fencing/isolation/custody/receiver qualification and final interface decisions; planning adoption alone is not authorization evidence.
- Hard earlier dependencies: **16.8**, accepted and verified before advancing this story. These dependency results are currently unresolved; refined preparation does not mean ready-for-dev. No prior implementation learning is available for the new Epic 16 story set.
- Promote only after contract freeze, earlier dependency evidence, bounded task ownership/re-estimation and independent story review. Preserve IDs and backlog status; no feature/release implementation is claimed here.

## Acceptance Criteria

1. **AC1:** Given registered aliases across projects, when a handoff-enabled run starts before collection, then all aliases resolve to one canonical target lock and overlapping requests cannot obtain it.
2. **AC2:** Given an eligible immutable decision, when authorization prepares dispatch, then one short transaction revalidates live identity/membership/feature/target/restore epochs, policy/evidence/custody/deadlines and writes exact payload, stable operation, grant and outbox before network effects.
3. **AC3:** Given a used idempotency key with identical payload, when retried, then the same operation returns; changed payload conflicts; a grant with changed binding/replay/expiry/wrong identity cannot consume authority.
4. **AC4:** Given registered destination DNS rebinding, redirects, IPv4/IPv6 metadata/loopback/private addresses or alias changes, when a connection is attempted, then connection-time validation denies it except an explicit audited administrator-owned internal-origin exception.
5. **AC5:** Given disable, revocation or restore, when new starts, claims, dispatch or outstanding-grant consumption race, then no new authority is exercised; accepted work remains readable/reconcilable and cannot gain a replacement grant.
6. **AC6:** Given unknown external work, cancellation or lease expiry, when unlock/retry is requested, then the lock remains until verified terminal resolution or audited privileged break acknowledging uncertainty without new authorization.

### Requirement Traceability

Coverage intent: Delta over the v1.4.0 baseline. These exact mapped requirements are acceptance obligations; mapping is not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| IAU15-FR-017 | Disable, revoke or restore epoch changes must invalidate unconsumed grants and prevent new run starts, collection claims, dispatch or grant consumption while preserving read and reconciliation for accepted external work. | Disable/revoke/restore-before-dispatch-or-consume race matrix |
| IAU15-FR-031 | Bind approval to authorization kind, revision, source identity and required exact-plan commit, project/workspace/environment, reports, artifact and unit-plan digests, policy version, exact target and payload digest. | Independent mutation of every decision-tuple field |
| IAU15-FR-035 | Invalidate eligibility when evidence, revision, source, scope, target, policy, membership or custody changes, expires or is superseded; no emergency bypass or delegated approval in P0. | Revocation/supersession/custody-loss and bypass-denial matrix |
| IAU15-FR-036 | Register outbound GitHub destinations with administrator-controlled host policy; revalidate DNS/connection addresses and redirects, blocking metadata/loopback/private targets except explicit audited internal-host exceptions. | IPv4/IPv6/DNS/redirect SSRF corpus |
| IAU15-FR-037 | Atomically persist the approved outbound intent and exact payload before network effects, with a stable receiver operation identity. | Transaction/crash-before-send and payload-tamper tests |
| IAU15-FR-038 | Issue one-use scoped receiver grants bound to the decision tuple, operation, expiry and live epoch; reject duplicate/replayed or altered consumption. | Grant replay/expiry/epoch/source/digest tests |
| IAU15-FR-042 | Canonicalize target lock identities across aliases and retain locks during unknown external work until verified resolution or an audited operator break that does not mint a new authorization. | Alias collision/lock expiry/unknown-work/break tests |
| IAU15-NFR-001 | The declared crash/race corpus must lose no committed run/decision state and produce no unauthorized or duplicate receiver action, including stale attempts, unknown delivery and restore epochs. | Published fault-injection results at every persisted boundary |

## Tasks / Subtasks and bounded ownership

- [x] **Packet 1 — Domain/persistence owner: registry and locks (AC 1,4,6).** Owned output: `infra_automation/targets.py, models/repositories and current-head migration (planned)`.
  - [x] Persist canonical identity/aliases and administrator host policy; acquire unique target lock before handoff-enabled collection, collision tests across projects, audited target changes.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 2 — Domain/persistence owner: operation/outbox/grant (AC 2,3).** Owned output: `infra_automation/handoff.py and repositories (planned)`.
  - [x] Atomic exact intent, request digest/idempotency, stable operation and hashed one-use grant; consumption CAS and binding verification; crash-before-commit/send, duplicate and changed-payload tests.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 3 — Security/service owner: live admission and SSRF (AC 2–5).** Owned output: `services/infra_automation_service.py, typed routes and fixed outbound transport`.
  - [x] Enforce live feature/epoch/membership/custody at dispatch and online consume; connection/DNS/redirect checks with no workflow-supplied arbitrary URL; disable/revoke/restore race corpus.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 4 — Test/documentation owner: recovery qualification (AC 1–6).** Owned output: `tests/test_infra_automation, tests/test_api, docs/infra-automation`.
  - [x] Fault-inject persisted boundaries, unknown-work retention and explicit audited break; publish grant secret corpus, SSRF corpus and target-lock operating contract.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.

Each packet is a bounded review unit under this stable story ID; split large packets after 16.0 estimation instead of silently broadening scope. One story branch follows Git Flow; coordinate shared-file edits and do not revert other work.

### Review Findings

BMad code review on 2026-11-02: **changes requested**. Independent blind, edge-case and acceptance layers completed. The original 3 findings are resolved by the review-fix validation below. The fresh rerun found High R4; final status is done after the resolution below. Full findings and reproduction evidence: `docs/verification/infra-automation/16-10/code-review.md`.

- [x] [Review][Patch][High] R1 — Recheck current material/custody after workflow-ref callbacks before prepare, dispatch, consume and action admission; exact-plan custody loss during the callback previously succeeded at all four boundaries. [services/infra_automation_handoffs.py:481]
- [x] [Review][Patch][Medium] R2 — Persist successful action-admission clock observations; a check at t0+60s followed by a regressed t0+30s previously succeeded because the retained floor stayed at consume time. [services/infra_automation_handoffs.py:1035]
- [x] [Review][Patch][Medium] R3 — Complete final root unittest/local CI evidence and reconcile task/verification checklists; the final broad-results record and post-fix validation are now complete. [docs/verification/infra-automation/16-10/results.md:90]

- [x] [Review][Patch][High] R4 — Revalidate selected and mandatory-ancestor material consistently after all graph material callbacks. A later ancestor lookup can revoke selected exact-plan custody while prepare, dispatch, consume and action still succeed. [services/infra_automation_handoffs.py:478; services/infra_automation_decisions.py:565] See `docs/verification/infra-automation/16-10/code-review-rerun-2026-11-02.md`.

- [x] [Review][Patch][Medium] R5 — Reserve future mutable handoff/outbox/grant and canonical-lock scalar bookkeeping before authority/admission; receipt timestamp/digest and terminal reason growth previously exceeded logical retained-byte charges. Fixed and independently reviewed; final qualification passed. See `docs/verification/infra-automation/16-10/r4-r5-resolution.md`.

- [x] [Review][Patch][Medium] R6 — Handle macOS killpg EPERM/exit-sentinel races through the existing bounded confirmation loop; release still requires sentinel plus whole-group death proof. Persistent denial remains fatal/dirty. Red/green units, full module,20 instrumented cancellation repetitions and Linux full CI passed. [infra_automation/worker_supervision.py:225]

## Dev Notes

### Derived settings UX ownership

This earlier slice owns the feature/configuration or registered-target API and its permission/epoch/validation contracts. It does not depend on a later settings screen to complete: use service/API tests now. Story 16.18 Packet 18.6 explicitly owns the integrated `/settings` browser controls and composed acceptance using these earlier APIs; any backend-for-UI support remains additive in its own labeled PR.



- Only registry/lock/outbox/grant entities needed here may migrate; inspect current Alembic head rather than inventing a revision number. Reuse models/database.py session and existing repositories; network effects never occur inside a SQLite transaction.
- Contracts include registered canonical target/receiver identity, aliases, allowlisted origin; stable operation/request digest; exact action binding; grant verifier, scope, expiry/live epoch and consumption receipt. 16.0 freezes wire names/routes/errors; no general webhook adapter.
- Acquire target lock before collection when handoff is intended, not only at dispatch. Alias mutation cannot evade locks; local cancel/timeout is not proof the remote pipeline stopped. Lock break does not produce a fresh approval or authorization.
- Use a scoped receiver-consumer test double to qualify online admission here; 16.11 owns real receiver durability/network proof. This slice must prove denied outstanding grants after disable/revoke/restore, not merely invalidate future token creation.
- Credentials use environment-backed references in config.py. Plaintext grant values never enter persistent DB/logs/audit. Raw binary saved plans/state never enter the server. Upload advisory grants cannot authorize apply.
- If target settings UI changes, separate backend behavior PR and run the composed UI gate below; otherwise record UI validation not applicable. Reuse existing GitHub URL validation cautiously: it is not complete DNS/connection SSRF proof.

### Project Structure Notes

- Planned modules are additions under the established Python/service/API/repository and React boundaries, not present-day implementation claims. Reuse `api/errors.py` ApiRoute/ApiError, `api/schemas.py`, `models/database.py`, `models/tables.py`, repositories and `migrations/versions/`; inspect head before allocation.
- Introduce only entities necessary for this slice; never precreate all automation tables. Keep deterministic findings in the shared analysis core, optional AI downstream and privileged execution outside FastAPI. No new dependencies without a recorded approved decision.
- Interface names/resources are design obligations pending 16.0 freeze, not permission to invent final route/schema contracts. Add docs and tests with behavior; do not defer slice coverage to 16.19.

## Required implementation verification

- [x] Register new `tests/test_infra_automation` directories in `scripts/ci-local.sh` and affected GitHub discovery/shards; root discovery alone skips non-package test directories.
- [x] For every Pydantic/schema/dataclass/constructor change, use repository-wide `rg` searches for direct instantiations/fixtures and update all consumers, including CLI/agent/action/report compatibility where affected.
- [x] Run `./.venv/bin/python -m unittest discover -q`, story-focused tests and exactly `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` for affected API/CLI/infra contracts.
- [x] Run `./.venv/bin/ruff check .`, **`./.venv/bin/ruff format --check .` repo-wide**, `bash scripts/ci-local.sh` and `git diff --check`; add applicable static/security/type checks. Record commands and actual results rather than assumed passes.
- [x] UI validation not applicable only if no rendered surface changes; if a UI surface is touched, use the complete composed-app Playwright/keyboard/axe/screenshot loop required by project context before review.

## References

- [Canonical feature PRD](../planning-artifacts/prd-infra-automation.md), [exact requirement registry](../planning-artifacts/infra-automation-requirement-dispositions.json) and [Epic 16](../planning-artifacts/epics.md).
- [Architecture §25](../planning-artifacts/architecture.md#25-v150-infrastructure-automation-architecture-amendment), especially slice qualification §25.12; [mandatory project context](../project-context.md).
- [Readiness gates IR-01–IR-06](../planning-artifacts/implementation-readiness-report-2026-10-07-infra-automation-v1.5.0.md) and [release sequencing](../planning-artifacts/infra-automation-v1.5.0-release-plan.md).
- [Feature UX contract](../../docs/design/infra-automation-ux.md), [UX authority](../planning-artifacts/ux-design-specification.md), [v3 visual authority](../../docs/design/deploywhisper-redesign-v3.jsx) and [RFC 0001](../../docs/rfcs/0001-infra-automation-preflight-and-handoff.md).

## Dev Agent Record

### Final accepted verification and closeout — 2026-11-02

- All three review layers accepted R4's exact graph/domain/generation witness, R5's future metadata reservations and R6's bounded EPERM confirmation correction. No High/Medium item remains. Missing witness defaults to503; source authority remains unqualified until later providers satisfy the documented atomic/lease contract.
- R4 red4cases became12 green methods / 92 subtests including selected/ancestor changes, both callback orders, ABA, malformed/wrong-scope/count/reset generations and end-read expiry/reviewer/supersession. All five constructor sites/DTO consumers were searched and updated.
- R5 receipt/dispatch undercount and lock reason growth were independently reproduced. Reservations now cover bounded future operation/outbox/grant scalar values and terminal lock metadata/max printable UTF8 reason. Actual initial records stay unchanged; raw receipt bytes are charged separately. Exact quota/one-byte-short rollback tests pass.
- R6 diagnostic captured macOS killpg EPERM before sentinel readiness. The narrow correction reuses existing bounded confirmation and never accepts EPERM as death proof. Permanent denial/live descendants remain unconfirmed, unjoined and dirty. Red3 observations,2 green unit methods / 2 subtests,15-test supervision module and 20 instrumented cancellation repetitions passed. No unknown execution was unlocked or granted replacement authority.
- Final LinuxARM64/Python3.11 frozen-source qualification: root 1,466 tests OK(6 skips),897.940s; exact API/CLI/infra shard 709 passed/1 skip,2,316 subtests,464.81s; full `bash scripts/ci-local.sh` exited 0 with2,912 tests across 10 directories,6 optional skips. Before/after 562 source hashes matched every lane. Four optional JSON Schema cases also passed on host (30 subtests); remaining skips are explicit live-provider/container opt-ins.
- Rebuilt nonroot Python3.11.17 runtime image ran 196 tests (all 15 story modules plus supervision), OK(1 optional schema skip),116.498s. Health/OpenAPI/schema035/zero seeded identities/no Node smoke passed; witness DTOs remain internal. Existing operator app/data preserved.
- Scoped mypy 13 modules, Ruff lint/repo-wide format 474 files, pip consistency, Bandit high/high gate, compileall, skill/prompt-injection and whitespace checks passed. Source stayed frozen after final corrections. Earlier interrupted/failing host attempts and their actual cause remain documented rather than claimed as final passes.
- Final commands, directory counts, hashes, diagnostics, review conclusions and limitations: `docs/verification/infra-automation/16-10/r4-r5-resolution.md`. UI validation not applicable. No project dependency, public API/frozen-wire/schema change was needed for review fixes; real provider/receiver/collector and host-power-loss integration remains later-story work.
- Story and sprint are done for the accepted scope. User-authorized git add/commit/push/PR targets develop on `feature/16-10-targets-outbox-grants`; merge/release remain separate. BMad Help's next delivery work is Story 16.11 planning after integration.

### R4/R5 implementation and final verification — 2026-11-02

- R4 implemented with exact graph material scope plus qualified server-owned domain/generation witnesses around all callbacks, including ABA. Missing witness defaults to503; final live/time guards remain later. Added12 regression methods / 92 subtests and updated all five constructor sites/fixture consumers; no public API or frozen-wire/schema change.
- Independent review confirmed R4 and found Medium R5 scalar-bookkeeping undercount. Added pre-reservation of future handoff/outbox/grant metadata and terminal lock metadata/max UTF8 reason; actual initial row values remain unchanged. Handoff and lock quota boundary regressions failed before fixes and pass after fixes. No dependencies added.
- Current handoff/decision/process suites passed103 methods/124 subtests; target-capacity module passed12 methods/9 subtests. Initial R4 broad runs were interrupted before R5 source changes; final frozen-source verification is running. No partial run is claimed as final. Full results and exact logs: `docs/verification/infra-automation/16-10/r4-r5-resolution.md`.
- User authorized git add/commit/push/PR after fixes, review and proper validation; closeout will run after all gates. Story remains in-progress until then. UI validation not applicable.

### Third code review — unchanged source, 2026-11-02

- Source/configuration/test hashes match the previous review; no R4 fix was present. All three fresh layers completed and confirmed the same High R4; no additional distinct defect was found.
- Leader and edge/acceptance reviewers reran the four-boundary custody counterexample: prepare, dispatch, consume and action still accept selected custody=false. Leader reproduction log: `/tmp/story16-10-rereview-round3-custody.log` (2.087s). These demonstrate the defect rather than correct acceptance.
- Ruff lint, repo-wide format 474 files and whitespace checks passed. Broad CI was not repeated for unchanged source; prior complete results remain evidence for their covered cases.
- R4 stays unchecked; story/sprint remain in-progress. Updated the existing rerun report without duplicating the action item. No production changes, commit or push. Next workflow remains dev-story for R4.

### Fresh code review rerun — 2026-11-02

- All three fresh layers completed. One High patch finding (R4) was independently reproduced by edge/acceptance reviewers and confirmed by the leader at all four authority boundaries; original R1–R3 fixes/evidence remain valid for their covered cases.
- The selected receipt is checked before a later required-ancestor material callback revokes its custody. Final graph admission carries the earlier selected material and refreshes clocks/reviewers rather than current custody. New action authority still succeeds. Reproduction and exact source locations are in `docs/verification/infra-automation/16-10/code-review-rerun-2026-11-02.md`.
- Fresh focused pytest:67 passed,39 subtests,30.77s; Ruff lint, repo-wide format 474 files and whitespace checks passed. Prior root/exact-shard/full-CI/production evidence was verified against unchanged source; existing green suites lack this counterexample.
- Story/sprint returned to in-progress. R4 and its owning live-admission task are unchecked; no production code, commit, remote push or PR was made during this review. BMad Help recommends dev-story for R4, then code-review again. UI validation not applicable.

### Initial formal review validation — 2026-11-02

- Three review layers completed; two reproduced code defects and one verification-record gap were initially recorded as unchecked findings. That review requested changes; the resolution below supersedes its open-item status.
- Story-focused pytest (15 qualification modules): 156 passed, 380 subtests, 38.52s.
- Exact `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: 709 passed, 1 skipped, 2,316 subtests, 397.40s.
- `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .` (474 files), and `git diff --check`: passed.
- Root unittest and full local CI were unrecorded at that initial review; both now completed as recorded below. Broader infra-automation pytest was stopped after 216 passing tests to prioritize the complete focused run; it is not a full-suite pass. UI validation not applicable.
- Report and reproduction details: `docs/verification/infra-automation/16-10/code-review.md`. Next BMad Help recommendation: return to `bmad-dev-story` for fixes, then rerun review. No remote push was made during the initial review.

### Review-fix completion — 2026-11-02

- Resolved R1: final approved material/custody checks follow ref lookup and the preparation capacity probe. Existing final target/receiver/human/policy/graph/clock floors follow material callbacks. No extra abstraction or dependency was introduced.
- Resolved R2: action admission conditionally advances the operation clock floor through the existing same-state CAS and transactional `handoff_action_checked` audit. Same-clock checks are unchanged; grant, receipt, outbox and binding identities remain stable. Audit failure rolls back the observation.
- Added 8 regression methods (12 ref-mutation subcases) covering custody/evidence/binding changes at prepare/dispatch/consume/action, custody loss in both disk probes, clock rollback after restart, repeatability and audit rollback/chaining. Before code changes, the first 6 methods reproduced 14 failures; all 60 handoff-service tests now pass. Independent source/test re-review found no remaining R1/R2 defect.
- Resolved R3: root `./.venv/bin/python -m unittest discover -q` ran1,447 tests, OK (2 skips); exact `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` passed 709 with 1 skip and 2,316 subtests; fresh `bash scripts/ci-local.sh` exited 0 with 2,893 tests across all 10 directories, OK (2 skips). Full CI includes all 690 infra-automation and 1,232 service tests. Existing discovery registration was verified; no constructor contract changed in these fixes.
- Rebuilt production Python 3.11 image and ran all 15 focused modules: 164 tests, OK (one optional schema-validator skip), 88.371s. Isolated health/OpenAPI/schema035/zero-identity/nonroot/no-Node startup smoke passed. The operator app/container was preserved.
- Ruff lint and repo-wide format (474 files), pip check, scoped mypy (10 story modules), configured Bandit gate, compileall, skill/prompt-injection checks and final whitespace checks passed. Bandit's existing medium sample-literal warning is documented; touched handoff code is clean at medium/high severity.
- Initial local CI hit one existing worker-shutdown test plus cleanup errors; six isolated runs and the fresh full CI passed with no supervision changes. Both attempts and the unknown cause are retained in the verification record.
- UI validation not applicable. No rendered surface, API constructor, frozen protocol or dependency changed. Qualification remains scoped to doubles/controlled crashes; live receiver and collector integration remain later-story work.
- Final commands, actual results, limitations and AC evidence: `docs/verification/infra-automation/16-10/results.md`; review resolutions: `docs/verification/infra-automation/16-10/code-review.md`. BMad Help's next step is fresh `bmad-code-review`; story/sprint are `review` on the existing Git Flow feature branch. No commit/push/PR was performed by this fix workflow.

### Agent Model Used

Codex — BMad dev-story with bounded native implementation lanes and independent contract, security and final acceptance audits.

### Implementation Plan

- Entry reassessment on 2026-10-30: accepted16.0 governance/frozen interfaces and16.8 decision evidence, plus merged16.9 (`501d789`), supersede the original unresolved preparation prose. The dated scoped readiness record fixes the owning API refinement; stable requirements/ACs remain unchanged.
- Packet1 adds canonical registry/aliases/scopes, immutable run-target snapshots and globally unique held locks before collection. Packet2 adds exact operation/outbox intent, independent frozen receiver mapping and reproducible verifier-only one-use grants. Packet3 adds transaction-bound live admission and fixed pinned HTTPS policy. Packet4 qualifies crash/race/secret/quota/recovery boundaries.
- Branch: `feature/16-10-targets-outbox-grants`. No dependencies, frozen wire artifacts or rendered React surfaces changed. Reuse existing session, authorization, canonicalization, audit, quota and error utilities.

### Debug Log References

- Durable commands, actual results, AC mapping, process-fault matrix, secret/SSRF corpus and limitations: `docs/verification/infra-automation/16-10/results.md`.
- Local transient command logs: `/tmp/story16-10-*.log`; credentials and exported operator data are excluded. Final broad command results, the first CI failure and the successful fresh run are recorded in `results.md`.
- Red/green corrections include callback-time ancestor/mode/membership changes, raw-SQL stale ORM state, parent-run possible delivery, receiver read scope, deadline flooring, retained-copy quota charging, uppercase aliases, generated-grant screening and older-SQLite malformed JSON rejection.

### Completion Notes List

- Registry administration requires verified global human administration plus assigned scoped capability/CSRF; no project-admin alias takeover or startup identity seeding. Canonical alias claims, captured exact bytes and locks survive uncertainty and cannot be reused after privileged break.
- Preparation persists exact semantic bytes and both decision/receiver binding identities with one stable operation per approval AND run/handoff. Sending commits before any delivery port call. Grant consume/receipt CAS and audits share one transaction; replays/read recovery cannot mint authority or add quota charges.
- Live dispatch/consume/action boundaries refresh requester/reviewer/receiver, feature, target, policy, custody/ref, restore, required evidence and monotonic deadlines. Receiver report reads are narrowly transaction-bound and supply no human/project mutation authority.
- Tests include actual subprocess exits before/after prepare/consume commit and after sending claim, concurrent consume, a durable receiver-double action ledger, unknown-work retention, explicit audited break, IPv4/IPv6/DNS/TLS/redirect bounds and grant/log screening.
- Independent entry/security/final acceptance audits found no remaining blockers after corrections. Formal `bmad-code-review` is the next separate workflow.
- UI validation not applicable. Only generated API declarations changed; no rendered route, browser interaction, keyboard or accessibility behavior changed. Later target-settings UI remains its owning story.
- Qualification is scoped to local SQLite, controlled process recovery, typed ports and DNS/TCP/TLS/receiver doubles. Material/ref/delivery ports default unavailable. Real receiver HTTP/credential-carrier/durability, collector custody, host-power-loss and integrated remote exactly-once guarantees are not claimed;16.11 owns parent-run terminal reconciliation.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/16-10-registered-targets-outbox-grants-and-locks.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-30-story-16-10.md`
- `_bmad-output/project-context.md`
- `api/routes/infra_automation.py`
- `api/schemas.py`
- `config.py`
- `docs/infra-automation/handoff-contract-v1.md`
- `docs/verification/infra-automation/16-10/code-review-rerun-2026-11-02.md`
- `docs/verification/infra-automation/16-10/code-review.md`
- `docs/verification/infra-automation/16-10/r4-r5-resolution.md`
- `docs/verification/infra-automation/16-10/results.md`
- `frontend/src/api/schema.d.ts`
- `infra_automation/approval_eligibility.py`
- `infra_automation/claims.py`
- `infra_automation/handoff.py`
- `infra_automation/handoff_context.py`
- `infra_automation/lifecycle.py`
- `infra_automation/receiver_protocol.py`
- `infra_automation/run_resolution.py`
- `infra_automation/target_transport.py`
- `infra_automation/targets.py`
- `infra_automation/worker_supervision.py`
- `migrations/versions/035_add_infra_handoffs.py`
- `models/database.py`
- `models/repositories/infra_automation_handoffs.py`
- `models/repositories/infra_automation_targets.py`
- `models/tables.py`
- `services/content_security.py`
- `services/infra_automation_decisions.py`
- `services/infra_automation_engine_service.py`
- `services/infra_automation_handoffs.py`
- `services/infra_automation_targets.py`
- `services/project_service.py`
- `tests/test_api/test_infra_automation_handoffs.py`
- `tests/test_api/test_infra_automation_targets.py`
- `tests/test_api/test_infra_automation_workflows.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_identity_migration.py`
- `tests/test_infra/test_infra_automation_engine_migration.py`
- `tests/test_infra/test_infra_automation_handoff_migration.py`
- `tests/test_infra/test_infra_automation_workflow_migration.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_infra/test_project_membership_migration.py`
- `tests/test_infra_automation/lifecycle_support.py`
- `tests/test_infra_automation/test_decision_service.py`
- `tests/test_infra_automation/test_engine_recovery.py`
- `tests/test_infra_automation/test_engine_recovery_claims.py`
- `tests/test_infra_automation/test_engine_supervision.py`
- `tests/test_infra_automation/test_handoff_alias_references.py`
- `tests/test_infra_automation/test_handoff_process_recovery.py`
- `tests/test_infra_automation/test_handoff_report_context.py`
- `tests/test_infra_automation/test_handoff_secret_screening.py`
- `tests/test_infra_automation/test_handoff_service.py`
- `tests/test_infra_automation/test_preflight_repository.py`
- `tests/test_infra_automation/test_receiver_protocol.py`
- `tests/test_infra_automation/test_target_admission.py`
- `tests/test_infra_automation/test_target_capacity.py`
- `tests/test_infra_automation/test_target_contracts.py`
- `tests/test_infra_automation/test_target_persistence.py`
- `tests/test_infra_automation/test_target_references.py`
- `tests/test_infra_automation/test_target_service.py`
- `tests/test_infra_automation/test_target_transport.py`

## Change Log

- 2026-11-02: Resolve R4/R5/R6 with consistent material witnesses, future metadata reservations and bounded positive process-exit confirmation. All independent reviews and final Linux/production qualification passed. Mark scoped story done and proceed with authorized Git Flow closeout.

- 2026-11-02: Third three-layer review confirmed unchanged source and reproduced existing High R4 at all four boundaries; no new distinct finding. Keep story in-progress and R4 open.

- 2026-11-02: Fresh three-layer code review reproduced High R4: later graph material callbacks revoke previously checked selected custody yet admission succeeds. Return story/sprint to in-progress; retain prior fixes and completed verification evidence.

- 2026-11-02: Resolve R1/R2 with final material admission and audited durable action clock floors; add8 regressions, complete root/exact-shard/full-CI/production-image qualification, resolve R3 and reconcile all task/verification checklists. Story is ready for review.

- 2026-11-02: Formal BMad code review requested changes: live-custody callback race, unretained action-admission clock floor and incomplete broad verification evidence. Story remains in-progress; see review report.

- 2026-10-30: Implement registered canonical targets, precollection locks, immutable exact handoff/outbox/grant storage, scoped online consumption and pinned HTTPS policy; add crash/race/secret/quota qualification and owning contracts. Broad verification is running; review status remains gated on passing results.
