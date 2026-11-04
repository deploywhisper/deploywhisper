# Story 16.12: Runner Enrollment and Attempt Protocol

Status: review
Preparation: refined
Release: v1.5.0

## Story

As a runner operator, I want to enroll and revoke an attempt-scoped outbound collection agent, so that only the current scoped agent can act on its task.

## Entry gates and slice boundary

- Release priority: P0 feature work for v1.5.0. **Blocked for implementation** until Story 16.0 has recorded public RFC/CODEOWNERS acceptance, executable identity/fencing/isolation/custody/receiver qualification and final interface decisions; planning adoption alone is not authorization evidence.
- Hard earlier dependencies: **16.2, 16.5**, accepted and verified before advancing this story. These dependency results are currently unresolved; refined preparation does not mean ready-for-dev. No prior implementation learning is available for the new Epic 16 story set.
- Promote only after contract freeze, earlier dependency evidence, bounded task ownership/re-estimation and independent story review. Preserve IDs and backlog status; no feature/release implementation is claimed here.

## Acceptance Criteria

1. **AC1:** Given an authenticated project administrator, when a bounded one-use enrollment credential is redeemed over supported HTTPS, then project-scoped expiring runner credentials are issued once, hashed at rest and protected from logs/audit; replay, rotation or revocation cannot reuse old authority.
2. **AC2:** Given wrong audience/project/runner/run/step/attempt/fence or expired lease, when claim/heartbeat/log/upload/complete occurs, then it is denied and cannot advance current work; concurrent claim/restart leaves one fenced owner.
3. **AC3:** Given required tag/tool/profile/version selection, when no eligible runner exists, then no silent fallback occurs and a clear denial or explicit finite wait/timeout is persisted.
4. **AC4:** Given disable/revoke/restore or expired tokens, when queued work is claimed or stale results arrive, then no new claims/results are accepted while authorized history/reconciliation remains accessible.
5. **AC5:** Given compatible runners, when scoped health is read, then last-seen/version/protocol/current task and status are screened and authorized; connectivity alone never certifies execution isolation.
6. **AC6:** Given the named 20-runner reference workload, when 1,000 claims are measured, then timestamped p95 enqueue-to-claim is below 2 seconds or qualification reports failure without advertising capacity.

### Requirement Traceability

Coverage intent: Delta over the v1.4.0 baseline. These exact mapped requirements are acceptance obligations; mapping is not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| IAU15-FR-019 | Fence leader/task attempts so only the current owner may heartbeat, log, upload or complete a task. | Overlapping leader and stale-attempt rejection tests |
| IAU15-FR-044 | Enroll runners using one-use tokens and project-scoped expiring credentials with rotation/revocation and outbound HTTPS protocol-version negotiation. | Enrollment replay/rotation/revocation/TLS/version tests |
| IAU15-FR-045 | Bind every task claim, heartbeat, log, upload and completion to the authorized runner, project, current attempt and live lease. | Wrong-runner/project/expired-lease matrix |
| IAU15-FR-046 | Route collection to eligible runner tags with no silent fallback; fail clearly when none qualify or enforce an explicit finite wait, and expose last-seen/version/task health. | No-runner/tag-mismatch/wait-timeout and health tests |
| IAU15-FR-059 | Record append-only application audit events with verified principal/type, role, scope, target, reason, time and before/after digests; expose scoped UI/JSON export without raw artifacts/secrets and document DB-admin trust limits. | Audit event coverage/export authorization and secret corpus |
| IAU15-NFR-002 | The declared principal × role × project/workspace × object/action matrix must produce zero cross-scope reads or unauthorized mutations. | Published complete authorization matrix results |
| IAU15-NFR-006 | Enqueue-to-claim latency must have p95 <2 seconds with 20 online compatible runners under the reference workload. | Timestamped 1,000-claim runner benchmark |

## Tasks / Subtasks and bounded ownership

