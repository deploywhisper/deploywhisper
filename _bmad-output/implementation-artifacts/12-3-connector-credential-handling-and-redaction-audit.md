# Story 12.3: Connector Credential Handling and Redaction Audit

Status: done

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

### Review Findings

The initial review repaired seven grouped findings. The fresh review found five additional patches and one pre-existing scope gap; the fix record below records their resolution and final validation.

- [x] [Review][Patch] Preserve full Terraform/Kubernetes sensitivity context before topology projection, including discarded-field and cross-resource echoes [services/topology_service.py:1094].
- [x] [Review][Patch] Preserve batch incident sensitivity through sibling content and import/reindex scope-validation errors [services/incident_import_service.py:120].
- [x] [Review][Patch] Keep incident source identity stable across content changes and distinct across plain-document sources [services/incident_import_service.py:481].
- [x] [Review][Patch] Preserve distinct scanner source filenames and screen encoded legacy tool/rule labels [services/scanner_import_service.py:306].
- [x] [Review][Patch] Decode nested query credential values before protecting sibling echoes [services/content_security.py:238].
- [x] [Review][Patch] Strengthen rendered connector coverage and enforce disposable fixture controls [frontend/e2e/connector-security.spec.ts:4].
- [x] [Review][Patch] Cover rejected POST redirects and preservation of all supported SARIF coordinates [tests/test_services/test_github_credential_security.py].
- [x] [Review][Defer] Scanner imports are standalone API evidence and are not automatically attached to analysis reports — deferred, pre-existing; recorded in `deferred-work.md`. Browser coverage now verifies actual incident matching and scanner import identity separately.

### Re-review Findings — 2026-10-06

- [x] [Review][Patch][P1] Carry artifact-local sensitivity into every retained topology reference check [services/topology_service.py:306]. `_screen_topology_payload` omits `sensitive_values` when decoding import metadata, labels, owners and resource keys. A synthetic three-times percent-encoded `opaque-review/value!` survives in retained labels/owners/keys despite being supplied as a sensitive value. Pass the same context through decoding; regress encoded echoes from discarded raw fields.
- [x] [Review][Patch][P1] Screen scanner tool/rule labels before persistence [services/scanner_import_service.py:377]. Only artifact URI/location receive contextual reference decoding in `safe_parsed`; tool name, rule ID and rule name remain lexically screened. Repository-call capture proves five-times percent-encoded `SynthValue/Case!` reaches evidence columns and import tool names, while the source reference is screened. Decode/screen these labels before writes and test both stored rows and returned/listed output.
- [x] [Review][Patch][P2] Collect form-decoded OAuth query credentials for sibling screening [services/content_security.py:243]. `unquote` preserves `+`; a callback `?state=opaque+oauth+state` is redacted but its sibling `opaque oauth state` remains visible. Retain existing literal/percent variants and collect standard form-decoded variants, with sibling regression coverage.
- [x] [Review][Patch][P2] Screen normalized scanner scope-error echoes [services/scanner_import_service.py:359]. The new exception wrapper screens raw sensitive values only; a detected `Opaque Review/Value!` does not screen the resolver's `project_key=opaque-review-value`. Include lowercased/normalized variants as incident import scope errors already do, without weakening scope validation.
- [x] [Review][Patch][P2] Avoid loading full incident archives to recover source aliases [services/incident_import_service.py:585]. New alias lookups use `list_incident_records`, which selects every column including content; project-only calls also load workspace rows before Python filtering. The same pattern occurs in `services/incident_service.py:373`. Query distinct source names with explicit scope instead of hydrating complete incident documents for each import/ingest.
- [x] [Review][Patch][P2] API permission prechecks and direct incident ingestion can bypass contextual scope-error screening [api/routes/incidents.py:216] — fixed in this follow-up; originally pre-existing. An isolated TestClient reindex request with a valid project ID, an unknown key echoed from a named password in imported content, returns that key verbatim before service screening. Equivalent scanner permission prechecks exist at `api/routes/scanner_imports.py:182,282`; direct ingestion resolves scope without a contextual exception wrapper. Baseline comparison confirms these paths were already exposed. Resolved with request-context error screening that preserves authorization order, covers configured/normalized echoes and is verified through isolated API/service regressions; resolution recorded in `deferred-work.md`.

### Post-fix Review Findings — 2026-10-06

