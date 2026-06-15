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

## Incident Replay Backtesting

- `services.backtesting_service.run_incident_backtest(...)` replays imported incident records that are linked to persisted analysis reports.
- The replay uses the locally stored accepted artifact snapshots from the linked report and runs them through the shared analysis core with ambient topology, incident memory, narrative generation, and LLM assistance disabled. Raw artifacts remain local.
- The CLI command is:

```bash
python -m cli.analyze benchmark backtest-incidents --project-key <project>
```

- Add `--workspace-key`, `--project-id`, or `--workspace-id` when a narrower scope is needed.
- Each scenario is classified as:
  - `detected` when the replay produces a caution/no-go warning.
  - `missed` when the replay returns `go`.
  - `unsupported` when the incident is not linked to a report, the linked report is unavailable, accepted artifact snapshots are missing, or the replay parser accepts no artifacts.
  - `insufficient_context` when the shared analysis core reports insufficient supporting context.
  - `error` when replay execution fails.
- Scenario rows link incident metadata, linked report metadata, expected evidence from the original persisted report, observed replay evidence, observed findings, context TODOs, and improvement guidance.
- The command exits non-zero when any scenario is missed or errors, so it can be used as a guardrail for benchmark claims while still reporting unsupported and insufficient-context scenarios explicitly.

## Risk Trend Review

- The history view includes a project-scoped risk trend card that updates with the selected workspace, time range, risk severity, toolchain, and deployment outcome filters. Project scope is required for CLI trend export.
- Trend data preserves historical report immutability. Feedback and deployment outcomes are joined as calibration signals, but they do not rewrite stored report verdicts, severity, recommendation, confidence, narrative, or context-completeness metadata.
- When a bounded time range is selected, the trend payload includes current and previous equal-length windows plus deltas so managers can compare whether signals are improving or recurring. Previous comparison windows use an exclusive upper bound, so events exactly at the current window start are counted only in the current window.
- Report rows are included when they were created in the selected window or have selected-window feedback/outcome activity. Deployment outcomes use `deployed_at` for the event window; reviewer feedback uses feedback `created_at`. The History table and trend card share this activity-window behavior.
- The trend payload compares:
  - verdict / recommendation distribution
  - high and critical report frequency
  - toolchain frequency
  - deployment outcome distribution
  - linked deployment outcome counts
  - reviewer false-positive feedback
  - deployment-backed and reviewer-backed false-reassurance signals
  - partial-context count/rate and average context-completeness score
- Sparse or missing report, feedback, outcome, and context-completeness inputs are returned as explicit limitation labels. Empty or unauthorized project scopes return no report metadata from inaccessible projects, and future-schema reports that history cannot render are excluded from trend summaries.
- Export scoped trend data from the CLI:

```bash
python -m cli.analyze benchmark risk-trends \
  --project-key payments \
  --workspace-key prod \
  --severity high \
  --toolchain terraform \
  --outcome failure \
  --created-from 2026-06-01T00:00:00Z \
  --created-to 2026-06-08T00:00:00Z
```

- The CLI emits the same JSON payload used by the history trend card so browser review and exported trend data stay aligned.
- API history consumers can use the same outcome scope with `GET /api/v1/analyses?outcome=failure` alongside existing project, workspace, severity, toolchain, status, and time filters.

## Scheduler and Calibration Feed

- The app lifecycle scheduler now runs `run_due_weekly_backtests()` alongside topology drift checks.
- Backtest snapshots are cached in `app_settings` per project, with separate workspace-scoped cache keys when workspace filtering is requested.
- Workspace-scoped on-demand backtests write only the workspace snapshot; they do not update the project-global weekly last-run marker used by the scheduler.
- Cached calibration snapshots are reused only while their recorded 7-day window is fresh, not future-dated, structurally complete, and scoped to the requested project/workspace; stale, malformed, old-schema, clock-skewed, or wrong-scope snapshots are recomputed on read without stamping the scheduler last-run marker.
- `services.backtesting_service.fetch_calibration_dashboard_seed(...)` returns the latest cached snapshot or computes one on demand.
- Reviewer feedback, deployment outcomes, and report deletion invalidate cached snapshots for the affected project so dashboard views and exports pick up false-positive and false-reassurance updates.
- Calibration math uses feedback recorded inside the active 7-day backtest window for false-positive, false-reassurance, sparse-feedback, and feedback-bias signals. The payload also keeps a `feedback_history_event_count` lifetime counter so operators can distinguish current-window evidence from older reviewer activity.
- The history view renders a calibration snapshot card from that shared feed, including the "Directional only" / sparse-data label when calibration evidence is limited. Workspace filters apply consistently to history rows, calibration, and adjacent risk-trend summaries.
