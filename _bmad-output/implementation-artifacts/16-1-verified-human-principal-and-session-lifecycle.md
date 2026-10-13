# Story 16.1: Verified Human Principal And Session Lifecycle

Status: done
Preparation: refined
Release: v1.5.0 — P0 highest-priority feature
Dependencies: 16.0; public RFC and 16.0 qualification required

Review gate (2026-10-12): Story 16.0's findings are resolved and requalified; foundation readiness is restored.

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

- [x] **Identity persistence owner: accounts and verifier lifecycle** (AC2/4/5)
  - [x] Owned write scope: `models/tables.py, models/repositories/identity.py (new), services/identity_service.py (new), next Alembic migration`.
  - [x] Create only principal/account, hashed session and one-use setup/recovery records with unique account identity, expiry/revocation/version fields. Adopt the crypto parameters frozen in 16.0; no new auth SDK or speculative memberships/runner/grant tables. Add fresh/upgrade/rollback fixtures and verifier timing/input bounds.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Authentication API owner: session and CSRF boundary** (AC2/3/5/6)
  - [x] Owned write scope: `api/routes/auth.py (new), api/dependencies.py, api/schemas.py, config.py, app.py`.
  - [x] Publish typed login/logout/current-principal and revoke contracts under /api/v1 with ApiRoute/ApiError envelopes. Separate authentication from project permission. Rotate sessions and CSRF state after login/privilege changes; ensure cookie and Origin configuration cannot silently weaken the supported HTTPS profile.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Operator CLI owner: bootstrap and recovery** (AC1/4/5)
  - [x] Owned write scope: `cli/ identity command module (new), docs/infra-automation/identity.md (new)`.
  - [x] Read credentials through protected stdin or permission-checked files, never process argv, URLs or logs. Prove first-account concurrent bootstrap replay resistance, recovery possession verification and session invalidation. Document rate limits, expiry and break-glass recovery trust without offering an approval bypass.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Test owner: principal and negative-request matrix** (AC1–6)
  - [x] Owned write scope: `tests/test_services, tests/test_api, tests/test_cli, tests/test_infra`.
  - [x] Use temporary databases and TestClient; freeze password/session/CSRF/replay/account-recovery fixtures. Scan captured audit/errors for credential values; record human versus synthetic machine audience cases and existing unauthenticated compatibility regressions.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.

### Review Findings — 2026-10-13

- [x] [Review][Patch][P2] Enforce custody checks for redirected password stdin — `--password-file -` currently accepts a group/world-readable redirected file that the named-file path rejects. Validate descriptor ownership/type/mode and retain protected-pipe support. [cli/identity.py:101]
- [x] [Review][Patch][P3] Validate the complete username contract at the HTTP boundary — UTF-8 byte overflow, surrounding whitespace and control characters currently return 401 instead of the documented 400 invalid-request envelope. Reuse the shared username validation and add HTTP regressions. [api/routes/auth.py:86]

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

Codex GPT-6; root owns integration and verification. Native persistence executor owns packet 1; independent security analysis supports the HTTP/CLI boundary.

### Debug Log References

2026-10-12 baseline: `./.venv/bin/python -m pytest tests/test_api/test_projects.py tests/test_api/test_error_security.py tests/test_infra/test_migrations.py -q` —47 passed. Tests-first failures were recorded for missing persistence/API/CLI contracts, incomplete migration recognition and administrator idle refresh, followed by passing regressions.

| Validation command / exercise | Actual result |
| --- | --- |
| `./.venv/bin/python -m pytest tests/test_services/test_identity_service.py tests/test_api/test_auth.py tests/test_cli/test_identity.py tests/test_infra/test_identity_migration.py -q` |48 passed,8 subtests |
| `./.venv/bin/python -m unittest discover -q` |658 tests, OK,2 existing skips |
| `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` |607 passed,1 skipped,2123 subtests |
| `./.venv/bin/python -m pytest tests/test_services -v --tb=short` |1110 passed,640 subtests |
| `bash scripts/ci-local.sh` |Pass; all9 unittest targets, 1978 tests, plus 8 prompt-injection tests; lint/format/dependency/security/compile/skill checks pass |
| `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .` |Pass;334 files formatted |
| Scoped `mypy` with `--ignore-missing-imports --follow-imports=silent --no-error-summary` on identity service/repository/API dependency/routes/CLI |Pass |
| Scoped `bandit -q` on identity API/CLI/service/repository/migration, plus CI security gate |Pass; no new suppressions |
| `git diff --check`; compileall; repository-wide constructor/fixture search |Pass; additive constructors and migration-head fixtures aligned |
| Final service/migration fixture close regression run |22 passed after explicitly closing SQLite fixture connections |
| Real app/CLI exercise, isolated temporary DB |Health/login/session/CSRF/logout/recovery invalidation passed |