- [x] [Review][Patch][P1] Include filename credentials in incident batch sensitivity before aliasing [services/incident_import_service.py:135]. Both import and reindex collect content only. A filename `password='OpaqueReviewValue!'.json` is correctly aliased, but its credential echoed in a valid incident title/root cause survives storage and returned incident data. Filename-only values can also escape direct batch scope errors. Use the existing filename-plus-content submission collector across the complete batch before validation/projection. This is an incomplete AC1 boundary in the new guards; the underlying exposure also exists at the story baseline.
- [x] [Review][Patch][P1] Screen bounded repeatedly encoded credentials in incident/scanner narrative fields before persistence [services/incident_import_service.py:606; services/scanner_import_service.py:376]. A named raw password `opaque-review/value!` is discarded, but its five-times percent-encoded echo survives incident title/root cause and SARIF message screening, database writes, import results and list responses. Reference/label fields now receive contextual decoding; retained narrative strings do not. Extend bounded contextual screening to those retained fields and cover stored/listed output plus harmless encoded prose. This is another incomplete AC1 guard, not a claim that this story introduced the underlying exposure.

### Fourth Review Findings — 2026-10-06

- [x] [Review][Patch][P1] Retain submission sensitivity when incident numeric fields become text [services/incident_import_service.py:817; services/content_security.py:481]. A named numeric password `739241` is detected, but numeric title/root-cause echoes bypass the metadata-only numeric screen. Incident normalization then casts them to strings after the discarded credential context is lost. Both import and reindex persist and return the credential through titles/content/list output while advertising `redacted`. Screen normalized retained incident text with the original submission sensitivity before persistence and add storage/result/list regressions for both operations; preserve legitimate numeric identifiers/coordinates. This is a remaining AC1 coverage gap with baseline exposure, not an introduced regression.

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
- Development Definition of Done: PASS. Review was handed off to `bmad-code-review`; final closure is recorded below.

### Code Review Record — 2026-10-06

- `bash scripts/ci-local.sh`: passed, 1,726 tests across all nine directories, plus the deterministic Skill harness/prompt checks and configured static-analysis gate. Final logs: `/private/tmp/story12-3-review-ci-final.log`, `story12-3-review-unittest-final.log`, `story12-3-review-shard-final.log`, `story12-3-review-browser-final.log`.

- Applied seven grouped findings: full raw snapshot sensitivity before projection; cross-file incident and scope-error screening; stable incident aliases including project-wide reindex; distinct scanner filenames and encoded legacy labels; nested query decoding; disposable browser fixtures with actual report match assertions; POST redirect and SARIF coordinate regressions.
- Reused shared screening and source alias helpers. No new dependency, schema field, production React flow or scoring rule. Full raw data stays local and is discarded after sensitivity collection.
- Final independent acceptance/edge probes confirm nonidentity, cross-resource and marked outer `index_key` credential echoes are screened, batch scope errors stay bounded, and alias reuse preserves explicit workspace isolation.
- `./.venv/bin/python -m unittest discover -q`: passed, 480 tests with one optional live-provider skip. API/CLI/infra pytest shard: 418 passed plus 134 subtests. Ruff check/format (289 files), TypeScript and diff checks pass.
- Rebuilt production Compose app with `/app/data` on disposable tmpfs and default DB filename; health passed. `BASE_URL=http://localhost:8080 PROVIDER_ADMIN_TEST_MUTATION=1 CONNECTOR_SECURITY_TEST_DISPOSABLE=1 npm run test:ui-review`: 17 passed. Screenshot evidence includes the matched redacted incident on `/reports/{id}`. Compose stopped; operator volumes never mounted.
- `bmad-help` next-step check: Story 12.4 is already `ready-for-dev`; use `bmad-dev-story` for its existing story in a fresh context after this PR. Epic 12 remains in progress.
- Residual limits: live remote credentials were not exercised; custom opaque values/encodings need manual screening; legacy stored rows/backups need operator retention cleanup. The pre-existing medium Bandit B104 sample-data finding remains outside this diff; configured high-severity gate passes. Scanner automatic report attachment remains a separate existing integration gap.

### Fresh Code Review Record — 2026-10-06

