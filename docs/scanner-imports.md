# Scanner Imports

DeployWhisper can ingest SARIF 2.1.0 output and Semgrep native JSON output from
external scanners, then store each scanner result as project-scoped external
evidence. Scanner severity stays labeled as scanner context; it does not
automatically become a high or critical DeployWhisper finding without
DeployWhisper evidence and scoring.

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

## Semgrep JSON Endpoint

```http
POST /api/v1/scanner-imports/semgrep
```

Request body:

```json
{
  "project_key": "payments",
  "source_file": "semgrep.json",
  "content": "{\"results\":[...]}"
}
```

Optional scope fields:

- `project_id`
- `workspace_id`
- `workspace_key`

The endpoint accepts Semgrep native JSON results with `check_id`, `path`,
`start`, and `extra.message`. `extra.severity` maps Semgrep `ERROR`, `WARNING`,
and `INFO` to DeployWhisper scanner-context severities `high`, `medium`, and
`low`. Report-safe `extra.fingerprint` is used for stable source identity when
available; otherwise a report-safe top-level `fingerprint` is used as a
compatibility fallback before the normalized identity falls back to tool, rule,
path, region, and message text.

DeployWhisper preserves a bounded Semgrep context object in evidence
`properties.semgrep`, including report-safe `extra.fingerprint`,
`extra.engine_kind`, and report-oriented `extra.metadata` fields such as `cwe`,
`owasp`, `confidence`, `impact`, `likelihood`, `category`, and `technology`.
Free-form URL/source metadata, raw code snippets, oversized values, nested
objects, and arbitrary scanner payload fields are not persisted.

## Validation

Unsupported SARIF and Semgrep JSON structures return `422` with actionable field
errors and do not store partial evidence. SARIF input must declare top-level
`"version": "2.1.0"`. Semgrep JSON input must include a top-level `results`
array. Semgrep JSON with non-empty top-level `errors` is rejected so failed or
partial scans are not imported as complete evidence.

SARIF validation example:

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

Semgrep validation example:

```json
{
  "error": {
    "code": "semgrep_import_validation_failed",
    "message": "Semgrep JSON import validation failed.",
    "details": {
      "failures": [
        {
          "source_file": "invalid.json",
          "field": "results",
          "message": "Semgrep JSON results must be an array.",
          "correction_path": "Run Semgrep with JSON output and include the results array."
        }
      ]
    }
  }
}
```

## Local-First Boundary

The importer parses scanner JSON locally and persists normalized fields needed
for review. It does not send raw scanner output to an external service, and it
does not persist arbitrary scanner-defined metadata because those fields may
contain snippets, fingerprints, or local paths.
