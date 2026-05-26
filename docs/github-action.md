# GitHub Action Integration Contract

DeployWhisper's GitHub Marketplace action runtime lives outside this
application repository in
[`deploywhisper/analyze-action`](https://github.com/deploywhisper/analyze-action).
Use the published action from workflow files as `deploywhisper/analyze-action@v1`.

This repository documents and integrates with the action contract. It must not
host local Marketplace action manifests such as `action.yml` or `action.yaml`;
action runtime code and Marketplace release metadata remain owned by the
external action repository.

## PR Review Workflow

```yaml
name: DeployWhisper

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write

jobs:
  deploywhisper:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: deploywhisper/analyze-action@v1
        with:
          api-url: ${{ secrets.DEPLOYWHISPER_API_URL }}
          project-key: payments
          workspace-key: prod
```

The action detects pull request file changes, filters to supported
DeployWhisper artifacts locally, and submits those artifacts to the existing
`POST /api/v1/analyses` API. Raw artifact handling remains governed by the
DeployWhisper server and local-first upload boundary.

DeployWhisper analysis submission requires project scope. The canonical
multipart fields are `project_key` or `project_id`, with optional
`workspace_key` or `workspace_id`. GitHub Action configuration must provide
that scope through supported action inputs such as `project-key` /
`workspace-key`, or through a DeployWhisper integration endpoint that derives
project scope from the repository context before forwarding to
`POST /api/v1/analyses`. Do not use an `api-url`-only workflow against an app
server that requires explicit project scope.

The app repository owns the required API/report contract; the external
`deploywhisper/analyze-action` repository owns the action runtime and `action.yml`
inputs that satisfy it. If an installed action tag does not expose project-scope
inputs, update the action tag or route through a scope-deriving integration
endpoint before using it with a project-scoped DeployWhisper server.

DeployWhisper remains advisory in CI. Successful analysis should not fail a
workflow based only on risk score or recommendation. Consumers should use
`data.advisory.requires_attention` to decide whether to notify reviewers or add
manual checks.

## Canonical Schema Mapping

Action outputs are derived from the canonical API response and report schema
documented in [Report Schema v2](./schemas/report-v2.md). The action should not
invent a separate report contract.

| Action output | Canonical source |
| --- | --- |
| `report-id` | `data.persisted_report.id` |
| `report-link` | `data.share_summary.json_payload.report_link` |
| `severity` | `data.advisory.severity` |
| `recommendation` | `data.advisory.recommendation` |
| `share-summary-json` | JSON-encoded `data.share_summary.json_payload` |
| `share-summary-markdown` | `data.share_summary.markdown` |
| `comment-id` | GitHub PR comment identifier returned by the external action |
| `comment-url` | GitHub PR comment URL returned by the external action |
| `comment-updated` | GitHub PR comment create/update state returned by the external action |

GitHub Action outputs are strings. The `share-summary-json` output is a
JSON-encoded string of `data.share_summary.json_payload`; consumers should parse
it with `fromJSON(steps.deploywhisper.outputs.share-summary-json)` in workflow
expressions or `JSON.parse(...)` in scripts.

The machine payload in `share_summary.json_payload` includes
`report_schema_version`, Evidence Law status, top findings, evidence count,
context completeness, and report/rollback links. Consumers that need to branch
on persisted report shape should use `report_schema_version` and the
`docs/schemas/report-v2.md` contract rather than parsing PR comment text.

For PR comments that include externally shareable report links, configure a
public `APP_BASE_URL` or `PUBLIC_APP_URL` on the DeployWhisper server. Without a
public base URL, the server falls back to its local host/port and the action may
emit report links that are only usable from the server network.

## Input Boundary

The external action may accept convenience inputs such as:

- `api-url`: DeployWhisper server URL.
- `api-token`: optional bearer token for protected DeployWhisper APIs.
- `project-key` or `project-id`: required unless your DeployWhisper integration
  endpoint derives project scope from repository context.
- `workspace-key` or `workspace-id`: optional project-local environment or
  deployment lane.
- `changed-files`: optional override for pull request file detection.
- `working-directory`: repository root when checkout is not `.`.

These input names are the app-side integration contract. The external action
repository is responsible for exposing equivalent runtime inputs and translating
them to the canonical API fields.

Do not store provider credentials, raw infrastructure state, or deployment
secrets in this repository for the action. Keep API tokens in GitHub Actions
secrets and pass them only to the external action at runtime.

## Repository Ownership

- Application repo: `deploywhisper/deploywhisper`
  - Documents the contract.
  - Owns API, CLI, report schema, share-summary, and advisory semantics.
  - Provides regression tests that guard the integration boundary.
- Action repo: `deploywhisper/analyze-action`
  - Owns `action.yml` or `action.yaml`.
  - Owns packaged action runtime code and Marketplace release metadata.
  - Owns consumer smoke tests for GitHub workflow execution.

When changing action behavior, update the external action repository and keep
this guide aligned with the stable DeployWhisper API/report contract.
