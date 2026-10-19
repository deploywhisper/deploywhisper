# Story 17.9: Multi-Provider Extensibility, CLI and Agent Surfaces, and Qualification

Status: backlog
Preparation: refined
Release: v1.6.0 | Priority: P1 within the independent Epic 17 lane

## Story

As a maintainer, I want the connector contract published with a conformance suite, the CLI and agent surfaces complete, and the whole feature qualified, so that the community can extend grounding and operators receive honest capability and safety evidence.

## Implementation gates

- Blocked until all earlier Epic 17 stories land their owned contracts.
- Hard earlier dependencies: **17.0 through 17.8**. **No Epic 16 dependency.**
- **This is the only story permitted to claim a qualified production provider profile.** Recorded fixtures from earlier slices do not qualify it.
- Qualification against a real AWS account requires explicit operator authority for that account. Do not assume it.

## Acceptance Criteria

1. **AC1:** Given the CLI, when grounding commands run, then they use the same API authority and the same read-only enforcement as the web surface, including dry-run, export, import and the divergence gate.
2. **AC2:** Given the agent and MCP-compatible interface, when grounded facts are returned, then determinism and freshness labels are explicit and grounded facts cannot be presented as equivalent to inferred ones.
3. **AC3:** Given Azure and GCP, when grounding is requested, then they fail explicitly and identically to the existing unimplemented topology sources, with no partial or misleading behaviour.
4. **AC4:** Given the published connector contributor guide and conformance suite, when a reference provider is implemented against them, then it passes without maintainer-specific knowledge and without modifying core analysis.
5. **AC5:** Given a real AWS account and the published minimal IAM policy, when the supported-profile qualification runs, then live grounding, divergence detection, recoverability classification and air-gapped import are all demonstrated end to end.
6. **AC6:** Given the benchmark corpus, when backtesting runs with and without grounding, then a published before/after accuracy delta, an `unmatched_resources` rate delta, a determinism-mix delta, and counted divergence and irreversible-destroy detections are recorded.
7. **AC7:** Given full CI, security, contract, fault-injection, end-to-end and accessibility gates, when release qualification runs, then all pass with no unresolved introduced critical or high defect, and a versioned manifest freezes supported SDK, provider API and application versions.

### Requirement Traceability

Coverage intent: delta over the current released baseline. Mapping is an acceptance obligation, not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| LEG-FR-037 | Provide a CLI surface using the same API authority and read-only enforcement as the web surface. | CLI parity and enforcement tests |
| LEG-FR-038 | Expose grounded facts to agent and MCP-compatible surfaces with explicit determinism and freshness labels. | Agent output contract tests |
| LEG-FR-039 | Register Azure and GCP as explicit unimplemented providers failing identically to existing unimplemented topology sources. | Unimplemented-provider behaviour tests |
| LEG-FR-040 | Publish a connector contributor guide and an executable conformance suite. | Reference provider passing conformance with no core diff |
| LEG-NFR-010 | A new provider must be addable without modifying core analysis. | Conformance suite against the reference stub |
| LEG-NFR-001..012 | Release-wide nonfunctional obligations. | Full qualification matrix, measured results and published deltas |

## Tasks / Subtasks and bounded ownership

Execute one bounded packet at a time on `feature/17-9-extensibility-and-qualification`. Each packet owns the named paths.

- [ ] **Packet 9.1: CLI surface completion — owner: CLI implementer.**
  - Owned write paths: `cli/`, `tests/test_cli/`.
  - Output: grounding, dry-run, export, import and divergence-gate commands sharing the web surface's API authority and read-only enforcement.
  - Acceptance proof: AC1 — CLI parity and enforcement tests.
- [ ] **Packet 9.2: Agent and MCP surfaces — owner: integrations implementer.**
  - Owned write paths: `integrations/`, `llm/` skill context, `tests/`.
  - Output: grounded facts carrying explicit determinism and freshness labels, with grounded and inferred facts structurally distinguishable.
  - Acceptance proof: AC2 — agent output contract tests.
- [ ] **Packet 9.3: Azure and GCP explicit stubs — owner: core implementer.**
  - Owned write paths: `cloud/registry.py`, `tests/test_cloud/`.
  - Output: explicit unimplemented registration failing identically to `cloudformation` and `ansible` in `TOPOLOGY_SOURCE_REGISTRY`.
  - Acceptance proof: AC3 — unimplemented-provider behaviour tests.
- [ ] **Packet 9.4: Contributor guide and conformance suite — owner: maintainer and test owner.**
  - Owned write paths: `docs/live-environment-grounding/connector-contract.md`, `tests/test_cloud/conformance/`.
  - Output: a published contributor guide and an executable conformance suite covering read-only enforcement, anti-enumeration, snapshot determinism, redaction, degradation and labelling.
  - Acceptance proof: AC4 — a reference provider passing with no core analysis diff.
