# Story 16.5: Durable Engine And Fenced Recovery

Status: backlog
Preparation: refined
Release: v1.5.0 — P0 highest-priority feature
Dependencies: 16.4; public RFC and 16.0 qualification required

## Story

As an operator, I want to retain run progress, deadlines and ownership across crashes, so that overlapping workers cannot lose state or complete stale/duplicate work.

## Acceptance Criteria

1. **AC1:** Given a published revision and validated input/source variant, when a run is requested twice with the same scoped key and digest, then one immutable run snapshot exists; changed payload reuse conflicts and draft/missing collected-source requests fail.
2. **AC2:** Given each owned run/step transition, when the process crashes immediately before or after transaction commit, then restart recovers the committed state and audit exactly; gate stop, rejection, expiry, timeout, cancellation, failure, success and delivery_unknown remain distinct.
3. **AC3:** Given overlapping coordinators or reclaimed attempts, when the old owner heartbeats, logs, uploads or completes, then current epoch/lease/monotonic fence checks reject it; a unique atomic claim admits only the current owner.
4. **AC4:** Given slow analysis and other ready work, when coordinator ticks run, then analysis executes in a bounded off-loop worker with its own DB session and committed input/output links; the coordinator continues claiming work and failed workers cannot complete another attempt.
5. **AC5:** Given a retry-safe local failure within its deadline, when retry is requested, then a new fenced attempt reuses immutable inputs and idempotent outputs; exhausted/expired deadlines terminate and uncertain external outcomes are reconciliation-only, never blind resend.
6. **AC6:** Given cancellation racing completion or dispatch, when cancellation is committed, then the owned local process double and descendants terminate within the defined deadline and stale completion is rejected; accepted external work remains unknown/reconciliation-only rather than reported undone.
7. **AC7:** Given configured project/workflow backlog, analysis-worker and storage limits, when workload reaches or exceeds them, then admission/backpressure is explicit and state remains correct; scoped 1,000-transition overhead and 30-minute capacity runs record hardware/resources and qualify p95 <1 s with 10 active runs, at most 2 analysis workers and 20 synthetic online runner slots.

### Requirement Traceability

Coverage intent: Delta over accepted v1.4.0; exact canonical requirement text/proof is preserved below. Shared IDs qualify only this owned slice; later mapped stories complete integration.

| Requirement | Contract owned or verified | Required acceptance proof |
| --- | --- | --- |
| IAU15-FR-016 | Snapshot the published definition, validated inputs, scope and source identity immutably when a run starts; require a repository commit for collected/exact-plan paths and explicitly mark unavailable source for upload-only advisory review. | Post-start mutation and rerun snapshot tests |
| IAU15-FR-018 | Persist run/step transitions and explicit `stopped_by_gate`, `expired`, `timed_out`, `cancelled`, `failed`, `succeeded` and `delivery_unknown` outcomes across restart. | Crash at each transition with state recovery assertions |
| IAU15-FR-019 | Fence leader/task attempts so only the current owner may heartbeat, log, upload or complete a task. | Overlapping leader and stale-attempt rejection tests |
| IAU15-FR-020 | Retry only declared safe/idempotent local work within finite deadlines; persist idempotent outputs and reconcile uncertain external work instead of blind resend. | Retry/deadline/duplicate-completion and dropped-response tests |
| IAU15-FR-021 | Record cancellation durably and terminate the owned runner process tree; explain that cancellation cannot undo accepted external work. | Cancellation/dispatch races and process-tree termination tests |
| IAU15-FR-022 | Bound per-workflow/project concurrency, backlog, analysis workers and storage usage with explicit quota/backpressure errors. | Saturation, queue-cap and storage-exhaustion tests |
| IAU15-NFR-001 | The declared crash/race corpus must lose no committed run/decision state and produce no unauthorized or duplicate receiver action, including stale attempts, unknown delivery and restore epochs. | Published fault-injection results at every persisted boundary |
| IAU15-NFR-005 | Ready-step server orchestration overhead must have p95 <1 second, excluding collection/network/analysis duration, under the reproducible reference workload. | Timestamped 1,000-transition overhead benchmark |
| IAU15-NFR-007 | The singleton SQLite profile must sustain 10 active runs with at most 2 concurrent analysis jobs and 20 online runners, with bounded queue/storage and no corrupted transitions. | 30-minute capacity/saturation run with resource and error report |

