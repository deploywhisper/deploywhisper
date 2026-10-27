# Story 17.5: Live Dependency Graph and Grounded Blast Radius

Status: backlog
Preparation: refined
Release: v1.5.0 (shared release train with Epic 16) | Priority: P0 within the independent Epic 17 lane

## Story

As a reviewer, I want blast radius computed from real dependency edges in my account, so that I learn what this change actually touches instead of reading a "no topology mapping" warning.

## Implementation gates

- Blocked until 17.3 lands plan-directed reflection and bounded collection.
- Hard earlier dependencies: **17.3**. **No Epic 16 dependency.**
- This slice proves graph construction and blast-radius integration against **recorded provider fixtures per family**. Live-account breadth is owned by 17.9.
- Grounding must reduce the unmatched set with evidence. It must never make an unmatched resource disappear from the report.

## Acceptance Criteria

1. **AC1:** Given live reads for supported families, when the graph is built, then real edges are produced for security-group references, load-balancer to target-group to instance paths, DNS to load-balancer paths, IAM trust relationships, event-source mappings and database replica topology.
2. **AC2:** Given the `aws` handler registered in `TOPOLOGY_SOURCE_REGISTRY`, when import runs, then it produces a change set compatible with the existing topology payload contract and import metadata.
3. **AC3:** Given grounded resources, when `compute_blast_radius` runs, then they match, and genuinely unmatched resources remain explicitly reported; grounding never conceals an unmatched resource.
4. **AC4:** Given live tags, when ownership signals are derived, then they supplement `ownership_service` without overriding CODEOWNERS, and conflicts are surfaced rather than silently resolved.
5. **AC5:** Given affected nodes, when the result is rendered, then liveness facts such as running count, availability-zone spread and last observed activity each carry their own freshness and source.
6. **AC6:** Given declared and live environment classification disagreeing, when classification runs, then the state is `conflicting` rather than silently preferring one source.

### Requirement Traceability

Coverage intent: delta over the current released baseline. Mapping is an acceptance obligation, not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| LEG-FR-022 | Build real dependency edges from live reads for the supported resource families. | Per-family edge tests over recorded fixtures |
| LEG-FR-023 | Register an `aws` topology source handler producing a change set compatible with the existing topology payload contract and import metadata. | Topology payload and import-metadata contract tests |
| LEG-FR-024 | Match grounded resources in blast-radius computation while still reporting genuinely unmatched resources explicitly. | Blast-radius tests including a deliberately unmatched resource |
| LEG-FR-025 | Derive ownership signals from live tags that supplement but never override CODEOWNERS, surfacing conflicts. | Ownership precedence and conflict-surfacing tests |
| LEG-FR-026 | Attach liveness facts to affected nodes, each carrying its own freshness and source. | Node freshness and source attribution tests |
| LEG-FR-031 | Classify environment from declared and live signals, reporting `conflicting` on disagreement. | Declared-versus-live disagreement tests |

## Tasks / Subtasks and bounded ownership

Execute one bounded packet at a time on `feature/17-5-live-graph-and-blast-radius`. Each packet owns the named paths.

- [ ] **Packet 5.1: Per-family edge builders — owner: core implementer.**
  - Owned write paths: `cloud/aws/graph.py`, `tests/test_cloud/aws/`.
  - Output: edge construction for security-group references, load-balancer to target-group to instance paths, DNS to load-balancer paths, IAM trust relationships, event-source mappings and database replica topology.
  - Acceptance proof: AC1 — per-family edge tests over recorded fixtures.
- [ ] **Packet 5.2: `aws` topology source handler — owner: services implementer.**
  - Owned write paths: `services/topology_service.py` **additive registry entry only**, `tests/test_services/`.
  - Output: an `aws` entry in `TOPOLOGY_SOURCE_REGISTRY` producing a change set compatible with the existing topology payload contract and import metadata.
  - Acceptance proof: AC2 — payload and import-metadata contract tests.
  - **Shared-file rule:** register additively. Do not alter `custom`, `terraform`, `kubernetes`, `cloudformation` or `ansible` handlers.
- [ ] **Packet 5.3: Blast-radius integration — owner: analysis implementer.**
  - Owned write paths: `analysis/blast_radius.py` **additive grounded-match path only**, `tests/test_analysis/`.
  - Output: grounded resources match; `unmatched_resources` continues to report genuinely unmatched resources with the existing warning.
  - Acceptance proof: AC3 — blast-radius tests including a deliberately unmatched resource.
  - **Shared-file rule:** do not change existing unmatched-resource reporting semantics.
