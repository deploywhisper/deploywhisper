# Story 12.1: Secrets and Raw Artifact Boundary Audit

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a security-conscious operator,
I want raw artifacts, prompts, logs, reports, and telemetry protected,
So that self-hosted analysis does not leak sensitive deployment data.

## Acceptance Criteria

1. Given uploaded artifacts, generated prompts, logs, reports, and telemetry exist, When security tests and review run, Then secrets are redacted and raw artifacts are not sent externally by default. And local-only operation remains possible.
2. Given sensitive content is detected in input or generated output, When persistence or narrative generation runs, Then unsafe content is blocked or redacted with an explicit status visible to reviewers and operators.

### Requirement Traceability

- Primary PRD requirements: Epic 12 coverage: ADM-01..02, NFR-SEC-01..07, NFR-OPS-01..06, GOV-06..07, DOC-11, DOC-12.
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
- [x] Verify the existing Report Audit metadata card displays content redaction through composed-app Playwright, and capture a screenshot. (AC: 2)

### Review Findings

- [x] [Review][Patch][P1] Preserve typed structures when screening large valid reports [services/content_security.py:209] — A 300-task supported upload exhausts the global node budget and crashes instead of completing analysis.
- [x] [Review][Patch][P1] Screen complete escaped quoted credentials [services/content_security.py:30] — Escaped quotes end the current regex match early and expose credential suffixes through configured logging.
- [x] [Review][Patch][P1] Recognize conventional SECRET_KEY labels [services/content_security.py:136] — Text assignments and named environment values for SECRET_KEY bypass screening.
- [x] [Review][Patch][P1] Inspect valid YAML key formats and binary Secret values [services/content_security.py:333] — Quoted or whitespace-separated kind keys skip YAML inspection; tagged binary values are not collected for derived-text screening.
- [x] [Review][Patch][P1] Collect sensitive values from failed uploads before every model call [services/analysis_service.py:2470] — A failed artifact has detected sensitive content, but a valid sibling artifact can echo it through hosted severity/narrative calls.
- [x] [Review][Patch][P1] Screen standard multiline and encoded Secret representations [services/content_security.py:176] — Literal YAML scalars retain trailing newlines and encoded Secret.data values omit decoded variants, permitting derived echoes.
- [x] [Review][Patch][P2] Redact detected numeric credentials in freeform structured values [services/content_security.py:213] — Known sensitive numeric values remain exposed when their original sensitive mask is absent from derived metadata.
- [x] [Review][Patch][P1] Honor Terraform sensitive output descriptors [services/content_security.py:229] — The standard sensitive:true plus value descriptor is persisted unchanged in snapshots.

- [x] [Review][Patch][P2] Exclude credential-bearing artifact names before parsing and snapshot manifest writes [services/intake_service.py:227] — Recognized secrets in uploaded filenames otherwise remain in local snapshot metadata and lose their report-to-artifact identity after text screening.

- [x] [Review][Patch][P1] Retain safe logging through migrations and Uvicorn startup [migrations/env.py:18] — Alembic fileConfig replaced the application formatter/filter and Uvicorn installed independent console handlers. Reuse the shared configuration and preserve it in the canonical entrypoint.

### Re-review Findings

- [x] [Review][Patch][P1] Decode quoted-source credential variants [services/content_security.py] — Escaped HCL quoted values are collected in source spelling only and decoded sibling values can enter prompts.
- [x] [Review][Patch][P1] Reuse values detected within a structured payload [services/content_security.py] — Sensitive labelled fields are redacted but duplicated unlabelled values survive; constrain enum exemptions to typed fields rather than freeform metadata.
- [x] [Review][Patch][P1] Decode standard multiline base64 Secret values [services/content_security.py] — Base64 validation rejects CR/LF in valid Secret.data block scalars and does not screen decoded echoes.
- [x] [Review][Patch][P1] Inspect supported CloudFormation intrinsic YAML [services/content_security.py] — SafeLoader rejects supported intrinsic tags before reaching sensitive parameter defaults.
- [x] [Review][Patch][P1] Screen encoded evidence references [services/content_security.py] — URI-encoded credential values remain reversible in evidence source references.
- [x] [Review][Patch][P1] Apply submitted credential context to all snapshots [services/artifact_snapshot_service.py] — Per-file snapshot screening retains an opaque credential discovered in a sibling artifact.
- [x] [Review][Patch][P2] Preserve artifact identity through redaction [services/analysis_service.py] — A secret equal to an artifact name makes sanitized names fail correlation with original submitted names during persistence.
- [x] [Review][Patch][P2] Carry redaction status from the first screening pass [services/analysis_service.py] — Already-screened evidence remains marked none when persistence does not see another change.
- [x] [Review][Patch][P1] Retain excluded-upload credentials during persistence [services/report_service.py] — An excluded .env credential reappears in original audit context and manifest provenance.
- [x] [Review][Patch][P2] Screen public intake serialization [api/schemas.py] — Successful API and CLI response intake items expose detected sensitive filenames outside screened artifacts.

