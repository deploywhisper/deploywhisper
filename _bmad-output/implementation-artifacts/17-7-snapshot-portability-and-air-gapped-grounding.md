# Story 17.7: Snapshot Portability and Air-Gapped Grounding

Status: backlog
Preparation: refined
Release: v1.5.0 (shared release train with Epic 16) | Priority: P1 within the independent Epic 17 lane

## Story

As a restricted-network operator, I want to collect on a connected host and analyze on a disconnected one, so that network isolation does not cost me grounded evidence.

## Implementation gates

- Blocked until 17.1 lands the snapshot model and 17.3 lands real collection.
- Hard earlier dependencies: **17.1, 17.3**. **No Epic 16 dependency.**
- This slice proves export, import, labelling and rejection semantics **locally**. The full disconnected-host operator exercise is recorded here and re-verified in 17.9.
- This story is how private-network operators get grounding value without the Epic 16 runner. It must stand alone.

## Acceptance Criteria

1. **AC1:** Given a completed snapshot, when it is exported, then the file is digest-bound, carries provenance, and contains no credential material, secret values or raw state.
2. **AC2:** Given an exported snapshot, when it is imported on a disconnected host, then grounding semantics are identical to a live read.
3. **AC3:** Given an imported snapshot, when it is used, then it is explicitly labelled `imported` and subject to an age check that can mark it `stale`.
4. **AC4:** Given a tampered or digest-mismatched snapshot file, when import runs, then it is rejected with a specific cause and never partially applied.
5. **AC5:** Given a snapshot from a different project or provider scope, when import runs, then it is rejected rather than silently rescoped.

### Requirement Traceability

Coverage intent: delta over the current released baseline. Mapping is an acceptance obligation, not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| LEG-FR-032 | Export and import digest-bound snapshots carrying provenance, labelled `imported` on use and subject to an age check. | Round-trip, tamper and age-check tests |
| LEG-FR-033 | Produce identical grounding semantics from an imported snapshot as from a live read. | Live-versus-imported equivalence tests |
| LEG-FR-004 | Redact every snapshot; no secret values, credential material, user data, raw state or plan bytes. | Sensitive-value corpus over exported files |
| LEG-NFR-006 | Snapshots must be deterministic and auditable. | Digest verification on import |
| LEG-NFR-011 | Air-gapped parity: a disconnected host must reach the same grounded conclusions from an imported snapshot. | Disconnected-host equivalence exercise |

## Tasks / Subtasks and bounded ownership

Execute one bounded packet at a time on `feature/17-7-snapshot-portability`. Each packet owns the named paths.

- [ ] **Packet 7.1: Export format and provenance — owner: core implementer.**
  - Owned write paths: `cloud/portability.py`, `tests/test_cloud/`.
  - Output: a versioned, digest-bound export carrying provenance including provider, scope, regions, read window and application version.
  - Acceptance proof: AC1 — format and provenance tests plus a sensitive-value corpus over exported files.
- [ ] **Packet 7.2: Import, verification and rejection — owner: core implementer.**
  - Owned write paths: `cloud/portability.py`, `services/cloud_context_service.py`, `tests/test_cloud/`, `tests/test_services/`.
  - Output: digest verification, atomic application, and specific-cause rejection for tampered, mismatched, wrong-project and wrong-scope files.
  - Acceptance proof: AC4, AC5 — tamper and scope-rejection tests confirming no partial application.
- [ ] **Packet 7.3: `imported` labelling and age check — owner: services implementer.**
  - Owned write paths: `services/cloud_context_service.py`, `tests/test_services/`.
  - Output: explicit `imported` labelling on every derived claim, plus an age check able to mark the snapshot `stale` using the existing freshness vocabulary.
  - Acceptance proof: AC3.
- [ ] **Packet 7.4: Live-versus-imported equivalence — owner: test owner.**
  - Owned write paths: `tests/test_services/`, `tests/test_analysis/`.
  - Output: an equivalence suite asserting that divergence, blast radius and recoverability results from an imported snapshot match those from the equivalent live read.
  - Acceptance proof: AC2 — equivalence tests.
- [ ] **Packet 7.5: CLI export and import — owner: CLI implementer and documenter.**
  - Owned write paths: `cli/`, `tests/test_cli/`, `docs/live-environment-grounding/README.md`.
  - Output: export and import commands and a documented air-gapped operator workflow.
  - Acceptance proof: AC1–AC5 through the CLI surface.
- [ ] **Packet 7.6: Disconnected-host exercise — owner: operator verifier.**
  - Owned write paths: `docs/verification/live-environment-grounding/17-7/`.
  - Output: a recorded exercise collecting on a connected host and analyzing on a host with network access removed, with identical conclusions.
  - Acceptance proof: AC2 — LEG-NFR-011 evidence, re-verified in 17.9.

## Dev Notes

- The exported file leaves the operator's trust boundary. Treat redaction here as stricter than internal persistence, and verify it against the sensitive-value corpus on the **exported bytes**, not only on the in-memory model.
- Import must be atomic. A rejected file that has already mutated project state is a defect even if the rejection message is correct.
- `imported` is a provenance label, not a freshness value. Keep them separate: a snapshot can be `imported` and `current`, or `imported` and `stale`.
- Wrong-project and wrong-scope rejection prevents cross-project contamination of grounded claims. Silent rescoping would be a correctness and privacy failure.
- The export format is a published contract once released. Version it explicitly from the first commit.
- Reuse `services/content_security.py` redaction and the existing freshness vocabulary. Do not introduce parallel mechanisms.
- Respect Python 3.10-compatible code on a 3.11 runtime, Pydantic 2, SQLAlchemy 2 and current lockfiles. **No dependency installation is authorized by this story.**
- Prohibited in this slice and in this epic: any write, apply, destroy, tag, provision or remediate capability; account-wide inventory; scheduled drift; cost estimation. Reports remain advisory with `should_block=False`.
- Epic independence: this story is the deliberate alternative to the Epic 16 runner for private-network operators. It must not import from `infra_automation/` or `services/infra_automation_*`.

### Project Structure Notes

Export and import live in `cloud/portability.py`; labelling and age checks live in `services/cloud_context_service.py` per architecture §26.3.

### Testing requirements

- Before changing constructors or schema, search the entire repository for direct instantiations and fixtures; update all of them.
- Run `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh`, `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- Run `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` for the CLI export and import commands.
- All snapshot fixtures are synthetic. Never commit an exported snapshot taken from a real estate.
- UI validation not applicable; presentation is owned by 17.8.

### Completion and integration boundary

- Attach exact commands, results, versions and proof artifact locations per AC and mapped requirement. Independent review resolves findings before advancement.
- This slice closes only export, import, labelling, rejection and equivalence. The disconnected-host exercise recorded here is re-verified under the qualified profile in 17.9.

### References

- [RFC 0002](../../docs/rfcs/0002-live-environment-grounding.md)
- [Canonical feature PRD](../planning-artifacts/prd-live-environment-grounding.md)
- [Epic 17 stories](../planning-artifacts/epics.md)
- [Architecture Section 26](../planning-artifacts/architecture.md)
- [Epic 16/17 boundary plan](../planning-artifacts/epic-16-17-boundary-and-parallelization-plan.md)
- [Operator guide](../../docs/live-environment-grounding/README.md)
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
- `_bmad-output/implementation-artifacts/17-7-snapshot-portability-and-air-gapped-grounding.md` (story specification only).
