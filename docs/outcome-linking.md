# Outcome Linking and Weekly Backtesting

DeployWhisper can now link incident records back to persisted analysis reports and run a weekly backtesting pass over deployment outcomes to measure whether the product warned before failed deploys.

## Incident Linking

- `incident_records` now supports an optional `analysis_id` reference.
- Use `services.incident_service.ingest_incident_document(..., analysis_id=<id>)` to link an incident directly to a persisted report.
- Deployment outcomes can still link incidents through `linked_incident_id`; Story 5.7 adds the reverse reference so incidents and analyses can be joined without inventing a separate history model.

## Weekly Backtesting

- `services.backtesting_service.run_weekly_backtest(...)` computes a 7-day backtest window for one project, or one workspace when `workspace_id` / `workspace_key` is supplied.
- Failed deploys are currently defined as deployment outcomes labeled `failure` or `rolled_back`.
- Linked incidents enrich failed deployment rows with incident context, but they do not create synthetic failed-deploy rows on their own.
- DeployWhisper counts a deploy as having warned when the persisted report recommendation is not `go`.
- The weekly summary includes:
  - failed deploy count
  - warned failed deploy count
  - overall precision
  - overall recall
  - per-severity precision/recall seed data
  - row-level failed-deploy backtest records
  - reviewer-feedback false-positive cases and false-positive rate across the latest effective finding-feedback signals
  - false-reassurance cases from latest missed-finding feedback or failed deploys that followed a `go` recommendation
  - deployment-backed false-reassurance rate, with reviewer-only missed-finding signals reported as counts/cases rather than deployment rates
  - confidence trend buckets based on deployment-outcome samples and persisted report confidence, with missing legacy confidence shown as unknown rather than `0.0`
  - confidence limitation labels when outcomes or feedback are too sparse or biased for statistical certainty
- Calibration metrics are directional signals. Sparse or biased inputs are labeled explicitly and should not be presented as statistically certain.
- Feedback-only reviewer signals are included in calibration cases even when no deployment outcome is linked yet, so dashboards do not claim "no calibration inputs" when review evidence exists.
- `calibration_metrics.feedback_event_count` reports the deduplicated latest effective feedback signals used for current calibration. `feedback_history_event_count` reports the raw historical feedback event count when callers need audit/history volume.
- Feedback and deployment outcomes update aggregate calibration metrics only; historical report severity, recommendation, verdict confidence, and narrative fields remain immutable.
- False-reassurance reviewer feedback is counted only when the report did not warn, so missed-finding notes on caution/no-go reports do not imply the advisory system reassured the user.

## Scheduler and Calibration Feed

- The app lifecycle scheduler now runs `run_due_weekly_backtests()` alongside topology drift checks.
- Backtest snapshots are cached in `app_settings` per project, with separate workspace-scoped cache keys when workspace filtering is requested.
- Workspace-scoped on-demand backtests write only the workspace snapshot; they do not update the project-global weekly last-run marker used by the scheduler.
- Cached calibration snapshots are reused only while their recorded 7-day window is fresh, not future-dated, structurally complete, and scoped to the requested project/workspace; stale, malformed, old-schema, clock-skewed, or wrong-scope snapshots are recomputed on read without stamping the scheduler last-run marker.
- `services.backtesting_service.fetch_calibration_dashboard_seed(...)` returns the latest cached snapshot or computes one on demand.
- Reviewer feedback, deployment outcomes, and report deletion invalidate cached snapshots for the affected project so dashboard views and exports pick up false-positive and false-reassurance updates.
- Calibration math uses feedback recorded inside the active 7-day backtest window for false-positive, false-reassurance, sparse-feedback, and feedback-bias signals. The payload also keeps a `feedback_history_event_count` lifetime counter so operators can distinguish current-window evidence from older reviewer activity.
- The history view renders a calibration snapshot card from that shared feed, including the "Directional only" / sparse-data label when calibration evidence is limited. Workspace filters apply consistently to history rows, calibration, and adjacent risk-trend summaries.
