# Incident File Import

DeployWhisper can import organization incident memory from simple Markdown, YAML, and JSON files through the incident import service.

Imports are project scoped. Callers must provide `project_id` or `project_key`; optional workspace scope can also be supplied. The importer validates every file before persisting anything, so a batch with one invalid record creates no partial incident index entries.

## Required Fields

Each record must include:

- `title`
- `severity`
- `incident_date`
- `root_cause`
- `trigger_change`
- `affected_services`
- `rollback_path`
- `prevention_notes`
- `source.system`
- `source.reference`
- `redaction.status`

Markdown files use YAML frontmatter for metadata and Markdown sections for narrative fields:

```markdown
---
severity: high
incident_date: "2026-04-20"
affected_services:
  - checkout-api
source:
  system: manual
  reference: INC-100
redaction:
  status: redacted
  contains_sensitive_data: false
---
# Checkout ingress exposure

## Root cause
Temporary administrative ingress was not removed.

## Trigger change
A deployment template widened the access range.

## Rollback path
Restore the previous access range and redeploy.

## Prevention notes
Require expiry checks for temporary access.
```

YAML and JSON records use the same field names directly. Validation errors include the source file, field name, and corrective message so operators can fix the record before retrying.

## Management and Reindexing

Admins can inspect incident memory status from the Incidents page or the versioned API:

```text
GET /api/v1/incidents/ingestion?project_key=payments
```

The response summarizes indexed count, rejected count, last indexed timestamp, redaction status, freshness, and per-source records for the selected project or workspace. Failed ingestions are retained in source status with the validation field, message, and correction path so operators can fix the source file after the original request has ended.

Reindexing replaces existing incident entries that use the same source file in the same project scope:

```text
POST /api/v1/incidents/reindex
```

Set `remove_missing_sources` to `true` when the submitted source list should become the complete managed index for that project/workspace. In that mode, omitted files are removed only when they already exist in DeployWhisper's ingestion source registry for the requested scope; manually recorded or otherwise unmanaged incident history is preserved. Duplicate source file names in a single reindex request are rejected because they would create ambiguous replacement state.

Reindex replacement is transactional: source validation, stale managed-source removal, replacement incident rows, and source status updates succeed or fail as one unit. Reports also snapshot the incident index version and freshness state used during analysis so consumers can tell whether incident matches came from current, stale, or empty incident memory.