- Reviewed commit range `6bf57d8..2020f41` on `feature/12-3-connector-credential-redaction`, excluding unrelated analytics snapshot churn. Scope: 33 files, 2,992 added / 194 removed text lines, plus three screenshots. Loaded the story, project context and relevant PRD/architecture/epic security requirements.
- Completed all three independent BMad layers: diff-only Blind Hunter, repository-aware Edge Case Hunter and Acceptance Auditor. Two initial role launches failed due to unavailable configured model; replacement agents completed all layers successfully.
- Triage: zero decision-needed, five patch findings, one grouped pre-existing deferral, two dismissed candidates. Arbitrary dictionary-key screening is unchanged from baseline and the proposed arbitrary scanner properties do not survive the adapter allowlist; encoded browser assertions are required regression coverage for the substantive patches rather than a separate production defect.
- Synthetic in-memory probes reproduced topology context loss, OAuth `+` decoding and normalized scanner scope errors. Independent repository-call capture reproduced scanner label persistence without database writes. The API deferral used an isolated temporary DB/TestClient and baseline comparison. Archive lookup was traced to the repository's full `select(IncidentRecord)` query. No operator data or shared artifact directories were modified.
- `./.venv/bin/python -m pytest tests/test_services/test_connector_content_security.py tests/test_services/test_connector_import_security.py tests/test_services/test_github_credential_security.py tests/test_services/test_topology_credentials.py tests/test_api/test_github_app.py -q --tb=short`: **56 passed, 62 subtests passed**, 26 existing Alembic configuration deprecation warnings. Log: `/private/tmp/story12-3-rereview-tests.log`.
- `./.venv/bin/ruff check .`: passed. `./.venv/bin/ruff format --check .`: passed, 289 files already formatted. `git diff --check`: passed. This run changes review/tracking documents only; no production code was changed, no full local CI or Compose/browser rerun was performed. Earlier browser evidence remains historical and does not cover the newly identified encoded cases.
- Story and sprint status reopened to `in-progress`; patches remain review action items. No commit/push was performed because review follow-up remains open. Existing PR: https://github.com/deploywhisper/deploywhisper/pull/130. `bmad-help` next step is `bmad-dev-story` for Story 12.3 fixes, then fresh `bmad-code-review`; Story 12.4 is not the next closure step while these findings remain open.

### Review Fix Record — 2026-10-06

- Fixed all five fresh-review patches and the previously deferred API/direct-ingestion scope leak. Also closed the two integration follow-ups: manual topology payloads now supply their discarded-field sensitivity, and scope normalization includes configured credentials even when absent from uploads. Independent acceptance verification reproduced the configured-secret API probe as a safe 404 with `[REDACTED]` and preserved `project_not_found`.
- Tests reproduced the failures before repairs. Topology checks cover encoded owner/label/key/import metadata echoes and real validation/save boundaries; scanner tests inspect stored SARIF/Semgrep labels, import tool names, public/listed output, healthy labels, raw identity digests and repeat-import IDs. Scope tests cover incident reindex, both scanner routes, direct ingestion, normalized workspace/project keys, harmless uploads with configured credentials, and denied callers that never enter import or credential collection.
- Alias cleanup plan: lock identity and exact workspace behavior, then replace complete document/status hydration with distinct source-name queries. Implemented SQL-scoped source queries for both incident records and ingestion statuses, including removed-source aliases and explicit project-wide reindex. Reused one shared scope-error helper and deleted the duplicate incident-import implementation. No dependency, schema, scoring, or production React-flow change.
- Final `bash scripts/ci-local.sh`: **1,744 tests passed across all nine directories**, plus deterministic Skill harness/prompt checks, compilation, dependency consistency, Ruff and configured Bandit gate. Log: `/private/tmp/story12-3-fixes-ci-final.log`.
- Final `./.venv/bin/python -m unittest discover -q`: **486 tests passed**, one optional live-provider skip. Final `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: **423 passed + 152 subtests passed**. Logs: `/private/tmp/story12-3-fixes-unittest-final.log`, `/private/tmp/story12-3-fixes-shard-final.log`. Focused configured-credential/API rerun: **14 passed + 36 subtests**; broad topology/shared suite: **122 passed + 108 subtests**; existing scanner suite: **92 passed**.
- `npm run ui:typecheck`: passed. `npm run ui:test`: **56 passed**. Final `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`: passed, **293 files formatted**. `git diff --check`: passed.
- Production Compose frontend/runtime build and health check passed using `/private/tmp/story12-3-fixes-compose.yaml`, with operator volumes removed and writable `/app/data` on disposable tmpfs. The initial fixture mount needed write permissions; sandboxed Chromium launch was also rejected. Corrected the mount, rebuilt the final code, confirmed health, then ran Chromium with approved execution. `BASE_URL=http://localhost:8080 PROVIDER_ADMIN_TEST_MUTATION=1 CONNECTOR_SECURITY_TEST_DISPOSABLE=1 npm run test:ui-review`: **17 passed**. Final log: `/private/tmp/story12-3-fixes-browser-approved.log`. Encoded topology/scanner and scope-error assertions now check plaintext plus five encoding rounds; updated all three screenshot artifacts. Compose stopped and removed after validation; no operator data volume was mounted.
- Remaining limits: live remote credentials were not exercised; the existing medium Bandit B104 finding in sample data remains unchanged and the high-severity gate passes. Existing automatic scanner-to-report attachment remains the separate previously documented integration gap. All fresh-review credential/alias findings are resolved; story/sprint set to `review` on the existing feature branch. Changes remain local and uncommitted. `bmad-help` next step: `bmad-code-review` of the fixes before final Git Flow/PR closure.