- [x] [Review][Defer][P2] Reconcile multi-finding top-risk ownership validation [models/repositories/analysis_reports.py:_validate_top_risk_contributor_refs] — pre-existing; isolated develop and current controls fail identically. Tracked in deferred-work.md; scoring semantics unchanged.

- [x] [Review][Patch][P2] Match the installed Gemini SDK logger namespace [logging_config.py:PayloadLogFilter] — the SDK uses google_genai, which escaped the google.genai-only debug suppression; verified directly from installed SDK source.

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 12 / Story 12.1 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

Codex (GPT-6), with bounded native subagents for independent boundary review, provider protection, and API/logging implementation.

### Debug Log References

- Initial regression tests demonstrated unchanged snapshot credentials, unsafe repository writes, parser exception echoes, provider metadata/raw payload leaks, and API/logging exposure before fixes.
- Independent boundary review re-probed quoted/flow Kubernetes Secrets, opaque authorization/URL values, Terraform numeric sensitive masks, secondary confidence prompts, configured-key JSON reserialization, short credentials, and every shared evidence enum. All findings fixed; final focused set: 25 tests passed.
- Final evidence logs: `/private/tmp/story-12-1-ci-verified.log`, `/private/tmp/story-12-1-unittest-verified.log`, `/private/tmp/story-12-1-shard-verified.log`, `/private/tmp/story-12-1-playwright-final.log`, `/private/tmp/story-12-1-browser-verified.log`, `/private/tmp/story-12-1-ui-tests.log`, `/private/tmp/story-12-1-ui-build.log`.
- Docker/browser validation required escalation for BuildKit state and localhost/browser access beyond the workspace sandbox. Verification completed successfully; compose containers/network shut down without deleting the data volume.

### Completion Notes List

- AC1: Added one dependency-free shared screening utility (using existing PyYAML/Pydantic contracts). Explicit provider field allowlists omit raw metadata; structured messages redact credentials and local secret values. Uploaded bytes remain local and only inform deterministic rules/skill selection. Ollama/local-mode behavior preserved; no telemetry exporter introduced.
- AC2: Protected successful and degraded outputs, shared artifact results, final repository writes, and report reads. Sensitive model responses produce blocked notices and deterministic fallback. Sensitive snapshots are blocked, sensitive filenames excluded, and redaction warnings/statuses persist through manifest/evidence/audit fields. Added the existing content-redaction API status to the Report Audit card using unchanged styles.
- API validation inputs/context and unsafe parser/provider error bodies are withheld. Console logging screens credentials, emits exception classes only, suppresses SDK debug payload dumps and SQL statement/parameter dumps.
- Simplifications: reused existing intake exclusions, service/repository boundaries, report warning/redaction contracts, evidence Literal definitions, Audit metadata grid, and provider adapters. No dependency additions, database migrations, or enforcement changes.
- `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`: passed repository-wide (278 formatted Python files).
- `./.venv/bin/python -m unittest discover -q`: 464 tests passed, 1 opt-in live smoke skipped.
- `bash scripts/ci-local.sh`: passed; dependency consistency, Bandit, compileall, Skill checks, prompt-injection gate, and all nine Python test directories (1,615 tests, 1 opt-in live smoke skipped). Final services directory: 954 tests passed. Final enum/protocol-focused rerun: 25 passed.
- `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: 404 passed, 121 subtests passed; existing deprecation warnings retained.
- `npm --prefix frontend run test`, `npm --prefix frontend run typecheck`, `npm --prefix frontend run build`: passed; 56 frontend tests and production static build.
- UI validation applicable: `docker compose up -d --build`; healthy `http://localhost:8080/api/v1/health`; synthetic data seeded by Playwright. `BASE_URL=http://localhost:8080 npm run test:ui-review`: 11 passed (report, share, history, dashboard, settings, skills, a11y, credential boundary). Rebuilt final fixes and reran `BASE_URL=http://localhost:8080 npm run test:ui-review -- content-security.spec.ts`: 1 passed. Screenshot: `docs/design/story-12-1-content-redaction.png`; manually inspected redacted headline and visible Audit status. `docker compose down`: completed, data volume preserved.
- Design reference: existing B3 Audit metadata card in `docs/design/deploywhisper-redesign-v3.jsx`; updated the Audit row in `docs/design/ui-parity-audit.md`. No visual values changed.
- Known limits: deterministic screening is best-effort for labelled/recognized credentials; obfuscated/unlabelled secrets and private business identifiers require operator review. Old database/snapshot bytes and backups are not rewritten or purged. Real hosted-provider network calls were not exercised; deterministic adapter doubles and local composed runtime were verified. Custom logging handlers require equivalent controls.
- Definition of Done: PASS. Story/sprint status moved to review on `feature/12-1-secrets-raw-artifact-boundary`. BMad Help identifies `bmad-code-review` as the next workflow; final reviewer owns Git Flow commit/push/PR closure before story lifecycle completion.

