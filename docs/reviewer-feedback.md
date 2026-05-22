# Reviewer Feedback Capture

DeployWhisper now captures reviewer feedback for persisted analysis reports so teams can start building an auditable learning loop around finding quality.

## Reviewer Workflow

- Open a saved report in the main review UI.
- Use the **Reviewer feedback** section to record:
  - `Thumbs up` when a finding was useful
  - `Mark noisy` when a finding was not useful but was not a false positive
  - `Mark false positive` with an optional reason when the finding should not have been surfaced
  - `Missed finding note` on the finding being reviewed when the report failed to call out an important risk
  - `Report-level missed finding note` when a clean report has no findings but still missed an important risk

The live dashboard review surface and the full history detail page both expose the same feedback controls.

## Storage Model

- Feedback is stored in the `feedback_events` table.
- Migration `012_add_feedback_event_fields` adds:
  - `finding_id`
  - `false_positive_reason`
- Feedback stays project-scoped by deriving the owning workspace from the persisted `analysis_id`.
- Finding feedback and finding-level missed-risk notes are validated against the findings stored on the target report before persistence.
- Clean reports with no findings can still store a report-scoped missed-risk note.
- Feedback events are append-only calibration inputs; they do not rewrite the historical report verdict, severity, recommendation, or confidence.

## Admin Summary

- The **Settings** page now shows a **Reviewer feedback summary** card for the active project.
- The settings summary is an all-workspaces aggregate for the active project.
- The summary reports:
  - useful findings
  - noisy findings
  - false positives
  - missed findings
  - recent reviewer notes

The summary uses the latest feedback state per finding while still retaining the underlying feedback events for auditability.
