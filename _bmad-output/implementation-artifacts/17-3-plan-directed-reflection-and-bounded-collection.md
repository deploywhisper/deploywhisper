# Story 17.3: Plan-Directed Reflection and Bounded Collection

Status: backlog. **Independent security review required before merge.**
Preparation: refined
Release: v1.5.0 (shared release train with Epic 16) | Priority: P0 within the independent Epic 17 lane

## Story

As a reviewer, I want DeployWhisper to read only what my change actually touches, plus one hop of real dependents, so that grounding is fast, cheap and minimally privileged instead of an estate-wide scan.

## Implementation gates

- Blocked until 17.1 and 17.2 land and an independent security review of the read-only boundary passes.
- Hard earlier dependencies: **17.1, 17.2, and a passed independent security review**. **No Epic 16 dependency.**
- This slice exercises **recorded provider fixtures and fault injection**. A single named live-account smoke exercise may be recorded as evidence but does **not** qualify the production profile, which is owned by 17.9.
- Plan-directed scope is the privacy and privilege argument of the whole epic. A connector that enumerates an account or region violates the contract even if the results are discarded.

## Acceptance Criteria

1. **AC1:** Given parsed artifacts including recorded prior state, when identity extraction runs, then a `ResourceIdentity` set is produced with no call issued.
2. **AC2:** Given a pure create with no physical counterpart, when reflection runs, then it is classified `no_live_counterpart` rather than failed or unreadable.
3. **AC3:** Given a connector that attempts account-wide or region-wide enumeration, when conformance runs, then it fails.
4. **AC4:** Given a touched resource set, when reverse expansion runs, then exactly one hop is expanded with a recorded bound and reason for each expansion.
5. **AC5:** Given an unreachable, partial, denied, throttled or expired context, when grounding completes, then severity is never lowered, confidence is never raised, `insufficient_context` is triggered, and unreadable resources carry the exact missing permission.
6. **AC6:** Given any collection, when it completes or is cancelled, then actual call count, elapsed time and budget consumption are reported.

### Requirement Traceability

Coverage intent: delta over the current released baseline. Mapping is an acceptance obligation, not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| LEG-FR-013 | Derive collection scope from the change itself by extracting resource identities from parsed artifacts and recorded prior state, without issuing any call. | Extraction tests over Terraform and OpenTofu plan fixtures |
| LEG-FR-014 | Classify a planned resource with no physical counterpart as `no_live_counterpart`, distinct from failure or unreadable. | Pure-create fixture tests |
| LEG-FR-015 | Never perform account-wide or region-wide enumeration. | Conformance test rejecting an enumerating connector |
| LEG-FR-016 | Expand exactly one hop of real dependents, recording the bound and the reason for each expansion. | Expansion bound and reason tests |
| LEG-NFR-003 | Collection must be bounded and interruptible, returning partial labelled results within the total deadline. | Deadline, cancellation and slow-provider fault injection |
| LEG-NFR-004 | Degradation must be fail-safe: missing context never lowers severity or raises confidence. | Degradation matrix across unreachable, partial, denied, throttled, expired |
| LEG-NFR-012 | Call count, elapsed time and budget consumption must be visible to the operator. | Budget reporting assertions in API and CLI |

## Tasks / Subtasks and bounded ownership

Execute one bounded packet at a time on `feature/17-3-plan-directed-reflection`. Each packet owns the named paths.

- [ ] **Packet 3.1: Identity extraction — owner: core implementer.**
  - Owned write paths: `cloud/reflection.py`, `tests/test_cloud/`.
  - Output: `ResourceIdentity` extraction from parsed artifacts and recorded prior state, issuing no call; `no_live_counterpart` classification for pure creates.
  - Acceptance proof: AC1, AC2 — extraction and pure-create fixture tests.
- [ ] **Packet 3.2: Scope guard and anti-enumeration conformance — owner: security-focused implementer.**
  - Owned write paths: `cloud/reflection.py`, `tests/test_cloud/conformance/`.
  - Output: a scope guard rejecting account-wide or region-wide enumeration, and a conformance test that fails an intentionally enumerating connector.
  - Acceptance proof: AC3 — LEG-FR-015 evidence.
- [ ] **Packet 3.3: One-hop reverse expansion — owner: core implementer.**
  - Owned write paths: `cloud/reflection.py`, `tests/test_cloud/`.
  - Output: exactly one hop of real dependents, with a recorded bound and a reason per expansion.
  - Acceptance proof: AC4.
