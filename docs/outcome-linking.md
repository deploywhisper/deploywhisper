# Outcome Linking and Weekly Backtesting

DeployWhisper can now link incident records back to persisted analysis reports and run a weekly backtesting pass over deployment outcomes to measure whether the product warned before failed deploys.

## Incident Linking

- `incident_records` now supports an optional `analysis_id` reference.
- Use `services.incident_service.ingest_incident_document(..., analysis_id=<id>)` to link an incident directly to a persisted report.
- Deployment outcomes can still link incidents through `linked_incident_id`; Story 5.7 adds the reverse reference so incidents and analyses can be joined without inventing a separate history model.

## Weekly Backtesting

- `services.backtesting_service.run_weekly_backtest(...)` computes a 7-day backtest window for one project.
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

## Scheduler and Calibration Feed

- The app lifecycle scheduler now runs `run_due_weekly_backtests()` alongside topology drift checks.
- Backtest snapshots are cached in `app_settings` per project.
- `services.backtesting_service.fetch_calibration_dashboard_seed(...)` returns the latest cached snapshot or computes one on demand.
- The history view renders a calibration snapshot card from that shared feed so later dashboard work can reuse the same storage contract.
