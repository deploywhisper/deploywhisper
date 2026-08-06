# Workflow Adapter Output Contract

DeployWhisper workflow adapters must consume one canonical report-output
contract. GitLab, Jenkins, Atlantis, Argo CD, Flux, chat, and policy adapters
should start from the shared `ShareSummary` produced by the analysis service,
then wrap it with adapter identity and delivery metadata by calling
`build_adapter_output_contract`.

## Contract Shape

The service helper returns an `AdapterOutputContract` with three parts:

- `canonical_summary`: immutable DeployWhisper report summary fields derived from
  `data.share_summary`, including `canonical_summary.severity`,
  `canonical_summary.recommendation`,
  `canonical_summary.json_payload.evidence_law_status`, markdown, plain text,
  and typed JSON payload fields.
- `adapter_metadata`: an `AdapterMetadata` object that names the adapter,
  destination format, version, required project scope, optional workspace scope,
  invocation ID, delivery target, and safe extra metadata.
- `adapter_payload`: adapter-specific rendering or delivery details, such as a
  GitLab discussion key, Jenkins build annotation identifier, Atlantis plan
  comment marker, or chat thread ID.

`adapter_payload` and `adapter_metadata.extra` must not shadow canonical fields
such as severity, recommendation, Evidence Law status, Evidence Law detail,
advisory posture, blocking decision, markdown, plain text, JSON payload, or
report schema version. Adapter-owned payload and metadata values must remain
JSON-safe; non-finite numeric values such as NaN and infinity are rejected.

The envelope `contract_version` is fixed to `v1` until a future migration story
introduces and documents a new adapter contract version.

Project scope is mandatory for adapter output. Provide exactly one of
`project_key` or `project_id`. Numeric IDs must be strict positive integers,
not coerced booleans, strings, or floats. Workspace scope is optional; provide
exactly one of `workspace_key` or `workspace_id` when the adapter output targets
a specific environment or deployment lane.

## Adapter Implementation Pattern

```python
from services.adapter_output_contract import (
    AdapterMetadata,
    build_adapter_output_contract,
)
from services.analysis_service import build_share_summary

share_summary = build_share_summary(persisted_report)
contract = build_adapter_output_contract(
    share_summary,
    AdapterMetadata(
        adapter="gitlab",
        format="merge_request_note",
        version="v1",
        project_key="payments",
        workspace_key="prod",
        extra={"merge_request_iid": 42},
    ),
    adapter_payload={
        "thread_key": "deploywhisper:17",
        "rendered_markdown": "Adapter wrapper around canonical markdown",
    },
)
```

Adapters may change layout, comments, issue labels, chat blocks, or delivery
metadata. They must not rewrite canonical severity or Evidence Law status. If a
workflow needs blocking or policy behavior, add that as a separate configured
interpretation of the canonical summary; do not mutate the report contract.

## Canonical Field Ownership

DeployWhisper core owns:

- severity and recommendation
- Evidence Law status and detail
- advisory-only and should-block posture
- report schema version
- share-summary markdown, plain text, and typed JSON payload

Adapters own:

- required project identity and optional workspace identity
- workflow destination metadata
- output markers used for idempotent updates
- rendered wrappers around canonical markdown or plain text
- external IDs such as merge request, build, plan, sync, or chat-thread IDs

This keeps future workflow integrations independent without letting adapter
formatting drift from the report object users inspect in API, CLI, UI, and
shared report views.

## Optional Policy Interpretation

Policy adapters add a separate `PolicyAdapterOutputContract` around an existing
`AdapterOutputContract`. The policy contract exposes a `PolicyAdapterStatus`
with exactly four values: `advisory`, `warn`, `soft-block`, and `hard-block`.
Every output requires at least one structured reason with a stable `code` and a
human-readable `message`.

```python
from services.policy_adapter_output_contract import (
    PolicyAdapterReason,
    PolicyAdapterStatus,
    build_policy_adapter_output_contract,
)

policy_output = build_policy_adapter_output_contract(
    contract,
    status=PolicyAdapterStatus.WARN,
    reasons=(
        PolicyAdapterReason(
            code="review_required",
            message="A human must review the deterministic evidence.",
        ),
    ),
)
```

`canonical_report_advisory` is fixed to `true`. The nested canonical summary
must keep `advisory_only=true` and `should_block=false`, even when the optional
policy status is `soft-block` or `hard-block`. The adapter interpretation is a
local workflow decision; it cannot rewrite the canonical severity,
recommendation, Evidence Law status, evidence, or advisory posture.

`PolicyAdapterSettings` manages severity thresholds and the below-threshold
`reporting_default` without changing core scoring. Built-in defaults interpret
medium as `warn`, high as `soft-block`, and critical as `hard-block`; reports
below those thresholds remain `advisory`. Admins can inspect, save, or reset
project defaults and integration-specific defaults through `GET`, `PUT`, and
`DELETE`
`/api/v1/settings/policy-adapter`. Integration-specific defaults take
precedence over project defaults, which take precedence over the built-in safe
defaults. Deleting an integration override restores its project defaults;
deleting a project override restores the built-in defaults.

Threshold evaluation reads only `canonical_summary.severity`. The emitted
policy envelope records the resolved settings in `applied_settings`, while the
original canonical severity, findings, evidence, recommendation, Evidence Law
status, and advisory flags remain unchanged and auditable. Enforcement mode is
a separate integration concern; the core remains useful when no policy adapter
is enabled.

Runtime integrations call `build_configured_policy_adapter_output`, which
resolves either adapter `project_key` or `project_id`, selects the integration
override before the project and built-in defaults, validates that the settings
scope matches the adapter metadata, and then emits the policy envelope.
