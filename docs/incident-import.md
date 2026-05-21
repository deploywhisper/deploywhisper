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
