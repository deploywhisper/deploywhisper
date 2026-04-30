# Reviewer Feedback Capture

DeployWhisper now captures reviewer feedback for persisted analysis reports so teams can start building an auditable learning loop around finding quality.

## Reviewer Workflow

- Open a saved report in the main review UI.
- Use the **Reviewer feedback** section to record:
  - `Thumbs up` when a finding was useful
  - `Thumbs down` when a finding was not useful
  - `Mark false positive` with an optional reason when the finding should not have been surfaced
  - `Missed finding note` when the report failed to call out an important risk

The live dashboard review surface and the full history detail page both expose the same feedback controls.

## Storage Model

- Feedback is stored in the `feedback_events` table.
- Migration `012_add_feedback_event_fields` adds:
  - `finding_id`
  - `false_positive_reason`
- Feedback stays project-scoped by deriving the owning workspace from the persisted `analysis_id`.
- Finding feedback is validated against the findings stored on the target report before persistence.

## Admin Summary

- The **Settings** page now shows a **Reviewer feedback summary** card for the active project.
- The summary reports:
  - useful findings
  - not useful findings
  - false positives
  - missed findings
  - recent reviewer notes

The summary uses the latest feedback state per finding while still retaining the underlying feedback events for auditability.