### Post-fix Code Review Record — 2026-10-06

- Reviewed the full story from `6bf57d8` through HEAD `2020f41` plus all current working-tree fixes and four new test files; unrelated analytics snapshot excluded. Frozen diff: `/private/tmp/story12-3-rereview-final.diff`, **41 files, 3,976 added / 256 removed text lines**, plus existing screenshot evidence. Full story/project/security requirements supplied to the acceptance layer; blind layer received only the diff.
- All three independent BMad layers completed. Triage: **two actionable P1 patches, zero decision-needed, zero new deferrals, one dismissed candidate**. Marketplace URL omission was dismissed because it derives from the same slug as the validated installation URL. Scanner lexical-sensitive filenames reject at the envelope; no scanner filename persistence claim is made. Prior patched boundaries remain covered; these findings describe missing AC coverage in the audit's newly added guards, with baseline exposures explicitly distinguished from introduced regressions.
- Independent isolated probes verified actual incident import/reindex database titles/content and returned/listed data for filename-only credentials. A git-show baseline importer reproduces the title exposure. Separate isolated probes verified five-round percent-encoded incident/scanner narrative copies in stored records and import/list output. A parent in-memory `redact_value` probe confirmed the named plaintext password is redacted while its encoded message echo remains. Probe files: `/private/tmp/edge_probe_123.py`, `/private/tmp/edge_baseline_123.py`, `/private/tmp/edge_encoded_probe_123.py`. No operator data or shared artifact storage was modified.
- Fresh targeted pytest across connector content/import, GitHub credential/API, topology, scanner/incident review, API scope and source-query regressions: **74 passed + 91 subtests**, 26 existing Alembic configuration warnings. Command: `./.venv/bin/python -m pytest tests/test_services/test_connector_content_security.py tests/test_services/test_connector_import_security.py tests/test_services/test_github_credential_security.py tests/test_services/test_topology_credentials.py tests/test_services/test_scanner_review_regressions.py tests/test_services/test_incident_review_regressions.py tests/test_api/test_connector_scope_security.py tests/test_models/test_incident_source_alias_queries.py tests/test_api/test_github_app.py -q --tb=short`. Log: `/private/tmp/story12-3-review-again-tests.log`.
- Fresh `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`: passed, **293 files formatted**. `git diff --check`: passed. No production code changed during this review; full CI/Compose was not repeated. The preceding full test/browser evidence remains valid for its covered cases but does not establish protection for these newly reproduced inputs.
- Findings recorded as action items; story/sprint reopened to `in-progress`. No commit/push because security review follow-up remains open. `bmad-help` next step: repair these Story 12.3 guards with regression tests, then rerun `bmad-code-review` before PR closure or Story 12.4.

### Post-review Fix Record — 2026-10-06

