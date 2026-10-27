# Story 16.6: Uploaded Artifact Preflight And Report Linkage

Status: done
Preparation: refined
Release: v1.5.0 — P0 highest-priority feature
Dependencies: 16.5; public RFC and 16.0 qualification required

## Story

As a reviewer, I want to start an authenticated uploaded-artifact preflight linked to a permanent report, so that automation uses the same analysis evidence as existing surfaces without inventing collector trust or apply authority.

## Acceptance Criteria

1. **AC1:** Given a scoped verified member and supported synthetic upload through a published workflow, when intake and off-loop analysis complete, then the existing shared pipeline creates an immutable linked report and canonical permanent URL with unchanged scoring/advisory semantics.
2. **AC2:** Given unsupported/traversal/oversized/state/private-key/credential/binary-plan input or inline secret-looking content, when intake screens it, then it is rejected or safely screened before persistence/analysis; metadata, errors and streamed chunk boundaries cannot leak the declared sensitive-data corpus.
3. **AC3:** Given an authenticated synthetic collected-provenance envelope, when storage verifies it, then sanitized digest is recomputed and attempt/project/fence/lease/command-source identities are checked; tampered, stale or wrong-scope envelopes fail without treating metadata as independent collector truth.
4. **AC4:** Given upload-only advisory evidence with unknown repository source, when report provenance is linked, then unknown source/trust limitations are explicit and no fabricated commit/raw saved-plan handle or exact-plan approval grant is created.
5. **AC5:** Given failed, mandatory-missing, partial or stale input/analysis, when workflow eligibility is derived, then visible confidence limitations/context TODOs persist and approval eligibility is false; a partial advisory report may still be read without becoming a handoff authorization.
6. **AC6:** Given AI disabled or narrative failure, when the upload workflow analyzes, then deterministic report creation remains usable and raw input stays local; existing structured-summary provider boundary and inferred/deterministic Evidence Law labels remain intact.
7. **AC7:** Given old v1/v2 reports and existing constructors/API/CLI/report consumers, when optional provenance v1 is absent or present, then legacy behavior and permanent URLs survive; schema/hash compatibility is proved before any additive v2 serializer change, with no casual minor schema bump or duplicated risk logic.

### Requirement Traceability

Coverage intent: Delta over accepted v1.4.0; exact canonical requirement text/proof is preserved below. Shared IDs qualify only this owned slice; later mapped stories complete integration.

| Requirement | Contract owned or verified | Required acceptance proof |
| --- | --- | --- |
| IAU15-FR-007 | Protect automation-linked report, policy, settings and artifact paths against bypass through legacy caller-controlled scope or role inputs. | Legacy-route and linked-object bypass regression tests |
| IAU15-FR-023 | Allow runner-less upload of currently supported artifact formats through existing scoped intake protections. | Uploaded-artifact vertical slice and size/type/traversal tests |
| IAU15-FR-024 | Screen inputs, metadata, streamed logs, errors and artifacts before persistence or analysis; reject state/credential/key/binary-plan uploads and inline secret-looking values. | Secret corpus including chunk boundaries and blocked-file tests |
| IAU15-FR-025 | Record authenticated collection provenance with runner/task attempt, command/argv digest, source SHA, exit code, time, raw-local digest, sanitized digest and redaction version; recompute received digests. | Tampered digest, stale attempt and redaction-provenance tests |
| IAU15-FR-026 | Invoke the existing shared analysis core without duplicating risk logic; provenance alone cannot turn inferred output into deterministic evidence. | Cross-surface report parity and Evidence Law fixtures |
| IAU15-FR-027 | Link runs to immutable reports through a compatible versioned optional provenance contract; retain permanent report URLs and existing report consumers. | Serializer/constructor/legacy-consumer contract tests |
| IAU15-FR-028 | Expose missing/partial/stale collection as confidence limitations and context TODOs; failed or incomplete mandatory collection cannot make approval eligible. | Partial/error/stale collection eligibility tests |
| IAU15-FR-029 | Keep deterministic automation usable with AI disabled or narrative failure, and preserve existing structured-summary/local-only provider boundaries without new AI composition. | AI-off and narrative-failure vertical slice |
| IAU15-NFR-003 | The versioned sensitive-data corpus must yield zero known secret patterns in stored artifacts/logs/metadata/errors/audit or transmitted narrative summaries; no universal-redaction claim follows. | Stored/output corpus scans including chunk boundaries |
| IAU15-NFR-004 | Automation-originated fixture reports must produce zero Evidence Law violations and preserve deterministic/inferred labels and advisory report semantics. | Evidence Law and cross-surface contract CI results |

