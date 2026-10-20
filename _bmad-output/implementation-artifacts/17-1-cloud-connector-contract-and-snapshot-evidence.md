# Story 17.1: Cloud Connector Contract, Registry and Snapshot Evidence

Status: backlog
Preparation: refined
Release: v1.5.0 (shared release train with Epic 16) | Priority: P0 within the independent Epic 17 lane

## Story

As a maintainer, I want a provider-neutral read-only connector contract and an immutable redacted snapshot that enters the existing evidence system, so that grounding is governed by Evidence Law from the first line of code and new providers never require core changes.

## Implementation gates

- Blocked until Story 17.0 records RFC 0002 acceptance, the approved dependency decision, frozen coverage list and feasibility evidence.
- Hard earlier dependencies: **17.0**. **No Epic 16 dependency; do not import from `infra_automation/` or `services/infra_automation_*`.**
- This slice is proven entirely against a **reference stub provider with no network access**. No live provider calls, no credentials and no AWS SDK are exercised here.
- Promote only after dependency evidence, final interfaces and packet estimates are independently reviewed.

## Acceptance Criteria

1. **AC1:** Given a registered reference stub provider, when grounding runs with no network access, then the connector contract, registry, snapshot model and evidence linkage work end to end without any provider SDK present.
2. **AC2:** Given an unregistered, unimplemented or unknown provider, when grounding is requested, then it fails explicitly with a specific cause and never silently returns a successful empty result.
3. **AC3:** Given a snapshot containing sensitive values, when it is persisted, then redaction removes secret values, credential material, user data and raw state, and account identifiers are maskable by configuration.
4. **AC4:** Given grounding disabled, which is the default, when the full existing suite runs, then every existing report, fixture, schema, API consumer, CLI output and agent output is unchanged and no cloud call is issued.
5. **AC5:** Given the same observation twice, when snapshots are produced, then their digests match, and every grounded claim in a report references its snapshot digest.
6. **AC6:** Given a partial or unreadable read result, when the snapshot is built, then it is labelled partial and each unreadable resource carries its specific cause; completeness is never implied.
7. **AC7:** Given a project that has not explicitly enabled a configured connector, when analysis runs, then grounding is skipped and no connector is instantiated.

### Requirement Traceability

Coverage intent: delta over the current released baseline. Mapping is an acceptance obligation, not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| LEG-FR-001 | Provide a provider-neutral read-only cloud connector contract and registry so a provider can be added without modifying core analysis; unregistered and unimplemented providers fail explicitly. | Registry tests covering stub, unimplemented and unknown provider cases |
| LEG-FR-002 | Produce an immutable `LiveContextSnapshot` recording provider, scope, regions, read window, per-resource read status, issued actions and a content digest. | Snapshot model, immutability and field-coverage tests |
| LEG-FR-003 | Persist the snapshot as project-scoped evidence using `live_state` with `deterministic` determinism; Evidence Law applies unchanged. | Evidence Law runtime gate tests for grounded claims |
| LEG-FR-004 | Redact every snapshot before persistence; no secret values, credential material, user data, raw state or plan bytes; maskable account identifiers. | Sensitive-value corpus over persisted snapshots |
| LEG-FR-005 | Integrate snapshot freshness into `ContextSourceMetadata` using the existing freshness vocabulary. | Freshness state matrix tests |
| LEG-FR-006 | Label partial reads as partial and enumerate every unreadable resource with its cause. | Partial and unreadable result tests |
| LEG-FR-007 | Make grounding opt-in per project and disabled by default. | Default-off and unconfigured-project tests |
| LEG-NFR-006 | Snapshots must be deterministic and auditable; every grounded claim references its snapshot digest. | Digest reproducibility and evidence-linkage tests |
| LEG-NFR-009 | With grounding disabled, all existing outputs must be unchanged. | Full existing suite plus legacy consumer contract tests |
| LEG-NFR-010 | A new provider must be addable without modifying core analysis. | Reference stub added with no core analysis diff |

## Tasks / Subtasks and bounded ownership

Execute one bounded packet at a time on `feature/17-1-connector-contract-and-snapshot`. Each packet owns the named paths; coordinate shared paths and do not revert other edits.

- [ ] **Packet 1.1: Connector contract and registry — owner: core implementer.**
  - Owned write paths: `cloud/base.py`, `cloud/registry.py`, `tests/test_cloud/`.
  - Output: `CloudConnector` protocol, `ResourceIdentity`, `ReadStatus`, provider registry mirroring `parsers/registry.py`, explicit unimplemented and unknown provider behaviour mirroring `_build_unimplemented_source_handler`.
  - Acceptance proof: AC1, AC2 — registry and contract tests.