### File List

- `README.md`
- `SECURITY.md`
- `_bmad-output/implementation-artifacts/12-1-secrets-and-raw-artifact-boundary-audit.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `analysis/risk_engine.py`
- `analysis/risk_scorer.py`
- `api/errors.py`
- `api/schemas.py`
- `app.py`
- `docs/design/story-12-1-content-redaction.png`
- `docs/design/ui-parity-audit.md`
- `docs/security/secrets-and-artifact-boundaries.md`
- `frontend/e2e/content-security.spec.ts`
- `frontend/src/screens/Report.test.tsx`
- `frontend/src/screens/Report.tsx`
- `llm/narrator.py`
- `llm/prompts.py`
- `llm/providers.py`
- `logging_config.py`
- `migrations/env.py`
- `models/repositories/analysis_reports.py`
- `parsers/registry.py`
- `services/analysis_service.py`
- `services/artifact_snapshot_service.py`
- `services/content_security.py`
- `services/intake_service.py`
- `services/report_service.py`
- `services/submission_manifest.py`
- `tests/snapshot_isolation.py`
- `tests/test_api/test_agent.py`
- `tests/test_api/test_analyses.py`
- `tests/test_api/test_analysis_content_boundary.py`
- `tests/test_api/test_deployments.py`
- `tests/test_api/test_error_security.py`
- `tests/test_api/test_stats.py`
- `tests/test_cli/test_analyze.py`
- `tests/test_infra/test_logging_security.py`
- `tests/test_infra/test_logging_startup_security.py`
- `tests/test_llm/test_content_boundary.py`
- `tests/test_llm/test_narrator.py`
- `tests/test_services/test_analysis_content_boundary.py`
- `tests/test_services/test_analysis_service.py`
- `tests/test_services/test_content_security.py`
- `tests/test_services/test_narrator.py`
- `tests/test_services/test_report_service.py`
- `tests/test_services/test_settings_service.py`
- `tests/test_services/test_snapshot_content_boundary.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.

- 2026-10-01: Implemented shared credential/raw-artifact boundary screening, safe provider/output/error/log handling, blocked snapshots, visible Audit redaction status, deterministic regressions, security audit documentation, and composed-app verification. Ready for review.

## Senior Developer Review (AI)

- Reviewer: Codex, 2026-10-05. Outcome: **APPROVE after fixes**. All three BMad layers completed independently (Blind Hunter, Edge Case Hunter, Acceptance Auditor); fix verification also passed.
- Triage: 0 decisions needed, 10 patched findings, 0 genuine deferrals. Dismissed one unrelated Bandit B104 false positive: `services/sample_incident_pack.py:327` compares a sample IP string; it does not bind a network interface. The high-severity security gate passed; touched code has no reported Bandit findings.
- Fixed: escaped/multiline log credentials; SECRET_KEY and valid YAML/binary forms; standard Terraform sensitive outputs; stripped/decoded credential variants; numeric/freeform metadata; large typed-report screening; failed/excluded upload context; credential-bearing filenames; migration/Uvicorn safe-log lifecycle.
- Simplifications: all-submitted credential context is derived once and forwarded explicitly through the shared evidence/scoring/narration paths, while raw rule/skill inputs stay restricted. Reused the application logging setup for migrations and Uvicorn instead of competing runtime log configuration. Shared screening visits alias graphs once without an arbitrary report-node cutoff.
- Red-first regressions proved the original leaks and 300-task failure, then passed after fixes. Existing narrator-mutation fixture updated for the additive credential-context parameter; repository-wide callable/fixture search and API/CLI/infra CI shard completed.
- Final `./.venv/bin/ruff check .` / `./.venv/bin/ruff format --check .`: passed, 280 Python files formatted. `git diff --check`: passed.
- `./.venv/bin/python -m unittest discover -q`: 466 passed, 1 opt-in live smoke skipped.
- `bash scripts/ci-local.sh`: passed across all nine Python test directories, 1,629 tests (1 opt-in live smoke skipped), dependency consistency, compile, Skill checks, prompt-injection gate, and high-severity Bandit gate. Services directory: 966 passed.
- `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: 406 passed, 130 subtests; existing deprecation warnings.
- Focused shared-core/provider/content/log regression set: 44 passed; final fresh-process migration/Uvicorn startup and log checks: 8 passed. Independent acceptance probes confirmed failed, excluded, literal, and base64 credentials absent from every fake hosted request and shared result.
- Frontend: `npm --prefix frontend run test` (56 passed), `npm --prefix frontend run typecheck`, `npm --prefix frontend run build`: passed.
- Compose: `docker compose up -d --build` and health check passed. `BASE_URL=http://localhost:8080 npm run test:ui-review`: 12 passed. After the final startup fix, `BASE_URL=http://localhost:8080 npm run test:ui-review -- content-security.spec.ts`: 2 passed. Updated screenshot `docs/design/story-12-1-content-redaction.png`. `docker compose down` completed; volume preserved.
- Evidence: `/private/tmp/story12-review-{ci-complete,shard-complete,smoke-complete,playwright,browser-complete}.log`; final startup regression `tests/test_infra/test_logging_startup_security.py`.
- Remaining limits: best-effort recognition cannot cover every custom/obfuscated secret or private business identifier. Old rows/snapshot bytes/backups are not rewritten. Live hosted providers were not used; deterministic hosted doubles and local composed runtime were verified.
- Git Flow: reviewed branch `feature/12-1-secrets-raw-artifact-boundary`; mandatory commit/push/PR closure follows verified approval.

