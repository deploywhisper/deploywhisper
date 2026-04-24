# Skills Analytics

Story 4.8 adds a shared analytics layer for the skills marketplace so the same
per-skill signals are available in the API, browser, and CLI.

## Metrics

Each registry skill now exposes:

- `install_count`
- `test_results.pass_rate`
- `updated_at`
- `active_issue_count`
- `analytics_updated_at`

## Data source

The snapshot lives in `data/skill-analytics.json`.

- `updated_at` still comes from the skill manifest file timestamp
- `test_results.pass_rate` still comes from the deterministic harness
- install count, star count, and active issue count come from the committed
  analytics snapshot
- `analytics_updated_at` records the snapshot refresh time

## Refresh workflow

Daily refresh is handled by:

- workflow: `.github/workflows/refresh-skill-analytics.yml`
- script: `scripts/refresh_skill_analytics.py`

The refresh workflow now combines two runtime sources:

- install and star metrics from `DEPLOYWHISPER_SKILL_ANALYTICS_URL`
- active issue counts from GitHub issue search

The refresh script refuses to run without the metrics URL so the job does not
silently republish stale install/star values with a fresh timestamp.

## Surfaces

- Browser: `/skills` and `/skills/{id}`
- API: `/api/v1/skills` and `/api/v1/skills/{id}`
- CLI: `deploywhisper skill list --catalog`
