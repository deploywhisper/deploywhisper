# Report Schema v2

`report_schema_version: "v2"` is the canonical persisted report contract for DeployWhisper Story 1.8.

## Scope

This schema version applies to:

- persisted `analysis_reports` rows
- API analysis payloads and report retrieval payloads
- CLI analysis payloads

## Core guarantees

1. Every persisted report stores `report_schema_version`.
2. API envelopes include `report_schema_version` in `meta`.
3. Stored reports remain readable across upgrades by version-aware readers.
4. Newer readers are expected to read older schemas when the older schema major version is less than or equal to the reader version.

## Envelope examples

### API/CLI meta

```json
{
  "meta": {
    "app": "DeployWhisper",
    "version": "0.1.0",
    "api_version": "v1",
    "report_schema_version": "v2"
  }
}
```

### Persisted report shape

```json
{
  "id": 42,
  "report_schema_version": "v2",
  "severity": "high",
  "recommendation": "no-go",
  "top_risk": "Security group exposure risk",
  "rollback_plan": {
    "complexity": "medium",
    "complexity_score": 3,
    "complexity_explanation": "Score 3/5 because the plan covers 2 rollback steps.",
    "steps": [
      {
        "order": 1,
        "title": "Revert aws_security_group.main",
        "detail": "Rollback the terraform change safely.",
        "estimated_minutes": 15,
        "critical": true
      }
    ]
  },
  "parse_summary": "1 parsed, 0 failed, 0 skipped, 1 normalized changes",
  "findings": [],
  "evidence_items": [],
  "contributors": [],
  "audit": {
    "files_analyzed": ["plan.json"]
  }
}
```

## Compatibility contract

- Missing schema version from legacy rows normalizes to `v1`.
- `v3` readers must continue to read `v2` reports.
- Readers may reject newer unknown major versions.

## v2 additions relative to legacy rows

- Explicit `report_schema_version`
- evidence-backed findings and `evidence_items`
- context completeness and traceable contributors
- persisted rollback plans with time estimates and complexity rationale
- degraded narrative visibility fields
