# Scanner Imports

DeployWhisper can ingest SARIF 2.1.0 output from external scanners and store
each scanner result as project-scoped external evidence. Scanner severity stays
labeled as scanner context; it does not automatically become a high or critical
DeployWhisper finding without DeployWhisper evidence and scoring.

## SARIF Endpoint

```http
POST /api/v1/scanner-imports/sarif
```

Request body:

```json
{
  "project_key": "payments",
  "source_file": "checkov.sarif",
  "content": "{\"version\":\"2.1.0\",\"runs\":[...]}"
}
```

Optional scope fields:

- `project_id`
- `workspace_id`
- `workspace_key`

`source_file` must be a safe relative `.sarif` or `.json` file name. The
importer rejects sensitive-looking names, parent traversal, reserved unsafe
prefixes, and payloads larger than the 50 MB local analysis-session intake
limit. Each SARIF import is capped at 1,000 results to keep local writes and API
responses bounded. Re-importing findings with the same project/workspace and
stable scanner source identity refreshes the existing evidence row, including
severity, message, location, and source-file metadata, while new findings in the
same SARIF run are imported as new evidence. When SARIF `fingerprints` are
present, DeployWhisper uses them with scanner tool, rule, artifact, and region
data for stable source identity instead of rendered message wording. SARIF
`partialFingerprints` are also combined with scanner tool, rule, artifact, and
region data so coarse scanner hashes do not collapse distinct findings. When
scanner fingerprints are absent, the fallback identity includes the rendered
message, artifact, and region so distinct same-location findings can still be
imported.
SARIF `artifactLocation.uri` values must also be concrete repository-relative
artifact paths; empty, dot-only, absolute, URL-style, query or fragment,
traversal, and sensitive-looking paths are rejected rather than persisted.
Message template arguments, fingerprints, and direct severity metadata must use
the SARIF string forms DeployWhisper can preserve deterministically.

Response data includes the scanner import id, project scope, imported count,
tool names, and normalized evidence rows. Each evidence row includes:

- `source_type`: always `external_scanner`
- `tool_name`
- `rule_id`
- `rule_name`
- `severity`
- `location`
- `source_ref`
- `project_id` and `project_key`

## Validation

Unsupported SARIF structures return `422` with actionable field errors and do
not store partial evidence. SARIF input must declare top-level
`"version": "2.1.0"`. For example:

```json
{
  "error": {
    "code": "sarif_import_validation_failed",
    "message": "SARIF import validation failed.",
    "details": {
      "failures": [
        {
          "source_file": "invalid.sarif",
          "field": "runs",
          "message": "SARIF runs must be an array.",
          "correction_path": "Use a SARIF 2.1.0 runs array."
        }
      ]
    }
  }
}
```

## Local-First Boundary

The importer parses SARIF locally and persists normalized fields needed for
review. It does not send raw scanner output to an external service, and it does
not persist arbitrary SARIF `properties` metadata because that field is
scanner-defined and may contain snippets, fingerprints, or local paths.
