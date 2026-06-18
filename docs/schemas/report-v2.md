# Report Schema v2

`report_schema_version: "v2"` is the canonical persisted report contract for DeployWhisper Story 2.8.

## Scope

This schema version applies to:

- persisted `analysis_reports` rows
- API analysis payloads and report retrieval payloads
- CLI analysis payloads
- share-summary JSON payloads used by PR, benchmark, and agent consumers

## Core guarantees

1. Every persisted report stores `report_schema_version`.
2. API and CLI envelopes include `report_schema_version` in `meta`.
3. Report-bearing `/api/v1` analysis envelopes include `api_version: "v1"`
   in `meta` alongside the report schema version.
4. Machine-friendly share-summary payloads include `report_schema_version`
   alongside their own share payload `version`.
5. Stored reports remain readable across upgrades by version-aware readers.
6. Newer readers are expected to read older schemas when the older schema major version is less than or equal to the reader version.
7. Successful analysis responses include a persisted report identifier and
   audit metadata derived from durable report state. Persistence failures use an
   explicit `report_persistence_failed` error/status instead of returning
   success, with sanitized remediation text rather than raw storage-driver
   details.

## Envelope examples

### API/CLI meta

```json
{
  "meta": {
    "app": "DeployWhisper",
    "version": "0.1.0",
    "api_version": "v1",
    "report_schema_version": "v2",
    "report_schema_versions": ["v2"]
  }
}
```

Analysis list responses may contain reports written under different report
schema versions. In that case, `meta.report_schema_version` remains the response
reader/envelope schema version and `meta.report_schema_versions` lists the
distinct item schema versions in numeric major-version order, such as
`["v1", "v2"]`. Consumers that need item-level branching should inspect
`data[*].report_schema_version` or `meta.report_schema_versions` instead of
assuming a uniform list.

Readers canonicalize valid schema versions to `vN` form, so values such as
`v02` are emitted as `v2`. Blank historical values are treated as legacy `v1`;
non-empty malformed markers are rejected as invalid, and versions newer than the
current reader schema are rejected until the runtime supports that report
contract.

### Durable audit metadata

`data.persisted_report.audit` is emitted only after the report has been saved.
It carries the source surface, trigger, actor, persisted row timestamp,
redaction state, and delivery metadata for the successful response:

```json
{
  "id": 42,
  "audit": {
    "source_interface": "api",
    "trigger_type": "api_request",
    "trigger_id": "sess-123",
    "actor": "api-reviewer@example.com",
    "persisted_at": "2026-05-13T12:00:00+00:00",
    "redaction_status": "none",
    "redaction": {
      "filenames_redacted": false,
      "sensitive_content_excluded": false
    },
    "delivery": {
      "surface": "api",
      "trigger_type": "api_request",
      "trigger_id": "sess-123",
      "report_id": 42,
      "status": "persisted"
    }
  }
}
```

The top-level `id` and `audit.delivery.report_id` identify the persisted
report. `audit.persisted_at` matches `created_at`: it is the persisted report row
creation timestamp, not a separate post-artifact timestamp. Successful delivery
responses emit it only after artifact persistence completes. CLI submissions
default the actor to `cli_local_user` unless `DEPLOYWHISPER_ACTOR` is set. API
submissions may send `X-DeployWhisper-Actor`; otherwise the actor is
`api_client`. GitHub App webhooks use `github:<sender-login>` when the webhook
sender is available. Actor values are whitespace-normalized, stripped of control
characters, bounded before persistence, and retained in the manifest fallback so
the audit actor can still be recovered if manifest JSON is malformed.

### Advisory and share-summary shape

API and CLI analysis responses include advisory fields for automation and PR
comment consumers. API report list/detail payloads also include
`data[*].advisory` / `data.advisory` derived from persisted report state, so
retrieval clients do not have to reconstruct DeployWhisper's advisory posture
from lower-level report fields. `should_block` remains `false`; downstream
systems may use `requires_attention` and `uncertainty_flags` to decide whether
to notify humans, but DeployWhisper's canonical contract remains advisory-first.

The share-summary JSON payload has its own `version` because PR comments,
benchmark reports, and agent integrations may evolve their compact summary shape
separately from the persisted report. It still carries `report_schema_version`
so consumers know which full report contract backs the summary.