## Tasks / Subtasks and bounded work packets

Execute packets in listed dependency order; assign one named owner per packet and review its tests before widening scope. Shared files must accommodate concurrent edits; no global tracker or unrelated story change is authorized by a packet.

- [ ] **Packet A — persistence/state owner; must merge first** (AC1/2)
  - [ ] Owned write scope: `infra_automation/state.py (new), models/tables.py, models/repositories/infra_automation_runs.py (new), next migration`.
  - [ ] Create only runs, step attempts, coordinator lease and request-idempotency records required by this engine; use 16.4 audit/epoch. Freeze transition/version enums and unique (run_id, step_id, attempt_number), scoped idempotency-key+digest constraints. Prove immutable source/input snapshots, full transition crash-before/after-commit matrix and v1.4 upgrade.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Packet B — atomic claim/recovery owner; after A** (AC2/3)
  - [ ] Owned write scope: `models/repositories/infra_automation_runs.py, infra_automation/claims.py (new)`.
  - [ ] Use short compare-and-update SQLite transactions checking state/version/epoch and unexpired lease; commit monotonic coordinator/attempt fencing before execution. Bind all worker writes to principal/project/run/step/attempt/fence. Test two connections/processes racing claims, restart overlap and all stale write classes. Never authorize solely from elapsed wall-clock lease.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Packet C — coordinator/worker owner; after B** (AC3/4)
  - [ ] Owned write scope: `infra_automation/coordinator.py and local_workers.py (new), services/infra_automation_service.py, app.py lifespan`.
  - [ ] Implement bounded tick and worker ports with separate database sessions. Register only supported local doubles/handlers available now; analyze_uploaded_files adapter is integrated in 16.6. Measure scheduler progress while blocking a worker; startup/shutdown must release ownership safely without performing collection in FastAPI.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Packet D — retries/output owner; after C** (AC2/5)
  - [ ] Owned write scope: `infra_automation/state.py, local_workers.py, repository output references`.
  - [ ] Persist safe-handler retry classification, finite total/attempt deadlines and atomic output link/idempotency. Retry creates new attempt, never reopens completed output. Model unknown external work via a typed adapter double that drops responses: assert reconciliation-only state, with no transport/resend implementation. Real outbox/receiver is 16.10/16.11.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Packet E — cancellation owner; after D** (AC3/6)
  - [ ] Owned write scope: `infra_automation/local_workers.py, coordinator.py, api/routes/infra_automation.py`.
  - [ ] Persist cancellation before signaling the owned worker double; terminate descendants and reject old attempt writes. Enumerate cancel-before-start, cancel-during-work, completion-race and hypothetical accepted/unknown dispatch races using local ports. Runner protocol/process-isolation proof remains 16.12–16.14.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Packet F — capacity/fault qualification owner; after E** (AC1–7)
  - [ ] Owned write scope: `tests/test_infra_automation, config.py, docs/infra-automation/engine.md (new), benchmark fixtures`.
  - [ ] Apply explicit project/workflow run/queue/byte limits and at most two local analysis workers. Exercise disk-full/queue-full/timeout/leader-overlap corpus, 1,000-transition timing and 30-minute reference capacity with 20 synthetic runner slots. Record commands/results/resources; these qualify only owned engine behavior, not real receiver/runner support. Independently review each packet before the next.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.

## Dev Notes

services/analysis_service.py analyze_uploaded_files is synchronous and must never execute inside coordinator tick. Use models/database.py sessions and existing audit/settings contracts; no new broker, control plane or distributed DB. Singleton SQLite still needs overlapping-generation fencing. Each packet has separate review and tests; story remains stable ID 16.5, with packet commits/PRs referencing its ACs rather than renumbering delivered stories.

### Contracts and migration boundary

Immutable RunSnapshot(source_variant, revision_digest, validated_inputs_digest, scope, input/source identity) plus transition-versioned run/attempt and monotonic fence. UTC deadlines and live epoch are checked at every write. Ports describe worker start/cancel/completion and uncertain external outcome only; no runner enrollment, approval/grant/outbox/receipt entity migration. Canonical audit and immutable report links are reused when integrated later.