- [ ] **Packet 5.4: Tag-derived ownership — owner: services implementer.**
  - Owned write paths: `services/ownership_service.py` **additive supplementary signal only**, `tests/test_services/`.
  - Output: live tag ownership signals that supplement CODEOWNERS and surface conflicts.
  - Acceptance proof: AC4 — precedence and conflict-surfacing tests.
- [ ] **Packet 5.5: Liveness facts and freshness attribution — owner: core implementer.**
  - Owned write paths: `cloud/aws/graph.py`, `services/cloud_context_service.py`, `tests/test_services/`.
  - Output: running count, availability-zone spread and last observed activity, each with its own freshness and source.
  - Acceptance proof: AC5.
- [ ] **Packet 5.6: Grounded environment classification — owner: analysis implementer.**
  - Owned write paths: `analysis/`, `tests/test_analysis/`.
  - Output: declared-versus-live classification producing `conflicting` on disagreement.
  - Acceptance proof: AC6 — disagreement tests.

## Dev Notes

- This slice is the direct answer to the existing missing-context warning in `analysis/blast_radius.py`. Read that code path before implementing; the grounded path must plug into the existing `resource_to_service_ids` matching rather than bypassing it.
- `TOPOLOGY_SOURCE_REGISTRY` in `services/topology_service.py` already supports `custom`, `terraform` and live `kubernetes`, with explicit unimplemented handlers for `cloudformation` and `ansible`. Follow the `kubernetes` live-state handler as the precedent for a live source, including its explicit degradation warnings.
- CODEOWNERS precedence is non-negotiable. A live tag may add a candidate owner or raise a conflict; it may never replace a CODEOWNERS result.
- `conflicting` already exists in the freshness vocabulary. Use it; do not add a parallel state.
- Each liveness fact needs its own freshness. One snapshot-level freshness label applied to everything hides staleness at the fact level.
- Live state is a point-in-time observation. Timestamp and digest it; do not present it as ground truth.
- Only add persistence and entities this slice needs. Inspect the migration head before allocating changes.
- Respect Python 3.10-compatible code on a 3.11 runtime, Pydantic 2, SQLAlchemy 2 and current lockfiles. **No dependency installation is authorized by this story.**
- Prohibited in this slice and in this epic: any write, apply, destroy, tag, provision or remediate capability; account-wide inventory; scheduled drift; cost estimation. Reports remain advisory with `should_block=False`.
- Epic independence: no import from `infra_automation/` or `services/infra_automation_*`.

### Project Structure Notes

Graph construction lives in `cloud/aws/graph.py`; registry integration is an additive entry in `services/topology_service.py`. Analysis modules consume results and must not construct connectors directly.

### Testing requirements

- Before changing constructors or schema, search the entire repository for direct instantiations and fixtures; update all of them. `services/topology_service.py`, `analysis/blast_radius.py` and `services/ownership_service.py` are high-blast-radius shared files.
- Run `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh`, `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- Run `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` for topology payload and serializer changes.
- All fixtures are synthetic. Never commit real account identifiers, ARNs, tags from a real estate or raw state.
- UI validation not applicable; presentation is owned by 17.8.

### Completion and integration boundary

- Attach exact commands, results, versions and proof artifact locations per AC and mapped requirement. Independent review resolves findings before advancement.
- This slice closes only graph construction, topology registration, grounded matching, tag ownership, liveness facts and environment classification. It does not qualify a production AWS profile and does not claim live-account family breadth.

### References

- [RFC 0002](../../docs/rfcs/0002-live-environment-grounding.md)
- [Canonical feature PRD](../planning-artifacts/prd-live-environment-grounding.md)
- [Epic 17 stories](../planning-artifacts/epics.md)
- [Architecture Section 26](../planning-artifacts/architecture.md)
- [Epic 16/17 boundary plan](../planning-artifacts/epic-16-17-boundary-and-parallelization-plan.md)
- [Project implementation context](../project-context.md)

## Dev Agent Record

### Agent Model Used
Planning preparation only; implementation agent records its model at execution.

### Debug Log References
Not executed.

### Completion Notes List
- Story specification prepared; no implementation, qualification or runtime test performed.
- Commands and proofs above are future obligations, not results.

### File List
- `_bmad-output/implementation-artifacts/17-5-live-dependency-graph-and-grounded-blast-radius.md` (story specification only).
