# Story 16.4: Scoped Workflows And Immutable Revisions

Status: done
Preparation: refined
Release: v1.5.0 — P0 highest-priority feature
Dependencies: 16.2, 16.3; public RFC and 16.0 qualification required

### Consumer contract amendment — 2026-10-13

Consume explicit `workflow_version: 2` from [workflow-contract-v2.md](../../docs/infra-automation/workflow-contract-v2.md) under the [approved course correction](../planning-artifacts/sprint-change-proposal-2026-10-13-workflow-v2.md). There is no nested version and no automatic conversion of historical v1 bytes or revisions. Preserve canonical revision/input digests with `tuple-json-utf8-v1` and the declared source/profile/environment constraints. A null definition workspace supports project-scoped drafts; the operation owner must resolve a concrete authorized workspace and bind it in the immutable run snapshot before any runner/receiver message. Independent runner/enrollment, receiver, provenance, state, error and cursor protocols stay v1; reports stay v2. Only receiver bindings directly carry workflow revision/input digests. Frozen v1 evidence remains unchanged history, and this amendment does not promote this story or claim implementation.

## Story

As a maintainer, I want to save scoped drafts and publish immutable revisions, so that draft edits and feature settings cannot silently change an active run or authorize disabled work.

## Acceptance Criteria

1. **AC1:** Given a project member with draft capability, when a valid draft is saved/validated, then it remains scoped to that project/workspace and nonexecutable; a cross-scope identifier or draft-run request is denied.
2. **AC2:** Given a verified human with reviewed publication capability, when a validated draft is published, then one immutable numbered revision with canonical content/digest is created atomically; changed published content and synthetic nonhuman publication are denied.
3. **AC3:** Given an archived workflow or an old revision, when an authorized restore is requested, then a new draft is created without rewriting published history; simultaneous publish with stale draft version returns conflict.
4. **AC4:** Given a published revision used through a run-snapshot consumer port, when its draft/policy is later edited, then the original revision, validated inputs and source variant remain unchanged; missing Git source is explicit for upload advisory, and collected/exact-plan source requires an immutable repository commit.
5. **AC5:** Given disable, revocation or restore epoch change before a claim/dispatch/grant consume, when a policy consumer checks live feature/epoch state, then unconsumed authority fails closed while read/reconciliation of already accepted/unknown work remains permitted.
6. **AC6:** Given authorized configuration or audit export, when limits/retention/credential floors change, then unsafe reductions are denied or invalidate affected pending authority before deletion; append-only screened events record verified actor/scope/reason/before-after digests and export contains no secrets.

### Requirement Traceability

Coverage intent: Delta over accepted v1.4.0; exact canonical requirement text/proof is preserved below. Shared IDs qualify only this owned slice; later mapped stories complete integration.

| Requirement | Contract owned or verified | Required acceptance proof |
| --- | --- | --- |
| IAU15-FR-014 | Scope workflow drafts and revisions to one project and optional workspace. | Workflow cross-scope CRUD tests |
| IAU15-FR-015 | Keep published revisions immutable; restore creates a new draft, and drafts cannot execute. | Publish/edit/restore/draft-run lifecycle tests |
| IAU15-FR-016 | Snapshot the published definition, validated inputs, scope and source identity immutably when a run starts; require a repository commit for collected/exact-plan paths and explicitly mark unavailable source for upload-only advisory review. | Post-start mutation and rerun snapshot tests |
| IAU15-FR-017 | Disable, revoke or restore epoch changes must invalidate unconsumed grants and prevent new run starts, collection claims, dispatch or grant consumption while preserving read and reconciliation for accepted external work. | Disable/revoke/restore-before-dispatch-or-consume race matrix |
| IAU15-FR-059 | Record append-only application audit events with verified principal/type, role, scope, target, reason, time and before/after digests; expose scoped UI/JSON export without raw artifacts/secrets and document DB-admin trust limits. | Audit event coverage/export authorization and secret corpus |
| IAU15-FR-060 | Let authorized operators configure feature enablement, targets, quotas, retention, TTL and credential lifetimes; reject unsafe reductions, protect pending evidence or invalidate its decision before deletion, and audit each change. | Configuration permissions, pending-retention and floor-change tests |