Use the locked Python-first stack (SQLAlchemy/Alembic/Pydantic and existing libraries), opaque IDs and UTC timestamps. Inspect current migration head and freeze wire/schema fixtures before coding. Existing accepted story capabilities are reused; no full future automation schema, new runtime SDK, Node server or risk-engine fork.

### Acceptance and regression matrix

| Input/condition | Required result |
| --- | --- |
| Same key/digest start versus changed digest | One run versus conflict; immutable snapshot |
| Crash on both sides of each owned commit | Committed state/audit recovered; no invented completion |
| Old coordinator/attempt log/upload/complete | Fence rejection; new owner/output intact |
| Blocked worker plus ready coordinator work | Bounded off-loop execution; tick remains responsive |
| Dropped external response in port; cancel/completion race | delivery_unknown/reconcile-only; stale completion denied |
| 10 active runs/2 workers/20 synthetic slots; queue/disk saturation | Bounded state-correct admission; timestamped scope-limited benchmark |

## Implementation verification requirements

- [ ] Add regression/contract tests with each packet; do not defer them to 16.19. Use temporary SQLite databases, TestClient and local synthetic fixtures; never real secrets/infrastructure state.
- [ ] If adding `tests/test_infra_automation/`, register it in `scripts/ci-local.sh` and `.github/workflows/ci.yml` services pytest shard, and prove discovery includes it; root unittest discovery alone is insufficient.
- [ ] Search repository-wide direct instantiations/fixtures whenever changing a constructor/Pydantic/dataclass/API contract; run affected CI shard exactly: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` and/or `./.venv/bin/python -m pytest tests/test_services -v --tb=short`, plus explicitly registered automation tests.
- [ ] Before review run `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh` and `git diff --check`; record actual outputs and resolve failures.
- [ ] Keep this slice backend/contract scoped. Record **UI validation not applicable** if no rendered surface changes. If React/browser semantics change, use a separate labeled backend-for-UI PR where required, compose production build (`docker compose up -d --build`), wait for health, seed data and run `BASE_URL=http://localhost:8080 npm run test:ui-review` plus necessary a11y/keyboard/screenshots, then `docker compose down`. Root SPA routes only; Vite is not proof.
- [ ] Update version-matched operator/schema/API docs and story file list with the actual implementation. Layered code/security review must examine this slice's trust boundary; no new dependency without explicit approved decision.

## Readiness and advancement

Preparation means the work is decomposed, not authorized as implementation-ready. Keep **backlog** until public RFC acceptance (IR-01), executable 16.0 feasibility (IR-02), finalized owning interface/crypto/error fixtures (IR-03), earlier dependencies and packet estimates/ownership are recorded. Re-run implementation readiness before promotion; missing evidence cannot be waived by creating this file. Later 16.11/16.14/16.19 integration does not block owned slice acceptance, but remains required for supported production claims.

## References

- [Project context](../project-context.md#v150-infra-automation-planning-authority)
- [Canonical feature PRD](../planning-artifacts/prd-infra-automation.md)
- [Exact active requirement text/proof](../planning-artifacts/infra-automation-requirement-dispositions.json)
- [Epic 16](../planning-artifacts/epics.md#epic-16-evidence-gated-infrastructure-automation)
- [Architecture §25](../planning-artifacts/architecture.md#25-v150-infrastructure-automation-architecture-amendment)
- [Release plan](../planning-artifacts/infra-automation-v1.5.0-release-plan.md)
- [Readiness gates IR-01–04 and slice boundary IR-06](../planning-artifacts/implementation-readiness-report-2026-10-07-infra-automation-v1.5.0.md)
- [Feature UX](../../docs/design/infra-automation-ux.md)

## Dev Agent Record

### Agent Model Used

Story preparation only; implementation agent/model must be recorded when execution starts.

### Debug Log References

Not executed. No application, migration, test, browser, runner, receiver or benchmark result is claimed by this story preparation.

### Completion Notes List

Prepared implementation context and owned acceptance matrix on 2026-10-07. Governance/feasibility/interface gates remain open; Status is backlog.

### File List

This story file only. Planned write scopes above are prospective, not an implemented file list.
