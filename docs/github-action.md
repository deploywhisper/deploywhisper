# GitHub Action Integration Contract

DeployWhisper's GitHub Marketplace action runtime lives outside this
application repository in
[`deploywhisper/analyze-action`](https://github.com/deploywhisper/analyze-action).
Use the published action from workflow files as `deploywhisper/analyze-action@v1`.

This repository documents and integrates with the action contract. It must not
host local Marketplace action manifests such as `action.yml` or `action.yaml`,
packaged action entrypoints, or copied action runtime code; action runtime code
and Marketplace release metadata remain owned by the external action repository.

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
manual checks. Advisory-first boundary: the action surfaces evidence and
recommendations for review, but does not enforce deployment blocking by itself.

## Canonical Report Output Mapping

Report-related action outputs are derived from the canonical API response and
report schema documented in [Report Schema v2](./schemas/report-v2.md). The
action should not invent a separate report contract.

| Action output | Canonical source |
| --- | --- |
| `report-id` | `data.persisted_report.id` |
| `report-link` | `data.share_summary.json_payload.report_link` |
| `severity` | `data.advisory.severity`, falling back to `data.share_summary.severity` when advisory is blank |
| `recommendation` | `data.advisory.recommendation`, falling back to `data.share_summary.recommendation` when advisory is blank |
| `share-summary-json` | JSON-encoded `data.share_summary.json_payload` |
| `share-summary-markdown` | `data.share_summary.markdown` |

GitHub Action outputs are strings. The `share-summary-json` output is a
JSON-encoded string of `data.share_summary.json_payload`; consumers should parse
it with `fromJSON(steps.deploywhisper.outputs.share-summary-json)` in workflow
expressions or `JSON.parse(...)` in scripts.

The `report-link` output is publicly shareable only when the DeployWhisper
server is configured with a public base URL such as `APP_BASE_URL` or
`PUBLIC_APP_URL`. Without that public URL prerequisite, self-hosted app
instances may emit a local or private fallback link such as
`http://127.0.0.1:8080/reports/{id}`, so GitHub Action consumers should treat
`report-link` and `share-summary-json.report_link` as optional for external
review workflows.

In the React UI, `/reports/{id}` renders the same read-only Report screen used
inside `/app/reports/{id}` with mutable actions hidden. Password-protected
shared reports still require the configured share password before the report
payload loads, and `?compare=previous` preserves the Compare with previous flow.

The machine payload in `share_summary.json_payload` includes
`report_schema_version`, Evidence Law status, top findings, evidence count,
context completeness, and report/rollback links. Consumers that need to branch
on persisted report shape should use `report_schema_version` and the
`docs/schemas/report-v2.md` contract rather than parsing PR comment text.

## Action-Owned GitHub Metadata Outputs

The external action also owns GitHub PR comment metadata outputs. These fields
are useful to workflow consumers, but they are not canonical API/report schema
fields:

| Action output | Action-owned source |
| --- | --- |
| `comment-id` | GitHub PR comment identifier returned by the external action |
| `comment-url` | GitHub PR comment URL returned by the external action |
| `comment-updated` | GitHub PR comment create/update state returned by the external action |

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

Local-first boundary: raw IaC, scanner artifacts, incident exports, and
sensitive context stay in the user's infrastructure by default. External model
calls should receive structured summaries, not raw uploads.

Secret-storage prohibition: the action contract must not persist API tokens,
provider credentials, raw infrastructure state, or deployment secrets.

## Repository Ownership

- Application repo: `deploywhisper/deploywhisper`
  - Documents the contract.
  - Owns API, CLI, report schema, share-summary, and advisory semantics.
  - Provides regression tests that guard the integration boundary.
- Action repo: `deploywhisper/analyze-action`
  - Owns `action.yml` or `action.yaml`.
  - Owns packaged action runtime code and Marketplace release metadata.
- Smoke consumer repo: `deploywhisper/action-smoke-consumer`
  - Owns live GitHub Actions smoke workflows for immutable release tags and the
    moving `v1` compatibility tag.
  - Owns same-repository PR smoke validation for published action behavior.

When changing action behavior, update the external action repository and keep
this guide aligned with the stable DeployWhisper API/report contract. When
changing live smoke behavior, update the smoke consumer repository.
