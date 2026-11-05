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

Units, affected IDs, prerequisite IDs and members of each wave sort
lexicographically before versioned canonical hashing. Input order does not change
the map or wave digest. Changing source, path, target, environment, scope or edges
changes the map identity. A wave contains all units whose prerequisites were in
earlier waves; it describes collection/review order only.

Run integration must preserve an immutable confirmed revision and exact
unit-to-intake/analysis bindings before collection starts. The combined evidence
digest must come from retained server evidence, not a caller-supplied digest.
Existing canonical target aliases and locks remain authoritative; expiry or
cancellation cannot release unknown external work, and audited lock break never
issues an approval. Default unavailable approval-material providers remain
unavailable.

Uploaded and mixed-source bundles remain advisory. Action eligibility requires
actual admitted collected evidence for every unit, the current immutable revision,
and matching server-derived combined evidence. The earliest policy, source or
custody deadline across the entire bundle bounds the decision. A fresh downstream
report cannot extend a prerequisite's expired evidence.

Implementation and acceptance results are recorded in
[Story 16.16](../../_bmad-output/implementation-artifacts/16-16-declared-multi-unit-preflight-planning.md).
Unchecked story packets remain acceptance obligations.
