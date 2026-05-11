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

### Analysis parse batch change shape

API and CLI analysis responses include the parser-normalized `parse_batch` payload
before persistence. Persisted report contributors also carry the same parser
metadata so history, shared report, and dashboard result surfaces can show module
context, replacement paths, and fields Terraform marked unknown or sensitive
without storing raw plan internals in a separate contract.

```json
{
  "source_file": "tfplan.json",
  "tool": "terraform",
  "resource_id": "module.network.aws_security_group.web",
  "action": "modify",
  "summary": "Security group module.network.aws_security_group.web changes network access rules and should be reviewed for exposure before deploy.",
  "metadata": {
    "source_format": "terraform_plan_json",
    "plan_format_version": "1.2",
    "terraform_version": "1.8.5",
    "module_address": "module.network",
    "mode": "managed",
    "resource_type": "aws_security_group",
    "resource_name": "web",
    "provider_name": "registry.terraform.io/hashicorp/aws",
    "actions": ["update"],
    "replace_paths": ["ingress.0.cidr_blocks"],
    "unknown_after_apply": ["arn"],
    "redacted_fields": ["ingress.0.description"],
    "unsupported_fields": ["change.importing"],
    "plan_unsupported_fields": ["plan.resource_drift"]
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
  "confidence": 0.62,
  "top_risk": "Security group exposure risk",
  "context_completeness": {
    "topology_freshness_days": null,
    "topology_last_imported_at": null,
    "incident_index_size": 0,
    "evidence_success_rate": 0.5,
    "parser_success_rate": 0.5,
    "parser_success_by_tool": {
      "terraform": 1.0,
      "unsupported": 0.0
    },
    "context_score": 0.22,
    "confidence_level": "low",
    "uncertainty": "Insufficient context: missing or stale topology, parser coverage, evidence coverage, or incident history prevents a confident low-risk verdict.",
    "context_todos": [
      "Import or refresh topology context for this project/workspace.",
      "Import relevant incident history for this project/workspace.",
      "Review evidence extraction gaps for supported artifacts.",
      "Review parser errors and resubmit supported artifacts."
    ],
    "insufficient_context": true
  },
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
  "submission_manifest": {
    "submitted_artifact_count": 2,
    "accepted_artifact_count": 1,
    "analyzed_artifact_count": 1,
    "excluded_artifact_count": 0,
    "sensitive_artifact_count": 1,
    "failed_artifact_count": 0,
    "partial_artifact_count": 1,
    "partial_analysis": true,
    "provenance": {
      "source_interface": "api",
      "trigger_type": "api_request",
      "trigger_id": "run-123",
      "project_id": 7,
      "project_key": "payments",
      "workspace_id": 12,
      "workspace_key": "prod"
    },
    "redaction": {
      "filenames_redacted": false,
      "sensitive_content_excluded": true
    },
    "items": [
      {
        "name": "plan.json",
        "tool": "terraform",
        "status": "accepted",
        "intake_status": "ready",
        "parse_status": "parsed",
        "message": "Terraform artifact parsed successfully and included in analysis.",
        "partial": false,
        "redaction_status": "none",
        "provenance": {
          "source_interface": "api",
          "trigger_type": "api_request",
          "trigger_id": "run-123",
          "project_id": 7,
          "project_key": "payments",
          "workspace_id": 12,
          "workspace_key": "prod",
          "submitted_index": 1,
          "submitted_name": "plan.json"
        }
      },
      {
        "name": ".env",
        "tool": "unsupported",
        "status": "sensitive",
        "intake_status": "sensitive",
        "parse_status": null,
        "message": "Sensitive file detected and excluded from unsafe downstream handling.",
        "partial": true,
        "redaction_status": "sensitive_blocked",
        "provenance": {
          "source_interface": "api",
          "trigger_type": "api_request",
          "trigger_id": "run-123",
          "project_id": 7,
          "project_key": "payments",
          "workspace_id": 12,
          "workspace_key": "prod",
          "submitted_index": 2,
          "submitted_name": ".env"
        }
      }
    ]
  },
  "submission_manifest_fallback": [
    {
      "name": "plan.json",
      "tool": "terraform",
      "status": "accepted",
      "intake_status": "ready",
      "parse_status": "parsed",
      "partial": false,
      "redaction_status": "none"
    },
    {
      "name": ".env",
      "tool": "unsupported",
      "status": "sensitive",
      "intake_status": "sensitive",
      "parse_status": null,
      "partial": true,
      "redaction_status": "sensitive_blocked"
    }
  ],
  "findings": [],
  "evidence_items": [],
  "contributors": [
    {
      "source_file": "plan.json",
      "tool": "terraform",
      "resource_id": "module.network.aws_security_group.web",
      "action": "modify",
      "normalized_action": "modify",
      "severity": "high",
      "metadata": {
        "module_address": "module.network",
        "replace_paths": ["ingress.0.cidr_blocks"],
        "unknown_after_apply": ["arn"],
        "redacted_fields": ["ingress.0.description"],
        "plan_unsupported_fields": ["plan.resource_drift"]
      }
    }
  ],
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
- context completeness, context TODOs, insufficient-context signals, and traceable contributors
- report-level confidence derived from available context
- persisted rollback plans with time estimates and complexity rationale
- degraded narrative visibility fields
- submission manifest payloads that record accepted, excluded, failed, partial, sensitive, provenance, and redaction status
- durable submission manifest fallback identity/status metadata for malformed-manifest recovery
- parser-normalized change metadata for Terraform plan JSON format and Terraform versions, module paths, replacement paths, unknown-after-apply fields, redacted fields, and unsupported resource/change/plan fields

Story 2.6 adds report-level confidence, context uncertainty, evidence coverage,
context TODOs, and insufficient-context signals as additive `v2` fields. Broader
schema-version policy changes remain deferred to Story 2.8.