- [ ] **Packet 1.2: Snapshot model and redaction — owner: core implementer.**
  - Owned write paths: `cloud/base.py` snapshot model, `cloud/redaction.py`, `tests/test_cloud/`.
  - Output: immutable digest-bound snapshot; redaction built on `services/content_security.py`; maskable account identifiers.
  - Acceptance proof: AC3, AC5, AC6 — redaction corpus and digest reproducibility tests.
- [ ] **Packet 1.3: Evidence and freshness integration — owner: core implementer.**
  - Owned write paths: `evidence/models.py` **additive enum members only**, `tests/test_evidence/`.
  - Output: `live_state` added to `EvidenceSourceType` and `ContextSourceType`; `deterministic` determinism; freshness reusing the existing vocabulary.
  - Acceptance proof: AC5 — Evidence Law gate and freshness matrix tests.
  - **Shared-file rule:** additive members only. Never remove or reorder existing members. Epic 16 may edit this file concurrently.
- [ ] **Packet 1.4: Orchestration service and opt-in gating — owner: services implementer.**
  - Owned write paths: `services/cloud_context_service.py`, `tests/test_services/`.
  - Output: per-project opt-in resolution, disabled-by-default behaviour, snapshot persistence and retrieval, degradation surface.
  - Acceptance proof: AC4, AC7 — default-off and unconfigured-project tests.
- [ ] **Packet 1.5: Reference stub provider and conformance seed — owner: test owner.**
  - Owned write paths: `cloud/` reference stub, `tests/test_cloud/conformance/`.
  - Output: a network-free reference provider proving the contract, and the seed of the conformance suite completed in 17.9.
  - Acceptance proof: AC1, and LEG-NFR-010 with no core analysis diff.
- [ ] **Packet 1.6: Backward-compatibility proof — owner: test owner.**
  - Owned write paths: `tests/`, CI registration in `scripts/ci-local.sh`.
  - Output: `tests/test_cloud/` registered in local CI and the relevant GitHub shard; full existing suite green with grounding off.
  - Acceptance proof: AC4 — LEG-NFR-009 evidence.

## Dev Notes

- Mirror existing extension patterns deliberately: `parsers/registry.py` for registration shape, and `_build_unimplemented_source_handler` in `services/topology_service.py` for explicit unimplemented behaviour. Do not invent a new pattern.
- Reuse `services/content_security.py` redaction helpers (`redact_text`, `redact_value`, `sensitive_artifact_values`) rather than writing new redaction logic.
- Reuse the existing freshness vocabulary `current`/`stale`/`missing`/`incomplete`/`conflicting`/`unknown` from `evidence/models.py`. A parallel vocabulary is a review rejection.
- Live state is a point-in-time observation. Timestamp and digest it; do not present it as ground truth.
- Only add the persistence and entities this slice needs. Do not create the full grounding schema in one foundational migration. Inspect the migration head before allocating changes.
- Respect Python 3.10-compatible code on a 3.11 runtime, Pydantic 2, SQLAlchemy 2 and current lockfiles. **No dependency installation is authorized by this story**; this slice must work with no provider SDK installed.
- Prohibited in this slice and in this epic: any write, apply, destroy, tag, provision or remediate capability; account-wide inventory; scheduled drift; cost estimation. Reports remain advisory with `should_block=False`.
- Epic independence: a grep for `infra_automation` under `cloud/` must return nothing.

### Project Structure Notes

New trees `cloud/` and `tests/test_cloud/` follow architecture §26.3. `tests/test_cloud/` must be explicitly registered in `scripts/ci-local.sh` and the relevant GitHub shard, because recursive root discovery skips directories that are not Python packages.

### Testing requirements

- Before changing constructors or schema, search the entire repository for direct instantiations and fixtures; update all of them. `evidence/models.py` changes are high-blast-radius — run the affected shards exactly as CI does.
- Run `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh`, `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- Run `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` for any serializer or constructor contract change.
- UI validation not applicable.

### Completion and integration boundary

- Attach exact commands, results, versions and proof artifact locations per AC and mapped requirement. Independent review resolves findings before advancement.
- This slice closes only the contract, registry, snapshot and evidence integration against a stub provider. It does not qualify any production provider profile and must not claim AWS support.

### References

- [RFC 0002](../../docs/rfcs/0002-live-environment-grounding.md)
- [Canonical feature PRD](../planning-artifacts/prd-live-environment-grounding.md)
- [Epic 17 stories](../planning-artifacts/epics.md)
- [Architecture Section 26](../planning-artifacts/architecture.md)
- [Epic 16/17 boundary plan](../planning-artifacts/epic-16-17-boundary-and-parallelization-plan.md)
- [Connector contract guide](../../docs/live-environment-grounding/connector-contract.md)
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
- `_bmad-output/implementation-artifacts/17-1-cloud-connector-contract-and-snapshot-evidence.md` (story specification only).