Detailed session-local logs: `/tmp/dw-16-1-{baseline,owned-final,smoke,api-cli-infra,services,local-ci,review-fixes,fixture-final}.log`. No raw credentials or real infrastructure fixtures were added to the repository. An early test inadvertently invoked shared app startup against the local default database; only newly added empty identity tables were rolled back to revision 028, a protected backup was retained outside the repository, and the test was changed to avoid lifespan. Final local revision 028 was verified.

UI validation not applicable. The ordinary qualification suite's existing skips do not substitute for later production TLS/browser/runner qualification.

### Implementation Plan

1. Persistence executor: add only account/session/one-use credential records and migration, durable bounded login attempts, exact frozen verifier and lifecycle contracts; prove fresh/upgrade/rollback and concurrent bootstrap.
2. Root API owner: add typed closed, bounded identity routes and exact Origin/profile/cookie/CSRF checks. Review packet tests before advancing.
3. Root CLI owner: local protected-file/stdin bootstrap and recovery, with versioned operator/API documentation.
4. Root test owner: negative identity/audience matrix, security review, full local CI and exact affected shards. No new dependencies.

Security configuration defaults closed. Persist origin/profile with sessions; local HTTP sessions cannot be reused in HTTPS mode. Preserve existing legacy route behavior for the later 16.2 authorization integration.

UI validation not applicable: this story is backend/contract scoped.

### Completion Notes List

Implemented the qualified local identity foundation without new dependencies: three identity tables and migration 029, salted bounded PBKDF2 verifiers, hashed one-use setup/recovery evidence, origin/profile-bound sessions, durable throttling and separate human audience checks. API/CLI share the service; account administration rechecks live administrator authority and CSRF transactionally. Existing project/report behavior remains under its existing compatibility contract; scoped automation authorization is owned by 16.2.

| Packet / named owner | Implemented scope and acceptance evidence |
| --- | --- |
| Persistence — native persistence executor | Accounts/session/setup/recovery models and repository, migration and brownfield recognition. Initial packet: 60 tests passed. Separate-process bootstrap permits exactly one account; fresh process retains throttling. Five migration tests prove fresh/upgrade/downgrade/reupgrade/partial-schema denial. |
| API — Codex root | Typed closed login/current/logout/rotate/account/revoke contracts, streamed 4096-byte input, no-store/correlation envelopes, exact transport/Origin, CSRF and cookie scope. Final 13 API tests cover negative credentials, profiles, duplicates, runtime proxy handling and OpenAPI. |
| CLI — native identity boundary executor | Four local commands with exclusive 0600 output, no-follow/current-owner input checks, protected stdin/getpass and generic errors. 13 tests plus 8 subtests; full CLI 98 passed. Real temporary-database subprocess bootstrap/recovery and two-consumer bootstrap passed. |
| Negative matrix / integration — Codex root | Final owned suite 48 passed plus 8 subtests. Complete identity-owned audience/request matrix is published in docs/infra-automation/identity.md. Root smoke and exact API/CLI/infra and service shards pass; full local CI passed across all nine registered test directories. |

Independent security reviews resolved four findings: implicit Uvicorn proxy-header trust, malformed login attempts bypassing throttling, omitted OpenAPI error envelopes, and successful administration failing to refresh idle expiry. The last defect was reproduced with a failing test, fixed within the transaction and independently retested. Reviewer closure reported no remaining blocking findings. Denied mutations still do not refresh idle time.

Local crypto check reused the frozen 600,000-iteration primitive: seven samples on Darwin arm64/Python 3.14.3/OpenSSL 3.6.2 had median 79.83 ms. This is local cost evidence, not a deployment capacity claim. Runtime uses a nonblocking derivation slot and durable 5/account +20/global attempts per 60 s. Malformed requests share an anonymous 5-attempt bucket within that global budget.

A real `python app.py` process on a temporary SQLite database passed health200, local login200, principal200, missing-CSRF403, logout200, old-session401 and CLI-recovery old-session401; local production eligibility remained false. Identity defaults disabled. Production TLS/proxy/browser qualification, project permissions and real machine enrollment remain explicitly outside this slice.

