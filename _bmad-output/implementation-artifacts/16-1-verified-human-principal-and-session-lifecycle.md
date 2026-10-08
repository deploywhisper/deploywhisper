# Story 16.1: Verified Human Principal And Session Lifecycle

Status: backlog
Preparation: refined
Release: v1.5.0 — P0 highest-priority feature
Dependencies: 16.0; public RFC and 16.0 qualification required

## Story

As an operator, I want to authenticate through a named, revocable local account, so that future decisions carry a verified human identity rather than caller-provided headers.

## Acceptance Criteria

1. **AC1:** Given an empty installation and a protected local, unexpired setup credential, when the operator bootstraps the first administrator through the local CLI, then one account is created atomically and a replay, expired token or remote/default-password attempt cannot create another account.
2. **AC2:** Given a named enabled account, when correct credentials are submitted, then the server verifies a salted password verifier, rotates a high-entropy opaque session and resolves principal identity from that session; supplied actor/role headers do not affect it.
3. **AC3:** Given a browser session, when a mutation is submitted, then cookie scope/HttpOnly/SameSite/Secure policy, CSRF token and allowed Origin are enforced; missing/incorrect tokens and cross-origin requests fail without mutation.
4. **AC4:** Given logout, idle/absolute expiry, administrator revocation or secured password recovery, when an old session is reused, then it is denied; recovery invalidates prior sessions and requires operator-held recovery evidence without logging reusable secrets.
5. **AC5:** Given service, agent, runner or receiver credentials presented to human login/session operations, when authentication resolves their audience, then no human session or human publish/decision authority is issued; malformed and repeated failures are bounded and rate-limited.
6. **AC6:** Given legacy project/report behavior and a production HTTPS versus explicit local-development profile, when identity routes are enabled, then protected automation identity fails closed, unrelated compatibility behavior remains covered, and local HTTP exceptions cannot enable production handoff.

### Requirement Traceability

Coverage intent: Delta over accepted v1.4.0; exact canonical requirement text/proof is preserved below. Shared IDs qualify only this owned slice; later mapped stories complete integration.

| Requirement | Contract owned or verified | Required acceptance proof |
| --- | --- | --- |
| IAU15-FR-002 | Resolve each human decision from a verified human principal; caller actor/role headers cannot establish identity. | Authenticated-session and malicious-header tests |
| IAU15-FR-003 | Bootstrap the first local operator through an operator-held one-use setup credential with no default account/password; provide a documented secured account-recovery procedure. | Bootstrap replay/default-credential tests and recovery exercise |
| IAU15-FR-004 | Enforce human session expiry, logout and revocation with protected cookies and CSRF defenses for browser mutations. | Session lifecycle, cookie and CSRF test matrix |
| IAU15-FR-005 | Distinguish human, service, agent and runner credentials; nonhuman credentials cannot obtain human sessions, publish workflows or decide approvals. | Principal-type privilege matrix |
| IAU15-NFR-002 | The declared principal × role × project/workspace × object/action matrix must produce zero cross-scope reads or unauthorized mutations. | Published complete authorization matrix results |

## Tasks / Subtasks and bounded work packets

Execute packets in listed dependency order; assign one named owner per packet and review its tests before widening scope. Shared files must accommodate concurrent edits; no global tracker or unrelated story change is authorized by a packet.

- [ ] **Identity persistence owner: accounts and verifier lifecycle** (AC2/4/5)
  - [ ] Owned write scope: `models/tables.py, models/repositories/identity.py (new), services/identity_service.py (new), next Alembic migration`.
  - [ ] Create only principal/account, hashed session and one-use setup/recovery records with unique account identity, expiry/revocation/version fields. Adopt the crypto parameters frozen in 16.0; no new auth SDK or speculative memberships/runner/grant tables. Add fresh/upgrade/rollback fixtures and verifier timing/input bounds.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Authentication API owner: session and CSRF boundary** (AC2/3/5/6)
  - [ ] Owned write scope: `api/routes/auth.py (new), api/dependencies.py, api/schemas.py, config.py, app.py`.
  - [ ] Publish typed login/logout/current-principal and revoke contracts under /api/v1 with ApiRoute/ApiError envelopes. Separate authentication from project permission. Rotate sessions and CSRF state after login/privilege changes; ensure cookie and Origin configuration cannot silently weaken the supported HTTPS profile.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Operator CLI owner: bootstrap and recovery** (AC1/4/5)
  - [ ] Owned write scope: `cli/ identity command module (new), docs/infra-automation/identity.md (new)`.
  - [ ] Read credentials through protected stdin or permission-checked files, never process argv, URLs or logs. Prove first-account concurrent bootstrap replay resistance, recovery possession verification and session invalidation. Document rate limits, expiry and break-glass recovery trust without offering an approval bypass.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Test owner: principal and negative-request matrix** (AC1–6)
  - [ ] Owned write scope: `tests/test_services, tests/test_api, tests/test_cli, tests/test_infra`.
  - [ ] Use temporary databases and TestClient; freeze password/session/CSRF/replay/account-recovery fixtures. Scan captured audit/errors for credential values; record human versus synthetic machine audience cases and existing unauthenticated compatibility regressions.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.

## Dev Notes

Reuse the database/session infrastructure in models/database.py and existing ApiRoute/ApiError/build_meta helpers. api/dependencies.py is currently a placeholder, not an authentication system. services/project_service.py normalize_project_role(None) returns admin; never call it to infer authenticated identity. The 16.0 threat model fixes password hashing/work factors and recovery custody before implementation. Synthetic machine credentials prove audience rejection only; real runner enrollment belongs to 16.12.

### Contracts and migration boundary

Typed verified-principal/session context includes principal ID/type, credential audience, session ID/expiry and authentication version. Keep reusable tokens out of persisted/audit fields; hash opaque tokens and salt password verifiers. Return uniform auth errors without account enumeration; account/member administration must authenticate an administrator. No workflow/approval/runner tables.

Use the locked Python-first stack (SQLAlchemy/Alembic/Pydantic and existing libraries), opaque IDs and UTC timestamps. Inspect current migration head and freeze wire/schema fixtures before coding. Existing accepted story capabilities are reused; no full future automation schema, new runtime SDK, Node server or risk-engine fork.

### Acceptance and regression matrix

| Input/condition | Required result |
| --- | --- |
| Valid local bootstrap; two concurrent consumers | Exactly one first administrator; second attempt denied |
| Actor=admin header with no session; wrong password | No human principal; generic bounded auth error |
| Valid cookie but foreign Origin or absent CSRF | Mutation denied; database unchanged |
| Expired/revoked/logout/password-reset session | No authorized request using old session |
| Synthetic agent/runner credential | No human session or publication/approval capability |

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
