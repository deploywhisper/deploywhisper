# Story 16.5: Durable Engine And Fenced Recovery

Status: done
Preparation: refined
Release: v1.5.0 — P0 highest-priority feature
Dependencies: 16.4; public RFC and 16.0 qualification required

### Consumer contract amendment — 2026-10-13

Consume explicit `workflow_version: 2` from [workflow-contract-v2.md](../../docs/infra-automation/workflow-contract-v2.md) under the [approved course correction](../planning-artifacts/sprint-change-proposal-2026-10-13-workflow-v2.md). There is no nested version and no automatic conversion of historical v1 bytes or revisions. Preserve canonical revision/input digests with `tuple-json-utf8-v1` and the declared source/profile/environment constraints. A null definition workspace supports project-scoped drafts; the operation owner must resolve a concrete authorized workspace and bind it in the immutable run snapshot before any runner/receiver message. Independent runner/enrollment, receiver, provenance, state, error and cursor protocols stay v1; reports stay v2. Only receiver bindings directly carry workflow revision/input digests. Frozen v1 evidence remains unchanged history, and this amendment does not promote this story or claim implementation.

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

- [x] **Packet A — persistence/state owner; must merge first** (AC1/2)
  - [x] Owned write scope: `infra_automation/state.py (new), models/tables.py, models/repositories/infra_automation_runs.py (new), next migration`.
  - [x] Create only runs, step attempts, coordinator lease and request-idempotency records required by this engine; use 16.4 audit/epoch. Freeze transition/version enums and unique (run_id, step_id, attempt_number), scoped idempotency-key+digest constraints. Prove immutable source/input snapshots, full transition crash-before/after-commit matrix and v1.4 upgrade.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Packet B — atomic claim/recovery owner; after A** (AC2/3)
  - [x] Owned write scope: `models/repositories/infra_automation_runs.py, infra_automation/claims.py (new)`.
  - [x] Use short compare-and-update SQLite transactions checking state/version/epoch and unexpired lease; commit monotonic coordinator/attempt fencing before execution. Bind all worker writes to principal/project/run/step/attempt/fence. Test two connections/processes racing claims, restart overlap and all stale write classes. Never authorize solely from elapsed wall-clock lease.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Packet C — coordinator/worker owner; after B** (AC3/4)
  - [x] Owned write scope: `infra_automation/coordinator.py and local_workers.py (new), services/infra_automation_service.py, app.py lifespan`.
  - [x] Implement bounded tick and worker ports with separate database sessions. Register only supported local doubles/handlers available now; analyze_uploaded_files adapter is integrated in 16.6. Measure scheduler progress while blocking a worker; startup/shutdown must release ownership safely without performing collection in FastAPI.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Packet D — retries/output owner; after C** (AC2/5)
  - [x] Owned write scope: `infra_automation/state.py, local_workers.py, repository output references`.
  - [x] Persist safe-handler retry classification, finite total/attempt deadlines and atomic output link/idempotency. Retry creates new attempt, never reopens completed output. Model unknown external work via a typed adapter double that drops responses: assert reconciliation-only state, with no transport/resend implementation. Real outbox/receiver is 16.10/16.11.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Packet E — cancellation owner; after D** (AC3/6)
  - [x] Owned write scope: `infra_automation/local_workers.py, coordinator.py, api/routes/infra_automation.py`.
  - [x] Persist cancellation before signaling the owned worker double; terminate descendants and reject old attempt writes. Enumerate cancel-before-start, cancel-during-work, completion-race and hypothetical accepted/unknown dispatch races using local ports. Runner protocol/process-isolation proof remains 16.12–16.14.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Packet F — capacity/fault qualification owner; after E** (AC1–7)
  - [x] Owned write scope: `tests/test_infra_automation, config.py, docs/infra-automation/engine.md (new), benchmark fixtures`.
  - [x] Apply explicit project/workflow run/queue/byte limits and at most two local analysis workers. Exercise disk-full/queue-full/timeout/leader-overlap corpus, 1,000-transition timing and 30-minute reference capacity with 20 synthetic runner slots. Record commands/results/resources; these qualify only owned engine behavior, not real receiver/runner support. Independently review each packet before the next.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.

