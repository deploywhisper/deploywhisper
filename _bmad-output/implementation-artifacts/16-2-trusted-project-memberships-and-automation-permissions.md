# Story 16.2: Trusted Project Memberships And Automation Permissions

Status: done
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

- [x] **Membership persistence owner** (AC1/2/5)
  - [x] Owned write scope: `models/tables.py, models/repositories/project_memberships.py (new), next Alembic migration`.
  - [x] Add only principal/project membership with role, workspace restriction and authorization version, unique/FK constraints and transactional updates. Inspect existing project/workspace records and identity tables from 16.1. No workflow/run/decision tables.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Authorization service owner** (AC2/4/5)
  - [x] Owned write scope: `services/project_service.py, services/identity_service.py, api/dependencies.py`.
  - [x] Reuse PROJECT_ROLE_CAPABILITIES names and existing report.read/report.review/analysis.submit/settings.manage/role.manage semantics; publish explicit automation read/request/draft/publish/decision/cancel/admin capability names and ownership rules. Admin publishes/manages; maintainers draft/request/cancel owned work; reviewers decide with review capability; contributors request; read-only reads. Extended publication needs reviewed assignment, not an implicit maintainer grant.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Legacy boundary owner** (AC3/5/6)
  - [x] Owned write scope: `api/routes/analyses.py, settings.py, projects.py, relevant linked artifact/policy adapters and services/report_service.py`.
  - [x] Inventory every alternate linked read/mutation, sharing, comparison, history, feedback/export/delete, settings/policy/project path. Apply one verified scope guard in both route and service entry points; test linked seeded objects without waiting for 16.6. Preserve unrelated compatibility only behind explicit profile.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Matrix and documentation owner** (AC1–6)
  - [x] Owned write scope: `tests/test_api, tests/test_services, docs/infra-automation/permissions.md (new)`.
  - [x] Publish principal × existing role × project/workspace × object/action cases, ownership/separation rules and generic denial behavior. Exercise a seeded decision-context port for shared versus acknowledgement semantics; later UI/collection integration is 16.6/16.9.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.

### Review Findings

- [x] [Review][Patch][High] Rollback must remove newly written artifact snapshots, including commit failure and enclosing-operation rollback [services/report_service.py:4975]. A failed commit leaves no report row but retains its artifact manifest; reuse of the integer report ID can expose those files under a different report's authority.
- [x] [Review][Patch][Medium] Derive protected report provenance actor from the verified principal [services/report_service.py:4887; api/routes/analyses.py:948]. An authenticated contributor can persist and return another actor's label through caller audit metadata.
- [x] [Review][Patch][Medium] Release the SQLite writer reservation during external topology collection and revalidate before persistence [services/topology_service.py:2542,2872]. A slow collector blocks unrelated reads and identity/membership writes beyond the five-second SQLite timeout.

- [x] [Review][Patch][Medium][Rerun] Preserve report artifacts when report deletion rolls back [services/report_service.py:6132-6149]. Failed commit, enclosing rollback or duplicate protected bulk-delete IDs restores the report row after its snapshot directory has already been removed. Defer artifact cleanup until commit and protect against report-ID reuse.

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

Codex GPT-6. Root owns authorization/API integration and final verification. Native packet owners: `s162_persistence` (schema/repository/migration), `s162_report_boundary` (reports/artifacts/stats), `s162_linked_boundary` (feedback/outcomes/incidents/backtesting/scanner/topology), `s162_settings_boundary` (policy/provider/skills), and `s162_matrix_docs` (independent matrix/operator docs). `s162_readiness` qualified dependencies; `s162_core_security` and `s162_legacy_security` independently examined the implemented trust boundaries.

### Debug Log References

Readiness rerun: `_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-13-story-16-2.md` — READY. Story16.1 merged at develop `02bdc0b` (PR156); foundation prerequisites are satisfied.

Validation runs use an isolated detached checkout of `02bdc0b` overlaid with the feature files, a shared interpreter only, and no application `.env` or data directory. SHA256 comparison confirmed the tested source matches the working branch. Fixtures use temporary SQLite and synthetic credentials.