## Tasks / Subtasks and bounded work packets

Execute packets in listed dependency order; assign one named owner per packet and review its tests before widening scope. Shared files must accommodate concurrent edits; no global tracker or unrelated story change is authorized by a packet.

- [x] **Workflow persistence owner** (AC1/2/3/4)
  - [x] Owned write scope: `models/tables.py, models/repositories/infra_automation_workflows.py (new), next Alembic migration`.
  - [x] Create only scoped workflows/drafts and immutable revisions with unique (workflow_id, revision_number), content digest, optimistic draft version and archive state. Add scoped feature/authorization epoch and audit records only as required here; no run/runner/grant/outbox tables. Prove upgrade from synthetic v1.4.0 DB copy.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Service and HTTP owner** (AC1–4)
  - [x] Owned write scope: `services/infra_automation_service.py (new), api/routes/infra_automation.py (new), api/schemas.py, app.py`.
  - [x] Expose typed draft/validate/publish/archive/restore/revision reads using 16.2 membership and 16.3 validation, ApiRoute/ApiError/build_meta. Revalidate at publish; bind idempotency key to request digest. Stale/changed payload reuse yields conflict. Run start is not implemented here: qualify immutable snapshot export against a consumer port.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Feature/configuration policy owner** (AC5/6)
  - [x] Owned write scope: `config.py, services/settings_service.py, services/policy_adapter_settings.py, automation policy module (new)`.
  - [x] Add administrator-only enablement and scoped settings/floor validation; implement live epoch policy used by later claims/dispatch/consume. Use grant-consumer and pending-retention doubles to test race/invalidation semantics. Registered targets and real grants remain 16.10; restore procedures remain 16.18.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Audit and lifecycle proof owner** (AC1–6)
  - [x] Owned write scope: `tests/test_api, tests/test_services, tests/test_infra_automation, docs/infra-automation/workflows.md (new)`.
  - [x] Exercise project/workspace CRUD, concurrent publication, immutable restore, post-snapshot edits, disable-before-consume and history/reconciliation allowances with typed doubles. Publish audit export permission/secret tests and configuration migration/operator examples.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.

### Review Findings

- [x] [Review][Patch][P2] Measure the complete response envelope against the declared 128-KiB ceiling; the undocumented 130,000-byte detail ceiling rejects valid drafts whose complete response fits. [services/infra_automation_support.py:90]

- [x] [Review][Patch][P2][Re-review] Check the updated draft response before publication commits; version 9→10 must not turn a readable exact-limit workflow into a 429 response. [services/infra_automation_service.py:339]
- [x] [Review][Patch][P3][Re-review] Apply the complete response ceiling to settings reads, no-op updates and mutations inside their transaction, including configured metadata. [services/infra_automation_policy.py:28]

## Dev Notes

### Derived settings UX ownership

This earlier slice owns the feature/configuration or registered-target API and its permission/epoch/validation contracts. It does not depend on a later settings screen to complete: use service/API tests now. Story 16.18 Packet 18.6 explicitly owns the integrated `/settings` browser controls and composed acceptance using these earlier APIs; any backend-for-UI support remains additive in its own labeled PR.



Reuse models/database.py and repositories conventions, services/settings_service.py and policy_adapter_settings.py without mutating report scoring semantics. Allocate migration after inspecting current Alembic head, never assume a number. Existing role registry does not grant maintainer publication implicitly. Feature-off must keep permitted history/reconciliation, not erase unknown external work.

### Contracts and migration boundary

Draft API carries version/precondition and schema version; published row is append-only canonical content with digest. Snapshot port exports revision+typed inputs+scope+source variant rather than creating future run tables. Feature-state/epoch check is a shared deny policy; consumer doubles are acceptance evidence for policy only. Audit application APIs are append-only, not tamper-proof against a host/DB administrator.

