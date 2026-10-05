# Story 12.2: Provider Settings Administration

Status: done

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

### Review Findings

- [x] [Review][Patch] Reject whitespace/control characters in provider endpoints before persistence [llm/providers.py:93].
- [x] [Review][Patch] Screen percent-decoded model/endpoint values for recoverable credentials [llm/providers.py:112].
- [x] [Review][Patch] Preserve environment-source settings when browser tests restore global configuration [frontend/e2e/provider-administration.spec.ts:43].
- [x] [Review][Patch] Keep browser validation local when hosted credentials are configured [frontend/e2e/provider-administration.spec.ts:34].
- [x] [Review][Patch] Restore reloaded configuration/service modules after fallback test cleanup [tests/test_services/test_provider_administration_fallback.py:28].
- [x] [Review][Defer] Settings UI describes temporary validation as lasting a session [frontend/src/screens/Settings.tsx:74] — deferred, pre-existing; runtime and operator docs correctly scope it to one request.
- [x] [Review][Defer] Generated Source Tree Guidance references retired Python UI style — deferred, pre-existing; mandatory project context specifies React.

### Re-review Findings

- [x] [Review][Patch] Screen every configured provider credential, including fallback and secondary aliases [services/settings_service.py:396].
- [x] [Review][Patch] Reject recoverable credentials hidden by nested percent encoding [llm/providers.py:124].
- [x] [Review][Patch] Validate malformed host authorities before saving provider settings [llm/providers.py:101].
- [x] [Review][Patch] Keep default browser tests from overwriting inactive provider profiles; isolate successful/temporary-key saves [frontend/e2e/provider-administration.spec.ts:43].
- [x] [Review][Patch] Register fixture cleanup before module reload or database initialization can fail [tests/test_services/test_provider_administration_fallback.py:42].
- [x] [Review][Patch] Correct deterministic-only guidance and clarify surrounding endpoint whitespace normalization [docs/security/provider-settings-administration.md:31].
- [x] [Review][Patch] Prevent invalid legacy provider credentials from leaking into fallback/report metadata [llm/narrator.py:339] — reproduced on develop too; repaired within AC1's credential boundary.

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
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `docs/verification/story-12-2/provider-settings.png`
- `frontend/e2e/provider-administration.spec.ts`
- `tests/test_api/test_settings.py`
- `tests/test_llm/test_providers.py`
- `tests/test_services/test_settings_service.py`
- `tests/test_services/test_provider_administration_fallback.py`