- [x] **Packet 1 — Identity/API owner: enrollment lifecycle (AC 1,4).** Owned output: `infra_automation/runner/protocol.py, runner routes and scoped credential repositories (planned)`.
  - [x] One-use enrollment, audience/version negotiation, hashes/expiry/rotate/revoke, HTTPS validation and secret-free error/audit corpus.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 2 — Domain owner: fenced attempt operations (AC 2,4).** Owned output: `infra_automation/runner/claims.py (planned), earlier coordinator/repositories`.
  - [x] Bind all five task operations to runner/project/run/step/attempt/fence/live lease and epoch in short transactions; replay and overlapping-owner matrix.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 3 — Runner/service owner: outbound agent and routing (AC 3,5).** Owned output: `infra_automation/runner/client.py and CLI entrypoint (planned), config.py`.
  - [x] Bound HTTPS polling/backoff; enforce tags/tool/profile/version, finite no-runner wait and failure; scoped health endpoint without commands or credentials.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 4 — Test/documentation owner: authorization and benchmark (AC 1–6).** Owned output: `tests/test_infra_automation, tests/test_api/test_cli/test_infra, docs/infra-automation`.
  - [x] Publish full principal×role×scope×action matrix, stale attempt races and reproducible 1,000-claim timing workload with versions/hardware and results.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.

### Review Findings

- [x] [Review][Patch][P1][R1] Reject encoded live task/runner credentials before log/upload retention [`infra_automation/runner/claims.py:191`] — percent-encoded current task token was persisted; reuse existing sensitive-value encoding handling and add regression coverage.
- [x] [Review][Patch][P1][R2] Refresh authority after parsing/screening for every operation [`infra_automation/runner/claims.py:211`] — production-path heartbeat advanced durable sequence after a controlled parsing delay crossed lease expiry.
- [x] [Review][Patch][P2][R3] Separate live enrollment capacity from retained history [`services/infra_automation_runners.py:212`] — 100 revoked enrollments block all future enrollment with zero active runners.
- [x] [Review][Patch][P2][R4] Implement frozen runner-health list pagination [`api/routes/infra_automation_runner_admin.py:61`] — default25/max100 scoped snapshot cursors are absent; 26 rows returned and pagination parameters reject422.

Full findings, reproductions and verification: [BMad code review](../../docs/verification/infra-automation/16-12/code-review.md). The formal review superseded the earlier development-only clean conclusion. R1–R4 are now resolved by the verified [repair follow-up](../../docs/verification/infra-automation/16-12/review-fixes.md); the original findings are retained above for traceability.

Each packet is a bounded review unit under this stable story ID; split large packets after 16.0 estimation instead of silently broadening scope. One story branch follows Git Flow; coordinate shared-file edits and do not revert other work.

## Dev Notes

- runner_protocol_version 1, enrollment/credential audience, typed claim/task/heartbeat/log-cursor/artifact-upload/completion envelopes and redacted error/correlation shapes must freeze in 16.0. Never let server tasks carry arbitrary commands or infrastructure secret values.
- Add only runner enrollment/credential/attempt lease data required by this slice; reuse 16.5 run/attempt state and audit. Store token verifiers, not reusable plaintext. Credential reveal is transient once; future 16.15 UI owns enrollment screen and cannot make this backend story depend forward.
- Every request rechecks all binding dimensions and live fence/lease; authenticated runner identity alone is insufficient. No runner can publish/approve or obtain a human session. Existing api/dependencies.py is only a placeholder in baseline, not a verified authentication implementation.
- Use compatible runner/test client doubles to qualify protocol and 20-online-runner timing; production isolation is 16.13 and real collection is 16.14. Hash/authentication proves sender, not truthful collected evidence.
- Default off and restore epochs prevent new collection claims even for previously valid credentials; bounded upload is finalized atomically only after digest/attempt validation. Incomplete/truncated upload cannot qualify mandatory evidence.

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

### Agent Model Used

Codex primary agent with native implementation and independent review subagents; session 2026-11-04.

### Debug Log References

- Review repair validation (latest): root unittest — 1,636 tests, 3 skipped, OK; exact API/CLI/infra pytest shard — 734 passed, 1 skipped, 2,353 subtests; full `bash scripts/ci-local.sh` — exit0 with all ten directories passing (3,083 test executions) and no retries. Focused final suite — 82 passed, 617 subtests; independent repair review — 38 passed, 188 subtests. Final Ruff check/format (517 files), touched-code Bandit and diff check passed. Commands, regression coverage and limits are in the [repair record](../../docs/verification/infra-automation/16-12/review-fixes.md).

