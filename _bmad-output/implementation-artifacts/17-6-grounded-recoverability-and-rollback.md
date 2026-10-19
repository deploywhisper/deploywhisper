# Story 17.6: Grounded Recoverability and Rollback

Status: backlog
Preparation: refined
Release: v1.6.0 | Priority: P0 within the independent Epic 17 lane

## Story

As a reviewer, I want to know whether a destructive change can actually be undone, so that "high risk" becomes a verified statement about restore paths rather than a category label.

## Implementation gates

- Blocked until 17.3 lands plan-directed reflection and bounded collection.
- Hard earlier dependencies: **17.3**. **No Epic 16 dependency.**
- This slice proves attribute collection and classification against **recorded fixtures per family**, including deliberately hostile combinations such as protection enabled but backups disabled.
- Absent data must never improve a classification. This is the core correctness property of the slice.

## Acceptance Criteria

1. **AC1:** Given a destructive change, when recoverability collection runs, then protection attributes are read, including deletion protection, final-snapshot behaviour, automated backup configuration and recovery-point age, object versioning, MFA delete, termination protection and most recent snapshot age.
2. **AC2:** Given collected attributes, when classification runs, then the change is classified `recoverable`, `recoverable_with_loss`, `irreversible` or `unknown`, citing the specific attributes that establish it.
3. **AC3:** Given an `irreversible` classification, when the rollback plan is produced, then it states explicitly that no restore path exists and names the attributes responsible.
4. **AC4:** Given unknown or unreadable recoverability, when results are rendered, then they are never presented as recoverable, and absent data never improves a classification.
5. **AC5:** Given grounding disabled, when rollback planning runs, then existing complexity-signalling behaviour is unchanged.

### Requirement Traceability

Coverage intent: delta over the current released baseline. Mapping is an acceptance obligation, not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| LEG-FR-027 | Collect protection and recoverability attributes for destructive changes across supported families. | Per-family attribute fixtures |
| LEG-FR-028 | Classify recoverability as `recoverable`, `recoverable_with_loss`, `irreversible` or `unknown`, citing establishing attributes. | Classification matrix including hostile combinations |
| LEG-FR-029 | Feed the rollback planner so an `irreversible` result states explicitly that no restore path exists and names the responsible attributes. | Rollback output tests for each classification |
| LEG-FR-030 | Never render unknown or unreadable recoverability as recoverable; absent data never improves a classification. | Negative-path and absent-data tests |
| LEG-NFR-004 | Degradation must be fail-safe. | Absent-data monotonicity assertions |
| LEG-NFR-009 | With grounding disabled, existing outputs must be unchanged. | Existing rollback behaviour regression |

## Tasks / Subtasks and bounded ownership

Execute one bounded packet at a time on `feature/17-6-grounded-recoverability`. Each packet owns the named paths.

- [ ] **Packet 6.1: Protection attribute collection — owner: core implementer.**
  - Owned write paths: `cloud/aws/recoverability.py`, `tests/test_cloud/aws/`.
  - Output: reads for deletion protection, final-snapshot behaviour, automated backup configuration and recovery-point age, object versioning, MFA delete, termination protection and most recent snapshot age.
  - Acceptance proof: AC1 — per-family attribute fixtures.
  - **Note:** every action required here must already be present in the 17.2 allow-list, or added to it together with the published policy and the equivalence test in the same PR.
- [ ] **Packet 6.2: Hostile fixture corpus — owner: test owner.**
  - Owned write paths: `tests/fixtures/` recoverability corpus, `tests/test_analysis/`.
  - Output: synthetic combinations including protection enabled with backups disabled, versioning enabled with MFA delete off, stale recovery points, and unreadable attributes.
  - Acceptance proof: fixture coverage underpinning AC2 and AC4.
- [ ] **Packet 6.3: Classification engine — owner: analysis implementer.**
  - Owned write paths: `analysis/recoverability.py`, `tests/test_analysis/`.
  - Output: four-way classification citing the specific attributes that establish each result.
  - Acceptance proof: AC2 — classification matrix.
- [ ] **Packet 6.4: Absent-data monotonicity — owner: analysis implementer.**
  - Owned write paths: `analysis/recoverability.py`, `tests/test_analysis/`.
  - Output: a mechanical guarantee that removing any attribute never improves a classification, and that unknown and unreadable are never rendered as recoverable.
  - Acceptance proof: AC4 — negative-path and absent-data tests.
- [ ] **Packet 6.5: Rollback planner integration — owner: analysis implementer.**
  - Owned write paths: existing rollback planning module **additive grounded path only**, `tests/test_analysis/`.
  - Output: grounded rollback output per classification, with an explicit no-restore-path statement and named attributes for `irreversible`.
  - Acceptance proof: AC3, AC5 — per-classification output tests plus a grounding-disabled regression.
  - **Shared-file rule:** additive only; existing complexity-signalling behaviour must be byte-identical with grounding off.

## Dev Notes

- Today, rollback output signals complexity by category. This slice replaces a category label with a verified statement about restore paths for grounded resources only; ungrounded resources keep existing behaviour.
- `unknown` is a first-class result, not an error. It must be visually and semantically distinct from `recoverable` everywhere it surfaces.
- The hostile fixtures are the point of the slice. A classifier that only handles clean combinations will mislead operators in exactly the cases that matter.
- Attribute citation must name the specific attributes, not a generic rationale sentence. A reviewer must be able to check the claim.
- Narrative generation must not soften an `irreversible` statement. Verify through the narrative path, not only the classifier unit test.
- Reuse the existing finding, evidence and confidence models and the existing freshness vocabulary. Do not bump the report schema version.
- Respect Python 3.10-compatible code on a 3.11 runtime, Pydantic 2, SQLAlchemy 2 and current lockfiles. **No dependency installation is authorized by this story.**
- Prohibited in this slice and in this epic: any write, apply, destroy, tag, provision or remediate capability; no snapshot creation, no backup enabling, no protection toggling. Recoverability is read and reported, never fixed. Reports remain advisory with `should_block=False`.
- Epic independence: no import from `infra_automation/` or `services/infra_automation_*`.

### Project Structure Notes

Attribute reads live in `cloud/aws/recoverability.py`; classification lives in `analysis/recoverability.py`. Analysis must not construct connectors directly.

### Testing requirements

- Before changing constructors or schema, search the entire repository for direct instantiations and fixtures; update all of them.
- Run `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh`, `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- Run `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` for serializer and rollback output changes.
- All fixtures are synthetic. Never commit real account identifiers, ARNs, snapshot identifiers or raw state.
- UI validation not applicable; presentation is owned by 17.8.

### Completion and integration boundary

- Attach exact commands, results, versions and proof artifact locations per AC and mapped requirement. Independent review resolves findings before advancement.
- This slice closes only recoverability collection, classification and rollback integration. It does not qualify a production AWS profile and does not claim live-account family breadth.

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
- `_bmad-output/implementation-artifacts/17-6-grounded-recoverability-and-rollback.md` (story specification only).
