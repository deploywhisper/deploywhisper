# Story {{epic_num}}.{{story_num}}: {{story_title}}

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a {{role}},
I want {{action}},
so that {{benefit}}.

## Acceptance Criteria

1. [Add acceptance criteria from epics/PRD]

### Requirement Traceability

- Primary PRD requirements: [Add PRD requirement IDs, e.g. `EVD-02`, `REV-05`]
- Supporting PRD / NFR / differentiation requirements: [Add supporting IDs where relevant]
- Coverage intent: [`Baseline`, `Delta`, or `Baseline + Delta`]
- Story alignment note: [Explain how this story maps to the current repo baseline and roadmap intent]

## Tasks / Subtasks

- [ ] Task 1 (AC: #)
  - [ ] Subtask 1.1
- [ ] Task 2 (AC: #)
  - [ ] Subtask 2.1
- [ ] UI validation gate (AC: UI-facing ACs, if applicable)
  - [ ] If this story changes any UI route, NiceGUI component, rendered report/history/dashboard surface, browser interaction, keyboard behavior, or accessibility semantics, add or update Playwright coverage and run the relevant browser validation before review. Use `npm run test:ui-review` for review/report flows, `RUN_UI_A11Y=1 bash scripts/ci-local.sh` when the full local UI lane is needed, and `npm run test:ui-review:voiceover` on macOS for screen-reader or keyboard/a11y semantics. If no UI surface is touched, record "UI validation not applicable" in the Dev Agent Record.

## Dev Notes

- Relevant architecture patterns and constraints
- Source tree components to touch
- Testing standards summary
- UI validation requirement: UI-facing stories must be validated in a real browser with Playwright before moving to review; do not close UI work with only Python/unit tests.

### Project Structure Notes

- Alignment with unified project structure (paths, modules, naming)
- Detected conflicts or variances (with rationale)

### References

- Cite all technical details with source paths and sections, e.g. [Source: docs/<file>.md#Section]

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