The share-summary payload `version` remains `v1` for these changes because
adding `report_schema_version` and Evidence Law summary fields is additive.
Additive fields are compatible with share-summary `v1`; consumers that validate
the compact summary should ignore unknown fields and branch on
`report_schema_version` when they need the backing full-report contract.
Evidence Law status values are `Satisfied`, `Needs review`, `Reconciled`, and
`Detail omitted`. CLI/API analysis responses include evidence detail and should
not emit `Detail omitted`; compact report-list style views may use it when
evidence rows were intentionally excluded.

```json
{
  "advisory": {
    "advisory_only": true,
    "should_block": false,
    "requires_attention": true,
    "severity": "high",
    "recommendation": "no-go",
    "top_risk": "Security group exposure risk",
    "partial_context": true,
    "narrative_degraded": true,
    "uncertainty_flags": ["partial_context", "narrative_degraded"]
  },
  "share_summary": {
    "advisory_only": true,
    "should_block": false,
    "json_payload": {
      "version": "v1",
      "report_schema_version": "v2",
      "report_id": 42,
      "report_link": "https://deploywhisper.example.com/reports/42",
      "rollback_link": "https://deploywhisper.example.com/reports/42",
      "verdict_banner": "DeployWhisper HIGH · NO-GO",
      "evidence_law_status": "Satisfied",
      "evidence_law_detail": "High and critical findings are backed by deterministic evidence.",
      "headline": "NO-GO: Security group exposure risk",
      "top_findings": [
        {
          "title": "HIGH: public ingress exposure",
          "severity": "high",
          "evidence_count": 2,
          "confidence": 1.0
        }
      ],
      "evidence_count": 4,
      "context_completeness": {
        "score": 0.22,
        "label": "LIMITED CONTEXT",
        "summary": "LIMITED CONTEXT (0.22) - reviewer verification required."
      },
      "advisory_summary": "This result requires additional human review before release."
    }
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
      "Review parser errors and resubmit supported artifacts.",
      "Add CODEOWNERS or ownership mapping for analyzed files/resources."
    ],
    "insufficient_context": true,
    "partial_context": true,
    "owner_signals": [
      {
        "scope": "file",
        "subject": "services/payments/plan.json",
        "owners": ["@payments-sre"],
        "source": "CODEOWNERS",
        "source_ref": ".github/CODEOWNERS",
        "matched_pattern": "/services/payments/",
        "resource_id": null,
        "service_id": null,
        "escalation_hint": "Escalate file review for services/payments/plan.json to @payments-sre."
      },
      {
        "scope": "service",
        "subject": "Payments API",
        "owners": ["@payments-runtime"],
        "source": "topology",
        "source_ref": "topology.json",
        "matched_pattern": null,
        "resource_id": "aws_security_group.payments",
        "service_id": "payments-api",
        "escalation_hint": "Escalate service review for Payments API to @payments-runtime."
      }
    ],
    "escalation_hints": [
      "Escalate file review for services/payments/plan.json to @payments-sre.",
      "Escalate service review for Payments API to @payments-runtime."
    ],
    "ownership_unmapped_subjects": [],
    "context_sources": [
      {
        "source_id": "artifact:plan.json",
        "source_type": "artifact",
        "source_ref": "plan.json",
        "scope": "project:payments/workspace:prod",
        "freshness_status": "current",
        "last_observed_at": null,
        "age_days": null,
        "confidence": 1.0,
        "conflicts": [],
        "limitations": []
      },
      {
        "source_id": "incident:index:incidents:empty",
        "source_type": "incident",
        "source_ref": "incidents:empty",
        "scope": "project:payments",
        "freshness_status": "empty",
        "last_observed_at": null,
        "age_days": null,
        "confidence": 0.0,
        "conflicts": ["missing_incident_history"],
        "limitations": ["empty_incident_index"]
      }
    ]
  },
  "blast_radius": {
    "affected": [
      {
        "service_id": "database",
        "label": "Primary Database",
        "depth": 0,
        "dependencies": [],
        "owners": ["sre"]
      },
      {
        "service_id": "api",
        "label": "Payments API",
        "depth": 1,
        "dependencies": ["database"],
        "owners": ["payments"]
      }
    ],
    "direct_count": 1,
    "transitive_count": 1,
    "warning": null,
    "unmatched_resources": [],
    "context_source": {
      "type": "custom",
      "ref": "topology.json"
    },
    "freshness": {
      "updated_at": "2026-06-08T12:00:00Z",
      "age_days": 1
    },
    "context_state": "current",
    "context_limitations": []
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
  "narrative_opening": "",
  "narrative_available": false,
  "narrative_degraded": true,
  "narrative_failure_notice": "Narrative provider unavailable: provider offline",
  "narrative_source": "fallback",
  "narrative_provider": "ollama",
  "narrative_model": "ollama/llama3",
  "narrative_local_mode": true,
  "skills_applied": ["terraform"],
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
      "redaction_status": "none",
      "actor": "api-reviewer@example.com"
    },
    {
      "name": ".env",
      "tool": "unsupported",
      "status": "sensitive",
      "intake_status": "sensitive",
      "parse_status": null,
      "partial": true,
      "redaction_status": "sensitive_blocked",
      "actor": "api-reviewer@example.com"
    }
  ],
  "findings": [
    {
      "finding_id": "finding-public-ingress",
      "analysis_id": 42,
      "title": "Public ingress exposure",
      "description": "Terraform opened SSH ingress from 0.0.0.0/0 on port 22.",
      "explanation": "Administrative ingress from the public internet has caused common deployment incidents.",
      "guidance": [
        "Confirm whether the public CIDR is intentional and time-bound.",
        "Restrict administrative ingress to trusted networks or a managed access path."
      ],
      "severity": "high",
      "category": "network_exposure",
      "deterministic": true,
      "confidence": 1.0,
      "uncertainty_note": null,
      "evidence_classification": "deterministic",
      "evidence_refs": ["ev-plan-json-1"],
      "skill_id": "terraform"
    }
  ],
  "evidence_items": [
    {
      "evidence_id": "ev-plan-json-1",
      "finding_id": "finding-public-ingress",
      "source_type": "artifact",
      "source_ref": "plan.json",
      "artifact": "plan.json",
      "summary": "Terraform opened SSH ingress from 0.0.0.0/0 on port 22.",
      "deterministic": true,
      "confidence": 1.0,
      "context_source": {
        "source_id": "artifact:plan.json",
        "source_type": "artifact",
        "source_ref": "plan.json",
        "scope": "project:payments/workspace:prod",
        "freshness_status": "current",
        "confidence": 1.0,
        "conflicts": [],
        "limitations": []
      }
    }
  ],
  "incident_matches": [
    {
      "incident_id": 0,
      "match_type": "public_risk_pattern",
      "public_pattern_id": "public-ingress-wide-open",
      "title": "Wide-open administrative ingress",
      "severity": "high",
      "source_file": "plan.json",
      "incident_date": null,
      "similarity": 0.86,
      "confidence": 0.86,
      "confidence_label": "high",
      "reason": "The change appears to expose administrative or data-plane network access to the public internet.",
      "evidence": [
        "plan.json: aws_security_group.web (modify) - Terraform opened SSH ingress from 0.0.0.0/0 on port 22."
      ],
      "matched_signals": ["0.0.0.0/0", "ssh", "ingress"],
      "affected_services": ["aws_security_group.web"],
      "prevention_notes": [
        "Use a trusted administrative access path instead of broad public ingress.",
        "Time-bound any exception and verify compensating controls before deployment."
      ],
      "verification_guidance": [
        "Confirm whether the public CIDR is intentional and time-bound.",
        "Restrict administrative ingress to trusted networks or a managed access path."
      ],
      "summary": "Public risk pattern match: wide-open administrative ingress has caused common deployment incidents."
    }
  ],
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

### Context source freshness ledger

`context_completeness.context_sources` is the per-report freshness ledger for
the context inputs used during analysis. Each row exposes `source_id`,
`source_type`, optional `source_ref`, `scope`, `freshness_status`,
`confidence`, `conflicts`, and `limitations` so API, CLI, and UI consumers can
show whether topology, incident history, artifact, parser, evidence, ownership,
or external context was current enough to trust.

`freshness_status` uses the same values as the report context state:
`current`, `stale`, `missing`, `incomplete`, `conflicting`, `unknown`, `empty`,
or `not_applicable`. Non-current populated incident ledgers should surface
remediation from `context_todos`; for example stale indexes ask reviewers to
refresh incident history, while conflicting or incomplete indexes ask reviewers
to resolve the specific incident freshness state.

Evidence rows may include `context_source` when DeployWhisper can tie that
evidence item to one ledger source. Consumers should render the relationship as
provenance, not as a separate finding. Legacy persisted reports can contain
malformed context-source rows; readers may drop invalid source rows while
preserving the rest of the context completeness payload.

### Blast-radius topology context

`blast_radius.context_state` is the report-facing topology trust state. It is
`current` when topology source and freshness metadata are valid and no
limitations were detected. It is `stale` when freshness warnings indicate old
topology, `missing` when no topology context was available, `incomplete` when
source metadata, freshness metadata, resource mappings, or imported context are
partial, `conflicting` when validation detects duplicate, circular, or otherwise
conflicting topology, and `unknown` for legacy payloads where no state was
persisted.

`blast_radius.context_limitations` contains machine-readable reasons for
non-current states. Current labels include `missing_topology`, `stale_topology`,
`conflicting_topology`, `incomplete_topology`, `missing_topology_source`,
`invalid_topology_source`, `missing_topology_freshness`,
`invalid_topology_freshness`, and `missing_resource_mapping`. Consumers should
treat unrecognized future labels as additional incomplete-context signals rather
than failing report parsing.

### Ownership context

`context_completeness.owner_signals` is a point-in-time ownership snapshot for
the analyzed files and mapped services/resources. File signals come from the
last matching `CODEOWNERS` rule in the analyzed submission's uploaded
`CODEOWNERS` source; DeployWhisper does not fall back to its own repository
checkout for analyzed-project ownership. Service signals come from topology
ownership fields when a changed resource maps to a service. Each signal carries
owners, source metadata, and an `escalation_hint` that report consumers can
render directly for reviewer routing.

When no file or service ownership can be found for analyzed subjects,
`context_completeness.context_todos` includes
`Add CODEOWNERS or ownership mapping for analyzed files/resources.`, and
`ownership_unmapped_subjects` lists the files or services that need owner data.

#### Request-side ownership setup

Directory-scoped ownership depends on preserving repo-relative artifact paths
for every submitted file. Upload `.github/CODEOWNERS`, `CODEOWNERS`, or
`docs/CODEOWNERS` with the analyzed artifacts from the same repository root.

API multipart clients should send one `artifact_paths` form value for each
`files` part, in the same order. Each value must be a safe repo-relative
artifact path such as `.github/CODEOWNERS` or
`services/payments/plan.json`; absolute paths, drive-root paths, traversal
segments, and reserved internal prefixes are rejected.

When two uploaded files share the same basename, the multipart filename must
also carry the matching repo-relative path for each file. This lets the server
prove that `artifact_paths` values were bound to the intended file parts instead
of relying on positional order alone.

```bash
curl -F project_key=payments \
  -F 'files=@.github/CODEOWNERS;filename=.github/CODEOWNERS' \
  -F artifact_paths=.github/CODEOWNERS \
  -F 'files=@services/payments/plan.json;filename=services/payments/plan.json' \
  -F artifact_paths=services/payments/plan.json \
  http://127.0.0.1:8080/api/v1/analyses