### Review Findings

BMad code review of `3af659e..7bd80da` (2026-10-22): **request changes**.
Two high, two medium and one low finding; all are unambiguous patch follow-ups.
Full evidence and reproduction details: [16-5-code-review-2026-10-22.md](16-5-code-review-2026-10-22.md).
The previously recorded qualification remains evidence for its declared workload;
these additional reachable cases are not covered by that passing workload.

- [x] [Review][Patch][High][CR16.5-01] Prevent orphaned worker overlap after coordinator crash — real parent crash and lease takeover produced four simultaneously live handlers despite the two-worker bound; qualify cleanup/accounting and cancellation after restart [infra_automation/coordinator.py:511; infra_automation/local_workers.py:267].
- [x] [Review][Patch][High][CR16.5-02] Stop terminal sibling processes — a permanent sibling failure cancels the persisted attempt but never signals its owned worker, even after both deadlines [infra_automation/coordinator.py:364].
- [x] [Review][Patch][Medium][CR16.5-03] Advance bounded scheduler selection — repeated oldest-100 selection starves a later eligible workflow; add fair/advancing selection and a >100-row regression [infra_automation/coordinator.py:275].
- [x] [Review][Patch][Medium][CR16.5-04] Preserve retryable local persistence errors — output-storage 429 becomes permanent failure despite retry_safe=True; classify transient infrastructure/backpressure and verify finite retry/adoption [infra_automation/local_workers.py:213].
- [x] [Review][Patch][Low][CR16.5-05] Correct lease visibility guidance — public StepView exposes lease_until, contradicting the operator guide; distinguish public metadata from private capabilities [docs/infra-automation/engine.md:44; services/infra_automation_engine_service.py:297].

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

- [x] Add regression/contract tests with each packet; do not defer them to 16.19. Use temporary SQLite databases, TestClient and local synthetic fixtures; never real secrets/infrastructure state.
- [x] If adding `tests/test_infra_automation/`, register it in `scripts/ci-local.sh` and the dedicated `.github/workflows/ci.yml` infrastructure-automation pytest shard, and prove discovery includes it; root unittest discovery alone is insufficient.
- [x] Search repository-wide direct instantiations/fixtures whenever changing a constructor/Pydantic/dataclass/API contract; run affected CI shard exactly: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` and/or `./.venv/bin/python -m pytest tests/test_services -v --tb=short`, plus explicitly registered automation tests.
- [x] Before review run `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh` and `git diff --check`; record actual outputs and resolve failures.
- [x] Keep this slice backend/contract scoped. Record **UI validation not applicable** if no rendered surface changes. If React/browser semantics change, use a separate labeled backend-for-UI PR where required, compose production build (`docker compose up -d --build`), wait for health, seed data and run `BASE_URL=http://localhost:8080 npm run test:ui-review` plus necessary a11y/keyboard/screenshots, then `docker compose down`. Root SPA routes only; Vite is not proof.
- [x] Update version-matched operator/schema/API docs and story file list with the actual implementation. Layered code/security review must examine this slice's trust boundary; no new dependency without explicit approved decision.

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

Codex primary agent with native implementation/readiness/review agents; active worktree feature/16-5-durable-engine-fenced-recovery, baseline3af659e (merged16.4).

### Debug Log References

Scoped readiness completed in implementation-readiness-report-2026-10-19-story-16-5.md.
Engine contract and fixture independently reviewed before PacketA. No implementation
or benchmark acceptance is claimed by this initial entry.

### Completion Notes List

