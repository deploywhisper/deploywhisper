# Story 9.4: Skills Installer CLI

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a platform admin,
I want to install, update, and remove Skills from the CLI,
So that self-hosted teams can manage extensions without manual file copying.

## Acceptance Criteria

1. Given a Skill registry or local Skill source is configured, When the CLI install/update/remove commands run, Then Skills are validated, stored, listed, and removable. And errors never execute untrusted Skill content.

### Requirement Traceability

- Primary PRD requirements: Epic 9 coverage: SKL-01..09, ADM-05, DOC-13, NFR-OSS-05.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 9 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Close the local-source check/read race so a file cannot be replaced with an escaping symlink after validation [services/skill_installer_service.py:474]
- [x] [Review][Patch] Distinguish a genuinely missing local Skill from permission, symlink-loop, and other resolution failures instead of reporting all as not found [services/skill_installer_service.py:474]
- [x] [Review][Patch] Replace the registry-specific no-source error code with a configured-source error contract [services/skill_installer_service.py:153]
- [x] [Review][Patch] Update source payload/result field descriptions that still claim every checksum and URI comes from the registry [services/skill_installer_service.py:69]
- [x] [Review][Patch] Add regression coverage for unavailable, non-directory, non-UTF-8, and unreadable local source paths [tests/test_services/test_skill_installer_service.py:228]
- [x] [Review][Patch] Add regression coverage for an unchanged local-source update [tests/test_services/test_skill_installer_service.py:116]
- [x] [Review][Patch] Add the ignored Story 9.4 artifact to the delivered change set so its File List and review record are auditable [\_bmad-output/implementation-artifacts/9-4-skills-installer-cli.md:110]
- [x] [Review][Patch] Include `PUBLIC_APP_URL` in no-source remediation because it participates in registry URL resolution [services/skill_installer_service.py:153]

### Review Findings (Re-run 2026-07-24)

- [x] [Review][Patch] Bound local Skill source size before reading to prevent memory exhaustion from oversized Markdown [services/skill_installer_service.py:485]
- [x] [Review][Patch] Add CLI-path regression coverage for local-source install/update behavior and surfaced errors [tests/test_cli/test_analyze.py:1215]
- [x] [Review][Patch] Replace remaining registry-only update guidance with configured-source behavior [docs/skills/installer-cli.md:63]
- [x] [Review][Patch] Clarify Dev Agent Record fallback wording so it does not imply registry fallback after a local source is selected [\_bmad-output/implementation-artifacts/9-4-skills-installer-cli.md:100]
- [x] [Review][Patch] Make installed Skill replacement atomic so update write failures cannot corrupt the existing file [services/skill_installer_service.py:734]

## Dev Notes

### Epic Context

- Epic: 9. Skills Ecosystem
- Epic goal: Grow community knowledge safely through non-executable, tested, versioned Skills.
- Epic coverage: SKL-01..09, ADM-05, DOC-13, NFR-OSS-05

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 9 / Story 9.4 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

OpenAI Codex (GPT-5.4)

### Implementation Plan

- Reuse the existing registry-backed installer and shared CLI/service path rather than introducing a second installer.
- Add an optional local self-hosted source with explicit precedence, strict manifest validation, and path-containment checks.
- Preserve registry behavior when no local source is configured and verify both focused behavior and the repository's exact CI test lanes.

### Debug Log References

