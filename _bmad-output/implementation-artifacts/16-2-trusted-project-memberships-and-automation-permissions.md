# Story 16.2: Trusted Project Memberships And Automation Permissions

Status: backlog
Preparation: refined
Release: v1.5.0 — P0 highest-priority feature
Dependencies: 16.1; public RFC and 16.0 qualification required

## Story

As a project administrator, I want to assign server-owned project memberships and automation capabilities, so that protected records cannot be exposed or changed by forged roles or alternate legacy paths.

## Acceptance Criteria

1. **AC1:** Given an authenticated administrator and existing project/workspace, when membership is assigned or revoked, then the server persists role and authorization version, audits the change and rejects an absent, invalid or caller-provided membership.
2. **AC2:** Given each existing role in two projects and two workspaces, when read/request/draft/publish/cancel/decision/admin actions are authorized, then only the explicit persisted capability matrix succeeds; missing membership, mismatched workspace and nonhuman publish/decision attempts fail closed.
3. **AC3:** Given a protected seeded automation-linked report or settings/policy/artifact context, when legacy read/share/export/delete/feedback or mutation routes are called with spoofed actor/role/project headers, then the same verified authority is enforced and denied responses reveal no other-project identifiers.
4. **AC4:** Given shared-mode decision context with requester A and reviewer B, when A attempts to approve itself, then it is denied; B requires report.review and an explicit automation decision capability. Single-operator mode records authenticated acknowledgement, never independent/four-eyes approval.
5. **AC5:** Given a membership change racing a protected operation, when the service checks live authorization version inside the operation transaction, then revoked authority cannot mutate or expose the object; caches do not retain stale capability grants.
6. **AC6:** Given legacy evaluation compatibility mode, when unrelated nonautomation analysis is exercised, then sanctioned behavior remains available but cannot grant automation permissions or share protected automation-linked evidence.

### Requirement Traceability

Coverage intent: Delta over accepted v1.4.0; exact canonical requirement text/proof is preserved below. Shared IDs qualify only this owned slice; later mapped stories complete integration.

| Requirement | Contract owned or verified | Required acceptance proof |
| --- | --- | --- |
| IAU15-FR-002 | Resolve each human decision from a verified human principal; caller actor/role headers cannot establish identity. | Authenticated-session and malicious-header tests |
| IAU15-FR-005 | Distinguish human, service, agent and runner credentials; nonhuman credentials cannot obtain human sessions, publish workflows or decide approvals. | Principal-type privilege matrix |
| IAU15-FR-006 | Derive project/workspace capabilities from server-owned memberships, denying absent membership and cross-scope access by default. | Role × project × workspace authorization matrix |
| IAU15-FR-007 | Protect automation-linked report, policy, settings and artifact paths against bypass through legacy caller-controlled scope or role inputs. | Legacy-route and linked-object bypass regression tests |
| IAU15-FR-008 | Enforce distinct requester/approver identities in shared mode; label authenticated single-operator decisions as acknowledgement with no separation-of-duties claim. | Self-approval denial and acknowledgement-mode E2E |
| IAU15-NFR-002 | The declared principal × role × project/workspace × object/action matrix must produce zero cross-scope reads or unauthorized mutations. | Published complete authorization matrix results |

## Tasks / Subtasks and bounded work packets

Execute packets in listed dependency order; assign one named owner per packet and review its tests before widening scope. Shared files must accommodate concurrent edits; no global tracker or unrelated story change is authorized by a packet.

- [ ] **Membership persistence owner** (AC1/2/5)
  - [ ] Owned write scope: `models/tables.py, models/repositories/project_memberships.py (new), next Alembic migration`.
  - [ ] Add only principal/project membership with role, workspace restriction and authorization version, unique/FK constraints and transactional updates. Inspect existing project/workspace records and identity tables from 16.1. No workflow/run/decision tables.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Authorization service owner** (AC2/4/5)
  - [ ] Owned write scope: `services/project_service.py, services/identity_service.py, api/dependencies.py`.
  - [ ] Reuse PROJECT_ROLE_CAPABILITIES names and existing report.read/report.review/analysis.submit/settings.manage/role.manage semantics; publish explicit automation read/request/draft/publish/decision/cancel/admin capability names and ownership rules. Admin publishes/manages; maintainers draft/request/cancel owned work; reviewers decide with review capability; contributors request; read-only reads. Extended publication needs reviewed assignment, not an implicit maintainer grant.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Legacy boundary owner** (AC3/5/6)
  - [ ] Owned write scope: `api/routes/analyses.py, settings.py, projects.py, relevant linked artifact/policy adapters and services/report_service.py`.
  - [ ] Inventory every alternate linked read/mutation, sharing, comparison, history, feedback/export/delete, settings/policy/project path. Apply one verified scope guard in both route and service entry points; test linked seeded objects without waiting for 16.6. Preserve unrelated compatibility only behind explicit profile.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Matrix and documentation owner** (AC1–6)
  - [ ] Owned write scope: `tests/test_api, tests/test_services, docs/infra-automation/permissions.md (new)`.
  - [ ] Publish principal × existing role × project/workspace × object/action cases, ownership/separation rules and generic denial behavior. Exercise a seeded decision-context port for shared versus acknowledgement semantics; later UI/collection integration is 16.6/16.9.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.

## Dev Notes

Reuse services/project_service.py PROJECT_ROLE_CAPABILITIES, authorize_project_action and require_project_permission after supplying trusted server membership. Their role argument and normalize_project_role(None) are not authenticators. models/repositories/projects.py owns project/workspace existence. api/routes/analyses.py _authorization_context currently parses caller scope: audit every linked report/shared route; a UI button restriction is insufficient.

### Contracts and migration boundary

Verified principal → live membership → named capability + project/workspace/object/ownership predicate. Server derives actor/role; request headers/body cannot replace them. Revocation increments authorization version for later decision/grant contracts. A scoped seeded protected-report marker/guard is enough for this slice; actual run/report relation is 16.6.

Use the locked Python-first stack (SQLAlchemy/Alembic/Pydantic and existing libraries), opaque IDs and UTC timestamps. Inspect current migration head and freeze wire/schema fixtures before coding. Existing accepted story capabilities are reused; no full future automation schema, new runtime SDK, Node server or risk-engine fork.

### Acceptance and regression matrix

| Input/condition | Required result |
| --- | --- |
| Admin A changes member A in project A | Persist and audit membership/version |
| No member/role header admin; workspace B in project A | Deny with no object existence detail |
| Reviewer B with report.review in A; requester A | Only B can decide in shared context |
| Authenticated single operator | Acknowledgement label and audit; no four-eyes claim |
| Legacy share/delete/export against protected seeded report | Verified scope enforced despite forged role/project headers |

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