## Tasks / Subtasks and bounded work packets

Execute packets in listed dependency order; assign one named owner per packet and review its tests before widening scope. Shared files must accommodate concurrent edits; no global tracker or unrelated story change is authorized by a packet.

- [x] **Intake/screening owner** (AC1/2/4)
  - [x] Owned write scope: `services/intake_service.py, services/content_security.py, services/submission_manifest.py, infra_automation artifact intake module (new)`.
  - [x] Reuse build_parse_batch, total_upload_bytes, is_sensitive_file, trusted_relative_artifact_path and redact_value/redact_text; enforce aggregate bytes and filename/content classification. Screen filenames, metadata/errors and bounded stream buffers before storage; reject forbidden artifacts and document known pattern limits rather than universal redaction.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Provenance/link persistence owner** (AC3/4/7)
  - [x] Owned write scope: `infra_automation/contracts.py, models/tables.py, models/repositories/infra_automation_reports.py (new), next migration`.
  - [x] Create only run/report/artifact-manifest immutable links and optional version-1 provenance fields needed here. Record source variant, project/attempt, command/argv digest, source SHA where available, times/exit status, raw-local versus sanitized digest and redaction version. Raw-local digest is metadata, not uploaded plan bytes. Use authenticated synthetic envelopes; real custody/collector admission remains 16.14.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Shared-analysis adapter owner** (AC1/4/5/6/7)
  - [x] Owned write scope: `services/infra_automation_service.py, services/analysis_service.py, services/report_service.py, api/routes/infra_automation.py`.
  - [x] Call analyze_uploaded_files through 16.5 bounded worker, preserving intake→parse→assess→blast-radius→rollback→incident→narrative→persist ordering. Validate returned immutable report/link and compute eligibility outside advisory scoring. Reuse canonical go/caution/no-go plus typed insufficient-context/error flags; unknown values fail closed. Add scoped linked read guards from 16.2.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Cross-surface/consumer proof owner** (AC1–7)
  - [x] Owned write scope: `tests/test_infra_automation, tests/test_services, tests/test_api, tests/test_cli, tests/test_analysis, docs/infra-automation/preflight.md (new)`.
  - [x] Run upload vertical slice, secret corpus/chunk boundaries, tampered digests/stale attempts, cross-surface parity/Evidence Law, AI-off/narrative failure and v1/v2/provenance compatibility. Search all changed constructor instantiations and lock API/CLI fixtures. Regression-test linked shared/export/delete routes; no collection/receiver success claim.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.

### Review Findings

- [x] [Review][Patch][P2][R1] Persisted failed/missing/stale evidence facts need a versioned visible limitations/TODO projection even when no report exists — AC5 / IAU15-FR-028 [services/infra_automation_preflight.py:110].
- [x] [Review][Patch][P2][R2] Bound warning/TODO summaries so valid shared-core reports cannot fail linkage on more than 49 messages; preserve full report detail [models/repositories/infra_automation_reports.py:274].
- [x] [Review][Patch][P2][R3] Validate the exact final link view including its generated ID so an admitted immutable relation cannot become unreadable at the 16 KiB boundary [models/repositories/infra_automation_reports.py:285].
- [x] [Review][Patch][P2][R4] Include retained filesystem snapshot payload copies in project/global quota accounting and prove rollback at the byte boundary [models/repositories/infra_automation_reports.py:307].
- [x] [Review][Patch][P3][R5] Reject lone-surrogate filenames as invalid UTF-8 direct-intake input with 422 before manifest canonicalization (HTTP already rejects invalid Unicode) [infra_automation/artifact_intake.py:88].

- [x] [Review][Patch][P3][R6] Align new preflight byte/status annotations and explicitly guard a missing admitted run row — non-blocking mypy identified five new diagnostics [infra_automation/artifact_intake.py:140; infra_automation/preflight_evidence.py:150; services/infra_automation_preflight.py:33].