| Validation command / evidence | Result |
| --- | --- |
| `./.venv/bin/python -m pytest tests/test_services/test_project_permission_matrix.py -q` | 3 tests / 1,400 independently specified subtests passed; zero unexpected grants or denials. |
| Persistence packet, migration/container regression, evidence-model regression | 18 tests / 12 subtests, 39 tests, and 5 tests passed respectively. |
| Initial nine new authorization/migration modules | 113 tests / 1,617 subtests passed; final shard runs include the subsequent cache regressions. |
| `./.venv/bin/python -m unittest discover -q` | 675 tests passed, 2 existing skips. |
| `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` | 628 passed, 1 existing skip, 2,146 subtests passed. |
| `./.venv/bin/python -m pytest tests/test_services -v --tb=short` | 1,209 passed, 2,248 subtests passed. |
| `./.venv/bin/python -m pytest tests/test_docs -q` | 51 tests / 312 subtests passed. |
| `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .` | Passed; all 345 Python files formatted. |
| CI-configured mypy command: `./.venv/bin/mypy api/ analysis/ services/ parsers/ models/ config.py --ignore-missing-imports --no-error-summary` | Nonblocking baseline debt remains: 310 errors versus 312 at `02bdc0b`; normalized comparison found zero new errors, no added suppressions. |
| Live `./.venv/bin/python app.py` with disposable database and local-development identity profile | Health/login/project creation/bootstrap passed; bootstrap invalidated prior session; relogin restored scoped membership access; missing CSRF denied workspace write; authorized write passed; anonymous protected read was generic403/no-store. Server stopped and temporary DB removed. |
| Independent core and alternate-path security reviews | All findings closed and independently reverified. Cache closure additionally covers failure, count-only success, current feedback, historical feedback and pre-manifest snapshots; returned data strips internal dependency metadata and read recomputation does not write storage. |
| `git diff --check` | Passed. |

The first broad runs exposed two test-fixture regressions (a missing isolated artifact report record and a stale imported exception class after module reload); both were reproduced, corrected without bypassing guards, and the full affected shards rerun green. Repository-wide constructor/fixture searches covered Settings, project/report markers, memberships, audit, response models and decision-context ports. No new test directory was introduced: all new tests are in existing registered API/services/infra targets.

`bash scripts/ci-local.sh` passed with exit0: Ruff, repository-wide formatting, dependency integrity, bytecode compilation, built-in skill scenarios, prompt-injection tests (8 tests / 96 subtests), and all nine registered unittest targets. Target counts: analysis69, API264, CLI102, docs51, infra263 (1 existing skip), LLM75 (1 existing skip), models22, parsers43, services1,209 — 2,098 tests total. Bandit high-severity/high-confidence gate found no issues; its medium report retains the existing B104 fixture-string finding in unchanged `services/sample_incident_pack.py:327`. No new security suppressions were added.

Final logs: `/tmp/dw-16-2-final-{smoke,api-cli-infra,services,local-ci,mypy}.log`, runtime checks `/tmp/dw-16-2-runtime-smoke.log`, and source digest manifest `/tmp/dw-16-2-validation.json`. These are local execution evidence, not runtime/application files. No rendered UI changed: **UI validation not applicable**.

Definition of Done: PASS for this owned backend slice. All packet tasks and acceptance criteria are verified; final file list matches the working diff. BMad help rerun against the catalog and tracker recommends [CR] `bmad-code-review` in a fresh context. At dev completion, story/sprint were `review`; final review results and Git Flow closure are recorded below.

### Implementation Plan

1. Add only scoped membership, minimal authorization audit and internal project/report protection markers; migration030 preserves legacy data and fails closed on partial authority schemas.
2. Resolve credentials and live membership inside the operation transaction. Reuse one operation session across nested services; no cached grant can replace the current role/version. Bootstrap only the global administrator's own first scoped administrator membership, explicitly and atomically.
3. Guard all report/context service entry points and API paths, including lists/counts, comparisons, stats, sharing, artifacts, feedback, outcomes and linked incident/backtest paths. Apply visible-row predicates before pagination or aggregation; mutation checks remain explicit.
4. Freeze and test the principal/role/project/workspace/action matrix, same-operation race orderings and server-owned decision-context port. Publish operator/API contracts and execute required broad validation.

