# Story 12.3: Connector Credential Handling and Redaction Audit

Status: review

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a self-hosted operator,
I want connector credentials and sensitive context protected,
So that topology, incident, scanner, and workflow integrations do not leak secrets.

## Acceptance Criteria

1. Given connector settings or imported context include credentials or sensitive references, When validation, logging, report rendering, API output, or docs examples are generated, Then credentials are redacted or referenced securely. And unsafe persistence, prompt inclusion, and telemetry exposure are covered by tests or documented controls.

### Requirement Traceability

- Primary PRD requirements: Epic 12 coverage: ADM-01..02, NFR-SEC-01..07, NFR-OPS-01..06, GOV-06..07, DOC-11, DOC-12.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 12 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

- [x] Run Compose browser validation of imported connector context and rendered incident/report surfaces. (AC: 1)

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 12 / Story 12.3 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

Codex, with native subagents for bounded connector slices and independent verification.

### Debug Log References

- `/private/tmp/story12-3-core-red.log`, scoped audit probes and new connector regression suites: reproduced credential leakage before changes.
- `/private/tmp/story12-3-callback-red.log`: callback metadata/link regressions before repair.
- `/private/tmp/story12-3-filename-red.log`: regression evidence for distinct screened source identities.
- `/private/tmp/story12-3-ci-close.log`, `story12-3-unittest-close.log`, `story12-3-shard-close.log`: final Python verification.
- `/private/tmp/story12-3-browser-close.log`: final Compose Playwright verification, 17 passed.
- `/private/tmp/story12-3-constructor-search.log`: repository-wide ScannerImportValidationError construction search.
- Restart recovery verified existing branch/diff and completed validations before continuing. Independent checks found and repaired scanner validation ordering, valid filename dispatch, unsupported suffix echo and source-alias collisions.

### Completion Notes List

- Audited topology, Terraform/Kubernetes discovery, incident/scanner imports, GitHub App/scaffold flows, configured logs, report/prompt screening and documented telemetry controls against AC1.
- Reused the shared content screen, adding configured connector credential collection and OAuth code/state/session/signature query screening. Secure credential-file paths remain references; no real credential files were read. Moved bounded reference decoding to the shared boundary and retained the provider-compatible wrapper.
- Terraform identity projection honors sensitivity masks/paths; Kubernetes credential selectors are excluded from persisted identity keys while local matching remains available. Unsafe operational source references and graph IDs reject before dispatch; public topology status, cache, preview/persistence and legacy reads are screened.
- Imported incident/scanner raw input supplies local sensitive values before field projection, validation and persistence. Declared redaction flags are not the only control. YAML/frontmatter errors expose syntax locations without source excerpts. SARIF drops raw snippets and arbitrary region keys, retaining validated coordinates.
- Preserve stable scanner identity digests and distinct incident source aliases without copying unsafe values. Incident aliases retain only sanctioned Markdown/YAML/JSON suffixes; unsupported suffixes cannot restore credentials to error output.
- GitHub authenticated transport requires HTTPS and safe same-origin GET redirects. Raw downloads use the configured Contents API instead of forwarding tokens to returned URLs. Fixed errors suppress upstream bodies, CLI stderr and command arguments; scaffold/config URLs reject credentials before publication. Callback HTML screens configured/transient values and unsafe link schemes; public webhook responses use shared screening.
- Added operator audit matrix and updated all supported connector/integration guides. Documented credential scope, file references/permissions, temporary signing-file lifecycle, revocation, proxy/tracing controls and legacy retention limits. No new dependency, schema field or scoring/advisory semantics change.
- Independent verification rechecked concrete import edge cases and GitHub trust behavior; all reported blockers resolved with no new concrete regression.

### Implementation Plan

1. Establish existing connector protections and reproduce missing boundaries with synthetic, isolated regressions.
2. Repair shared screening plus bounded topology, import and workflow service boundaries using existing helpers and secure references.
3. Cover persisted/public/legacy data, validation/logging and prompt/output paths; preserve identity, scope and healthy input behavior.
4. Update operator controls and verify through the real Python CI lanes and production Compose app before review.

### Validation

- `bash scripts/ci-local.sh`: passed, 1,715 tests in all nine test directories; includes Ruff, compilation, dependency consistency, Skill harness, prompt-injection tests and configured Bandit gate.
- `./.venv/bin/python -m unittest discover -q`: passed, 480 tests, one optional live-provider test skipped.
- `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: 418 passed, 134 subtests passed.
- Scoped connector checks: 78 topology tests, 61 GitHub service tests, 134 final incident/scanner/import tests, shared screening and callback/API tests passed. Test fixtures use synthetic data, temporary DB/files and early runtime cleanup.
- `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`: passed; 289 Python files formatted. `npm run ui:typecheck` and `git diff --check`: passed.
- Compose production build and health check, API fixtures, `BASE_URL=http://localhost:8080 PROVIDER_ADMIN_TEST_MUTATION=1 npm run test:ui-review`: 17 passed. `/app/data` was overridden to disposable tmpfs; original operator volumes were never mounted. Screenshots captured from root `/incidents` and `/reports/{id}` routes, then Compose stopped.
- One existing unrelated medium Bandit B104 sample-data finding remains; configured high-severity gate passes and changed files add no finding. Live remote connector/provider credentials were not exercised; transport tests use synthetic mocks. Local VoiceOver lane is not applicable per project memory.
- Scalar/API model fields unchanged. Optional ScannerImportValidationError constructor keyword was searched across the repository; affected GitHub shard passed. External Marketplace action implementation remained outside this repository.
- Definition of Done: PASS. No pending story task or known test error. `bmad-help` recommends `bmad-code-review` next in a fresh context; reviewer owns final story closure/push/PR.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/12-3-connector-credential-handling-and-redaction-audit.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `api/routes/github_app.py`
- `config.py`
- `docs/github-action.md`
- `docs/github-app-self-hosted-setup.md`
- `docs/github-app.md`
- `docs/incident-import.md`
- `docs/kubernetes-live-state-connector.md`
- `docs/scanner-imports.md`
- `docs/security/connector-credential-boundaries.md`
- `docs/security/secrets-and-artifact-boundaries.md`
- `docs/terraform-state-connector.md`
- `docs/verification/story-12-3/connector-incidents.png`
- `docs/verification/story-12-3/connector-report.png`
- `frontend/e2e/connector-security.spec.ts`
- `integrations/github/app_service.py`
- `integrations/github/init_service.py`
- `llm/providers.py`
- `services/content_security.py`
- `services/incident_import_service.py`
- `services/incident_service.py`
- `services/scanner_import_service.py`
- `services/topology_service.py`
- `tests/test_api/test_github_app.py`
- `tests/test_services/test_connector_content_security.py`
- `tests/test_services/test_connector_import_security.py`
- `tests/test_services/test_github_credential_security.py`
- `tests/test_services/test_topology_credentials.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.

- 2026-10-06: Implemented connector credential/redaction guards, isolated regressions, operator controls and composed-app browser evidence; moved story to review.
