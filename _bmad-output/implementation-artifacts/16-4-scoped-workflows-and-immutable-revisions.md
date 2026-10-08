# Story 16.4: Scoped Workflows And Immutable Revisions

Status: backlog
Preparation: refined
Release: v1.5.0 — P0 highest-priority feature
Dependencies: 16.2, 16.3; public RFC and 16.0 qualification required

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

- [ ] **Workflow persistence owner** (AC1/2/3/4)
  - [ ] Owned write scope: `models/tables.py, models/repositories/infra_automation_workflows.py (new), next Alembic migration`.
  - [ ] Create only scoped workflows/drafts and immutable revisions with unique (workflow_id, revision_number), content digest, optimistic draft version and archive state. Add scoped feature/authorization epoch and audit records only as required here; no run/runner/grant/outbox tables. Prove upgrade from synthetic v1.4.0 DB copy.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Service and HTTP owner** (AC1–4)
  - [ ] Owned write scope: `services/infra_automation_service.py (new), api/routes/infra_automation.py (new), api/schemas.py, app.py`.
  - [ ] Expose typed draft/validate/publish/archive/restore/revision reads using 16.2 membership and 16.3 validation, ApiRoute/ApiError/build_meta. Revalidate at publish; bind idempotency key to request digest. Stale/changed payload reuse yields conflict. Run start is not implemented here: qualify immutable snapshot export against a consumer port.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Feature/configuration policy owner** (AC5/6)
  - [ ] Owned write scope: `config.py, services/settings_service.py, services/policy_adapter_settings.py, automation policy module (new)`.
  - [ ] Add administrator-only enablement and scoped settings/floor validation; implement live epoch policy used by later claims/dispatch/consume. Use grant-consumer and pending-retention doubles to test race/invalidation semantics. Registered targets and real grants remain 16.10; restore procedures remain 16.18.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Audit and lifecycle proof owner** (AC1–6)
  - [ ] Owned write scope: `tests/test_api, tests/test_services, tests/test_infra_automation, docs/infra-automation/workflows.md (new)`.
  - [ ] Exercise project/workspace CRUD, concurrent publication, immutable restore, post-snapshot edits, disable-before-consume and history/reconciliation allowances with typed doubles. Publish audit export permission/secret tests and configuration migration/operator examples.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.

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
