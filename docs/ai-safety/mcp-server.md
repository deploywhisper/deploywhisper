# MCP Server and Agent Interface

DeployWhisper does not ship a standalone Model Context Protocol listener in the
current release. Its supported MCP-compatible equivalent is a self-hosted HTTP
agent interface over the same FastAPI analysis core used by the UI, API, and
CLI. An MCP host can expose these HTTP operations as tools without changing the
canonical report or granting the model approval, deployment, or remediation
authority.

## Safe invocation

Start DeployWhisper in infrastructure you control, then submit artifacts to the
local endpoint:

```bash
curl -sS -X POST http://localhost:8080/api/v1/agent/analyses \
  -H "X-DeployWhisper-Project-Role: contributor" \
  -H "X-DeployWhisper-Project-Keys: payments" \
  -F "project_key=payments" \
  -F "files=@plan.json"
```

Retrieve a scoped persisted report with:

```bash
curl -sS http://localhost:8080/api/v1/agent/reports/42 \
  -H "X-DeployWhisper-Project-Role: read-only" \
  -H "X-DeployWhisper-Project-Keys: payments"
```

The submission endpoint applies shared artifact classification, aggregate
upload limits, project/workspace resolution, deterministic analysis, Evidence
Law, and persistence. Sensitive filenames such as credentials, `.env` files,
and state files are excluded by the shared intake boundary. Raw IaC and other
sensitive artifacts stay local; responses do not echo uploaded content or the
submission manifest.

Optional `artifact_paths` values are repository-relative metadata paired with
uploads. They never instruct the server to read filesystem paths. Absolute
paths, traversal, filename mismatches, and ambiguous duplicate bindings are
rejected.

## Output contract

Both operations wrap the stable agent JSON contract, but consumers must verify
that `meta.operation` matches the endpoint they invoked:

- `POST /api/v1/agent/analyses` returns `"operation": "analysis.submit"`.
- `GET /api/v1/agent/reports/{report_id}` returns
  `"operation": "report.read"`.

The following complete example is for `report.read`:

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

Consumers must validate both `data.schema_version` and
`meta.interface_schema_version`, verify the expected `meta.operation`, and
honor every value in `meta.output_limits`. If `meta.truncated` is `true`, the
human reviewer must inspect the canonical report rather than assuming the
omitted items are low risk. See
[Agent JSON CLI Output](./agent-json-output.md) for all stable data fields and
interpretation rules.

## Scope and authorization

- `X-DeployWhisper-Project-Role` must permit the requested operation.
- `X-DeployWhisper-Project-Keys` limits non-admin callers to explicit projects.
- Project and workspace scope is resolved before analysis or retrieval.
- Inaccessible and missing resources use a bounded response for scoped callers
  so agents cannot discover project or report existence through error details.

Expose only these bounded operations to an agent. Do not provide arbitrary
filesystem, shell, credential, repository-write, approval, or deployment tools
alongside them. Transport access is not artifact-authorship provenance.

## Errors and human control

An operational error, authorization error, timeout, malformed response, or
unsupported schema is a failed review, not approval. The caller must stop and
surface the failure to a human. It must not retry by widening project scope,
removing intake controls, sending artifacts to a third party, or substituting
model judgment for the missing report.

Every response remains advisory. Agents may summarize evidence and prepare
review notes, but a human must decide whether to merge, apply, deploy, request
changes, or invoke a separately configured policy adapter. The safe end-to-end
workflow is documented in
[Reviewing AI-Generated and AI-Assisted IaC](./reviewing-ai-generated-iac.md).
