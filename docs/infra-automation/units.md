# Declared unit preflight planning

Unit inventories describe human-declared collection and review scope. Waves do
not prove that upstream infrastructure was provisioned. After an external change,
collect new downstream evidence, analyze it and obtain a new decision.

The closed version-1 map declares each unit's ID, source/path, environment,
registered target alias and prerequisite IDs. `affected` identifies the units
the operator intends to review. The inventory must contain exactly those units
and their transitive declared prerequisites. Duplicate or unknown identities,
duplicate edges, cycles, missing prerequisites and unrelated extra units reject
the entire map with located diagnostics. No topology inference supplies missing
identities or edges.

Repository declarations use `kind: declared_repository`, `repository_id`,
`commit_sha` and a normalized relative `path`. Uploaded declarations use
`kind: uploaded`, `repository_source: unavailable` and a declared path. A
declaration does not verify provenance. The current qualified collector operates
at repository root: collected run bindings require `path: .`. Declaring another
path does not enable a new working-directory selector or qualify its evidence.

The planner admits at most 25 units, 200 explicit prerequisite edges and 128 KiB
of UTF-8 JSON, with nesting bounded to 16. These are conservative planner bounds,
not a 200-unit scale or production throughput promise. The separate workflow
limit remains 50 actual steps, including policy, decision and handoff steps.
Retained authoring is bounded to 25 inventories per project, 32 revisions per
inventory and 8 MiB of project inventory content, subject to the shared engine
storage quotas. Revisions are immutable; saving a later revision supersedes old
run eligibility without rewriting historical run evidence.

Authorized readers can recover older revisions through
`GET /api/v1/infra-automation/units/{inventory_id}/revisions` with explicit
`project_id` and `workspace_id`. The response contains all retained revision
summaries in descending version order, at most 32, with `truncated: false`.
This permits locating a saved revision even when another edit superseded it.

Units, affected IDs, prerequisite IDs and members of each wave sort
lexicographically before versioned canonical hashing. Input order does not change
the map or wave digest. Changing source, path, target, environment, scope or edges
changes the map identity. A wave contains all units whose prerequisites were in
earlier waves; it describes collection/review order only.

Run integration must preserve an immutable confirmed revision and exact
unit-to-intake/analysis bindings before collection starts. Collection and analysis
cannot depend on a human decision that itself requires the complete bundle.
The combined evidence
digest must come from retained server evidence, not a caller-supplied digest.
Existing canonical target aliases and locks remain authoritative; expiry or
cancellation cannot release unknown external work, and audited lock break never
issues an approval. Default unavailable approval-material providers remain
unavailable.

An identical authenticated start request with its original idempotency key reads
back the previously admitted run, including after inventory supersession. It does
not admit new work or renew eligibility. Changed payloads still conflict, and new
run admission requires the latest inventory revision.

Uploaded and mixed-source bundles remain advisory. Action eligibility requires
actual admitted collected evidence for every unit, the current immutable revision,
and matching server-derived combined evidence. The earliest policy, source or
custody deadline across the entire bundle bounds the decision. A fresh downstream
report cannot extend a prerequisite's expired evidence.

## Exact scope example

This uploaded map declares `app` as affected and `network` as its prerequisite.
Removing `network`, adding an unrelated unit, or referencing an undeclared ID
rejects the map. Its waves are `[network]`, then `[app]`.

```json
{
  "version": 1,
  "affected": ["app"],
  "units": [
    {"id": "network", "source": {"kind": "uploaded", "path": "network"}, "environment": "dev", "target": "network-target", "prerequisites": []},
    {"id": "app", "source": {"kind": "uploaded", "path": "app"}, "environment": "dev", "target": "app-target", "prerequisites": ["network"]}
  ]
}
```

The workflow must declare network intake → network analysis → app intake → app
analysis. Admission rejects hidden additional cross-unit dependencies as well as
missing ones, and rejects external handoff ancestors in this collection order.
The service consumes supplied screened uploads through the existing shared
analysis core. It does not generate or rewrite workflow dependencies.

## API and browser use

All routes below use the existing authenticated response/error envelopes and
concrete project/workspace scope. Mutations require current human session and
CSRF authority. Entire requests/responses remain bounded to 128 KiB, including
uploaded content in a multi-unit start request.

| Route under `/api/v1/infra-automation` | Purpose |
| --- | --- |
| `POST /units/validate` | Validate a declared map and return located diagnostics or canonical waves. |
| `GET /units` | Read the latest scoped inventory revisions. |
| `POST /units` | Save an immutable revision with expected-version checking. |
| `GET /units/{inventory_id}/revisions/{revision_id}` | Read an exact authorized revision. |
| `POST /units/runs` | Confirm `revision_id` and `confirmed_map_digest`, with the existing `run` request and exact `unit_id`/`intake_step_id`/`analysis_step_id` bindings. Uploaded bindings also supply `artifacts`. |
| `GET /runs/{run_id}/units` | Read the retained snapshot, server-derived evidence status/digest and shared canonical lock observations. |

The Inventory screen uses these APIs. Editing invalidates confirmation. A lost
save response requires loading and explicitly adopting the exact verified
revision; a lost start response retains the same request identity. A confirmed
start offers a separate new-preflight action that requires fresh confirmation and
files. Unit evidence refreshes independently of run status, because source expiry
or inventory supersession may not change the run version.

Local diagnostic measurement used a 25-unit/200-edge maximum-length ASCII corpus:
59,416 input bytes, 62,951 planned-result bytes, and 1,000 validations with p50
6.073 ms, p95 6.312 ms and p99 6.564 ms. Exact 128 KiB input and one-byte-over
rejection are regression-tested. These figures are local diagnostics, not a
production throughput qualification.

Implementation and acceptance results are recorded in
[Story 16.16](../../_bmad-output/implementation-artifacts/16-16-declared-multi-unit-preflight-planning.md).
Unchecked story packets remain acceptance obligations.