- Resolved both post-fix P1 findings. Incident import/reindex now use the existing filename-plus-content submission collector across the whole batch before aliasing, scope validation and field projection. This protects filename-only credentials in the original document, sibling files and normalized scope errors while keeping aliases stable.
- Extended the shared string boundary with bounded percent decoding. The existing lexical routine remains the plaintext screen; a wrapper checks nine decoded candidates without recursive variant generation. Harmless encoded text retains its exact spelling, known encoded credentials block the complete string, and unresolved encoding at the bound fails closed. Plaintext bypasses repeated decoding work. Credential collection follows the same bounded candidates and decodes escaped URL userinfo before syntax is lost. No dependency/schema/scoring change or new per-surface screen.
- Regression evidence includes the original filename/encoded database probes, plus named/configured credentials, nested JSON, percent escape case, decoding bound, idempotency and enum preservation. Actual SARIF/Semgrep messages and allowed metadata are checked in database rows, import/list output and repeat-import identity; incident import/reindex check stored content, same-document/sibling echoes, scope errors, stable aliases and healthy prose. New fixtures use isolated databases and mocked snapshot invalidation. Red logs include `/private/tmp/story12-3-finalfix-incidents-red.log`; shared and scanner tests independently reproduced their leaks before repair.
- Independent verifier reran `/private/tmp/edge_probe_123.py` and `/private/tmp/edge_encoded_probe_123.py`: neither original credential appears in stored or returned/listed data. `/private/tmp/edge_bound_probe_123.py` verified credential encoding depths 0–12, exact healthy text at depths 0–8, fail-closed depth 9, configured keys, enums and stable aliases. No unresolved defect in this bounded verification. Independent focused pytest: **24 passed + 45 subtests**. Parent combined connector/import/new-regression pytest: **42 passed + 54 subtests**. Scanner suites: **98 passed + 8 subtests**; shared/content/logging suites: **52 passed + 127 subtests**.
- Final `bash scripts/ci-local.sh`: **1,755 tests passed across all nine directories**, plus deterministic Skill harness/prompt checks, compilation, dependency consistency, Ruff and configured Bandit gate. Final `./.venv/bin/python -m unittest discover -q`: **486 passed**, one optional live-provider skip. Final `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: **423 passed + 152 subtests**. Logs: `/private/tmp/story12-3-finalfix-ci.log`, `/private/tmp/story12-3-finalfix-unittest.log`, `/private/tmp/story12-3-finalfix-shard.log`.
- `npm run ui:typecheck`: passed; `npm run ui:test`: **56 passed**. Final `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`: passed, **294 Python files formatted**. `git diff --check`: passed. Existing Alembic/TestClient warnings remain; unchanged medium sample-data Bandit B104 is the only medium finding and the high-severity gate passes.
- Rebuilt production Compose frontend/runtime with `/private/tmp/story12-3-fixes-compose.yaml`, waited for `http://localhost:8080/api/v1/health`, and seeded fixtures through APIs. `/app/data` used writable disposable tmpfs; operator volumes were never mounted. Approved Chromium run: `BASE_URL=http://localhost:8080 PROVIDER_ADMIN_TEST_MUTATION=1 CONNECTOR_SECURITY_TEST_DISPOSABLE=1 npm run test:ui-review`: **17 passed**, including filename-only/sibling incident content, encoded root cause, encoded scanner message and real matched report assertions. Updated all three screenshot artifacts and stopped/removed Compose afterward. Log: `/private/tmp/story12-3-finalfix-browser.log`.
- Definition of Done: PASS for this fix workstream. Both action items checked, story/sprint moved to `review` on the existing feature branch. Changes remain local and uncommitted. `bmad-help` next step: review the fixes before Git Flow/PR closure. Remaining limits: live remote credentials were not exercised; encodings beyond the documented percent-decoding screen require operator controls. The separately documented scanner-to-report attachment gap remains outside these credential findings.

### Fourth Code Review Record — 2026-10-06