- 2026-10-05: Completed layered code review, fixed all 10 findings, added runtime/credential regressions, verified CI and composed browser flows, and approved Story 12.1.

## Senior Developer Re-review (AI)

- Date: 2026-10-05. Base reviewed: `490d473`, PR #128. Outcome: **APPROVE after 11 additional fixes**, with one confirmed pre-existing issue deferred. Blind Hunter, Edge Case Hunter, and Acceptance Auditor reviewed independently without inherited conclusions; original findings passed independent fix checks.
- Fixed: decoded quoted-source and base64 credentials; CloudFormation tags/NoEcho; whole-payload and cross-model sibling protection; URL-encoded evidence; batch snapshots; stable artifact aliases; carried redaction status; excluded-input audit/provenance; public API/CLI intake; actual installed Gemini SDK debug logger namespace. No new dependencies, public model fields, or scoring changes.
- Simplifications: reused credential collection across payload groups and snapshot batches; shared API run-data builder protects both API and CLI; deterministic aliases keep local parsing/ownership on original names and preserve report/manifest/snapshot correlations; shared test snapshot isolation replaces accidental default-directory writes.
- Deferred: existing low/medium multi-finding top-risk evidence ownership conflict. Isolated `develop` and reviewed builders fail the same control; tracked in `deferred-work.md`. It is not introduced by Story 12.1.
- Regression checks: helper/public-surface/provider tests passed; real TestClient and CLI cases verify intake, excluded audit context, encoded evidence, alias/snapshot lookup, and reviewer redaction status. Cross-model repository/service/log regressions passed. Installed SDK source confirmed `google_genai` namespace; red-first filter regression now passes.
- Final Ruff lint, repository-wide formatting (283 files), and git diff check: passed.
- `./.venv/bin/python -m unittest discover -q`: 471 passed, one opt-in live smoke skipped.
- `bash scripts/ci-local.sh`: passed all nine test directories, 1,648 tests (one opt-in live smoke skipped), dependency consistency, compile, Skill/prompt-injection checks, and high-severity Bandit gate. The same unrelated sample-IP comparison B104 remains a documented false positive.
- `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: 411 passed, 132 subtests; existing deprecation warnings retained.
- Frontend unit tests/typecheck/build passed (56 tests). Compose build/health passed; full `BASE_URL=http://localhost:8080 npm run test:ui-review`: 13 passed; final `-- content-security.spec.ts`: 3 passed. Screenshot refreshed. Compose shut down, data volume preserved.
- Evidence logs: `/private/tmp/story12-rereview-{ci-final,smoke-verified,shard-verified,browser,browser-verified,focused-final,aggregate}.log`.
- Operational incident: an early read-only review probe isolated its SQLite database but not snapshot storage, overwriting pre-existing ignored `data/report-artifacts/1/manifest.json` and `2/manifest.json`; it also created a safe synthetic snapshot. Prior manifest contents were not captured. Read-only recovery inspection found persisted metadata did not match the existing snapshot hashes, so reconstructing the old indexes was ambiguous and no guessed restore was performed. Existing artifact bytes were retained. Shared API/CLI snapshot fixtures now isolate storage; filesystem timestamps confirmed no subsequent writes to those manifests during final validation.
- Remaining limits: deterministic recognition is best-effort, older stored bytes/backups are not purged, and live hosted network calls were not used. The baseline persistence contract and prior local manifest restoration remain separate follow-up work.
- Git Flow closure: follow-up commit on `feature/12-1-secrets-raw-artifact-boundary`, push to origin, update existing PR #128 targeting develop.

- 2026-10-05: Re-ran layered code review, fixed 11 new findings, documented the baseline deferral and snapshot-isolation incident, added public/cross-boundary regression coverage, and reverified the composed app.
