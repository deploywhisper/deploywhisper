# Story 12.2: Provider Settings Administration

Status: review

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a platform admin,
I want to configure narrative-provider settings through DeployWhisper's provider adapter boundary,
So that external or local model usage is explicit, local-first, and safe.

## Acceptance Criteria

1. Given an admin opens provider settings, When they configure local-only mode or an external provider, Then settings are validated through the DeployWhisper-owned provider adapter boundary. And provider credentials are read from environment-backed configuration or equivalent secure references, not stored unsafely.
2. Given provider configuration is missing, invalid, or disabled by local-only mode, When narrative generation is requested, Then deterministic analysis still completes and the report records degraded or disabled narrative status.

### Requirement Traceability

- Primary PRD requirements: ADM-01, ADM-02, NFR-SEC-01, NFR-SEC-02, NFR-SEC-03.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 12 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Implement and verify acceptance criterion 2. (AC: 2)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

## Dev Notes

### Epic Context

- Epic: 12. Security and Supply Chain Hardening
- Epic goal: Make the project trustworthy to install, operate, and contribute to.
- Epic coverage: ADM-01..02, NFR-SEC-01..07, NFR-OPS-01..06, GOV-06..07, DOC-11, DOC-12

### Architecture and Product Guardrails

- Preserve DeployWhisper's local-first raw artifact boundary: raw IaC, scanner artifacts, incident exports, and sensitive context stay in the user's infrastructure by default.
- Preserve the advisory-first core. Optional adapters may interpret report outputs, but canonical report semantics remain advisory unless explicit story scope says otherwise.
- Reuse the shared analysis core and service layer before adapting UI, API, CLI, GitHub, or future workflow surfaces.
- Keep Evidence Law behavior intact: no high or critical finding without deterministic evidence.
- Keep project/workspace scope explicit for reports, incidents, topology, outcomes, feedback, scanner imports, and connector-related data.
- Do not introduce new dependencies unless the active story explicitly requires and justifies them.

### Source Tree Guidance

- API routes belong under `api/routes/` and should use existing `ApiRoute` / `ApiError` envelope patterns.
- Shared orchestration belongs in `services/`; parsers normalize input, analysis modules score/derive risk, and surfaces adapt outputs.
- UI work belongs under `frontend/src/screens/` and `frontend/src/components/`, following the existing retired Python UI composition style.
- CLI behavior belongs under `cli/` and must call the same service-layer paths as UI/API flows.
- Persistence work belongs under `models/` with Alembic migrations when schema changes are required.
- Documentation required by a story should be updated in the same workstream.

### Testing Requirements