UI validation not applicable: no React, rendered screen or browser workflow was changed. Simplifications: reuse existing API envelopes, SQLAlchemy/Alembic and standard-library crypto; no SDK, dependency, membership/workflow/runner tables, alternative identity core or legacy role-header authentication.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/16-1-verified-human-principal-and-session-lifecycle.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/project-context.md`
- `api/dependencies.py`
- `api/routes/auth.py`
- `api/schemas.py`
- `app.py`
- `cli/identity.py`
- `config.py`
- `docs/infra-automation/identity.md`
- `migrations/versions/029_add_identity_lifecycle.py`
- `models/database.py`
- `models/repositories/identity.py`
- `models/tables.py`
- `services/identity_service.py`
- `tests/test_api/test_auth.py`
- `tests/test_cli/test_identity.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_identity_migration.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_services/test_identity_service.py`

### Foundation readiness — 2026-10-10

Story16.0 qualification and final validation are complete. Its maintainer decision, frozen contracts and final readiness report satisfy this story's earlier dependency. This context is ready for its own implementation workflow; all implementation tasks remain unchecked. Use `docs/infra-automation/contract-v1.md` and the qualified evidence boundaries; no production work in this story is claimed by promotion.

## Change Log

- 2026-10-13: Three-layer BMad review resolved two findings (stdin custody and malformed-username errors), independently reverified fixes, passed full validation and moved the story/sprint entry to done on its Git Flow feature branch.

- 2026-10-12: Implemented and verified Story 16.1 local human identity/session lifecycle, migration 029, protected operator CLI and API/operator documentation. Resolved four independent review findings and recorded all validation; story and sprint status moved to review.

### Definition of Done / workflow handoff

The following records the 2026-10-12 development handoff; the completed review below supersedes it.

PASS: all six acceptance criteria and owned packet/verification tasks are covered; all required checks passed, the file list is complete, and UI validation is explicitly not applicable. No dependency or future automation capability was added.

BMad help reassessment: **[CR] bmad-code-review** is the next workflow in a fresh context. Current branch is `feature/16-1-verified-human-principal`; changes are intentionally uncommitted for reviewer closure. That workflow owns final Git Flow verification, commit/push and optional PR to develop. Later stories remain gated; this dev-story completion does not mark the story lifecycle done or claim production TLS/browser/automation qualification.

## Senior Developer Review — 2026-10-13

Full-spec BMad review covered 22 changed files (3111 added/39 removed lines at review start). Three independent layers completed: blind adversarial review, edge-case tracing and acceptance audit. Triage: 2 patch findings, 0 decisions, 0 deferred, 0 dismissed. The acceptance audit found no missing behavior within this story's identity boundary; project permissions/browser delivery remain assigned to later stories.

Both findings were reproduced before fixing and independently verified after fixing:

1. **P2 — Redirected stdin custody:** reading a mode 0644 password file through stdin previously bypassed named-file protection and consumed setup evidence. Shared descriptor checks now enforce current ownership, supported type and private permissions. Owned anonymous pipes remain supported on macOS/Linux; linked FIFOs and regular files require 0400/0600. Real subprocess tests prove denied input preserves setup evidence, protected-file bootstrap works and pipe-based recovery works.
2. **P3 — Malformed username error contract:** UTF-8 byte overflow, surrounding whitespace and C0 controls now use the shared service validator at the HTTP boundary and return generic 400 envelopes. Eight HTTP subcases failed before the fix and pass afterward. No duplicate username policy was added.

Independent final verification: CLI/API 31 passed with 20 subtests; service 17 passed. No blocking findings remain. Final validation on 2026-10-13:

| Check | Result |
| --- | --- |
| Identity service/API/CLI/migration pytest suite | 53 passed; 20 subtests |
| `./.venv/bin/python -m unittest discover -q` | 659 tests, OK; 2 existing skips |
| Exact API/CLI/infrastructure pytest shard | 612 passed; 1 skipped; 2135 subtests |
| Exact services pytest shard | 1110 passed; 640 subtests |
| `bash scripts/ci-local.sh` | All 9 directories passed: 1983 tests; plus 8 prompt-injection tests/96 subtests |
| Ruff lint and repository-wide format | Passed; 334 formatted files |
| Bandit, scoped identity mypy, diff checks | Passed |
| Independent fix re-review | Both findings closed; no remaining blockers |

Session-local evidence: `/tmp/dw-16-1-review-{baseline,username-red,username-green,owned-final,smoke,api-cli-infra,services,local-ci}.log`. The redirected-stdin regression also reproduced acceptance/consumption before the fix and passed afterward with real descriptors and isolated subprocesses.

Outcome: **Approved / done** for the owned identity slice. UI validation not applicable. Production TLS/proxy/browser qualification and project/automation authorization remain with their declared downstream owners.

Git Flow: reviewed branch `feature/16-1-verified-human-principal`, based on `develop`. This reviewed change is prepared for the required commit/push and PR to `develop`; the workflow's final result records the actual publication link. No unrelated story was promoted.

BMad help reassessment: prepare/validate Story 16.2 against the completed identity contract; Story 16.3 is already ready for development as a separate lane. This review does not start either story.

### GitHub CodeQL fixture follow-up — 2026-10-13

The initial PR156 CodeQL gate reported two cleartext-storage alerts (112/113), both classified as test code, in the CLI credential fixtures. The fixtures used generated synthetic account inputs; no operator credentials or production storage were involved. Disk fixtures now reference an explicitly public, fixed test input, and fixture files are created exclusively with mode0600 before writing. Random setup tokens and all exact-value output-leakage assertions remain covered. No CodeQL exclusion, suppression or runtime behavior change was introduced.

The fixture-only change passed17 CLI tests/12 subtests, repository Ruff/334-file formatting and independent review. The existing test subprocess calls are trusted, fixed-argv invocations; the configured security threshold remains clean. Final GitHub re-analysis is part of reviewer closeout. Full local CI above covers the unchanged production implementation; fixture-specific checks validate this follow-up.
