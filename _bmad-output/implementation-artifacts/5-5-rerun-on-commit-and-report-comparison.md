# Story 5.5: Rerun-on-Commit and Report Comparison

Status: review

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a PR reviewer,
I want analysis to rerun and compare after new commits,
So that I can see whether changes resolved or introduced risk.

## Acceptance Criteria

1. Given a PR receives new commits or changed artifacts, When rerun is triggered, Then a new report is generated and compared with the previous relevant report. And PR output highlights new, resolved, and persistent findings.

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

- [x] [Review][Patch] Finding metadata can exceed the 2,000-character PR comment cap because scan-marker keys are unbounded and fallback compaction preserves oversized metadata [/private/tmp/deploywhisper-analyze-action/action_runtime.py:650]
- [x] [Review][Patch] Reruns that resolve all findings or introduce findings after a clean previous scan suppress the finding-delta summary instead of showing all-resolved or all-new results [/private/tmp/deploywhisper-analyze-action/action_runtime.py:687]
- [x] [Review][Patch] Finding comparison truncates metadata to the first 12 findings before computing deltas, so larger reruns can hide or miscount new, resolved, and persistent findings [/private/tmp/deploywhisper-analyze-action/action_runtime.py:650]
- [x] [Review][Patch] Finding identity ignores stable finding ids and collapses duplicate title/category findings, which can misclassify changed wording or duplicate resources as new/resolved/persistent incorrectly [/private/tmp/deploywhisper-analyze-action/action_runtime.py:635]
- [x] [Review][Patch] Legacy scan markers without `finding_keys` are truncated to 6 findings before delta comparison, undercounting resolved and persistent findings from older comments [/private/tmp/deploywhisper-analyze-action/action_runtime.py:515]
- [x] [Review][Patch] Current scan markers capped at 32 keys can misclassify retained previous findings beyond the cap as new findings instead of avoiding or qualifying exact counts [/private/tmp/deploywhisper-analyze-action/action_runtime.py:710]
- [x] [Review][Patch] Delta example lines can render `UNKNOWN Untitled finding` when the changed finding key has no stored label, so the PR comment does not actually identify the new or resolved finding [/private/tmp/deploywhisper-analyze-action/action_runtime.py:740]
- [x] [Review][Patch] Existing upstream finding keys are truncated to 16 characters instead of compact-hashed, so distinct long keys with the same prefix collapse into one comparison identity [/private/tmp/deploywhisper-analyze-action/action_runtime.py:668]
- [x] [Review][Patch] Fallback identity still collapses distinct no-ID findings with the same title and category, hiding duplicate-resource new/resolved changes [/private/tmp/deploywhisper-analyze-action/action_runtime.py:676]
- [x] [Review][Patch] Large previous reports over the marker key cap degrade to “exact counts unavailable,” so PR output no longer highlights new, resolved, and persistent findings for those reruns [/private/tmp/deploywhisper-analyze-action/action_runtime.py:840]
- [x] [Review][Patch] Current scan markers with 13-32 findings store keys but no labels, so a later rerun can show exact counts without naming the changed finding [/private/tmp/deploywhisper-analyze-action/action_runtime.py:564]
- [x] [Review][Patch] Marker truncation flags are parsed with `bool(...)`, so string values such as `"false"` are treated as true and can suppress exact delta output unnecessarily [/private/tmp/deploywhisper-analyze-action/action_runtime.py:539]
- [x] [Review][Patch] Fallback identity uses the first discriminator field only, so same-file no-ID findings that differ by line can still collapse into one comparison key [/private/tmp/deploywhisper-analyze-action/action_runtime.py:713]

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