- RED: `./.venv/bin/python -m pytest tests/test_services/test_skill_installer_service.py -q --tb=short` — 3 failed, 26 passed, 6 subtests passed; the new local-source install/update tests proved the baseline still used the registry.
- GREEN: `./.venv/bin/python -m pytest tests/test_services/test_skill_installer_service.py -q --tb=short` — 32 passed, 6 subtests passed.
- Focused cross-layer regression: `./.venv/bin/python -m pytest tests/test_services/test_skill_installer_service.py tests/test_api/test_skills.py tests/test_cli/test_analyze.py -q --tb=short` — 125 passed, 92 warnings, 6 subtests passed.
- CI services shard: `COVERAGE_FILE=/tmp/deploywhisper-story-9-4-services.coverage ./.venv/bin/python -m pytest tests/test_services --cov=. --cov-report=xml:/tmp/coverage-services-9-4.xml --cov-report=term-missing -v --tb=short` — 847 passed, 554 warnings, 171 subtests passed.
- CI API/CLI/infra shard: `COVERAGE_FILE=/tmp/deploywhisper-story-9-4-api-cli-infra-rerun.coverage ./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra --cov=. --cov-report=xml:/tmp/coverage-api-cli-infra-9-4-rerun.xml --cov-report=term-missing -v --tb=short` — 339 passed, 330 warnings, 15 subtests passed.
- Full local CI: `bash scripts/ci-local.sh` — passed Ruff, formatting, dependency validation, Bandit, compilation, Skill benchmark corpus, and all unittest discovery lanes; services reported 847 tests passed.
- Review RED: `./.venv/bin/python -m pytest tests/test_services/test_skill_installer_service.py -q --tb=short` — 3 failed, 36 passed, 6 subtests passed; failures covered the stale source error code and unimplemented descriptor-based race/error handling.
- Review GREEN: `./.venv/bin/python -m pytest tests/test_services/test_skill_installer_service.py -q --tb=short` — 39 passed, 6 subtests passed.
- Review focused cross-layer regression: `./.venv/bin/python -m pytest tests/test_services/test_skill_installer_service.py tests/test_api/test_skills.py tests/test_cli/test_analyze.py -q --tb=short` — 131 passed, 92 warnings, 6 subtests passed.
- Review CI services shard: `COVERAGE_FILE=/tmp/deploywhisper-story-9-4-review-services.coverage ./.venv/bin/python -m pytest tests/test_services --cov=. --cov-report=xml:/tmp/coverage-services-9-4-review.xml --cov-report=term-missing -v --tb=short` — 853 passed, 554 warnings, 171 subtests passed.
- Review CI API/CLI/infra shard: `COVERAGE_FILE=/tmp/deploywhisper-story-9-4-review-api-cli-infra.coverage ./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra --cov=. --cov-report=xml:/tmp/coverage-api-cli-infra-9-4-review.xml --cov-report=term-missing -v --tb=short` — 339 passed, 330 warnings, 15 subtests passed.
- Review full local CI: `bash scripts/ci-local.sh` — passed Ruff, formatting, dependency validation, Bandit, compilation, Skill benchmark corpus, and all unittest discovery lanes; services reported 853 tests passed.
- Review re-run RED: selected oversized-source and atomic-update regressions — 2 failed before implementation, proving unbounded reads and direct destination writes remained.
- Review re-run targeted GREEN: selected service regressions — 2 passed; CLI local-source install/update/error regressions — 2 passed.
- Review re-run focused cross-layer regression: `./.venv/bin/python -m pytest tests/test_services/test_skill_installer_service.py tests/test_api/test_skills.py tests/test_cli/test_analyze.py -q --tb=short` — 135 passed, 94 warnings, 6 subtests passed.
- Review re-run CI services shard: `COVERAGE_FILE=/tmp/deploywhisper-story-9-4-rerun-services.coverage ./.venv/bin/python -m pytest tests/test_services --cov=. --cov-report=xml:/tmp/coverage-services-9-4-rerun.xml --cov-report=term-missing -v --tb=short` — 855 passed, 554 warnings, 171 subtests passed.
- Review re-run CI API/CLI/infra shard: `COVERAGE_FILE=/tmp/deploywhisper-story-9-4-rerun-api-cli-infra.coverage ./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra --cov=. --cov-report=xml:/tmp/coverage-api-cli-infra-9-4-rerun.xml --cov-report=term-missing -v --tb=short` — 341 passed, 335 warnings, 15 subtests passed.
- Review re-run full local CI: `bash scripts/ci-local.sh` — passed Ruff, formatting, dependency validation, Bandit, compilation, Skill benchmark corpus, and all unittest discovery lanes; services reported 855 tests passed.
- Review re-run remote CI diagnosis: GitHub installed unpinned Ruff 0.16.0 while local CI used Ruff 0.15.11, enabling new repository-wide rules and stopping the test matrix before execution; the workflow now pins Ruff 0.15.11 to the locally verified toolchain.
- UI validation not applicable: no React route, component, interaction, or accessibility behavior changed.

### Completion Notes List

- Added `DEPLOYWHISPER_SKILLS_SOURCE_DIR` for private, organization-owned, and air-gapped Skill Markdown sources.
- Local sources take precedence without network fallback; registry installation remains available when no local source is configured.
- Local files must be UTF-8 regular files contained within the configured source directory; symlinks and special files are rejected.
- Local reads are anchored to an open directory descriptor and verify file identity before reading, closing the review-reported path-swap race.
- Local source reads are capped at 1 MiB and use a bounded binary buffer before UTF-8 decoding.
- Source Markdown is strictly parsed and validated as data before writes and is never imported, evaluated, or executed.
- Installs and updates use same-directory atomic replacement; invalid inputs and write failures preserve the installed Skill.
- Missing, unavailable, invalid, and unreadable sources have distinct error contracts, including complete configuration remediation.
- Updated CLI help and operator documentation for configured source resolution and validation behavior.

### File List

- `.github/workflows/ci.yml`
- `_bmad-output/implementation-artifacts/9-4-skills-installer-cli.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `cli/analyze.py`
- `config.py`
- `docs/skills/installer-cli.md`
- `services/skill_installer_service.py`
- `tests/test_cli/test_analyze.py`
- `tests/test_services/test_skill_installer_service.py`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-07-23: Implemented and verified registry/local-source Skill install and update behavior, safe validation, CLI help, tests, and operator documentation.
- 2026-07-24: Resolved all code-review findings with descriptor-anchored local reads, precise error contracts, expanded regression coverage, and full CI verification.
- 2026-07-24: Resolved the review re-run with bounded source reads, atomic writes, CLI-path regressions, corrected operator guidance, and repeat full-CI verification.
- 2026-07-24: Pinned the CI Ruff version to the locally verified release so tool upgrades cannot introduce unrelated repository-wide lint failures between stories.