- [ ] **Packet 9.5: Supported-profile qualification — owner: operator verifier.**
  - Owned write paths: `docs/verification/live-environment-grounding/17-9/`.
  - Output: an end-to-end exercise against a real AWS account using only the published minimal policy, demonstrating live grounding, divergence detection, recoverability classification and air-gapped import.
  - Acceptance proof: AC5 — recorded qualification evidence.
  - **Authority note:** requires explicit operator authority for the target account. Prefer a disposable account. Never commit account identifiers, ARNs or captured state.
- [ ] **Packet 9.6: Measured value deltas — owner: analysis verifier.**
  - Owned write paths: `benchmarks/`, `docs/verification/live-environment-grounding/17-9/`.
  - Output: backtesting with and without grounding over the benchmark corpus, publishing accuracy delta, `unmatched_resources` rate delta, determinism-mix delta, and counted divergence and irreversible-destroy detections.
  - Acceptance proof: AC6 — published before and after results, including a null or negative result if that is what the data shows.
- [ ] **Packet 9.7: Release qualification and version manifest — owner: maintainer.**
  - Owned write paths: `docs/verification/live-environment-grounding/17-9/`, release notes, `ROADMAP.md`.
  - Output: full CI, security, contract, fault-injection, end-to-end and accessibility gate results; a versioned manifest freezing supported SDK, provider API and application versions.
  - Acceptance proof: AC7 — qualification matrix with no unresolved introduced critical or high defect.

## Dev Notes

- `services/backtesting_service.py` and `benchmarks/` already exist. Packet 9.6 uses the existing harness; do not build a parallel measurement path.
- Publish the measured delta honestly. If grounding does not improve accuracy on the corpus, publish that result and record the reason. A fabricated or selectively reported delta is worse than a null result.
- The conformance suite is the real extensibility deliverable. A guide without an executable suite does not satisfy AC4.
- Azure and GCP must fail **identically** to existing unimplemented sources. Partial Azure support shipped as "experimental" violates AC3.
- Agent surfaces are where grounded and inferred facts are most likely to be flattened. The distinction must be structural in the payload, not merely present in prose.
- Qualification is a release gate, not a story checkbox. Any missing mandatory proof keeps the relevant status blocked or in progress.
- Respect Python 3.10-compatible code on a 3.11 runtime, Pydantic 2, SQLAlchemy 2 and current lockfiles. Dependency changes are limited to the option approved in 17.0.
- Prohibited in this slice and in this epic: any write, apply, destroy, tag, provision or remediate capability; account-wide inventory; scheduled drift; cost estimation. Reports remain advisory with `should_block=False`.
- Epic independence: a grep for `infra_automation` under `cloud/` must return nothing. Public GitHub writes and release publication require authority for those actions.

### Project Structure Notes

Conformance lives in `tests/test_cloud/conformance/`; the contributor guide lives in `docs/live-environment-grounding/connector-contract.md`. Verification evidence lives under `docs/verification/live-environment-grounding/`.

### Testing requirements

- Run `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh`, `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- Run `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` plus the registered `tests/test_cloud/` shard.
- Run the composed UI lane: `docker compose up -d --build`, then `BASE_URL=http://localhost:8080 RUN_UI_A11Y=1 bash scripts/ci-local.sh`, then `docker compose down`.
- Keep deterministic fixtures separate from real-account qualification. Local real-credential custody is disposable and never committed.

### Completion and integration boundary

- Attach exact commands, results, versions, measured deltas and proof artifact locations per AC and mapped requirement. Independent review resolves findings before advancement.
- This slice is the only one that may claim a qualified AWS production profile. Azure and GCP remain explicitly unimplemented and must not be claimed as supported.

### References

- [RFC 0002](../../docs/rfcs/0002-live-environment-grounding.md)
- [Canonical feature PRD](../planning-artifacts/prd-live-environment-grounding.md)
- [Epic 17 stories](../planning-artifacts/epics.md)
- [Architecture Section 26](../planning-artifacts/architecture.md)
- [Epic 16/17 boundary plan](../planning-artifacts/epic-16-17-boundary-and-parallelization-plan.md)
- [Connector contract guide](../../docs/live-environment-grounding/connector-contract.md)
- [Operator guide](../../docs/live-environment-grounding/README.md)
- [Project implementation context](../project-context.md)

## Dev Agent Record

### Agent Model Used
Planning preparation only; implementation agent records its model at execution.

### Debug Log References
Not executed.

### Completion Notes List
- Story specification prepared; no implementation, qualification, measurement, release publication or runtime test performed.
- Commands and proofs above are future obligations, not results.

### File List
- `_bmad-output/implementation-artifacts/17-9-extensibility-cli-agent-and-qualification.md` (story specification only).
