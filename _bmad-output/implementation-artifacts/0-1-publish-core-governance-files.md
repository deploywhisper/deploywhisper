# Story 0.1: Publish Core Governance Files

Status: done

## Story

As a project maintainer,
I want public governance, support, security, conduct, contributing, and roadmap files,
so that users and contributors understand how the project operates.

## Acceptance Criteria

1. Given a new contributor or user visits the repository, when they inspect governance and community files, then they can find `GOVERNANCE.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`, and `ROADMAP.md`.
2. Given a new contributor or user reads those documents, when they evaluate project access and roadmap posture, then the documents do not imply SaaS, open-core, paid feature gating, vendor-controlled roadmap priority, or proprietary plugins required for major supported platforms.

### Requirement Traceability

- Primary PRD requirements: `GOV-01`, `GOV-03`, `GOV-04`, `GOV-05`, `GOV-06`, `NFR-OSS-01`.
- Supporting PRD / NFR / differentiation requirements: `DOC-15`, `DOC-19`, `DOC-20`, `NFR-OSS-02`, `NFR-OSS-04`.
- Coverage intent: Baseline.
- Story alignment note: This story publishes the root community files required for open-source trust. It does not implement maintainer ownership, CODEOWNERS routing, RFC mechanics, contributor ladder, release process, or adopters tracking; those are covered by later Epic 0 and Epic 14 stories.

## Tasks / Subtasks

- [x] Audit existing repository community files and identify missing required files. (AC: 1)
  - [x] Confirm whether root `CONTRIBUTING.md` already exists and can be reused.
  - [x] Confirm missing root `GOVERNANCE.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`, and `ROADMAP.md`.
- [x] Add missing root community files with self-hosted, advisory-first, open-source posture. (AC: 1, 2)
  - [x] Add `GOVERNANCE.md` that defines public governance principles and references future maintainer/RFC artifacts without inventing completed maturity.
  - [x] Add `CODE_OF_CONDUCT.md` with clear participation standards and reporting path.
  - [x] Add `SECURITY.md` with supported reporting process, sensitive data guidance, and local-first security boundary.
  - [x] Add `SUPPORT.md` with community support channels and no paid support guarantees.
  - [x] Add `ROADMAP.md` with public roadmap phases and honest non-guarantees.
- [x] Add documentation guardrail tests for the required files and forbidden posture claims. (AC: 1, 2)
  - [x] Test that all six required root files exist.
  - [x] Test that required files do not contain SaaS/open-core/paid feature-gating claims.
  - [x] Test that required files guard against vendor-controlled roadmap priority and proprietary plugin prerequisites.
- [x] Run focused validation and update story status. (AC: 1, 2)
  - [x] Run the new docs test.
  - [x] Run the relevant repository validation for docs-only changes.

### Review Findings

- [x] [Review][Patch] Guardrail coverage does not enforce all AC2 posture constraints [tests/test_infra/test_governance_files.py:20] — fixed by expanding forbidden posture patterns and adding positive assertions for vendor roadmap control, hosted-control-plane, and proprietary-prerequisite guardrails.
- [x] [Review][Patch] Sprint status changes exceed the Story 0.1 docs-only scope [_bmad-output/implementation-artifacts/sprint-status.yaml:44] — fixed for this follow-up by leaving the existing 2026-05-01 planning baseline intact and avoiding any new broad sprint-status rewrite; Story 0.1 remains `review`.
- [x] [Review][Patch] Proprietary-plugin regex misses singular `plugin is required` phrasing [tests/test_infra/test_governance_files.py:35] — fixed with singular/plural coverage and regression examples.
- [x] [Review][Patch] Forbidden-posture scan flags explicit negations such as `not open-core` as violations [tests/test_infra/test_governance_files.py:21] — fixed with negation-aware pattern matching and regression examples.
- [x] [Review][Patch] Required posture assertion depends on exact sentence text and unguarded file reads [tests/test_infra/test_governance_files.py:102] — fixed with intent regexes and missing-file-safe failures.
- [x] [Review][Patch] Placeholder guard only rejects blank files, not placeholder-only docs [tests/test_infra/test_governance_files.py:76] — fixed with minimum meaningful content and placeholder term checks.
- [x] [Review][Patch] Forbidden patterns miss typographic dash variants from pasted Markdown [tests/test_infra/test_governance_files.py:21] — fixed by normalizing typographic dash variants before matching.
- [x] [Review][Patch] Forbidden patterns miss common equivalent hosted-control-plane and private-roadmap-priority wording [tests/test_infra/test_governance_files.py:21] — fixed with expanded hosted-control-plane and roadmap-priority patterns plus regression examples.