`legacy-evaluation` is the explicit server profile for existing unprotected advisory behavior; protection markers always require verified identity and membership. A protected report also protects its parent project context. `verified` requires authorization for all project data; unknown profiles deny. `shared` decision mode rejects self-review; server-selected single-operator mode emits acknowledgement only. No workflow/run/decision tables, machine enrollment, production handoff or rendered UI are introduced.

UI validation not applicable: backend/contract scope; existing HTML markup and React screens remain untouched.

### Completion Notes List

Implementation and acceptance verification are complete; the earlier backlog preparation snapshot is superseded by the 2026-10-13 READY assessment and recorded validation below.

- AC1: migration030 adds membership constraints, authorization versions and audit; explicit first-admin bootstrap, assignment and revocation require live human credentials, preserve history and invalidate target sessions.
- AC2/4: explicit automation capabilities preserve legacy role semantics; 1,400 independently specified matrix subtests cover human and synthetic machine policy. Shared decisions reject self-review; server-owned single-operator context records acknowledgement.
- AC3/6: shared service/route guards protect report, share, artifact, settings, policy and linked evidence; filters precede pagination/counts. Legacy evaluation permits only unprotected advisory context. Protected report deletion retains project protection.
- AC5: one SQLite operation transaction resolves credentials, membership and object scope; nested services flush without committing. Revocation orderings, stale versions, cached evidence and download-gap reauthorization have regression coverage.
- Independent security checks identified and closed global settings checks for unmarked projects in verified mode, outcome aggregation permissions, private incident links, read-triggered topology collection, alternate skill administration and stale cached report dependencies. Independent reviewers reverified all closures; final suite evidence is recorded in the table above.
- Reused existing repositories, capability names and identity service; no dependencies or future workflow/run/decision persistence were added. Actual machine issuance and browser/production integration remain later-story work.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/16-2-trusted-project-memberships-and-automation-permissions.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-13-story-16-2.md`
- `_bmad-output/project-context.md`
- `api/dependencies.py`
- `api/errors.py`
- `api/routes/analyses.py`
- `api/routes/deployments.py`
- `api/routes/incidents.py`
- `api/routes/projects.py`
- `api/routes/scanner_imports.py`
- `api/routes/settings.py`
- `api/schemas.py`
- `app.py`
- `cli/analyze.py`
- `config.py`
- `docs/infra-automation/permissions.md`
- `llm/skill_context.py`
- `migrations/versions/030_add_project_memberships.py`
- `models/database.py`
- `models/repositories/analysis_reports.py`
- `models/repositories/deployment_outcomes.py`
- `models/repositories/feedback_events.py`
- `models/repositories/incident_ingestion_sources.py`
- `models/repositories/incident_records.py`
- `models/repositories/project_memberships.py`
- `models/repositories/projects.py`
- `models/repositories/settings.py`
- `models/tables.py`
- `services/analysis_service.py`
- `services/artifact_snapshot_service.py`
- `services/backtesting_service.py`
- `services/deployment_outcome_service.py`
- `services/feedback_service.py`
- `services/identity_service.py`
- `services/incident_import_service.py`
- `services/incident_service.py`
- `services/policy_adapter_service.py`
- `services/project_service.py`
- `services/report_service.py`
- `services/scanner_import_service.py`
- `services/settings_service.py`
- `services/skill_installer_service.py`
- `services/stats_service.py`
- `services/topology_service.py`
- `tests/test_api/test_project_authorization_context.py`
- `tests/test_api/test_projects.py`
- `tests/test_api/test_protected_reports.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_identity_migration.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_infra/test_project_membership_migration.py`
- `tests/test_llm/test_skill_context.py`
- `tests/test_services/test_analysis_content_boundary.py`
- `tests/test_services/test_content_security.py`
- `tests/test_services/test_linked_authorization.py`
- `tests/test_services/test_project_authorization.py`
- `tests/test_services/test_project_membership_repository.py`
- `tests/test_services/test_project_permission_matrix.py`
- `tests/test_services/test_project_service.py`
- `tests/test_services/test_report_authorization.py`
- `tests/test_services/test_report_service.py`
- `tests/test_services/test_settings_authorization.py`
- `tests/test_services/test_settings_service.py`
- `tests/test_services/test_skill_installer_service.py`
- `tests/test_services/test_snapshot_content_boundary.py`
- `tests/test_services/test_topology_credentials.py`


## Change Log

- 2026-10-13: Implemented Story 16.2 memberships, live scoped authorization, protected legacy boundaries, migration030, the explicit capability matrix and operator documentation. Added regression coverage and corrected alternate-path/cache issues found by independent security validation. Work remains on `feature/16-2-trusted-project-permissions`; formal code-review owns commit/push/PR closure.
- 2026-10-13: Layered code review identified and fixed three report-identity/artifact/topology transaction issues; independent reviewers reverified every correction.


## Senior Developer Review (AI)

Review date: 2026-10-13. Workflow: `bmad-code-review`; all three independent layers completed (Blind Hunter, Edge Case Hunter, Acceptance Auditor). Reviewed all 68 files including untracked additions against `02bdc0b`; the branch subsequently fast-forwarded to `67c9518`, whose only extra change is the upstream skill analytics snapshot.

Triage: **3 patch findings** (1 high, 2 medium), **0 decision-needed**, **0 deferred**, **1 dismissed**. The dismissed final-administrator-removal concern is intentional documented policy: retained membership/audit history prevents bootstrap reopening; project decommissioning must not silently create a new grant.

| Finding | Correction | Independent closure evidence |
| --- | --- | --- |
| High: report commit failure leaves artifacts that can attach to a reused integer ID | Register snapshot compensation on the outer authorization operation; run before releasing a live SQLite reservation. Skip cleanup after native reservation loss. Clear orphaned directories on every new report, even without snapshots. | Original reviewer induced a real SQLite COMMIT failure with a concurrent reader: snapshots removed while reservation held and row rolled back. Enclosing rollback, ID reuse, lost reservation/new writer and successful persistence regressions pass. |
| Medium: caller actor survives protected report persistence | Derive top-level and per-artifact provenance actor from the live verified principal before storage and fallback serialization. Keep unprotected legacy labels. | Original auditor's direct-service reproduction now stores/returns `human-a`; supported API upload with forged actor header excludes that forged label. |
| Medium: topology collection holds SQLite writer across external I/O | Preauthorize and capture source state; collect outside the writer reservation; recheck live authority, revision and payload before saving. Nested reads stay cached-only and nested collection fails without releasing caller ownership. | Original edge reviewer measured unrelated read at 0.003s during collection, denied post-collection session revocation and identical-payload/new-revision races, and verified no stale cache writes. |

Focused verification: report/API/core regression modules **248 tests / 241 subtests passed**; linked/topology modules **114 tests / 30 subtests passed**. Initial fresh full authorization/migration review check: **115 tests / 1,619 subtests passed**. Ruff lint and repository-wide format passed. Mypy remains **310 baseline errors** (312 before story), with zero new errors.

Production build `docker build -t deploywhisper:story-16-2-review .` passed from the isolated validation checkout, which contains no application `.env` or user data. A disposable container returned health200, migrated to030 with both authority tables, and contained no Node runtime; it was removed afterward. UI validation not applicable: no React/rendered markup changes.

Final review outcome: **APPROVED — all 3 findings fixed, no unresolved high/medium issue**.

Final post-review validation (source SHA256 verified against the isolated checkout):

- `./.venv/bin/python -m unittest discover -q`: **676 tests**, 2 existing skips, passed.
- `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: **629 passed**, 1 existing skip, **2,146 subtests passed**.
- `./.venv/bin/python -m pytest tests/test_services -v --tb=short`: **1,223 passed / 2,248 subtests passed**.
- `bash scripts/ci-local.sh`: **PASS**, all nine registered directories, **2,113 tests total**, 2 existing skips; Ruff, format (345 files), pip check, compileall, skill scenarios, prompt-injection tests and configured Bandit high/high gate passed.
- Mypy: 310 pre-existing errors; normalized baseline comparison found zero new errors. Existing unchanged medium Bandit fixture-string finding remains as recorded above.
- Docker build and disposable container health/migration030/no-Node smoke: **PASS**.
- Changed production source secret-pattern scan, file-list completeness and `git diff --check`: **PASS**.
- UI validation not applicable.