Use the locked Python-first stack (SQLAlchemy/Alembic/Pydantic and existing libraries), opaque IDs and UTC timestamps. Inspect current migration head and freeze wire/schema fixtures before coding. Existing accepted story capabilities are reused; no full future automation schema, new runtime SDK, Node server or risk-engine fork.

### Acceptance and regression matrix

| Input/condition | Required result |
| --- | --- |
| Admin publishes valid draft; maintainer saves draft | Immutable revision versus nonexecutable draft |
| Wrong project/workspace; service credential publish | Generic denial and no revision creation |
| Concurrent publish/stale version/changed idempotent payload | Single revision or explicit conflict |
| Restore old revision; edit after snapshot export | New draft; old digest/snapshot preserved |
| Disable/epoch change before doubled consume | Authority denied; accepted-work reconciliation/read permitted |

## Implementation verification requirements

- [x] Add regression/contract tests with each packet; do not defer them to 16.19. Use temporary SQLite databases, TestClient and local synthetic fixtures; never real secrets/infrastructure state.
- [x] If adding `tests/test_infra_automation/`, register it in `scripts/ci-local.sh` and `.github/workflows/ci.yml` services pytest shard, and prove discovery includes it; root unittest discovery alone is insufficient.
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

Codex GPT-6. Root owns typed lifecycle contracts, service/HTTP, policy/snapshot integration and final verification. `s164_persistence` owns repository/tables/migration/bootstrap and packet tests; `s164_readiness` and `s164_contract_review` independently qualified the bounded design. Read-only auth/storage mapping informed reuse.

### Debug Log References

Baseline: merged Story16.3 at `ce4416d` (PR158), clean develop. Branch: `feature/16-4-scoped-workflow-revisions`. Scoped readiness report: `_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-14-story-16-4.md` (READY). Interface authority: `docs/infra-automation/workflow-lifecycle-contract-v1.md` and `tests/fixtures/infra_automation/workflow_lifecycle_v1/contract.json`; independent review resolved publication version/replay and archive/advisory-policy invalidation details before coding. No local application database is used.

### Completion Notes List

- Implemented scoped, nonexecutable workflow drafts and immutable numbered revisions with optimistic versions, atomic publication/audit and publisher/key request binding. Restore creates a new draft version; same-key replay after later edits returns the original revision. Publication, archive, restore and configuration remain verified scoped-human admin operations.
- Added migration `031_add_infra_workflows` with four entity families and13 database guards, including replacement protection; startup refuses partial/damaged schema. Synthetic028(v1.4.0) database-copy upgrade,030 upgrade, downgrade/reupgrade and preserved legacy data are verified.
- Added closed typed HTTP lifecycle endpoints, bounded JSON intake, fixed error-v1 mapping, success/error correlation IDs, `no-store`, validation diagnostics in data and signed bounded cursor pages. Lists filter actual scope before pagination and preserve an insertion snapshot across equal/backward timestamps.
- Added immutable snapshot exports for later run creation, including validated inputs, actual scope, resolved uploaded/collected sources and exact policy bytes. No run, runner, grant, outbox, collector or execution mechanism is installed.
- Added project-wide disabled-by-default policy, validated environment defaults, configuration floors and live epoch/membership/principal checks. Settings and advisory-policy changes invalidate prior authority atomically with audit; accepted/unknown work stays readable and retention-protected. Consumer doubles hold authorization, live checking and local mutation in the same reserved transaction.
- Reused existing identity/membership transactions, Pydantic/PyYAML validation, settings interpretation and credential screening. No dependency added; shared support helpers avoid duplicating canonicalization, scope and screening logic between lifecycle and policy modules.
- Independent contract/persistence/security/policy reviews found no remaining blocker. Full discovery exposed stale authorization exception identities after module reload and one old migration-list fixture; both were corrected with regression proof. Final contract checks also tightened Unicode labels, diagnostic vocabulary/length, correlation metadata and snapshot input-map schema closure.
- **UI validation not applicable**: no React surface, browser interaction or rendered settings/report behavior changed. The settings browser controls and real runtime integrations remain with their owning later stories.