- Focused runner/API/migration command: `./.venv/bin/python -m pytest tests/test_infra_automation/test_runner_protocol.py tests/test_infra_automation/test_runner_client.py tests/test_infra_automation/test_runner_enrollment.py tests/test_infra_automation/test_runner_attempts.py tests/test_infra_automation/test_runner_authorization_matrix.py tests/test_infra_automation/test_runner_sensitive_defaults.py tests/test_api/test_infra_automation_runner.py tests/test_infra/test_runner_enrollment_migration.py -q` — 57 passed, 192 subtests.
- Final full principal × role × scope × administration-action matrix: `./.venv/bin/python -m pytest tests/test_infra_automation/test_runner_authorization_matrix.py -q` — 2 passed, 300 subtests; extends earlier focused-run coverage without runtime changes.
- Final wire-expiry repair: whole-second advertised deadlines are exclusive even when stored deadlines retain fractions; task/coordinator 42 tests / 141 subtests and enrollment/API 18 tests / 4 subtests passed.
- Final coordinator/callable-clock regression: 39 passed, 136 subtests. OpenAPI workflow regression: 15 passed, 16 subtests.
- `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .` (515 files), touched-code Bandit, compileall and `git diff --check` passed during integration; final repo-wide formatting and diff checks also passed after CI.
- Fresh isolated `python app.py` smoke: health HTTP200 and plaintext runner operation HTTP403; temporary database only.
- Exact `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` — 732 passed, 1 skipped, 2,353 subtests in 481.94s. `./.venv/bin/python -m unittest discover -q` — 1,612 tests passed, 3 skipped in 782.518s. `bash scripts/ci-local.sh`: lint/format/dependency/Bandit/compile/skill checks and analysis/API/CLI/docs/infra targets passed; automation target hit one receiver temporary lock-file failure. Its isolated 11-test runtime suite passed; full automation rerun passed 837 tests, 1 skipped in 404.785s. All 10 local CI test directories completed successfully across the original run and explicit continuation (3,063 test executions, with existing skips); the original script failure remains recorded. Remaining CI targets (`PYTHON_BIN=./.venv/bin/python bash scripts/run-test-targets.sh tests/test_llm tests/test_models tests/test_parsers tests/test_services`) passed 76/22/43/1,232 tests respectively. Initial runs exposed stale migration036 and no-runner OpenAPI assumptions; repaired and subsequently rerun. No initial failing run is counted as passing evidence.
- [Independent review and repairs](../../docs/verification/infra-automation/16-12/review.md), [authorization matrix](../../docs/verification/infra-automation/16-12/authorization-matrix.md), [benchmark qualification](../../docs/verification/infra-automation/16-12/qualification.md).

### Completion Notes List

- Latest review repair: R1–R4 resolved, all four action items checked, story returned to review. Reused the shared credential redactor, engine transaction boundaries and cursor infrastructure; no dependency or migration added. New tests reproduce the original failures before fixes and cover encoded audit reasons, fractional expiry during final checks, concurrent enrollment/rotation and snapshot pagination. UI validation not applicable. Fresh full local CI completed cleanly; previous development/review records below remain historical evidence.

- 2026-11-04 formal BMad code review: changes requested (two P1 and two P2 findings); status returned to in-progress. Prior completion claims below describe development verification, not current approval. Four patch follow-ups were left unchecked at that review and are now resolved.

