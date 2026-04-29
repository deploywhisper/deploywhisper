# Sprint Change Proposal: Epic 5 Cross-Page Project Switching

Date: 2026-04-28
Project: deploywhisper
Workflow: bmad-correct-course
Mode assumption: Batch

## 1. Issue Summary

Story 5.1 introduced lightweight project/workspace scoping and made the dashboard upload flow require an explicit project selection before manual analysis. That solved isolation for new uploads, but it left project switching trapped inside the dashboard upload panel.

Once a user navigates to History or other secondary pages, they can see only the currently active project's reports with no obvious way to identify, search, or change the active project without returning to the dashboard first. This creates a workflow break in the new project-scoped model: data is correctly isolated, but cross-page navigation does not let users intentionally move between project contexts.

This is not a new product direction. It is a usability and workflow-completion gap in the Story 5.1 workspace model.

## 2. Change Navigation Checklist

| Item | Status | Finding |
| --- | --- | --- |
| 1.1 Trigger story | Done | `5-1-project-workspace-foundation` revealed the gap after completion. |
| 1.2 Core problem | Done | Misunderstanding of original requirements: project scoping was implemented, but project context switching remained dashboard-local instead of cross-page. |
| 1.3 Supporting evidence | Done | `ui/components/upload_panel.py` contains the only project selector; `ui/theme.py` shared navigation shell has no project control; `ui/routes/history.py` reads `get_active_project()` and scopes results but offers no switcher. |
| 2.1 Current epic viability | Done | Epic 5 remains viable as planned. The issue is a refinement to the existing workspace foundation, not an epic-level failure. |
| 2.2 Epic-level changes | Done | No new epic needed. Reopen and patch Story 5.1, or add an explicit follow-up note under that story's acceptance/tasks. |
| 2.3 Future epic impact | Done | Future Epic 5 stories benefit from a clear active-project model across pages, especially history, outcomes, feedback, trends, and topology workflows. |
| 2.4 New epic need | Done | No. The change stays inside Epic 5. |
| 2.5 Priority/order | Done | Address before deeper Epic 5 context features so later pages do not repeat the same dashboard-only project-switch constraint. |
| 3.1 PRD conflicts | Done | No PRD conflict. PRD already calls for lightweight project/workspace scoping for analyses, topology, history, and feedback. |
| 3.2 Architecture conflicts | Done | No architecture rewrite needed. The change stays within the shared UI shell and existing project service boundary. |
| 3.3 UI/UX conflicts | Done | UX spec currently defines project selection before upload, but it does not yet make cross-page project switching explicit in navigation/page-header behavior. |
| 3.4 Secondary artifacts | Done | Story 5.1 artifact, project-workspaces docs, and UI regression coverage should be updated. |
| 4.1 Direct adjustment | Viable | Low-to-moderate effort, low risk. Best path is a focused Story 5.1 refinement. |
| 4.2 Rollback | Not viable | No rollback is justified. The underlying project-scoping model is correct and should be extended, not removed. |
| 4.3 MVP review | Not viable | MVP and Phase 2 scope remain achievable. This improves usability of already-approved scope. |
| 4.4 Recommended path | Done | Direct adjustment inside Story 5.1 with shared-shell/history-page project switching and regression coverage. |

## 3. Impact Analysis

### Epic Impact

Epic 5 remains the correct home for this work. The issue is part of the "project/workspace foundation" story because it affects how users move between isolated history and report contexts after scoping is introduced.

No epic renumbering or resequencing is required.

### Story Impact

Story 5.1 should be reopened for a targeted refinement. The core change is to expand the web-UI workspace behavior from:

- selecting/creating a project before upload

to:

- selecting/creating a project before upload
- clearly showing the active project across pages
- allowing users to switch project context from History or the shared navigation shell
- ensuring dashboard, history, and related report views refresh consistently when the active project changes

This avoids adding a new story solely to compensate for a recently completed but incomplete workspace interaction model.

### Artifact Conflicts

- PRD: no requirement change needed; current scope already supports this refinement.
- Architecture: no structural change needed; existing shared-shell and service boundaries are sufficient.
- UX Design: navigation and project-workspace flow should explicitly mention cross-page project switching and active-project visibility.
- Story artifact: Story 5.1 acceptance and tasks should be clarified so the behavior is testable and reviewable.
- Project docs: `docs/project-workspaces.md` should describe the cross-page project switch behavior instead of only the dashboard upload flow.

### Technical Impact

Implementation should prefer one shared project-context control rather than duplicating separate selectors on every page.

Likely technical touchpoints:

- `ui/theme.py` for shared shell or shared header-level project context UI
- `ui/components/upload_panel.py` to avoid conflicting dashboard-only ownership of project switching
- `ui/routes/history.py` to surface active project context and refresh behavior
- `ui/routes/dashboard.py` and `ui/routes/settings.py` to ensure the active project remains obvious and consistent after switching
- `tests/test_ui/test_app_shell.py`
- `tests/test_ui/test_history_page.py`
- `tests/test_ui/test_upload_panel.py`