2026-10-19: Earlier governance/feasibility/dependency gates and scoped IR03 are
satisfied. Root owns service/HTTP, identity reservation, integration and qualification.
PacketA owner: s165_packet_a (state/persistence/migration); independent reviewer
assigned after tests. Later B→F owners will be recorded before their packets start.
Each packet integrates into this story branch with its own tests/review/commit.
UI validation not applicable unless a rendered surface is changed.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/16-5-code-review-2026-10-22.md`
- `_bmad-output/implementation-artifacts/16-5-durable-engine-and-fenced-recovery.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-19-story-16-5.md`
- `api/routes/infra_automation.py`
- `api/schemas.py`
- `app.py`
- `config.py`
- `docs/infra-automation/engine-contract-v1.md`
- `docs/infra-automation/engine.md`
- `docs/verification/infra-automation/16-5/benchmark.json.gz`
- `docs/verification/infra-automation/16-5/capacity.json.gz`
- `docs/verification/infra-automation/16-5/faults.json.gz`
- `docs/verification/infra-automation/16-5/local-validation.md`
- `docs/verification/infra-automation/16-5/qualification.md`
- `docs/verification/infra-automation/16-5/reference-results.json`
- `docs/verification/infra-automation/16-5/results.md`
- `docs/verification/infra-automation/16-5/review-fixes/benchmark.json.gz`
- `docs/verification/infra-automation/16-5/review-fixes/capacity.json.gz`
- `docs/verification/infra-automation/16-5/review-fixes/faults.json.gz`
- `docs/verification/infra-automation/16-5/review-fixes/process.json`
- `docs/verification/infra-automation/16-5/review-fixes/process.log`
- `docs/verification/infra-automation/16-5/review-fixes/reference-results.json`
- `docs/verification/infra-automation/16-5/review-fixes/results.md`
- `docs/verification/infra-automation/16-5/review-fixes/runtime-smoke.json`
- `docs/verification/infra-automation/16-5/review-fixes/source-provenance.json`
- `docs/verification/infra-automation/16-5/review-fixes/test-dependency-manifest.json`
- `docs/verification/infra-automation/16-5/review-fixes/verification-summary.json`
- `infra_automation/claims.py`
- `infra_automation/coordinator.py`
- `infra_automation/local_workers.py`
- `infra_automation/state.py`
- `infra_automation/storage.py`
- `infra_automation/worker_failures.py`
- `infra_automation/worker_supervision.py`
- `migrations/versions/032_add_infra_automation_engine.py`
- `models/database.py`
- `models/repositories/infra_automation_runs.py`
- `models/tables.py`
- `schemas/infra-automation/engine-v1.json`
- `services/infra_automation_engine_service.py`
- `services/infra_automation_engine_support.py`
- `services/infra_automation_policy.py`
- `services/infra_automation_service.py`
- `tests/fixtures/infra_automation/engine_v1/contract.json`
- `tests/fixtures/infra_automation/engine_v1/qualification.py`
- `tests/test_api/test_infra_automation_engine.py`
- `tests/test_api/test_infra_automation_workflows.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_identity_migration.py`
- `tests/test_infra/test_infra_automation_engine_migration.py`
- `tests/test_infra/test_infra_automation_workflow_migration.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_infra/test_project_membership_migration.py`
- `tests/test_infra_automation/test_engine_app_lifespan.py`
- `tests/test_infra_automation/test_engine_cancel_service.py`
- `tests/test_infra_automation/test_engine_cancellation.py`
- `tests/test_infra_automation/test_engine_claims.py`
- `tests/test_infra_automation/test_engine_coordinator.py`
- `tests/test_infra_automation/test_engine_identity.py`
- `tests/test_infra_automation/test_engine_limits.py`
- `tests/test_infra_automation/test_engine_owner_liveness.py`
- `tests/test_infra_automation/test_engine_parent_recovery.py`
- `tests/test_infra_automation/test_engine_qualification.py`
- `tests/test_infra_automation/test_engine_recovery.py`
- `tests/test_infra_automation/test_engine_recovery_claims.py`
- `tests/test_infra_automation/test_engine_repository.py`
- `tests/test_infra_automation/test_engine_review_scheduler.py`
- `tests/test_infra_automation/test_engine_service.py`
- `tests/test_infra_automation/test_engine_state.py`
- `tests/test_infra_automation/test_engine_supervision.py`
- `tests/test_infra_automation/test_engine_worker_failures.py`
- `tests/test_infra_automation/test_engine_workers.py`

### Packet A evidence — 2026-10-19

Implemented state/persistence/migration and non-login audit support. Initial absent
state/helper tests were red, then passed. Boundary tests found and fixed an actual
SQLite legacy savepoint implicit-commit trap by reserving a physical transaction
before nesting. All declared run/attempt edges have commit/rollback/reopen assertions;
real process fault qualification remains PacketF and no full-story acceptance is
claimed here. Immutable SQL guards, exact snapshot binding, typed output consistency,
scoped FKs, partial-schema/history rejection and copied synthetic028 upgrade pass.
Migration leaves identity_accounts empty; service audit account is lazy and non-login.

Independent s165_packet_a_review approved frozen code:36tests/182subtests,3optional
skips. Whole automation+infra regression:415passed,4skipped,2561subtests. Focused
engine state/repository:14passed. Root identity support:4passed. Ruff lint/format,
Bandit and diff checks pass (383Pythonfiles format-clean). PacketA code integrates
into story branch before B. All story acceptance checkboxes stay pending final
qualification; no UI changed and UI validation not applicable.

PacketB owner:s165_packet_b; root owns service/HTTP/coordinator integration and
qualification. B may begin after this reviewed packet commit.

### Packet B evidence — 2026-10-19

Owner:s165_packet_b; independent reviewer:s165_packet_a_review. Current coordinator
and unique per-attempt secrets authenticate separately from public stamp fields.
Claim/start/heartbeat/log/upload/output/complete check exact scope, generation,
fence, leases, finite deadlines and current authority under one operation transaction.
Safety-only cleanup/stop retains current coordinator authentication while allowing
revoked/expired work to stop without accepting new outputs. Trusted finish_run
checks current policy and committed required outputs.

Review found two storage defects and both were corrected: evidence growth now
charges exact persisted UTF8JSON bytes with atomic run-version/audit updates, and
unknown/corrupt counters in another retained run cause503 rather than being ignored
by SQLite SUM. Project/global caps include terminal/unknown rows. Replays charge
zero. Initial attempt creation charges4empty-arraybytes; D must preserve that charge
when adding retry/adoption. Payload measure excludes fixed ORM/audit overhead;
physical-disk checks/qualification remain F.

Final automation pytest:165passed,3optional-skips,536subtests. Bfocused:20tests and
75subtests, including spawned-process claims, sibling forgery, stale writes, epoch/
clock/restart/dependency/quotas and transaction-boundary rollback/reopen. Independent
combined A/B review:33tests/122subtests; final finish_run delta1test passed. Ruff
lint/format and diffcheck passed (385Pythonfiles). Actualprocess fault/capacity
qualification and full-story acceptance remain pending.

PacketC owner:s165_packet_c for coordinator/local_workers and dedicated tests; root
owns service admission/read integration and app wiring. No rendered UI changes.

### Packet C evidence — 2026-10-19

Owner:s165_packet_c for coordinator/local_workers; root for human admission/read
service and app lifespan. Trusted registry defaults empty; handler input contains
only immutable snapshot/prerequisite bytes. A child receives only its own attempt
capability, opens fresh guarded SQLite sessions and commits typed upload/output
references before parent completion. Parent binds pipe results to its original
handle. At most2spawned processes/no pending executor queue; short ticks run off
the event loop and claims commit before spawning. UTC is sampled after transaction
acquisition to avoid cross-process false rollback detection.

Human admission tests prove same-key concurrent deduplication, changed-payload
conflict, exact immutable snapshots, replay after disable/edit without recapture,
live scope, no-credential denial, project/workflow queue caps, byte/response
rollback and draft-ID denial. Lifespan has no engine effects for empty registry;
configured startup/shutdown and failed-start cleanup are covered.

Cowned tests:17passed/47subtests. Rootservice/lifespan:11passed. Independent
s165_packet_c_review:28passed/47subtests; approved all Cfiles. Final automation
regression:193passed,3optional-skips,583subtests. Ruff lint/format,Bandit,diff
checks pass (392Pythonfiles).

Dmust add safe finite retry/output adoption, orphan recovery and cached-owner reset
after lease loss; no-output handoff registrations require the D typed external
uncertainty port before execution. Actual descendant-cancel, process-fault and
30-minute capacity qualification remain E/F. No full-story acceptance is claimed.

### Packet D evidence — 2026-10-19

Owners:s165_packet_b claims helpers; s165_packet_c coordinator/worker integration.
Retries create at most3fresh fenced attempts only for declared-safe local failures
within immutable run/evidence deadlines; permanent failures stop after1. A successor
adopts an existing committed typed output before handler invocation without changing
the old output. External test doubles commit handing_off intent before invocation;
actual spawned acceptance followed by os._exit/noresponse becomes delivery_unknown,
and restart never resends. No real transport/receiver/grant is supplied.

Fault review found known permanent outcomes could retry after a result-persistence
failure; corrected with at-most-worker-count pending completion receipts and slot
backpressure until the exact result transaction commits. Lost ownership discards
old-generation receipts/children. Gate/rejection/permanent meanings survive stop/
audit faults, while stale results cannot become current. Evidence-horizon expiry
remains expired, distinct from earlier timeout. Owner loss resets cached authority
and permits later fresh generation acquisition.

Run admission is independent of worker slots:10active across2workflows,2attempts
executing,11thrunqueued under active quotas. Attempts are only created for ready
work when a worker slot is available.

Independent claims review:29tests/75subtests. Independent worker/coordinator review:
53tests/94subtests, plus3final admission-delta tests; both approved. Full working-tree
automation regression:232passed,3optional-skips,630subtests. Ruff lint/format,
Bandit,diff checks pass. Read/API compatibility groundwork is tracked separately
with E. Cancellation and real process/capacity qualification remain pending.

PacketE:s165_packet_c owns process-group cancellation/control tests; root owns
human cancellation service, typed HTTP resources, compatibility and app callback.


### Packets E/F completion evidence — 2026-10-22

All packets A–F are implemented, independently reviewed and verified. Owners:
root service/API/app/integration; s165_packet_c runtime cancellation and limits;
s165_packet_b claims/storage/configuration; s165_qualification fault/capacity harness.
Independent reviewers s165_packet_a_review, s165_packet_c_review and s165_readiness
approved their bounded reviews. Core packet commits: A dfd4927; B 44f3808;
C 727fdeb; D d7a3a08; E 1fb5a19; F 1661a94; harness correction cc27c6f.
Earlier packet entries above are historical milestones; all pending E/F proofs
mentioned there are completed by this final evidence.

E commits human cancellation flag, scoped owner/admin authority, audit, replay
binding and local termination state before signaling. Identical retries are
idempotent; changed/stale bindings conflict. Signals execute only after the outer
transaction commits. Rollback/response overflow cannot signal. Worker groups and
SIGTERM-ignoring descendants terminate within five seconds; unconfirmed cleanup
retains ownership/slots. Tick recovery catches lost callbacks. Stale evidence
writes fail; accepted external work remains delivery_unknown, without resend.
Closed human-only run/detail/steps/log/cancel API routes preserve current scoped
read authority, CSRF, signed snapshot cursors and fixed bounded error envelopes.

F adds strict trusted ceilings, global backlog/storage caps, physical disk reserve,
quota-reduction guards and explicit installed-only SQLite WAL/FULL. Real engine
SQLITE_FULL tests prove transaction/audit rollback and safe retry. No new dependency
or runtime transport was introduced. Reuse of the existing authorization, audit,
signed cursor and immutable output contracts avoids a parallel control plane.

Final Linux evidence: 128 actual process-exit cases; 1,000 real ready-step samples
with p95 0.014543958 seconds; 1,800.102835 real seconds with 10 active runs in all
6,502 samples, <=2 analysis workers, 20 synthetic online slots, zero engine errors,
explicit queue backpressure and stale/forged-owner denials. Source hashes remained
identical. The initial unqualified capacity attempt exposed synthetic human-session
idleness; legitimate periodic authorized reads fixed the fixture and all phases
were rerun. Runtime identity policy is unchanged.

Exact commands, hardware/resources, checksums, raw compressed artifacts, scope
limitations and AC proof are recorded in
`docs/verification/infra-automation/16-5/results.md` and `reference-results.json`.
Final verification: root unittest 1,002 tests/5 skips; every-directory ci-local
passed; exact API/CLI/infra pytest 660 passed/1 skip/2,200 subtests; exact services+
automation pytest 1,524 passed/3 skips/3,017 subtests; Ruff lint/401-file format and
diff checks passed; scoped engine/repository mypy clean, full scope has 313 existing
diagnostics vs314 baseline and no new diagnostics. Bandit high gate passed with
only unchanged baseline B104 sample-IP comparison finding. Production image build,
startup and restart passed migration032/integrity/healthyAPI and empty-registry
zero-engine-identity/lease checks. UI validation not applicable.

Remaining scope: production registry deliberately empty; actual analysis adapter
is Story16.6 and real runner/receiver/transport/host-power-loss support is outside
this proof. BMad Help routes the completed development story to `bmad-code-review`
in a fresh context. Status is review; this is not a release or merge claim.

### Change Log

- 2026-10-19: Scoped readiness and contracts frozen; packets A–E implemented and reviewed.
- 2026-10-22: Packet F limits, real fault/overhead/capacity evidence and validation completed; story moved to review.
- 2026-10-22: BMad code review reproduced four functional gaps and one documentation discrepancy; five follow-ups recorded and story returned to in-progress.
- 2026-10-23: All five follow-ups fixed, hardened and independently audited; fresh runtime qualification and full current-fixture verification passed; story returned to review.
- 2026-10-27: Three-layer BMad code review rerun approved the repaired implementation; 365 tests and 885 subtests passed, with no actionable findings. Story moved to done.

### Code review outcome — 2026-10-22

Three independent BMad layers completed and root verified candidates with synthetic
reproductions. Review outcome: request changes; five follow-ups recorded above,
no production fixes applied by the review. Focused regression passed 67 tests and
156 subtests, but the new crash/process-lifetime, fairness and transient failure
cases remain open. Story/sprint returned to in-progress. Remote push was not
performed because review follow-up remains open. PR159 and the original checkout
were untouched. Next: bmad-dev-story for follow-ups, then bmad-code-review.

### Review follow-up implementation plan

Resume CR16.5-01–05 on the existing feature branch. Owners: root worker-port
integration, actual parent-death/takeover regression, documentation and qualification;
s165_fix_arch supervision foundation; s165_fix_coord terminal cleanup and fair
candidate sweeps; s165_fix_retry explicit infrastructure error classification;
s165_fix_review independent verification. No new dependencies or ORM families.

Use a gated execution process with an independent supervisor, creator-liveness
pipe, stable global file slots and dirty-slot fail-closed accounting. Keep the
leader unreaped until the whole group stops. Clean terminal siblings regardless
of the run's cancellation flag. Use bounded candidate pages with a frozen sweep
ceiling and project/workflow interleaving. Classify transient storage only inside
wrapper-owned setup/read/write boundaries; never infer retry authority from a
handler exception. Correct public lease metadata guidance.

Lock each review defect with a failing regression before applying its fix, then
run process-tree cancellation, actual coordinator crash and real lease takeover,
slot reuse/dirty-state/configuration reduction, >100-row deadline/fairness, and
transient retry/adoption/exhaustion proofs. Independently review the repaired
source, freeze it, and rerun full CI plus real Linux fault/1,000-transition/
1,800-second capacity qualification. Keep review findings unchecked until all
required evidence completes. UI validation not applicable.

### Validation hardening — 2026-10-23

Broad validation exposed a cold-start shutdown confirmation budget shorter than
the five-second owned cancellation contract, and a one-second test attempt that
could expire before the added supervision bootstrap. Shutdown now signals every
matching guardian first and shares a4.5-second confirmation deadline. The expiry
regression waits for the actual persisted five-second test deadline after proving
its handler ran; it no longer assumes one-second process startup.

Independent review also reproduced a live but stalled creator retaining its open
pipe across lease takeover and cancellation. Guardians now require finite3-second
monotonic keepalives bounded by current lease expiry. Every pulse follows explicit
private-owner validation and committed transaction, including the cached<10s
renewal path; rollback or stale generation cannot extend execution. Tests prove
expiry without EOF while the creator stays alive, actual31-second takeover and
cancellation, stale/cached pulse rejection and group/slot cleanup.

Targeted validation:56 cancellation/recovery/expiry tests plus103subtests;21 real
parent-death/stall/takeover and supervision tests;4 SQLite pulse-authority tests.
The earlier parallel run was invalidated by host/VM suspend (82-minute UTC gap)
and qualified evidence is being rerun with an active temporary sleep assertion.
A subsequent awake run identified the confirmed cold-start/fixture issues above;
its incomplete metrics are also excluded. All review items remain unchecked until
fresh full regression and reference qualification finish on the final source.


### Review findings resolved and verified — 2026-10-23

All CR16.5-01–05 are resolved by runtime commits7bf930a/fbb638c and test-fixture
commit570e7ec. Independent source review and artifact audit found no remaining
blocker. Root owns integration/evidence; native bounded owners implemented and
cross-reviewed supervision, scheduler and infrastructure classification slices.

- Resolved [High] CR01: independent gated global-slot supervisors plus finite
  lease-bounded current-owner pulses stop crashed OR live-stalled creator trees.
  All stop requests precede a shared4.5-second confirmation budget. Real parent
  death, stalled creator, descendant cleanup,31-second takeover/cancellation,
  dirty slots, reduced capacity, stale pulses and rollback are verified.
- Resolved [High] CR02: terminal/missing run/attempt ownership stops live siblings
  and retains the slot until cleanup is confirmed; real handler PID and reuse proven.
- Resolved [Medium] CR03: bounded advancing pages with a fixed sweep tail and
  project/workflow interleaving progress beyond100rows despite ongoing arrivals.
- Resolved [Medium] CR04: explicit wrapper setup/read/write infrastructure scope
  retries only declared-safe capacity429/SQLite BUSY,LOCKED,FULL. Handler and
  authority failures remain permanent; external uncertainty remains no-resend;
  immutable output adoption and three-attempt exhaustion pass.
- Resolved [Low] CR05: operator guide distinguishes public lease/fence/generation
  metadata from private ownership capabilities. Existing auth/audit/cursor/state
  contracts are reused, without new dependencies or domain persistence families.

Fresh repaired-runtime qualification atfbb638c:128 actual process-exit cases with
exact restart/audit recovery;1,000 dispatch samples p95=0.019121375seconds;
1,800.124686 real monotonic seconds,6,362 samples all10active with<=2workers and
20synthetic slots,zero errors,queue429and119private-owner denials. Source136hashes
were identical at start/end. Production startup/restart passed health,migration032,
integrity and empty-registry zero identity/lease/slot side effects.

The later test-only570e7ec correction waits for durable successful runs across
allowed retry history and gives five cold serial supervised stages30seconds.
Actual execution/cancellation deadlines were unchanged. All production, harness,
contract,migration and used fixture bytes remain exactlyfbb638c; exactly3unused
test modules differ (133/136 total qualified entries match). Independent static,
dynamic-import and hash audits establish this explicit provenance. Reference
artifacts are retained unchanged, not falsely relabeled as current136-map matches.

Current-fixture full Linux runtime automation:354tests,zero failures/errors,3optional
JSON Schema validator skips,329.510seconds;136current hashes start=end. The already
locked test-onlytomli2.5.0 pure Python files were supplied read-only and verified
against distribution RECORD; project dependency files were unchanged.

Final current-fixture native verification: `bash scripts/ci-local.sh` all10test
directories passed (automation354,services1232); root unittest1062 OK5skips; exact
services/automation pytest1583passed3skips3084subtests. Exact API/CLI/infra pytest
660passed1skip2200subtests passed on byte-identical production/test scope; current
CI reran allthree directories. Ruff lint and repo-wide408-file formatting, scoped
mypy and diff checks passed. Full mypy313baseline diagnostics vs314beforethisstory,
none new. Bandit high gate passed; only unchanged B104sample-IP comparison remains.
UI validation not applicable. Existing application containers/original Epic17
checkout/PR159 were untouched; all16owned test containers removed after evidence.

Final command summaries, original raw/compressed data, checksums, runtime test log,
source equivalence, pinned test-dependency evidence and independent audit are in
`docs/verification/infra-automation/16-5/review-fixes/results.md` and accompanying
`verification-summary.json`. Remaining intentional scope: empty production handler
registry until16.6; real runner/receiver/transport and host-power-loss support are
not qualified. Unexpected supervisor failure retains dirty capacity for trusted
operator recovery. Story returns to review for the next BMad code-review cycle.

### Code review rerun outcome — 2026-10-27

Approved the full `3af659e..5e9a3b3` story diff with all three independent BMad
review layers complete. No decision-needed or patch findings remain;
two candidates were dismissed after validation. CR16.5-01–05 remain resolved.
Fresh automation/API/migration pytest:365 passed,885 subtests passed; Ruff lint
and repository-wide408-file formatting passed. Independent acceptance checks
also passed59tests/67subtests and recomputed published qualification evidence.
No production changes; UI validation not applicable. Existing Linux/full-CI
evidence was audited rather than rerun. Native tests used installed Python3.14.
Full scope, commands, triage and remaining limitations are in
[16-5-code-review-2026-10-27.md](16-5-code-review-2026-10-27.md).
Story status is done. BMad Help routes next to scoped Story16.6 readiness;
later-story backlog and production integration/release gates remain unchanged.

- [x] [Review][Defer][High] Inherited Vite 8.0.16 fails the remote frontend npm
  audit gate [frontend/package-lock.json:2072] — deferred, pre-existing;
  frontend dependency files are unchanged from baseline3af659e. Dependency
  maintenance must resolve this before merging PR195. See the rerun report and
  `deferred-work.md`; no audit suppression or dependency change was applied.

### CI follow-up hardening — 2026-10-27

The dependency repair is supplied by maintenance PR197 and carried onto this
branch, preserving the automatic-update pause. Once audits passed, hosted CI
exposed a test-observer race: `/proc/<pid>/stat` may raise ProcessLookupError
when the observed process exits. A deterministic red/green regression now covers
that race, missing entries, zombies, running processes and visible permission
errors. The helper treats an exited process as stopped; actual five-second
process-tree cancellation assertions remain unchanged.

Linux verification also exposed a legitimate optimistic-version conflict in the
takeover fixture: worker evidence can advance a run between its version read
and cancellation. The two takeover tests now read and request cancellation in
the same authorized operation transaction, with process signaling still deferred
until commit. Production authorization and stale-version rejection are unchanged.

The combined services/automation coverage job reached its15-minute limit with
the expanded engine suite still running. Dedicated services and automation
matrix rows retain the original15-minute budget and execute every test. Updated
configuration coverage guards this split. These are verification corrections;
engine runtime behavior and the scope of historical qualification remain intact.

The older16.0 SQLite race test also exposed expected bounded SQLITE_BUSY denial
as an unreported child result under coverage. Its test-local spawned adapter now
reports that no-claim outcome as a loser, while exactly-one-winner/attempt checks
and unexpected-error visibility remain enforced. The frozen prototype bytes are
unchanged. Deterministic backpressure coverage was red before the adapter and
green afterward;13real Linux qualification tests passed.
