# Story 16.6: Uploaded Artifact Preflight And Report Linkage

Status: backlog
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

- [ ] **Intake/screening owner** (AC1/2/4)
  - [ ] Owned write scope: `services/intake_service.py, services/content_security.py, services/submission_manifest.py, infra_automation artifact intake module (new)`.
  - [ ] Reuse build_parse_batch, total_upload_bytes, is_sensitive_file, trusted_relative_artifact_path and redact_value/redact_text; enforce aggregate bytes and filename/content classification. Screen filenames, metadata/errors and bounded stream buffers before storage; reject forbidden artifacts and document known pattern limits rather than universal redaction.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Provenance/link persistence owner** (AC3/4/7)
  - [ ] Owned write scope: `infra_automation/contracts.py, models/tables.py, models/repositories/infra_automation_reports.py (new), next migration`.
  - [ ] Create only run/report/artifact-manifest immutable links and optional version-1 provenance fields needed here. Record source variant, project/attempt, command/argv digest, source SHA where available, times/exit status, raw-local versus sanitized digest and redaction version. Raw-local digest is metadata, not uploaded plan bytes. Use authenticated synthetic envelopes; real custody/collector admission remains 16.14.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Shared-analysis adapter owner** (AC1/4/5/6/7)
  - [ ] Owned write scope: `services/infra_automation_service.py, services/analysis_service.py, services/report_service.py, api/routes/infra_automation.py`.
  - [ ] Call analyze_uploaded_files through 16.5 bounded worker, preserving intake→parse→assess→blast-radius→rollback→incident→narrative→persist ordering. Validate returned immutable report/link and compute eligibility outside advisory scoring. Reuse canonical go/caution/no-go plus typed insufficient-context/error flags; unknown values fail closed. Add scoped linked read guards from 16.2.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Cross-surface/consumer proof owner** (AC1–7)
  - [ ] Owned write scope: `tests/test_infra_automation, tests/test_services, tests/test_api, tests/test_cli, tests/test_analysis, docs/infra-automation/preflight.md (new)`.
  - [ ] Run upload vertical slice, secret corpus/chunk boundaries, tampered digests/stale attempts, cross-surface parity/Evidence Law, AI-off/narrative failure and v1/v2/provenance compatibility. Search all changed constructor instantiations and lock API/CLI fixtures. Regression-test linked shared/export/delete routes; no collection/receiver success claim.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.

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