- 2026-11-04 readiness reconciliation: independent review verified 16.0 accepted qualification/freeze, 16.2 final approval and 16.5 final 2026-10-27 approval. Earlier backlog dependency statements above are historical preparation notes, superseded by this evidence. Four bounded packets assigned and implemented on `feature/16-12-runner-enrollment-attempt-protocol`.
- Implemented one-use scoped enrollment, expiring hashed credentials, rotation/revocation, HTTPS machine routes, transient credential reveal, protected-file enrollment CLI and screened health. Machine credentials cannot become human sessions.
- Reused durable engine attempts, fencing, leases, live policy and quotas through runner bindings; no parallel engine. Added explicit no-eligible-runner failure, bounded transient assignment mailbox and remote coordinator ownership. Production profile mapping and collection handler remain unavailable by default.
- Preserved frozen enrollment/runner v1; strict scope/profile/capability/sequence checks, atomic screened digest-bound uploads, runner-attributed audit, stale owner/replay rejection, and generic errors. Finalization requires current upload reference even for failed completion under the frozen contract; failure before upload uses bounded cleanup/recovery.
- Independent review repairs cover post-lock clock freshness, credential leakage across accumulated log chunks/upload metadata, contextual HCL secrets, CLI consumed-grant loss, coordinator ownership and migration037 recognition. No unresolved actionable high-priority findings in final independent review.
- AC6 follows its explicit failure-reporting alternative: initial development Linux diagnostic completed 100 warmups / 1,000 claims / 20 processes with zero failures and p95 = 46.33 ms, stable source hashes, 4 CPU / 7 GiB. **Named reference capacity qualification failed/unqualified** (required 8 GiB / local SSD proof/HTTPS concurrent workload absent). No capacity or production isolation claim. Real isolation/collection and release qualification remain 16.13 / 16.14 / 16.19; 30-minute saturation remains later capacity qualification.
- Test discovery: `tests/test_infra_automation` was already registered in local CI and GitHub CI; no new test directory required registration. Repository-wide constructor/fixture searches updated current migration-head expectations and preserved historical migration references.
- UI validation not applicable: no rendered surface, browser interaction or accessibility semantics changed.
- Development verification complete; status is review. BMad help identifies `[CR] bmad-code-review` as the next workflow after development verification; this development pass does not claim Git Flow review/commit/push closure.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/16-12-runner-enrollment-and-attempt-protocol.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/project-context.md`
- `api/routes/infra_automation_runner.py`
- `api/routes/infra_automation_runner_admin.py`
- `app.py`
- `cli/runner.py`
- `docs/infra-automation/runner-protocol-v1.md`
- `docs/verification/infra-automation/16-12/authorization-matrix.md`
- `docs/verification/infra-automation/16-12/benchmark-linux.json`
- `docs/verification/infra-automation/16-12/benchmark-local.json`
- `docs/verification/infra-automation/16-12/code-review.md`
- `docs/verification/infra-automation/16-12/qualification.md`
- `docs/verification/infra-automation/16-12/review-fixes.md`
- `docs/verification/infra-automation/16-12/review.md`
- `infra_automation/coordinator.py`
- `infra_automation/runner/__init__.py`
- `infra_automation/runner/claims.py`
- `infra_automation/runner/client.py`
- `infra_automation/runner/protocol.py`
- `migrations/versions/037_add_runner_enrollment.py`
- `models/database.py`
- `models/repositories/infra_automation_runners.py`
- `models/tables.py`
- `scripts/benchmark_runner_protocol.py`
- `services/infra_automation_runner_tasks.py`
- `services/infra_automation_runners.py`
- `tests/test_api/test_infra_automation_runner.py`
- `tests/test_api/test_infra_automation_workflows.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_identity_migration.py`
- `tests/test_infra/test_infra_automation_engine_migration.py`
- `tests/test_infra/test_infra_automation_handoff_migration.py`
- `tests/test_infra/test_infra_automation_workflow_migration.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_infra/test_project_membership_migration.py`
- `tests/test_infra/test_receiver_reconciliation_migration.py`
- `tests/test_infra/test_runner_enrollment_migration.py`
- `tests/test_infra_automation/test_preflight_repository.py`
- `tests/test_infra_automation/test_runner_attempts.py`
- `tests/test_infra_automation/test_runner_authorization_matrix.py`
- `tests/test_infra_automation/test_runner_client.py`
- `tests/test_infra_automation/test_runner_enrollment.py`
- `tests/test_infra_automation/test_runner_health.py`
- `tests/test_infra_automation/test_runner_protocol.py`
- `tests/test_infra_automation/test_runner_review_security.py`
- `tests/test_infra_automation/test_runner_sensitive_defaults.py`

## Change Log

- 2026-11-04: Implemented runner enrollment/attempt protocol and independent review repairs; verification complete; ready for BMad code review.

- 2026-11-04: BMad layered code review reproduced four defects, added patch action items and returned story/sprint status to in-progress; no runtime edits or remote push.

- 2026-11-04: Resolved all four reviewer findings, added security/quota/pagination regressions and completed fresh full CI with exit0; story ready for re-review.
