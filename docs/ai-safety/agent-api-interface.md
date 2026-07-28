# Agent API Interface

DeployWhisper exposes an HTTP interface for agent-tool integrations that need
the same stable advisory contract as `deploywhisper analyze --agent-json`.
This is the supported equivalent to an MCP server for the current release. It
uses the existing FastAPI analysis core and does not grant agents deployment,
approval, or remediation authority.

## Submit artifacts

```bash
curl -sS -X POST http://localhost:8080/api/v1/agent/analyses \
  -H "X-DeployWhisper-Project-Role: contributor" \
  -H "X-DeployWhisper-Project-Keys: payments" \
  -F "project_key=payments" \
  -F "files=@plan.json"
```

The endpoint applies the same artifact classification, aggregate upload limit,
project/workspace resolution, deterministic analysis, Evidence Law, and report
persistence used by `POST /api/v1/analyses`. Sensitive filenames such as
`.env`, credential files, and state files are excluded by the shared intake
boundary. The response never echoes raw uploaded artifact content or the
submission manifest.

Optional `artifact_paths` form fields are safe repository-relative metadata
paired one-for-one with uploaded files. They preserve directory context for
ownership matching; they never cause DeployWhisper to read a path from the
server filesystem. Absolute paths, traversal segments, mismatched filenames,
and ambiguous duplicate bindings are rejected.

## Retrieve a report

```bash
curl -sS http://localhost:8080/api/v1/agent/reports/42 \
  -H "X-DeployWhisper-Project-Role: read-only" \
  -H "X-DeployWhisper-Project-Keys: payments"
```

Both endpoints return:

```json
{
  "data": {
    "schema_version": "v1",
    "report_id": 42,
    "advisory_only": true,
    "deployment_approval": false,
    "human_decision_required": true
  },
  "meta": {
    "interface_schema_version": "v1",
    "operation": "report.read",
    "advisory_only": true,
    "output_limits": {
      "max_string_characters": 2048,
      "max_collection_items": 50,
      "max_findings": 50,
      "max_evidence": 100
    },
    "truncated": false,
    "truncated_fields": []
  }
}
```

The abbreviated example omits the remaining stable agent fields documented in
[Agent JSON CLI Output](./agent-json-output.md). Consumers must check both
`data.schema_version` and `meta.interface_schema_version`. When an output limit
is applied, `meta.truncated` is `true` and `meta.truncated_fields` identifies
the affected paths.

## Scope and authorization

Agent callers use the existing project authorization headers:

- `X-DeployWhisper-Project-Role`: `contributor` or `maintainer` for artifact
  submission; any role with `report.read` for retrieval.
- `X-DeployWhisper-Project-Keys`: comma-separated project keys the caller may
  access. Non-admin callers must provide this explicit scope.

Project and workspace scope is resolved before analysis. An inaccessible
project, report, or workspace/context reference returns the same bounded error
without confirming whether the requested resource exists:

```json
{
  "error": {
    "code": "agent_scope_forbidden",
    "message": "Caller is not authorized for the requested agent resource.",
    "details": {}
  }
}
```

Do not use error differences as a discovery mechanism. A privileged admin may
receive `agent_report_not_found` for a genuinely missing report because that
role is not constrained to a project allowlist.

## Safety requirements for consumers

- Treat every response as advisory. It is never deployment approval.
- Require a human to inspect evidence and make the deployment decision.
- Do not send raw IaC to a remote model merely because the HTTP interface
  returned a structured result.
- Treat `truncated=true`, uncertainty flags, context TODOs, and degraded
  narrative state as reasons to gather more context, not as low-risk signals.
- Operational or authorization errors are not successful reviews and must not
  be interpreted as approval.