- `api/routes/health.py`
- `config.py`
- `docs/ci.md`
- `docs/verification/story-12-2/provider-settings-transient-key.png`
- `llm/narrator.py`
- `services/report_service.py`
- `tests/test_llm/test_narrator.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.

- 2026-10-05: Implemented provider administration validation and credential screening, deterministic degraded-report regressions, operator docs, and composed-app browser coverage.

- 2026-10-05: Code review approved after five fixes, deterministic regressions and Compose browser/isolation checks; story/sprint moved to done and deferred documentation issues recorded.

- 2026-10-05: Fresh re-review fixed seven additional credential, endpoint, fixture-isolation and documentation findings; verified full Python and disposable Compose browser lanes.

## Senior Developer Review (AI)

- Date: 2026-10-05
- Reviewer: Codex with independent Blind Hunter, Edge Case Hunter and Acceptance Auditor layers.
- Outcome: **Approve** after fixes; no unresolved high or medium findings.
- Scope: implementation commit `e4e82e8` plus review fixes on `feature/12-2-provider-settings-administration`, compared with `develop`.
- Triage: five actionable findings fixed (one high credential-screening finding, four medium validation/test-isolation findings), two pre-existing low copy/template issues deferred, four candidates dismissed. All review layers completed.
- Fixed: raw whitespace/control endpoint rejection; percent-decoded credential screening in models and endpoints; browser preservation of environment-source settings; localhost-only browser probes with configured credentials; fallback test cleanup restoring environment/configuration/service modules.
- Dismissed: global browser concurrency is already serialized (`workers: 1`, `fullyParallel: false`); hypothetical keyless future adapters are outside the supported provider catalog; profile validation occurs entirely before database writes; environment-source Ollama cannot have `local_mode=false` under the current resolver.
- Independent recheck: 39 provider/fallback tests and 26 subtests passed; acceptance remains satisfied and original edge findings are resolved.
- Validation: focused suite 129 passed, one optional live-provider skip, 140 subtests; API/CLI/infra shard 415 passed and 132 subtests; root unittest 475 tests OK with one optional live-provider skip; local CI all nine test directories passed (1,667 tests total), including lint, repo-wide formatting (285 Python files), compilation, dependency consistency, Skill harness, prompt-injection tests and configured Bandit gate.
- Browser validation: rebuilt Compose app at root SPA URLs, seeded through APIs, full Playwright 15 passed; additional isolated temporary-database runs each passed for environment-source preservation and configured synthetic hosted credentials. Health remained `source=environment` after the first isolated check. Localhost-only successful-save probe covers the configured-key case without hosted network calls. All Compose instances stopped; persistent original data volume retained.
- Evidence: `/private/tmp/story12-2-review-{red,focused,ci,unittest,shard,browser,env-browser,key-browser}.log`; screenshot committed at `docs/verification/story-12-2/provider-settings.png`.
- Limitations: real hosted-provider connectivity remains untested. Existing unrelated medium Bandit B104 sample-data finding remains; no touched-file finding and the configured security gate passes. Two low copy/template issues are recorded in `deferred-work.md`.
- Git Flow: verified compliant feature branch; review fixes and closure record are committed there. Push/PR closure follows this record; no merge is authorized by this review.

## Fresh Re-review (AI)

- Date: 2026-10-05
- Outcome: **Approve after fixes**; no remaining high/medium blocker.
- Scope: PR #129 at `23adf97`, all changes from `develop`, plus the fresh review fixes on the existing feature branch.
- Layers: fresh Blind Hunter (diff only), Edge Case Hunter (reachable paths) and Acceptance Auditor (AC1/AC2 plus context). All completed; independent rechecks found no concrete blocker.
- Fixed seven actionable findings: full configured credential collection including inactive provider keys, fallback and Gemini aliases; bounded nested percent-decoding; DNS/IP authority checks; default browser tests preserving inactive profiles with successful writes isolated behind `PROVIDER_ADMIN_TEST_MUTATION=1`; fixture cleanup registered before reload/init failure; correct narration-only operator guidance; credential-safe legacy fallback and report metadata.
- Credential collection lives in `config.py` and is reused by the provider/service boundary. Invocation and prompt/response screening, settings/health serialization and narrative/report persistence/read boundaries use the same configured values. Healthy metadata and credential precedence are preserved.
- Legacy metadata exposure was also reproduced on `develop`; it was repaired within AC1 rather than leaving that credential leak on the new degraded-result path. No data migration, schema/constructor change, scoring-rule change, dependency addition, or production React change.
- Regression verification: fresh focused suite 137 passed, one optional live-provider skip, 185 subtests; root unittest 478 tests OK with one optional live-provider skip; affected API/CLI/infra shard 416 passed and 134 subtests; full local CI nine directories, 1,675 tests total, including configured security gate, compilation, dependency checks, Skill harness and prompt-injection lane. Ruff lint and repository-wide formatting passed (285 Python files); frontend typecheck passed.
- Browser verification: production Compose build at `http://localhost:8080`, all `/app/data` test storage overridden to disposable tmpfs. Default provider run passed and skipped the opt-in mutation test; direct SQL comparison confirmed every active, inactive and legacy provider setting stayed unchanged (background maintenance rows excluded). Full opt-in suite passed all 16 tests with keys absent; additional configured synthetic key run passed both provider tests, proving temporary key validation and environment re-resolution without persistence or hosted calls. The existing report seed requires `/app/data/deploywhisper.db`; an initial alternate-basename fixture was corrected and the full suite rerun successfully. Original persistent data volume was never mounted by these fixtures; all disposable instances stopped.
- Evidence: `/private/tmp/story12-2-rereview-{shape-red,metadata-red,final-focused,ci,unittest,shard,default-browser,browser-final,key-browser,profile-preservation}.log`. Screenshots: `docs/verification/story-12-2/provider-settings.png` and `provider-settings-transient-key.png`.
- Limitations: real hosted-provider connectivity remains untested. The unrelated existing medium Bandit B104 sample-data finding remains; no touched-file finding. The two prior low copy/template issues remain deferred; no new deferral or human decision was required.
- Git Flow: existing `feature/12-2-provider-settings-administration` verified, fixes and this record committed there, PR #129 targets `develop`; remote closure/checks recorded in runtime state and the PR description.
