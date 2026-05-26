# Story 5.4: PR Comment Formatter

Status: review

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a PR reviewer,
I want concise advisory comments,
So that I can understand risk without opening the full UI.

## Acceptance Criteria

1. Given a report is generated for a PR, When the comment formatter runs, Then the comment includes verdict, Evidence Law status, top risks, evidence, blast radius, rollback, incident/public pattern matches, scanner context, uncertainty, and report link. And it remains explicitly advisory.

### Requirement Traceability

- Primary PRD requirements: Epic 5 coverage: WRK-01..10, REV-05..08, ADM-07, DOC-08.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 5 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] Malformed or older-shaped formatter payloads can crash the action after analysis succeeds [/private/tmp/deploywhisper-analyze-action/action_runtime.py:779]
- [x] [Review][Patch] Evidence Law fallback can overclaim `Satisfied` from aggregate counts or unverified evidence refs [/private/tmp/deploywhisper-analyze-action/action_runtime.py:581]
- [x] [Review][Patch] Pattern match summary can report `none returned` when malformed leading entries hide later valid matches [/private/tmp/deploywhisper-analyze-action/action_runtime.py:671]
- [x] [Review][Patch] PR comment renderer interpolates unescaped markdown/HTML text and unsafe link schemes [/private/tmp/deploywhisper-analyze-action/action_runtime.py:813]
- [x] [Review][Patch] `Uncertainty:` falls back to advisory boilerplate instead of uncertainty-specific signals [/private/tmp/deploywhisper-analyze-action/action_runtime.py:755]
- [x] [Review][Patch] Non-dict API response sections can still crash the action before the hardened formatter runs [/private/tmp/deploywhisper-analyze-action/action_runtime.py:1344]
- [x] [Review][Patch] Newly rendered comment fields still interpolate unsanitized markdown/control text [/private/tmp/deploywhisper-analyze-action/action_runtime.py:714]
- [x] [Review][Patch] Non-finite parser success rates can crash scanner context rendering [/private/tmp/deploywhisper-analyze-action/action_runtime.py:800]

## Dev Notes

### Epic Context

- Epic: 5. Workflow-Native Delivery
- Epic goal: Deliver the report in real review workflows without duplicating analysis logic.
- Epic coverage: WRK-01..10, REV-05..08, ADM-07, DOC-08

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
- UI work belongs under `ui/routes/` and `ui/components/`, following the existing NiceGUI composition style.
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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 5 / Story 5.4 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5.4

### Debug Log References

- Implemented in canonical action repo `deploywhisper/analyze-action`, branch `feature/5-4-pr-comment-formatter`, commits `4748d9f` and `8764724`.
- Review edge fixes implemented in canonical action repo `deploywhisper/analyze-action`, branch `feature/5-4-pr-comment-formatter`, commit `744a571`.
- Live smoke validation used canonical consumer repo `deploywhisper/action-smoke-consumer`, temporary PR `#8`, workflow run `26455287510`, rerun job `77888153317`.
- Review-fix live smoke validation used canonical consumer repo `deploywhisper/action-smoke-consumer`, temporary PR `#9`, workflow run `26456848533`.
- Review edge-fix live smoke validation used canonical consumer repo `deploywhisper/action-smoke-consumer`, temporary PR `#10`, workflow run `26457945837`.

### Completion Notes List

- Expanded the marketplace action PR comment formatter to include verdict, Evidence Law status/detail, top risks with evidence counts, blast radius, rollback, incident/public pattern matches, scanner context, uncertainty, report link, and an explicit advisory-only line.
- Added Evidence Law compatibility fallback so older/partial compact summaries can derive `Satisfied` / `Needs review` from persisted findings and evidence.
- Preserved the existing 2,000-character comment cap, scan metadata marker, same-commit rerun delta, and Python-stdlib-only action runtime.
- Updated the action README behavior section to document the expanded PR comment content.
- Resolved all five code-review patch findings: malformed payloads now degrade, Evidence Law fallback requires verified linked evidence, malformed pattern-match entries no longer hide later valid matches, rendered comment text/links are sanitized, and the `Uncertainty:` line no longer reuses advisory boilerplate.
- Resolved the three follow-up code-review patch findings: non-dict API response sections now degrade before output/comment handling, rendered comment fields collapse control-line injection and escape common Markdown markers, and non-finite parser success rates are ignored instead of crashing scanner context rendering.
- UI validation not applicable: this story changes GitHub PR comment text in the standalone Marketplace action, not a NiceGUI route, browser interaction, keyboard flow, or screen-reader surface.
- Validation passed:
  - `python3 -m unittest tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_includes_full_advisory_context -q`
  - `python3 -m unittest discover -s tests -q` in `deploywhisper/analyze-action` (`33 tests OK`)
  - `python3 -m unittest discover -s tests -q` in `deploywhisper/analyze-action` after review fixes (`39 tests OK`)
  - `python3 -m unittest discover -s tests -q` in `deploywhisper/analyze-action` after review edge fixes (`41 tests OK`)
  - `python3 -m py_compile action_runtime.py tests/test_action_runtime.py` in `deploywhisper/analyze-action`
  - `PYTHONPATH=/private/tmp/deploywhisper-analyze-action python3 /private/tmp/deploywhisper-analyze-action/run_action.py --help`
  - `git diff --check` in `deploywhisper/analyze-action`
  - `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/deploywhisper-smoke.yml"); puts "workflow yaml ok"'` in `deploywhisper/action-smoke-consumer`
  - `git diff --check` in `deploywhisper/action-smoke-consumer`
  - live smoke PR `deploywhisper/action-smoke-consumer#8`, workflow run `26455287510`, rerun job `77888153317`, passed and posted comment `4545180466` with the Story 5.4 fields.
  - live smoke PR `deploywhisper/action-smoke-consumer#9`, workflow run `26456848533`, passed and posted comment `4545450694` with the hardened Story 5.4 formatter.
  - live smoke PR `deploywhisper/action-smoke-consumer#10`, workflow run `26457945837`, passed and posted comment `4545629237` with the hardened Story 5.4 edge fixes.
  - `./.venv/bin/python -m unittest discover -q` in `deploywhisper/deploywhisper` (`445 tests OK`, `skipped=1`)
  - `ruby -e 'require "yaml"; YAML.load_file("_bmad-output/implementation-artifacts/sprint-status.yaml"); puts "sprint yaml ok"'` in `deploywhisper/deploywhisper`
  - `git diff --check` in `deploywhisper/deploywhisper`

### File List

- `/private/tmp/deploywhisper-analyze-action/action_runtime.py`
- `/private/tmp/deploywhisper-analyze-action/tests/test_action_runtime.py`
- `/private/tmp/deploywhisper-analyze-action/README.md`
- `_bmad-output/implementation-artifacts/5-4-pr-comment-formatter.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-26: Implemented PR comment formatter expansion in `deploywhisper/analyze-action` and validated through `deploywhisper/action-smoke-consumer`.
- 2026-05-26: Code review found 5 patch findings; story returned to in-progress for fixes.
- 2026-05-26: Fixed all 5 code-review findings in `deploywhisper/analyze-action` and revalidated through `deploywhisper/action-smoke-consumer`.
- 2026-05-26: Fixed 3 follow-up code-review findings in `deploywhisper/analyze-action` and revalidated through `deploywhisper/action-smoke-consumer`.