## Dev Notes

### Scope

- Create or update root-level documentation only, plus a small docs guardrail test.
- Do not edit `.github/CODEOWNERS`; Story 0.2 owns maintainer areas and CODEOWNERS.
- Do not create `MAINTAINERS.md`, `CONTRIBUTOR_LADDER.md`, `RELEASE_PROCESS.md`, `ADOPTERS.md`, or an RFC directory in this story; architecture and PRD list them as required governance artifacts, but this story's acceptance criteria names only six root files.
- Do not imply DeployWhisper has CNCF status, production adopters, paid support, proprietary plugins, or vendor-controlled roadmap priority.

### Existing Repository Context

- `CONTRIBUTING.md` already exists and includes Git Flow, branch naming, PR process, code standards, testing, and release guidance.
- `.github/CODEOWNERS` already exists but is outside this story's acceptance criteria.
- `LICENSE` exists and is MIT.
- Required missing files before implementation: `GOVERNANCE.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`, and `ROADMAP.md`.

### Architecture and Product Guardrails

- Documentation and governance are architectural surfaces because DeployWhisper is self-hosted and open-source. Required governance artifacts are listed in the architecture's documentation and governance section.
- The PRD requires public governance documentation, public roadmap, contributor guide, code of conduct, security policy, and public open-source processes.
- Preserve the product posture: local-first, advisory-first, self-hosted, evidence-backed, and benchmark-honest.

### Testing Requirements

- Use standard-library `unittest` style consistent with project context.
- Put the docs guardrail test under `tests/test_infra/` because it validates repository packaging/community metadata rather than runtime behavior.
- Keep tests deterministic and local; do not call network services.

### References

- `_bmad-output/planning-artifacts/epics.md` - Epic 0, Story 0.1 acceptance criteria.
- `_bmad-output/planning-artifacts/prd.md` - Open Governance and CNCF readiness requirements.
- `_bmad-output/planning-artifacts/architecture.md` - Documentation and Governance Architecture.
- `_bmad-output/project-context.md` - testing and workflow rules.
- `CONTRIBUTING.md` - existing contributor guide to preserve and reuse.

## Dev Agent Record

### Agent Model Used

GPT-5

### Debug Log References

- `./.venv/bin/python -m unittest tests.test_infra.test_governance_files -q` failed before implementation because five required root files were missing.
- `./.venv/bin/python -m unittest tests.test_infra.test_governance_files -q` passed after adding governance files.
- `./.venv/bin/ruff check tests/test_infra/test_governance_files.py` passed.
- `./.venv/bin/ruff format --check tests/test_infra/test_governance_files.py` initially required formatting; passed after `./.venv/bin/ruff format tests/test_infra/test_governance_files.py`.
- `./.venv/bin/python -m unittest discover -q` passed: 211 tests, 1 skipped.
- 2026-05-01 dev-story verification rerun: `./.venv/bin/python -m unittest tests.test_infra.test_governance_files -q` passed: 2 tests.
- 2026-05-01 dev-story verification rerun: `./.venv/bin/ruff check .` passed.
- 2026-05-01 dev-story verification rerun: `./.venv/bin/ruff format --check .` passed: 250 files already formatted.
- 2026-05-01 dev-story verification rerun: `./.venv/bin/python -m unittest discover -q` passed: 211 tests, 1 skipped.

### Completion Notes List

- Added required root governance/community files for Story 0.1: `GOVERNANCE.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`, and `ROADMAP.md`.
- Reused the existing root `CONTRIBUTING.md`.
- Added a deterministic docs guardrail test that verifies all six required root files exist and that they avoid forbidden SaaS/open-core/feature-gating posture claims.
- Preserved Story 0.1 scope: did not change CODEOWNERS or add maintainer/RFC/release/adopters artifacts owned by later stories.
- Re-ran `bmad-dev-story` verification from the validation-report request; no implementation gaps remained and Story 0.1 stays ready for code review.

### File List

- `_bmad-output/implementation-artifacts/0-1-publish-core-governance-files.md`
- `_bmad-output/implementation-artifacts/0-1-publish-core-governance-files-validation-report.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `CODE_OF_CONDUCT.md`
- `GOVERNANCE.md`
- `ROADMAP.md`
- `SECURITY.md`
- `SUPPORT.md`
- `tests/test_infra/test_governance_files.py`

## Change Log

- 2026-05-01: Story created from corrected Epic 0.1 context.
- 2026-05-01: Implemented core governance files and docs guardrail test; story moved to review.
- 2026-05-01: Re-ran dev-story verification from validation report; focused governance test, Ruff check, Ruff format check, and full unittest suite passed.
