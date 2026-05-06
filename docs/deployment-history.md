# Deployment Outcome Capture

DeployWhisper can now capture post-deployment results for persisted analyses so teams can audit deployment history per project/workspace and feed later calibration work.

## API

Record an outcome with the deployment webhook endpoint:

```bash
curl -X POST http://localhost:8080/api/v1/deployments/outcomes \
  -H 'Content-Type: application/json' \
  -H 'X-DeployWhisper-Outcome-Token: change-me' \
  -d '{
    "analysis_id": 42,
    "outcome": "success",
    "deployed_at": "2026-04-30T08:15:00Z",
    "environment": "prod"
  }'
```

Query stored outcome history:

```bash
curl "http://localhost:8080/api/v1/deployments/outcomes?analysis_id=42"
```

Project and workspace filters are also supported for scoped history views:

```bash
curl "http://localhost:8080/api/v1/deployments/outcomes?project_key=payments&workspace_key=prod"
```

Supported outcome values are `success`, `failure`, and `rolled_back`.
Set `DEPLOYWHISPER_OUTCOME_TOKEN` (or `APP_DEPLOYMENT_OUTCOME_TOKEN`) on the server before using the ingestion endpoint.

## CLI

Record an outcome from the shared CLI surface:

```bash
deploywhisper outcome record \
  --analysis-id 42 \
  --outcome success \
  --deployed-at 2026-04-30T08:15:00Z \
  --project payments \
  --workspace prod \
  --environment prod
```

`--deployed-at` is optional for the CLI path; when omitted, DeployWhisper records the current UTC timestamp.

## Rollout Notes

- Migration `011_add_deployment_outcome_fields` adds `deployed_at` and `linked_incident_id` to the existing `deployment_outcomes` table.
- Migration `011_add_deployment_outcome_fields` also backfills the previously metadata-only `incident_records` table into the Alembic chain so `alembic upgrade head` produces a complete schema.
- Migration `016_scope_learning_context_records` adds project/workspace scope to incidents, topology snapshots, feedback, and deployment outcomes.
- Outcome capture stays project/workspace-scoped by deriving the owning scope from the referenced `analysis_id`.
- Incident linkage is optional and validates that the incident belongs to the same project and compatible workspace when provided.
- The webhook-style ingestion path now requires `X-DeployWhisper-Outcome-Token`, aligned with the repo's existing explicit token-based mutation pattern.