- Use standard-library `unittest` in the existing `tests/test_*` layout.
- Add focused regression tests for the layer changed by the story before broad refactors.
- For Python changes, run `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, and `./.venv/bin/python -m unittest discover -q` before closing implementation.
- Use `bash scripts/ci-local.sh` for broader or cross-layer changes.

### Project Structure Notes

- Follow the current repository shape documented in `_bmad-output/project-context.md` and `AGENTS.md`.
- If implementation reveals a conflict between this story and the current code baseline, keep the smallest compatible change and update the story notes rather than silently drifting from the PRD.

### References

- `_bmad-output/planning-artifacts/epics.md` - source Epic 12 / Story 12.2 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-6 (Codex), with native subagents for bounded fallback tests and independent verification.

### Debug Log References

- `/private/tmp/story12-2-red.log`: confirmed provider save/local-only/environment-key regressions fail before implementation.
- `/private/tmp/story12-2-credential-red.log`: confirmed credential-in-profile regressions fail before the boundary fix.
- `/private/tmp/story12-2-ci-closing.log`: closing local CI output; all nine test-directory runs passed (1,666 tests total), with one optional live-provider skip.
- `/private/tmp/story12-2-shard-closing.log`: final GitHub API/CLI/infra shard, 415 passed and 132 subtests passed.
- `/private/tmp/story12-2-unittest-closing.log`: final root unittest discovery, 475 tests, OK (one optional live-provider test skipped).
- `/private/tmp/story12-2-browser-closing.log`: composed-app Playwright, 15 passed.
- `.omx/evidence/story-12-2/provider-settings.png`: screenshot captured from the composed app.
- Earlier browser runs exposed test selector/error-copy assumptions; corrected tests to assert the existing accessible-role selectors and generic UI error contract.
- An earlier CI process overlapped signature edits and failed with stale loaded code; closing validation runs use the final stable source.

### Completion Notes List

- Added offline profile-shape checks to the existing provider adapter boundary before persistence and provider invocation. Rejected unsupported providers, blank models, unsafe URL shapes, invalid timeouts, hosted/local-only conflicts, and credentials in profile fields without replacing the active profile.
- Preserved environment-backed credentials and temporary validation-only keys; screen both independently, including when a temporary key differs from the environment key. No database schema, new dependency, or provider SDK change.
- Simplified the settings route by removing provider-specific local-mode rewriting; the shared boundary now enforces capabilities and returns `400 invalid_provider_settings` for invalid profiles.
- Live connectivity failures still permit saving structurally valid profiles and deterministic analysis. Missing keys are rejected before live SDK construction. Health checks reject invalid stored profiles without network probes.
- Added three analysis/persistence integration regressions proving missing credentials, invalid legacy profiles, and hosted providers disabled by local-only mode preserve deterministic findings and record degraded narrative metadata.
- Reused the approved settings screen unchanged; Playwright verifies rejected saves preserve local configuration, validates missing-key warning behavior, and captures a screenshot. The existing UI uses generic error copy for HTTP failures; detailed validation reasons remain in the API error envelope.
- Updated README operator guidance and added provider administration documentation. Independent verification found and rechecked credential boundary edge cases; no remaining concrete blocker.

### Implementation Plan

1. Lock save-time validation and environment credential behavior with failing service/API regressions.
2. Validate profile structure through the provider boundary before persistence and invocation; preserve deterministic fallback and environment credential resolution.
3. Add persistence regressions, operator documentation and composed-app browser coverage.
4. Run local CI, the GitHub API/CLI/infra shard, unittest discovery, typecheck, security checks and Playwright; record evidence and hand off to BMad code review.

### Validation

- `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`: passed; 285 Python files formatted.
- `./.venv/bin/python -m unittest discover -q`: passed, 475 tests (one optional live-provider test skipped).
- `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: passed, 415 tests plus 132 subtests.
- `bash scripts/ci-local.sh`: passed; all nine test directories passed (1,666 tests total), with one optional live-provider skip; includes all test directories, compilation, dependency consistency, Skill harness, injection suite, Ruff and Bandit.
- `npm run ui:typecheck`: passed.
- `docker compose up -d --build`, health check, API setup, `BASE_URL=http://localhost:8080 npm run test:ui-review`, screenshot capture, `docker compose down`: passed, 15 browser tests. Restored original Compose Ollama defaults after setup and retained the data volume.
- Bandit reports one existing medium B104 finding in unrelated `services/sample_incident_pack.py`; configured high-severity gate passes and changed files introduce no finding.
- Live hosted-provider credentials/connectivity were not exercised; synthetic/injected clients keep regression tests deterministic. Local VoiceOver lane is not applicable per project memory.
- No constructor/schema contract changed; repository direct constructors were inspected. Definition of Done: PASS; all acceptance criteria, story tasks and validation gates satisfied. Next workflow from `bmad-help`: `bmad-code-review` in a fresh context; reviewer owns final push/PR closure.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/12-2-provider-settings-administration.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `api/routes/settings.py`
- `llm/providers.py`
- `services/settings_service.py`
- `docs/security/provider-settings-administration.md`
- `frontend/e2e/provider-administration.spec.ts`
- `tests/test_api/test_settings.py`
- `tests/test_llm/test_providers.py`
- `tests/test_services/test_settings_service.py`
- `tests/test_services/test_provider_administration_fallback.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.

- 2026-10-05: Implemented provider administration validation and credential screening, deterministic degraded-report regressions, operator docs, and composed-app browser coverage.