- Reviewed the complete Story 12.3 change from `6bf57d8` through `2020f41` plus current working fixes and five new test files. Frozen diff: `/private/tmp/story12-3-review-round4.diff`, **42 files, 4,435 added / 257 removed text lines**, plus screenshot evidence; unrelated analytics snapshot excluded. Story/project/security constraints loaded for acceptance; blind reviewer received only the diff.
- All three independent layers completed. Triage: **one P1 patch, zero decision-needed, zero new deferrals, one dismissed candidate**. Scanner filename-only persistence candidate was withdrawn/dismissed: plain/encoded credential-bearing filenames reject at the scanner envelope before persistence. Prior filename, encoded narrative, normalized scope, topology projection, alias-query and GitHub boundary fixes remain covered.
- Edge reviewer reproduced the remaining numeric-field issue in an isolated temporary database; acceptance reviewer independently confirmed both import and reindex with separate temporary fixtures. The collector identifies `739241`, yet numeric title/root cause survive screening and become literal persisted/returned text with redaction status set to `redacted`. Returned import records, reindex source titles and `get_incident_records` all retain the credential. A parent pure normalization probe independently confirmed the conversion/context-loss path. Baseline import implementation also exposes the value: classified as incomplete in-scope audit coverage. No production edits, operator data or shared artifacts touched by review probes.
- Fresh targeted pytest over connector content/import, GitHub security/API, topology, scanner/incident/submission regressions, API scope and source-query tests: **85 passed + 116 subtests**, 26 existing Alembic warnings. Command: `./.venv/bin/python -m pytest tests/test_services/test_connector_content_security.py tests/test_services/test_connector_import_security.py tests/test_services/test_github_credential_security.py tests/test_services/test_topology_credentials.py tests/test_services/test_scanner_review_regressions.py tests/test_services/test_incident_review_regressions.py tests/test_services/test_incident_submission_review_regressions.py tests/test_api/test_connector_scope_security.py tests/test_models/test_incident_source_alias_queries.py tests/test_api/test_github_app.py -q --tb=short`. Log: `/private/tmp/story12-3-round4-tests.log`. Acceptance reviewer independently ran the same suite successfully; additional isolated decoding/filename/error/enum/topology probes passed.
- Fresh `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`: passed, **294 Python files formatted**. `git diff --check`: passed. This review changes tracking documents only; full local CI and Compose/browser were not repeated. Previous 1,755-test/17-browser evidence remains valid for its covered cases but does not cover numeric incident normalization.
- Recorded the remaining finding as an action item and reopened story/sprint to `in-progress`. No commit/push because review follow-up remains open. Existing feature branch and PR #130 verified. `bmad-help` next step: fix this Story 12.3 guard with regression coverage, then rerun review before Git Flow closure or starting Story 12.4.

### Numeric Review Fix Record — 2026-10-06

- Resolved the fourth-review P1 finding by converting nonempty retained incident text fields to strings before contextual screening, while original submission credentials are available. Source system/reference receive the same handling. The shared severity exemption stays intact, missing values retain required-field validation, caller records are copied, and typed identifiers/coordinates remain unchanged. Redaction status is now set before persistence/status serialization rather than after normalization loses the credential declaration. Reused `_has_value` and the existing shared screen; no dependency, schema, scoring, or global numeric-screen change.
- Added regressions for both import and reindex with integer/float credentials across JSON, YAML and Markdown frontmatter. Tests cover title/root cause/trigger/rollback/source fields, same-document/filename/sibling sensitivity, actual database content, import/list/status output, severity collisions, healthy numeric zero/integer/float text, unchanged `none` redaction status for healthy inputs, and missing null/blank/list/dict values. Red run: **14 failing cases**; green import/submission suite: **25 passed + 40 subtests**. Logs: `/private/tmp/story12-3-numeric-red.log`, `/private/tmp/story12-3-numeric-green.log`.
- Independent verifier passed 18 fresh temporary-database credential scenarios plus healthy cases: import/reindex × integer/float × content/filename-own/filename-sibling declarations. Stored/listed/returned values omit credentials, redaction status is accurate, severity `high` survives a same-spelled credential, aliases and healthy text remain stable, non-text numbers and caller input remain unchanged. No residual finding in this bounded verification.
- Final `bash scripts/ci-local.sh`: **1,758 tests passed across all nine directories**, plus deterministic Skill harness/prompt checks, compilation, dependency consistency, Ruff and configured Bandit gate. `./.venv/bin/python -m unittest discover -q`: **486 passed**, one optional live-provider skip. `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: **423 passed + 152 subtests**. Logs: `/private/tmp/story12-3-numeric-ci.log`, `/private/tmp/story12-3-numeric-unittest.log`, `/private/tmp/story12-3-numeric-shard.log`.
- `npm run ui:typecheck`: passed; `npm run ui:test`: **56 passed**. Final `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`: passed, **294 Python files formatted**. `git diff --check`: passed. Existing medium sample-data Bandit B104 remains unchanged; the high-severity gate passes. Existing Alembic/TestClient warnings remain.
- Rebuilt production Compose app with `/private/tmp/story12-3-fixes-compose.yaml`, verified `http://localhost:8080/api/v1/health`, and seeded via APIs. Writable `/app/data` used disposable tmpfs; no operator volume mounted. `BASE_URL=http://localhost:8080 PROVIDER_ADMIN_TEST_MUTATION=1 CONNECTOR_SECURITY_TEST_DISPOSABLE=1 npm run test:ui-review`: **17 passed**, including a numeric title/root-cause/password incident, safe reindex status, incident screen, actual matched report and credential-absence assertions. Log: `/private/tmp/story12-3-numeric-browser.log`. Updated all three screenshots and stopped/removed Compose after validation.
- Definition of Done: PASS for the numeric fix. Finding checked; story/sprint moved to `review` on the existing feature branch. Changes remain local and uncommitted. `bmad-help` next step: `bmad-code-review` before final Git Flow/PR closure. Live remote credentials were not exercised; existing operator cleanup/custom-encoding controls and the separately documented scanner-report integration gap remain unchanged.