All three independent layers completed. No decision-needed or pre-existing deferred finding. Two hypotheses dismissed after dependency tracing: committed-output adoption already prevents rerunning successfully committed analysis after a crash; existing reserved-transaction rollback callbacks already compensate snapshot writes on final COMMIT failure (add focused proof).

Review fixes passed 63 focused tests and 450 subtests, with independent re-audits of the evidence projection and metadata/quota boundaries. Real SQLite COMMIT-failure compensation and real spawned committed-output adoption tests passed. Final checks passed. Git Flow remote closure is performed by this review workflow and recorded at completion.

## Dev Notes

Reuse services/analysis_service.py analyze_uploaded_files, build_context_completeness and build_advisory_summary; services/report_service.py persist_analysis_report/fetch_analysis_report/normalize_report_schema_version/can_read_report_schema and share/export paths; models/repositories/analysis_reports.py create_analysis_report and get_analysis_report_for_project_keys. These are existing report contracts, not permission to rewrite them. provenance has its own version 1; verify v1/v2 readers and canonical report digest interpretation before serializer changes.

### Contracts and migration boundary

Upload source variant can lack Git identity and supports advisory_request only. Collected envelope may be stored with authenticated identity and digest checks but remains synthetic contract proof here; production collector/custody is 16.14. Optional infra_automation_provenance is versioned separately from report schema. Link digest/bytes are immutable; provenance does not change evidence classification, risk severity or should_block=False. No approval/grant/runner tables.

Use the locked Python-first stack (SQLAlchemy/Alembic/Pydantic and existing libraries), opaque IDs and UTC timestamps. Inspect current migration head and freeze wire/schema fixtures before coding. Existing accepted story capabilities are reused; no full future automation schema, new runtime SDK, Node server or risk-engine fork.

### Acceptance and regression matrix

| Input/condition | Required result |
| --- | --- |
| Same supported artifact across upload/API/CLI fixture | Same deterministic findings/evidence/advisory report |
| State/key/binary plan, traversal, aggregate oversize | Blocked before persistence/analysis; no leaked error payload |
| Chunk-split secret/log/error/metadata corpus | Zero known stored/transmitted pattern matches in named corpus |
| Tampered sanitized digest; stale synthetic attempt | Rejected envelope; no trusted collected claim |
| Missing Git on upload; partial/failed/stale mandatory evidence | Explicit unknown/limitation and no exact-plan/approval eligibility |
| AI-off/narrative failure; old v1/v2 consumer | Deterministic report and compatible URL/serialization |

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

Codex GPT-6; root owns adapter/integration/verification, native intake packet owner owns artifact screening and its tests. Read-only native readiness review completed before implementation.

### Implementation Plan

1. Intake owner: native `intake`; local bounded rejection/screening, fixed errors and named synthetic corpus. Independent `readiness_check` review found BOM/legacy-state bypasses; regression fixes pass.
2. Persistence owner: native `persistence`; migration033, immutable scoped manifests/links, synthetic envelope checks and brownfield schema validation. No report serializer change.
3. Adapter owner: root; install a private wrapper-authenticated exact-scope analysis context, call shared `analyze_uploaded_files` off-loop and fence final report/link/output atomically. HTTP accepts a closed bounded upload request and exposes authorized relational links.
4. Consumer/verification owner: root; shared-core parity, AI-off/failure, stale/cancelled/revoked capability denial, linked legacy-route protection, frozen schema/hash compatibility, full CI and independent trust-boundary review. UI validation not applicable.

Native `readiness_check` reviewed the concrete port and required exact database-factory binding, workspace-limited visibility, live analysis.submit role checking, atomic output/link persistence, payload quota accounting and report filesystem compensation. These are implementation obligations, not completed proof.

### Debug Log References

- Baseline migration head032; delivered migration033. Branch `feature/16-6-uploaded-artifact-preflight`; implementation commit `5289b8d`.
- Durable acceptance/review notes: `docs/verification/infra-automation/16-6/results.md`; scoped readiness: `_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-27-story-16-6.md`.
- Test output retained locally in `/tmp/story16-6-{ci,unittest,api-cli-infra,services,automation-shard}-verified.log`; app smoke `/tmp/story16-6-pinned-app-smoke.log`. Initial interrupted/failed diagnostic runs are not presented as passes. Dependency synchronization used the existing requirements lock; no manifest/dependency addition.

