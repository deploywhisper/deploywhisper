# Epic 17 Story Preparation Report — Live Environment Grounding

Date: 2026-10-19
Scope: Story preparation only. **No implementation, spike, qualification, review or test was performed.**
Branch: `feature/epic-17-live-environment-grounding`

## 1. What was prepared

Ten dedicated story contexts for Epic 17, 17.0 through 17.9, each carrying role and goal statement, status, implementation gates, numbered Given/When/Then acceptance criteria, a requirement traceability table with canonical requirement text and required proof, bounded ownership packets naming owned write paths, dev notes, testing requirements, a completion and integration boundary, and a Dev Agent Record stub.

| Story | File | Dependencies | Owned outcome |
| --- | --- | --- | --- |
| 17.0 | [17-0-adopt-and-qualify-the-grounding-contract.md](17-0-adopt-and-qualify-the-grounding-contract.md) | none | Governance decision, dependency decision, feasibility evidence, frozen coverage |
| 17.1 | [17-1-cloud-connector-contract-and-snapshot-evidence.md](17-1-cloud-connector-contract-and-snapshot-evidence.md) | 17.0 | Connector contract, registry, snapshot, evidence integration |
| 17.2 | [17-2-aws-read-only-session-allowlist-and-dry-run.md](17-2-aws-read-only-session-allowlist-and-dry-run.md) | 17.0, 17.1 | Credentials, allow-list, targeting, bounded execution, dry-run |
| 17.3 | [17-3-plan-directed-reflection-and-bounded-collection.md](17-3-plan-directed-reflection-and-bounded-collection.md) | 17.1, 17.2, security review | Plan-directed scope, one-hop expansion, fail-safe degradation |
| 17.4 | [17-4-plan-versus-reality-divergence-and-ci-gate.md](17-4-plan-versus-reality-divergence-and-ci-gate.md) | 17.3 | Divergence detection, plan freshness, severity floor, CI gate |
| 17.5 | [17-5-live-dependency-graph-and-grounded-blast-radius.md](17-5-live-dependency-graph-and-grounded-blast-radius.md) | 17.3 | Live graph, `aws` topology source, grounded blast radius, tag ownership |
| 17.6 | [17-6-grounded-recoverability-and-rollback.md](17-6-grounded-recoverability-and-rollback.md) | 17.3 | Protection attributes, recoverability classification, rollback guidance |
| 17.7 | [17-7-snapshot-portability-and-air-gapped-grounding.md](17-7-snapshot-portability-and-air-gapped-grounding.md) | 17.1, 17.3 | Snapshot export and import, air-gapped parity |
| 17.8 | [17-8-live-context-ui.md](17-8-live-context-ui.md) | 17.4, 17.5, 17.6 | `live_context` block, Live Context tab, Settings surface |
| 17.9 | [17-9-extensibility-cli-agent-and-qualification.md](17-9-extensibility-cli-agent-and-qualification.md) | all | CLI and agent surfaces, provider stubs, conformance suite, qualification |

## 2. Supporting artifacts prepared alongside

| Artifact | Purpose |
| --- | --- |
| [RFC 0002](../../docs/rfcs/0002-live-environment-grounding.md) | Governance gate; status Proposed |
| [Feature PRD](../planning-artifacts/prd-live-environment-grounding.md) | Canonical `LEG-FR-001..040` and `LEG-NFR-001..012` |
| [Architecture §26](../planning-artifacts/architecture.md) | v1.6.0 amendment with `LEG-ADR-01..10` |
| [Epic 17 in epics.md](../planning-artifacts/epics.md) | Epic header and all ten story definitions |
| [Sprint change proposal](../planning-artifacts/sprint-change-proposal-2026-10-19-epic-17-live-environment-grounding.md) | Course correction recording the new epic |
| [Boundary and parallelization plan](../planning-artifacts/epic-16-17-boundary-and-parallelization-plan.md) | Epic 16 conflict-avoidance contract |
| [Traceability matrix](../planning-artifacts/requirements-traceability-matrix.md) | Appended `LEG-*` adoption section, 52 rows |
| [sprint-status.yaml](sprint-status.yaml) | Appended `epic-17` block, all stories `backlog` |
| [Status map](story-implementation-status-map.md) | Appended Epic 17 section |

## 3. Requirement coverage

All 40 functional and 12 nonfunctional `LEG-*` requirements are mapped to at least one story with a named required proof. Coverage was generated from the PRD text rather than transcribed, to prevent drift between the PRD and the matrix.

**Mapping is not implementation evidence.** A mapped requirement has a planned acceptance path and nothing more.

## 4. Epic 16 independence

Epic 17 declares no dependency on any Epic 16 story. Verification obligations carried in every story file:

- New code lives in `cloud/` and `tests/test_cloud/`; a grep for `infra_automation` under `cloud/` must return nothing.
- Shared-file edits are append-only and additive: `evidence/models.py` enum members, the `TOPOLOGY_SOURCE_REGISTRY` entry, `config.py` redaction entries, `analysis/blast_radius.py` grounded match path, `analysis/risk_scorer.py` floor application, `services/ownership_service.py` supplementary signal.
- Tracking edits touched only Epic 17 keys, rows and sections. No Epic 16 key, row, section or story file was read for modification or changed.
- The single integration point is one-directional and optional: Epic 16 preflight may consume grounded context if both ship. Epic 17 never calls into Epic 16.

Architecture §26.2 `LEG-ADR-10` records the deliberate decision **not** to reuse the Epic 16 runner, with Story 17.7 snapshot import serving private-network operators instead.

## 5. Known gaps and open decisions

| Item | Owner | Status |
| --- | --- | --- |
| RFC 0002 maintainer decision | Maintainers | **Accepted 2026-10-19** — authorizes Story 17.0 only |
| AWS SDK runtime dependency decision | Story 17.0 Packet 0.2 | Open |
| Default deadline, concurrency and call-budget values | Story 17.0 Packet 0.5 | Open — must be measured, not guessed |
| Resource-family coverage list and per-capability permission map | Story 17.0 Packet 0.6 | Open — frozen at 17.0 close |
| Plan prior-state extraction fallback when absent | Story 17.0 Packet 0.4 | Open |
| Snapshot retention and age thresholds | Story 17.0 Packet 0.6 | Open |
| Tag-only divergence floor behaviour | Story 17.4 Packet 4.1 | Open — must be decided and documented, not left implicit |
| Real-account qualification authority | Story 17.9 Packet 9.5 | Not granted; requires explicit operator authority |

## 6. Readiness verdict

**Story 17.0 is READY. Stories 17.1-17.9 are NOT READY.**

RFC 0002 was accepted on 2026-10-19, which authorizes Story 17.0 qualification only. Story 17.0 must close its feasibility gate, record the dependency decision and freeze the coverage list before any downstream story is promoted. The open items in the table above remain open.

No code was written, no spike was run, no dependency was installed, no provider was contacted and no test result is claimed anywhere in this preparation set.