### Git Flow Closeout Record — 2026-10-06

- User authorized `git add`, commit, push and PR after final verification. Existing branch `feature/12-3-connector-credential-redaction` and PR #130 target `develop`; no direct protected-branch commit or merge.
- All recorded review findings are resolved. Final independent acceptance gate confirmed numeric import/reindex storage/result/list protection, required-field behavior and severity preservation. The previous three-layer review's only remaining finding is closed; no concrete blocker remains. Fresh ten-file connector/security regression run: **88 passed + 137 subtests**, with existing Alembic warnings. Log: `/private/tmp/story12-3-closeout-tests.log`.
- Previously completed final-source validation remains green: full local CI **1,758 tests**, root smoke **486 with one optional skip**, API/CLI/infra **423 + 152 subtests**, frontend **56 tests/typecheck**, production Compose **17 browser tests** and updated screenshots. Fresh Ruff lint/format (**294 files**) and diff checks pass. No production code changed after these final gates.
- Story/sprint moved to `done`; all fixes, deterministic regressions, audit docs and screenshots included in a Lore-format commit on the existing story branch. PR #130 description is updated to the final implementation and verification evidence. Exact pushed commit/check results are recorded in the PR and runtime closeout state.
- Remaining documented limits: live remote credentials not exercised; operator cleanup needed for legacy retention/backups; unsupported opaque encodings require manual controls. Existing sample-data medium Bandit B104 and scanner automatic report attachment gap remain outside these resolved findings.
- `bmad-help` next step after PR integration: `bmad-dev-story` for existing ready Story 12.4; Epic 12 remains in progress.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/12-3-connector-credential-handling-and-redaction-audit.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `api/routes/github_app.py`
- `config.py`
- `docs/ci.md`
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
- `docs/verification/story-12-3/connector-report-context.png`
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

- `api/routes/incidents.py`
- `api/routes/scanner_imports.py`
- `models/repositories/incident_ingestion_sources.py`
- `models/repositories/incident_records.py`
- `tests/test_api/test_connector_scope_security.py`
- `tests/test_models/test_incident_source_alias_queries.py`
- `tests/test_services/test_incident_review_regressions.py`
- `tests/test_services/test_scanner_review_regressions.py`

- `tests/test_services/test_incident_submission_review_regressions.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.

- 2026-10-06: Implemented connector credential/redaction guards, isolated regressions, operator controls and composed-app browser evidence; moved story to review.

- 2026-10-06: Layered code review repaired seven grouped findings, strengthened isolated browser evidence and documented one pre-existing scanner integration gap; all final verification passed and story/sprint moved to done.

- 2026-10-06: Fresh three-layer re-review found five open patches and one grouped pre-existing scope-validation gap; recorded evidence and reopened story/sprint to in-progress.

- 2026-10-06: Repaired all fresh-review findings and scope-validation deferral with regression coverage, source-only alias queries, full Python/static gates and 17 composed-app browser tests; moved story/sprint to review.

- 2026-10-06: Post-fix three-layer review reproduced two remaining AC1 credential-coverage gaps in incident filename context and encoded incident/scanner narratives; recorded action items and reopened story/sprint to in-progress.

- 2026-10-06: Fixed both post-review credential gaps with shared bounded text screening and batch filename/content sensitivity; actual storage/list regressions, all Python/static checks and 17 composed-app browser tests passed; story/sprint moved to review.

- 2026-10-06: Fourth three-layer review independently reproduced one remaining numeric-credential normalization gap; recorded action item and reopened story/sprint to in-progress.

- 2026-10-06: Fixed numeric incident text/context normalization with storage/result/list/status and healthy-behavior regressions; 1,758 full local CI tests and 17 production browser tests passed; moved story/sprint to review.

- 2026-10-06: Final independent gate passed with all review findings closed; synchronized story/sprint done and prepared the authorized feature-branch commit/push/PR closeout.