### Completion Notes List

- **AC1/2:** Human-scoped authenticated preflight admission binds screened manifests to a published two-step workflow; real spawned workers produce permanent immutable report links through the shared pipeline. Named version1 eight-case corpus covers type/path/aggregate bounds, BOM/legacy state disguises, metadata/errors and every secret chunk split. API error/SQLite scans contain zero declared known patterns.
- **AC3/4:** Separate immutable relational provenance v1 and authenticated retained synthetic envelopes recompute sanitized digests and bind private live attempt/fence/lease/project/command/collector/source identities. Upload source is explicitly unknown, has no invented commit/custody and never grants approval. Actual collector/custody admission remains 16.14.
- **AC5/6:** Partial/fallback reports retain limitations/context TODOs with eligibility false; cancellation, stale/fake capability and mid-analysis revocation prevent final persistence. AI-disabled/narrative failure remains usable. Report/link/output commit atomically; failed linkage compensates report and local snapshots. Raw inputs remain local and provider input remains structured summaries.
- **AC7:** Existing v1/v2 readers, agent output, six real CLI cases, permanent URLs and all frozen protocol hashes remain compatible. No report minor schema bump or duplicated risk logic. Linked report children and artifact snapshots reject SQL REPLACE/reparenting and public mutation; legacy/shared/export/delete paths retain live membership guards.
- Independent native readiness, intake, persistence and adapter trust-boundary reviews completed. Corrections include BOM/state screening, SQLite implicit replacement/reparenting, app spawn bootstrap, explicit empty-registry test semantics and reload-safe snapshot guard exceptions. Full final validation passed after fixes.
- **Validation (provider fallback isolated with `LLM_API_BASE=http://127.0.0.1:9`):**
  - `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`: pass; 419 Python files formatted.
  - `./.venv/bin/python -m unittest discover -q`: 1,112 tests passed; two skips.
  - `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: 671 passed and 2,230 subtests; one opt-in real Linux qualification skipped.
  - `./.venv/bin/python -m pytest tests/test_services -v --tb=short`: 1,232 passed and 2,248 subtests.
  - `./.venv/bin/python -m pytest tests/test_infra_automation -v --tb=short`: 393 passed and 1,311 subtests.
  - `bash scripts/ci-local.sh`: pass; all 10 registered directories (2,558 unittest tests), plus 8 prompt-injection pytest tests and 96 subtests, skill harness, compile, dependency, lint/format and Bandit gates. New tests are included in the pre-existing dedicated automation GitHub shard and local target registration.
  - `python app.py` in a temporary pinned-dependency environment: health 200 and clean shutdown. `git diff --check`: pass.
- **UI validation not applicable.** No React/browser surface changed. No production collector, receiver, exact-plan grant, action runtime or release qualification is claimed.
- **Definition of Done: PASS (29/29 applicable checklist items).** All story task/verification boxes are complete. BMad Help recommends `[CR] bmad-code-review` in a fresh context. Implementation is ready for review; final reviewer must verify branch compliance, push and optionally open the PR to `develop` before marking the story done. No remote push or PR is claimed here.

## Senior Developer Review (AI)

- **Outcome:** Approved after fixes; no unresolved high/medium finding.
- **Reviewer/date:** Codex native three-layer adversarial review, 2026-10-27.
- **Scope:** Story 16.6 against its original8e4cf16 baseline, synchronized with current `origin/develop` 2656949. Epic 17 append-only planning was preserved; no cross-epic runtime dependency was introduced.
- **Disposition:** Six fixes (four P2 behavior defects, one P3 direct-input boundary, one P3 type-contract follow-up), zero decision-needed, zero deferred story findings, two dismissed hypotheses backed by real SQLite COMMIT and spawned-output-adoption tests. All findings above are checked off.
- **Acceptance:** AC1–7 satisfied for uploaded/synthetic advisory evidence. R1 adds a fixed v1 projection from durable facts, without new writes or frozen report/engine DTO changes. R2/R3 retain readable bounded links and complete report detail. R4 accounts for actual snapshot copies with authorization before filesystem access. R5/R6 tighten input/type contracts.
- **Verification:** Provider fallback isolated using `LLM_API_BASE=http://127.0.0.1:9`; `pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: 672 passed /2,233 subtests /one opt-in skip; `pytest tests/test_services -v --tb=short`: 1,232 passed /2,248 subtests; `pytest tests/test_infra_automation -v --tb=short`: 416 passed /1,318 subtests. Root `unittest discover -q`: 1,136 tests /two skips. Full `bash scripts/ci-local.sh` passed all 10 directories /2,582 tests plus prompt/skill/compile/pip/Bandit/Ruff gates. Review-focused 63 tests /450 subtests and final type-alignment 31 tests /405 subtests passed.
- **Static analysis:** Repo-wide Ruff lint/format pass (424 Python files). Exact CI mypy comparison against a clean current-develop archive: 308 existing diagnostics versus 314 baseline, zero new normalized diagnostics; CI intentionally keeps that legacy gate advisory. Existing unrelated Bandit medium B104 remains outside this slice; high/high gate passes.
- **Production runtime:** Docker build from a tracked-source archive passed. Final source image e3cb6df health 200, preflight/evidence OpenAPI present, Python 3.11, non-root, no Node runtime; temporary container removed.
- **Git Flow:** `feature/16-6-uploaded-artifact-preflight`; review fixes b0ccb68, base synchronization e62f43b, type alignment e3cb6df. Push/PR closure follows this evidence commit; final remote outcome is reported by the workflow.
- **Limits:** UI validation not applicable. No new dependency; no production collector/custody/receiver, exact-plan grant, host-power-loss or release qualification claim. Fixed known-pattern corpus does not promise universal secret detection.
- **BMad Help:** Next is scoped readiness/story refinement for 16.7 (`bmad-create-story`) in a fresh context. No next story is started here.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/16-6-uploaded-artifact-preflight-and-report-linkage.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/story-implementation-status-map.md`
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-27-story-16-6.md`
- `_bmad-output/project-context.md`
- `api/routes/infra_automation.py`
- `api/schemas.py`
- `app.py`
- `docs/infra-automation/engine.md`
- `docs/infra-automation/preflight.md`
- `docs/schemas/report-v2.md`
- `docs/verification/infra-automation/16-6/results.md`
- `infra_automation/analysis_context.py`
- `infra_automation/artifact_intake.py`
- `infra_automation/claims.py`
- `infra_automation/coordinator.py`
- `infra_automation/local_workers.py`
- `infra_automation/preflight_contracts.py`
- `infra_automation/preflight_evidence.py`
- `migrations/versions/033_add_infra_preflight.py`
- `models/database.py`
- `models/repositories/infra_automation_reports.py`
- `models/tables.py`
- `services/analysis_service.py`
- `services/artifact_snapshot_service.py`
- `services/infra_automation_engine_service.py`
- `services/infra_automation_preflight.py`
- `services/infra_automation_service.py`
- `services/project_service.py`
- `tests/fixtures/infra_automation/preflight_v1/sensitive-corpus.json`
- `tests/test_api/test_infra_automation_preflight.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_identity_migration.py`
- `tests/test_infra/test_infra_automation_engine_migration.py`
- `tests/test_infra/test_infra_automation_workflow_migration.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_infra/test_project_membership_migration.py`
- `tests/test_infra_automation/test_artifact_intake.py`
- `tests/test_infra_automation/test_engine_app_lifespan.py`
- `tests/test_infra_automation/test_engine_coordinator.py`
- `tests/test_infra_automation/test_preflight_atomic_recovery.py`
- `tests/test_infra_automation/test_preflight_compatibility.py`
- `tests/test_infra_automation/test_preflight_evidence.py`
- `tests/test_infra_automation/test_preflight_limits.py`
- `tests/test_infra_automation/test_preflight_read_projection.py`
- `tests/test_infra_automation/test_preflight_repository.py`
- `tests/test_infra_automation/test_preflight_service.py`

## Change Log

- 2026-10-27: Implemented authenticated uploaded-artifact preflight and immutable relational report linkage through the shared fenced analysis pipeline. Preserved report v2/provenance v1 and advisory-only semantics; added scoped migration, corpus/consumer/runtime proofs and operator documentation. Fixed BOM/state screening, SQL replacement/reparenting, linked snapshot mutation, spawned app bootstrap and reload-safe authorization guard findings.

- 2026-10-27: Completed adversarial review, resolved six findings, proved commit rollback/output adoption, synchronized current develop, and passed final validation.