The active-project state should continue to flow through `services.project_service` rather than introducing page-local project state.

## 4. Detailed Change Proposals

### Story: 5.1 Project workspace foundation

Section: Acceptance Criteria

OLD:

```text
2. Web UI requires selecting or creating a project before new manual analysis uploads.
5. Analysis reports, topology imports, deployment outcomes, and reviewer feedback are scoped to a project/workspace.
```

NEW:

```text
2. Web UI requires selecting or creating a project before new manual analysis uploads, and makes the active project obvious in the shared workspace so users can change project context without returning to the dashboard upload panel.
5. Analysis reports, topology imports, deployment outcomes, and reviewer feedback are scoped to a project/workspace, and dashboard/history/report views refresh consistently when the active project changes.
```

Rationale: Story 5.1 established isolation but left project switching trapped inside one page-local control. The acceptance criteria should test both isolation and cross-page usability.

### Story: 5.1 Project workspace foundation

Section: Tasks / Subtasks

OLD:

```text
- [x] Implement AC2: web UI create/select project flow before manual analysis upload
- [x] Add deterministic tests, docs, and rollout notes covering project-scoped analysis flows
```

NEW:

```text
- [ ] Implement AC2 refinement: shared-shell or history-page project selection/search flow that updates the active workspace across routed pages
- [ ] Make the active project visible on dashboard, history, and settings surfaces without relying on upload-panel context
- [ ] Add deterministic UI regression coverage for cross-page project switching and project-scoped history refresh
```

Rationale: The missing behavior is not just a label change. It needs explicit implementation and regression ownership.

### UX Design Specification

Section: Project Workspace Selection Flow

OLD:

```text
A[Open dashboard or trigger GitHub analysis] --> B{Project already selected or derivable?}
...
E --> F[Upload files or submit repository-triggered analysis]
F --> G[Report, topology, history, feedback, and outcomes are stored under that project]
```

NEW:

```text
A[Open dashboard, history, or trigger GitHub analysis] --> B{Project already selected or derivable?}
...
E --> F[User can confirm, search, or switch the active project from shared workspace chrome or history controls]
F --> G[Upload files or review project-scoped reports in the selected workspace]
G --> H[Report, topology, history, feedback, and outcomes are stored and viewed under that project]
```

Rationale: The workspace model should support both analysis submission and later report retrieval without forcing a return to the dashboard.

### UX Design Specification

Section: Navigation Patterns

OLD:

```text
- route-level navigation for dashboard, history, settings, and admin areas
- stable left-side shell navigation using stock Quasar patterns
- the left navigation must remain visible on desktop and serve as the primary page-switching control
```

NEW:

```text
- route-level navigation for dashboard, history, settings, and admin areas
- stable shell navigation also communicates the active project/workspace context
- users can identify and switch the active project from shared workspace chrome or a history-local selector without detouring through the dashboard upload flow
```

Rationale: The new project-scoped product model changes navigation requirements, not only upload requirements.

### Project Workspace Docs

Section: User Flows in `docs/project-workspaces.md`

OLD:

```text
- Web UI: choose an existing project or create one from the upload panel before running a manual analysis.
```

NEW:

```text
- Web UI: choose an existing project or create one before running a manual analysis, and switch the active project from shared workspace controls or the history page when moving between report sets.
```

Rationale: User-facing docs should describe the actual workspace-navigation contract, not only the initial upload step.

## 5. Recommended Approach

Use direct adjustment inside Story 5.1.

This is a moderate sprint correction, not a major replan. The safest path is:

1. Reopen Story 5.1 from `done` to `review` or `in-progress`.
2. Update the story acceptance/tasks to include cross-page project visibility and switching.
3. Implement one shared project-context control in the shell or one shell-plus-history pattern, not one-off selectors per page.
4. Add regression coverage for cross-page switching and history refresh behavior.
5. Return Story 5.1 to review and rerun code review.

Effort impact:

- Estimate: low-to-moderate
- Timeline impact: small, localized follow-up
- Risk: low-to-moderate because the change touches shared UI chrome, but it builds on existing project service behavior instead of altering the data model

## 6. Implementation Handoff

Scope classification: Moderate.

Recommended handoff:

- Product Owner / Developer:
  - reopen Story 5.1
  - update story text and sprint status
  - confirm the selector placement decision (shared shell preferred; history-local acceptable if shared-shell complexity is disproportionate)
- Developer:
  - implement the project-switch UX
  - keep one active-project source of truth
  - update regression coverage and workspace docs
- Code Review:
  - verify active-project visibility
  - verify switching refreshes dashboard/history/report surfaces consistently
  - verify no page can imply "wrong project" after a switch

Success criteria:

- users can identify/search/select the active project from History or shared workspace chrome
- switching project refreshes dashboard, history, and related report views consistently
- the active project is obvious in the UI
- deterministic regression tests lock the cross-page behavior