### Development verification (before code-review correction)

All database/application checks ran in isolated checkouts or disposable containers, with synthetic `DATABASE_URL`; local `.env` and app data were excluded. Final documentation/schema/frozen-contract recheck: **66 tests and391 subtests passed**. Definition of Done: **PASS for this owned slice**.

| Command/check | Actual result |
| --- | --- |
| `bash scripts/ci-local.sh` | Passed all ten directories: **2,269 tests, two expected skips**; plus8 prompt-injection tests/96subtests, skill checks, dependency consistency, compilation and configured Bandit. |
| `./.venv/bin/python -m unittest discover -q` | Final source: **823 tests, OK (two skips)**. |
| `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` | **646 passed, one skipped, 2,176 subtests passed**. |
| `./.venv/bin/python -m pytest tests/test_services tests/test_infra_automation -v --tb=short` | Final source: **1,362 passed, 2,692 subtests passed**. |
| Production Python 3.11 unittest for all new lifecycle/API/migration modules | **85 tests, OK (one optional jsonschema skip)**. |
| `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `git diff --check` | Passed; **375 Python files** format-clean. |
| Scoped mypy over new domain/cursor/service/policy/snapshot/repository/route modules | Passed with missing third-party import stubs excluded. Whole-repository CI mypy remains nonblocking: baseline314/current313 errors, no new diagnostics. |
| Docker production build, health, migration and restart smoke | Passed; migration 031 and default disabled-profile403/no-store verified; all 15 runtime source files byte-match the image. |

Source/image identities and detailed qualification boundaries are in `docs/verification/infra-automation/16-4/`. Repository-wide constructor/fixture and migration-head searches were completed. Existing nonblocking type/stub debt and pre-existing Bandit warning remain unchanged. Full integrated runtime/receiver/retention-worker qualification remains later work. Story is ready for `bmad-code-review`; no commit, push or PR is performed by this dev-story workflow.

### File List

- `_bmad-output/implementation-artifacts/16-4-code-review-2026-10-14.md`
- `_bmad-output/implementation-artifacts/16-4-code-review-2026-10-19.md`
- `README.md`
- `_bmad-output/implementation-artifacts/16-4-scoped-workflows-and-immutable-revisions.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-14-story-16-4.md`
- `_bmad-output/project-context.md`
- `api/routes/infra_automation.py`
- `api/schemas.py`
- `app.py`
- `config.py`
- `docs/infra-automation/workflow-lifecycle-contract-v1.md`
- `docs/infra-automation/workflows.md`
- `docs/verification/infra-automation/16-4/README.md`
- `docs/verification/infra-automation/16-4/source-evidence.json`
- `infra_automation/lifecycle.py`
- `infra_automation/lifecycle_cursors.py`
- `migrations/versions/031_add_infra_workflows.py`
- `models/database.py`
- `models/repositories/infra_automation_workflows.py`
- `models/tables.py`
- `schemas/infra-automation/workflow-lifecycle-v1.json`
- `services/infra_automation_policy.py`
- `services/infra_automation_service.py`
- `services/infra_automation_snapshots.py`
- `services/infra_automation_support.py`
- `services/settings_service.py`
- `tests/fixtures/infra_automation/workflow_lifecycle_v1/contract.json`
- `tests/test_api/test_infra_automation_workflows.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_identity_migration.py`
- `tests/test_infra/test_infra_automation_workflow_migration.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_infra/test_project_membership_migration.py`
- `tests/test_infra_automation/lifecycle_support.py`
- `tests/test_infra_automation/test_lifecycle_contracts.py`
- `tests/test_infra_automation/test_lifecycle_cursors.py`
- `tests/test_infra_automation/test_workflow_lifecycle_service.py`
- `tests/test_infra_automation/test_workflow_policy.py`
- `tests/test_infra_automation/test_workflow_repository.py`
- `tests/test_infra_automation/test_workflow_snapshots.py`

### Packet evidence — execution history

These intermediate packet results are superseded by the completed final verification above.

- Persistence: `s164_persistence` ran 56 isolated repository/migration tests, including synthetic028 copy and030 upgrade, downgrade/reupgrade, partialschema failure, CAS and immutable SQL update/delete/replacement guards. Independent `s164_contract_review` found no blocking persistence defect.
- Typed lifecycle and cursor contracts: strict settings/preconditions/UTF-8 bounds and frozen schema parity; nine cursor tests cover signed context, expiry, restart, eviction and concurrency. `s164_cursors` returned completed implementation to root.
- Service/HTTP: root CRUD/contracts/cursor integration passed 25 tests/46subtests before the two added Unicode-label boundaries; `s164_http` passed 30 isolated auth/schema/HTTP tests/17subtests, with its policy integration test reserved for the next packet. Actual publication/replay/archive/restore/history paths pass.
- Snapshots: `s164_snapshots` passed 10 tests/17subtests, covering immutable definitions/inputs/policies, uploaded/collected/mixed sources, scope/profile/commit checks, nonhuman denial, corruption, membership and oversized-export rollback.
- Independent `s164_auth_map` reviewed the completed trust boundary and ran 38 tests/56subtests; no actionable security issue found. Its lone failing path reaches the not-yet-completed settings module, so policy remains pending. Corrected a documentation-only promise of latest revision metadata; history is exposed by the dedicated revision endpoints.


## Senior Developer Review (AI) — 2026-10-14

Outcome: **Approved; one P2 finding fixed, no unresolved findings.** Three fresh
independent layers reviewed the complete change: Blind Hunter, Edge Case Hunter
and Acceptance Auditor. Full findings, triage and regression evidence are in
[the review report](16-4-code-review-2026-10-14.md).

The review replaced arbitrary response headroom with exact shared-envelope sizing
inside the transaction. A valid large workflow now supports create/save/publish/read;
a 131,072-byte response succeeds and one byte more returns 429 with no workflow or
audit mutation. The regression failed before the fix and passed afterward. The
Acceptance Auditor independently approved the correction and contract clarification.

Post-fix verification, all isolated from local app data:

| Command/check | Result |
| --- | --- |
| `bash scripts/ci-local.sh` | **2,270 tests across ten directories**, two expected skips; prompt-injection/skill/dependency/compile/Ruff/Bandit gates passed. |
| `./.venv/bin/python -m unittest discover -q` | **824 tests, OK**, two expected skips. |
| `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` | **647 passed, one skipped, 2,176 subtests**. |
| Production Python 3.11 lifecycle/API/migration unittest | **86 tests, OK**, one optional jsonschema skip; host validator passed. |
| Root Ruff lint/format and `git diff --check` | Passed; 375 Python files format-clean. |
| Scoped mypy / whole-repository diagnostic comparison | Eight modules clean; existing repository debt baseline 314/current 312, no new diagnostic signatures. |
| Docker build/start/restart/migration/hash checks | Passed; current image and all 15 runtime source hashes recorded in the qualification packet. |

**UI validation not applicable.** No dependency, execution subsystem or UI was added
by the correction. Real runtime/receiver/retention-worker integration remains later
work. The story branch is `feature/16-4-scoped-workflow-revisions`; review closure
commits and pushes this branch and opens its PR to `develop`. The newer upstream
analytics-only commit `29a7310` does not overlap these files.

BMad Help next step: assess Story 16.5 readiness against the completed 16.4 ports
before promoting it from backlog; do not start its engine implementation here.

## Re-review closure — 2026-10-15

Outcome: **Approved; one P2 and one P3 corrected, no open findings.** Fresh Blind
Hunter, Edge Case Hunter and Acceptance Auditor layers reviewed the full branch
change. Publication now checks the updated draft before committing its version;
settings reads, no-op writes and mutations enforce the complete response ceiling
inside their transaction. Both fixes reuse existing checks and add rollback proofs,
with no new abstraction or dependency. Reporting reviewers independently approved
the corrections; see [the review report](16-4-code-review-2026-10-14.md).

| Verification | Result |
| --- | --- |
| `python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` | **648 passed, one skipped, 2,181 subtests**. |
| `python -m pytest tests/test_services tests/test_infra_automation -v --tb=short` | **1,362 passed, 2,692 subtests**. |
| `python -m unittest discover -q` | **825 tests, OK**, two expected skips. |
| Focused automation/API/migration pytest | **149 passed, 479 subtests**. |
| Production Python 3.11 lifecycle/API/migration unittest | **87 tests, OK**, one optional schema-validator skip. |
| Ruff lint/format, diff check, touched-module mypy and Bandit | Passed; 375 Python files format-clean. |
| Final documentation/schema/frozen-contract pytest | **66 passed, 391 subtests**. |
| Rebuilt Docker image, startup/restart, migration 031 and source hashes | Passed; all 15 runtime files match the recorded image. |

All application/DB checks used isolated synthetic databases and excluded local
`.env` and application data. Closure confirmed source hashes and test bytes still
match the checked revision after the interrupted session. The prior full local CI
run of 2,270 tests and hosted checks on `b2f8051` remain baseline evidence; both
affected shards and root/production suites above were rerun after these fixes.
The full local CI command was not repeated. Existing typing debt remains;
**UI validation not applicable**. Later engine/receiver/retention integration stays
with its owning stories. Story 16.4 remains **done** on the existing feature branch,
with corrections committed/pushed to PR #159 targeting `develop`.

## Re-review — 2026-10-19

Outcome: **Approved; no actionable findings.** Three fresh independent layers
reviewed the full 40-file branch diff through `136ea88`, including previous fixes:
Blind Hunter, Edge Case Hunter and Acceptance Auditor. All layers completed;
no patches, decisions, deferred issues or dismissed findings. See the
[review report](16-4-code-review-2026-10-19.md) for scope, verification and limitations.

Fresh isolated lifecycle/API/migration pytest: **149 passed, 479 subtests**.
Independent acceptance verification: **75 passed, 122 subtests**. Repo-wide Ruff
lint/format and diff checks passed; **375 Python files format-clean**. Hosted
PR #159 checks at the reviewed head are green, including both CI summaries,
API/CLI/infra and services shards, security/CodeQL, migrations and Docker.
Broader verification ran the API/CLI/infra shard (647 passed, one skip, 2,181
subtests, one Git-only environment failure) and root discovery (825 tests, two
skips, one Git-only failure and one Git-only error). After initializing private
Git metadata in the disposable checkout, both affected modules passed: **24 tests,
34 subtests**. Broad suites were not repeated after this environment-only repair.
No application code, dependency or simplification was needed. **UI validation
not applicable**. Later-owned runtime integration and existing typing debt remain
outside this review. Story/sprint stay **done** on the existing feature branch;
review documentation is delivered through existing PR #159 to `develop`.
BMad Help recommends scoped Story 16.5 implementation readiness in a fresh context.

## Change Log

- 2026-10-14: Closed scoped readiness and interface gates; implemented persistence, HTTP/service lifecycle, immutable snapshots, policy invalidation, audit and qualification. Completed all owned acceptance criteria and moved story/sprint to **review** on `feature/16-4-scoped-workflow-revisions`.

- 2026-10-14: Completed three-layer BMad review, corrected the complete-response byte boundary with red/green and rollback proof, reran all required gates, and moved story/sprint to **done**.

- 2026-10-15: Closed the re-review after verifying publication/readability and settings-envelope fixes, rollback regressions, both affected CI shards and production qualification; no findings remain open.

- 2026-10-19: Re-ran all three BMad review layers against the complete branch; no actionable findings. Recorded fresh verification and retained done status.