- `_bmad-output/planning-artifacts/epics.md` - source Epic 5 / Story 5.5 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- 2026-05-26: Implemented in required action repo, not in `deploywhisper/deploywhisper` source code: `/private/tmp/deploywhisper-analyze-action` branch `feature/5-5-rerun-report-comparison`, commit `ae4ab59`.
- 2026-05-26: Addressed all 4 code-review patch findings in required action repo commit `7d266c6`: bounded marker metadata, preserved all-new/all-resolved deltas, compared up to compact key capacity before label truncation, and used stable finding ids for identity.
- 2026-05-26: Re-ran `bmad-code-review` on Story 5.5 after commit `7d266c6`; review found 5 remaining patch findings around legacy marker truncation, capped comparison accuracy, unlabeled delta examples, long-key collisions, and no-ID duplicate fallback identity.
- 2026-05-26: Addressed all 5 re-review patch findings in required action repo commit `f8d8b3c`: legacy markers now reconstruct all available keys, capped previous markers avoid exact misleading deltas, unlabeled placeholders are skipped, long explicit keys are compact-hashed, and no-ID fallback identity includes resource/location discriminators.
- 2026-05-26: Re-ran `bmad-code-review` on Story 5.5 after smoke-consumer validation; review found 4 patch findings around large-report comparison degradation, 13-32 finding label omission, string truncation flags, and same-file line-level fallback identity.
- 2026-05-26: Addressed all 4 final re-review patch findings in required action repo commit `be3db00`: compact keyset metadata now supports exact comparison for medium-sized reports, 13-32 finding labels are retained when comment budget allows, truncation flags require real JSON booleans, same-file no-ID fallback identity includes line-level discriminators, and final comment compaction preserves visible delta lines.
- Red test: `python3 -m unittest tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_highlights_new_resolved_and_persistent_findings -q` failed before implementation because PR comments did not include finding-level deltas.
- Focused green test: `python3 -m unittest tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_highlights_new_resolved_and_persistent_findings tests.test_action_runtime.UpsertPrCommentTests.test_extract_comment_metadata_reads_previous_scan_marker -q` passed.
- Review-fix focused validation: `python3 -m unittest tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_highlights_new_resolved_and_persistent_findings tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_reports_all_resolved_and_all_new_findings tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_uses_stable_ids_for_changed_titles_and_duplicates tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_counts_more_than_twelve_findings_before_truncating_labels tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_keeps_hidden_metadata_within_comment_budget tests.test_action_runtime.UpsertPrCommentTests.test_extract_comment_metadata_reads_previous_scan_marker -q` passed with 6 tests.
- Re-review focused validation: `python3 -m unittest tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_counts_legacy_marker_findings_beyond_label_floor tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_avoids_exact_delta_counts_for_capped_previous_marker tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_labels_resolved_finding_beyond_first_six tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_hashes_long_existing_keys_without_prefix_collision tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_distinguishes_duplicate_no_id_findings_by_resource tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_keeps_hidden_metadata_within_comment_budget -q` passed with 6 tests.
- Final re-review focused validation: `python3 -m unittest tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_compares_large_previous_marker_with_compact_keyset tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_labels_resolved_finding_in_medium_sized_marker tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_distinguishes_same_file_findings_by_line tests.test_action_runtime.BuildPrCommentTests.test_build_pr_comment_keeps_hidden_metadata_within_comment_budget tests.test_action_runtime.UpsertPrCommentTests.test_extract_comment_metadata_requires_boolean_truncation_flags -q` passed with 5 tests.
- Full action validation: `python3 -m unittest discover -s tests -q` passed with 42 tests.
- Full action review-fix validation: `python3 -m unittest discover -s tests -q` passed with 46 tests.
- Full action re-review validation: `python3 -m unittest discover -s tests -q` passed with 51 tests.
- Full action final re-review validation: `python3 -m unittest discover -s tests -q` passed with 53 tests.
- Compile validation: `python3 -m py_compile action_runtime.py tests/test_action_runtime.py` passed.
- Entrypoint validation: `PYTHONPATH=/private/tmp/deploywhisper-analyze-action python3 /private/tmp/deploywhisper-analyze-action/run_action.py --help` passed.
- Whitespace validation: `git diff --check` passed.
- Live smoke-consumer validation: `deploywhisper/action-smoke-consumer` workflow run `26463827370` passed on branch `smoke/story-5-5-action-branch`; the workflow used `deploywhisper/analyze-action@feature/5-5-rerun-report-comparison`, downloaded action SHA `f8d8b3c4c3566f9124a02af9d692736c18580758`, and asserted successful manual outputs for report IDs `52` and `53`.
- Final live smoke-consumer validation: `deploywhisper/action-smoke-consumer` workflow run `26464659540` passed on branch `smoke/story-5-5-action-branch`; the workflow used `deploywhisper/analyze-action@feature/5-5-rerun-report-comparison`, downloaded action SHA `be3db000956ea1f70ad0b0e15e5266748f6fdf5e`, and asserted successful manual outputs for report IDs `54` and `55`.
- Main repository regression: `./.venv/bin/python -m unittest discover -q` passed with 445 tests and 1 skipped.
- Main repository review-fix validation: `git diff --check` passed, and `./.venv/bin/python -m unittest discover -q` passed with 445 tests and 1 skipped.
- Main repository re-review validation: `git diff --check` passed, and `./.venv/bin/python -m unittest discover -q` passed with 445 tests and 1 skipped.
- Main repository final re-review validation: `git diff --check` passed, and `./.venv/bin/python -m unittest discover -q` passed with 445 tests and 1 skipped.
- UI validation not applicable: no NiceGUI route, rendered app UI, browser interaction, keyboard behavior, or accessibility semantics changed in `deploywhisper/deploywhisper`.

### Completion Notes List

- Added finding metadata to the action PR comment scan marker so a later PR rerun can compare against the previous relevant scan.
- Added PR comment output for finding-level deltas: new, resolved, and persistent finding counts with representative labels.
- Resolved review findings by compacting scan-marker identity keys, separating compact comparison keys from human labels, allowing all-new/all-resolved comparisons, and preferring stable finding ids over title/category fallback identity.
- Resolved re-review findings by preventing capped previous markers from emitting false exact counts, preserving legacy marker comparison beyond the display-label limit, hashing long explicit keys, and adding resource/location fallback discrimination for duplicate no-ID findings.
- Resolved final re-review findings by increasing compact comparison capacity with packed keysets, preserving medium-sized marker labels, strictly parsing truncation flags, adding line-level fallback discriminators, and keeping visible finding-delta lines through final 2,000-character compaction.
- Kept existing score/severity comparison, same-commit rerun note, advisory-only behavior, single-comment update behavior, and 2,000-character comment cap.
- Updated action README behavior docs to describe new/resolved/persistent finding comparison.

### File List

- `_bmad-output/implementation-artifacts/5-5-rerun-on-commit-and-report-comparison.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `/private/tmp/deploywhisper-analyze-action/action_runtime.py`
- `/private/tmp/deploywhisper-analyze-action/tests/test_action_runtime.py`
- `/private/tmp/deploywhisper-analyze-action/README.md`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-05-26: Implemented rerun finding comparison in the external analyze-action runtime and moved story to review.
- 2026-05-26: Code review found 4 patch issues and moved story back to in-progress.
- 2026-05-26: Fixed all 4 code-review patch findings in the external analyze-action runtime and moved story back to review.
- 2026-05-26: Re-run code review found 5 remaining patch issues and moved story back to in-progress.
- 2026-05-26: Fixed all 5 re-review patch findings in the external analyze-action runtime and moved story back to review.
- 2026-05-26: Re-run code review found 4 remaining patch issues and moved story back to in-progress.
- 2026-05-26: Fixed all 4 final re-review patch findings in the external analyze-action runtime, passed action and smoke-consumer validation, and moved story back to review.
