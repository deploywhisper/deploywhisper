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

- install and star metrics from `DEPLOYWHISPER_SKILL_ANALYTICS_URL`, or from
  the default public registry feed at
  `https://deploywhisper.github.io/skills-registry/skill-popularity.json`
- active issue counts from GitHub issue search

`DEPLOYWHISPER_SKILL_ANALYTICS_URL` is optional and should only be configured
when the workflow needs to read a different metrics feed. The metrics feed must
contain a top-level `skills` object with every built-in skill id and
`install_count` / `star_count` values.

## Surfaces

- Browser: `/skills` and `/skills/{id}`
- API: `/api/v1/skills` and `/api/v1/skills/{id}`
- CLI: `deploywhisper skill list --catalog`