Logs: `/tmp/dw-16-2-reviewed-{smoke,api-cli-infra,services,local-ci,mypy,docker,container-smoke}.log`. Git Flow branch is `feature/16-2-trusted-project-permissions`, based on current develop `67c9518`; closure commit/push and PR target `develop`. This review does not merge or release the feature.

BMad help: Story16.2 is done; the next ready implementation slice is Story16.3. Its own scope and prerequisites still apply.


### Re-review — 2026-10-13

Fresh Blind Hunter, Edge Case Hunter and Acceptance Auditor reviewed PR157 at `18d22fb` against develop. Acceptance audit passed all owned ACs and independently ran 130 tests / 1,619 subtests. Defect layers independently confirmed **one new medium patch finding**: failed or enclosing-rolled-back deletion restored a report after its snapshots had already been removed. Duplicate protected bulk IDs reproduced the loss deterministically. Triage: 1 patch, 0 decisions, 0 deferred; the already documented final-administrator policy remains intentional.

Correction: deduplicate bulk IDs and defer filesystem cleanup until successful outer commit. Cleanup runs after resetting the old session/context, captures the original database factory, reserves a fresh writer, and deletes only while the report ID remains absent. A reused ID preserves the replacement report's files. Persistence after pending deletions in the same operation is rejected before INSERT, including when a caller catches the error. Cleanup failures log a generic warning and can retain inaccessible orphan files; later ID reuse clears those files before writing new snapshots. No dependency, schema or API change was introduced.