```

CLI analysis preserves relative paths when files are submitted from a common
repository root, so run it from the target checkout or pass paths that share the
same root. For the dashboard, prefer directory upload when analyzing a tree; the
browser supplies repo-relative artifact paths so directory-scoped CODEOWNERS
rules can match.

### Analysis run incident and pattern matches

Live API/CLI analysis responses and persisted report retrieval payloads include
`incident_matches`. Matches from stored organization incident memory use
`match_type: "organization_incident"`. Built-in day-zero risk patterns use
`match_type: "public_risk_pattern"` and include `public_pattern_id`, `reason`,
`evidence`, `confidence`, `confidence_label`, `matched_signals`,
`affected_services`, `prevention_notes`, and `verification_guidance` so
consumers can distinguish public guidance from a prior incident in their own
environment. Public risk pattern matches are general failure-mode guidance and
must not be presented as organization-specific incident history.

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
- advisory-only automation fields for API, CLI, PR, benchmark, and agent consumers
- share-summary JSON payloads include the source `report_schema_version`
- submission manifest payloads that record accepted, excluded, failed, partial, sensitive, provenance, and redaction status
- durable submission manifest fallback identity/status metadata for malformed-manifest recovery
- parser-normalized change metadata for Terraform plan JSON format and Terraform versions, module paths, replacement paths, unknown-after-apply fields, redacted fields, and unsupported resource/change/plan fields
- ownership owner signals, escalation hints, and missing-ownership context TODOs

Story 2.6 added report-level confidence, context uncertainty, evidence coverage,
context TODOs, and insufficient-context signals as additive `v2` fields. Story
2.8 makes the report schema version explicit for API, CLI, PR, benchmark, and
agent-facing machine consumers.