- [ ] **Packet 3.4: Bounded collection and fault injection — owner: implementer.**
  - Owned write paths: `services/cloud_context_service.py`, `tests/test_services/`.
  - Output: deadline, concurrency, budget and cancellation applied to real collection; partial labelled results returned within the deadline.
  - Acceptance proof: AC5, AC6 — slow-provider and cancellation fault injection.
- [ ] **Packet 3.5: Fail-safe degradation matrix — owner: analysis implementer.**
  - Owned write paths: `services/cloud_context_service.py`, `analysis/` degradation hooks, `tests/test_analysis/`.
  - Output: enforcement that unreachable, partial, denied, throttled and expired context never lowers severity or raises confidence; `insufficient_context` triggered; unreadable resources carry the exact missing permission.
  - Acceptance proof: AC5 — full degradation matrix.
- [ ] **Packet 3.6: Budget reporting surface — owner: API and CLI implementer.**
  - Owned write paths: `api/` additive fields, `cli/` additive output, `tests/test_api/`, `tests/test_cli/`.
  - Output: actual call count, elapsed time and budget consumption on completion and on cancellation.
  - Acceptance proof: AC6 — LEG-NFR-012 assertions.
  - **Shared-file rule:** additive response fields only; do not change existing field semantics or bump the report schema version.
- [ ] **Packet 3.7: Independent security review — owner: reviewer who did not implement the packets above.**
  - Owned write paths: `docs/verification/live-environment-grounding/17-3/`.
  - Output: recorded review of the read-only boundary, scope guard, degradation and secret absence, with dispositions.
  - Acceptance proof: review record required before merge.

## Dev Notes

- The existing failure mode this slice fixes is visible in `analysis/blast_radius.py`, where unmatched resources produce a missing-context warning. Grounding must reduce that set with evidence, never paper over it.
- `parsers/terraform_parser.py` already reaches `change.get("before")` and `change.get("after")`. Use the 17.0 prior-state extraction findings; do not re-derive them ad hoc.
- `no_live_counterpart` is a **success** classification. Reporting a pure create as unreadable or failed is a defect, not a cosmetic issue.
- Fail-safe is a hard contract, not a heuristic. If a degradation path can lower a severity or raise a confidence value, the slice is not done.
- "Exact missing permission" means the specific action name the operator must grant, not a generic access-denied message.
- Reuse the existing `insufficient_context` machinery and the `ContextSourceFreshness` vocabulary rather than introducing parallel states.
- Live state is a point-in-time observation. Timestamp and digest it; do not present it as ground truth.
- Respect Python 3.10-compatible code on a 3.11 runtime, Pydantic 2, SQLAlchemy 2 and current lockfiles. **No dependency installation is authorized by this story.**
- Prohibited in this slice and in this epic: any write, apply, destroy, tag, provision or remediate capability; account-wide inventory; scheduled drift; cost estimation. Reports remain advisory with `should_block=False`.
- Epic independence: a grep for `infra_automation` under `cloud/` must return nothing.

### Project Structure Notes

Reflection logic lives in `cloud/reflection.py`; orchestration stays in `services/cloud_context_service.py` per architecture §26.3. Analysis modules consume grounding results and must not call connectors directly.

### Testing requirements

- Before changing constructors or schema, search the entire repository for direct instantiations and fixtures; update all of them.
- Run `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh`, `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- Run `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` for the additive API and CLI budget fields.
- Keep deterministic recorded fixtures separate from any live-account smoke exercise; a live smoke run is evidence, not qualification.
- Never use real production credentials against a production account without explicit operator authority. Never commit real account identifiers, ARNs or raw state.
- UI validation not applicable.

### Completion and integration boundary

- Attach exact commands, results, versions and proof artifact locations per AC and mapped requirement. Independent review resolves findings before advancement.
- This slice closes only plan-directed scoping, bounded collection and fail-safe degradation. It does not qualify a production AWS profile and does not deliver divergence, blast radius, recoverability or UI value.

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
- Story specification prepared; no implementation, security review, qualification or runtime test performed.
- Commands and proofs above are future obligations, not results.

### File List
- `_bmad-output/implementation-artifacts/17-3-plan-directed-reflection-and-bounded-collection.md` (story specification only).