Both original defect reviewers independently verified closure. Added regressions cover commit failure, enclosing rollback, later batch failure, duplicate IDs, postcommit ID reuse, same-operation reuse and caught rejection, the captured database factory, and cleanup failure. Focused report/core suites: **240 passed / 225 subtests passed**.

Final verification of this correction used a fresh detached `18d22fb` checkout with the six changed files overlaid, no application `.env` or data, and verified Python source digests:

- Root `unittest discover -q`: **676 tests passed**, 2 existing skips.
- Exact API/CLI/infra pytest shard: **629 passed / 2,146 subtests**, 1 existing skip.
- Exact services pytest shard: **1,232 passed / 2,248 subtests**.
- Documentation: **51 passed / 312 subtests**.
- Ruff check, repository-wide format (345 files), configured Bandit high/high gate and diff whitespace: **PASS**.
- Fresh nonincremental mypy comparison: **311 diagnostics on both `18d22fb` and corrected code**, zero new diagnostics. The extra diagnostic versus the earlier cached count is the existing missing PyYAML-stub diagnostic, not a code change.
- Container build passed. Production Python3.11 container executed migration030 and verified that deletion rollback preserves the original snapshot and committed deletion removes it. Disposable container removed.
- UI validation not applicable.

The earlier full local CI run and all GitHub checks at `18d22fb` remain recorded above; this bounded correction reran the affected complete shards rather than repeating unchanged parser/LLM suites locally. Logs: `/tmp/dw-s162-rerun-{smoke,api-cli-infra,services,docs,security,mypy-clean,mypy-baseline-clean,docker,container}.log`.

**Re-review outcome: APPROVED; one new finding fixed, zero unresolved findings.** Story/sprint remain `done`; follow-up commit belongs to `feature/16-2-trusted-project-permissions` and existing PR https://github.com/deploywhisper/deploywhisper/pull/157. BMad help still routes next implementation to ready Story16.3; no other story was promoted.
