# Story 17.3: Plan-Directed Reflection and Bounded Collection

Status: done. **Independent offline security review passed.**
Preparation: refined
Release: v1.6.0 (independent release train) | Priority: P0 within the independent Epic 17 lane

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

- [x] **Packet 3.1: Identity extraction — owner: core implementer.**
  - Owned write paths: `cloud/reflection.py`, `tests/test_cloud/`.
  - Output: `ResourceIdentity` extraction from parsed artifacts and recorded prior state, issuing no call; `no_live_counterpart` classification for pure creates.
  - Acceptance proof: AC1, AC2 — extraction and pure-create fixture tests.
- [x] **Packet 3.2: Scope guard and anti-enumeration conformance — owner: security-focused implementer.**
  - Owned write paths: `cloud/reflection.py`, `tests/test_cloud/conformance/`.
  - Output: a scope guard rejecting account-wide or region-wide enumeration, and a conformance test that fails an intentionally enumerating connector.
  - Acceptance proof: AC3 — LEG-FR-015 evidence.
- [x] **Packet 3.3: One-hop reverse expansion — owner: core implementer.**
  - Owned write paths: `cloud/reflection.py`, `tests/test_cloud/`.
  - Output: exactly one hop of real dependents, with a recorded bound and a reason per expansion.
  - Acceptance proof: AC4.
- [x] **Packet 3.4: Bounded collection and fault injection — owner: implementer.**
  - Owned write paths: `services/cloud_context_service.py`, `tests/test_services/`.
  - Output: deadline, concurrency, budget and cancellation applied to real collection; partial labelled results returned within the deadline.
  - Acceptance proof: AC5, AC6 — slow-provider and cancellation fault injection.
- [x] **Packet 3.5: Fail-safe degradation matrix — owner: analysis implementer.**
  - Owned write paths: `services/cloud_context_service.py`, `analysis/` degradation hooks, `tests/test_analysis/`.
  - Output: enforcement that unreachable, partial, denied, throttled and expired context never lowers severity or raises confidence; `insufficient_context` triggered; unreadable resources carry the exact missing permission.
  - Acceptance proof: AC5 — full degradation matrix.
- [x] **Packet 3.6: Budget reporting surface — owner: API and CLI implementer.**
  - Owned write paths: `api/` additive fields, `cli/` additive output, `tests/test_api/`, `tests/test_cli/`.
  - Output: actual call count, elapsed time and budget consumption on completion and on cancellation.
  - Acceptance proof: AC6 — LEG-NFR-012 assertions.
  - **Shared-file rule:** additive response fields only; do not change existing field semantics or bump the report schema version.
- [x] **Packet 3.7: Independent security review — owner: reviewer who did not implement the packets above.**
  - Owned write paths: `docs/verification/live-environment-grounding/17-3/`.
  - Output: recorded review of the read-only boundary, scope guard, degradation and secret absence, with dispositions.
  - Acceptance proof: review record required before merge.

### Review Findings

- [x] [Review][Patch][P1] Exclude ordinary no-op resources from direct and reverse collection (`cloud/reflection.py:349`).
- [x] [Review][Patch][P1] Screen plan-known private values through provider projection and retention (`cloud/aws/projection.py:94`).
- [x] [Review][Patch][P1] Enforce the total deadline and account for cancellation through service completion (`services/cloud_context_service.py:638`).
- [x] [Review][Patch][P2] Share scheduling limits across regions and align call accounting with dispatch (`cloud/collection.py:138`, `cloud/aws/client.py:389`).
- [x] [Review][Patch][P2] Distinguish current and deposed Terraform objects during extraction (`cloud/reflection.py:336`).
- [x] [Review][Patch][P2] Keep unsupported identities from blocking supported siblings and label unobserved identities unknown (`cloud/reflection.py:173`, `cloud/collection.py:210`).
- [x] [Review][Patch][P2] Resolve and reconcile recorded AWS selectors before dispatch (`cloud/reflection.py:188`).
- [x] [Review][Patch][P2] Extract screened recorded tags as identity metadata (`cloud/reflection.py:250`).
- [x] [Review][Patch][P2] Treat literal keys in AWS tag maps as tags (`cloud/aws/projection.py:70`).
- [x] [Review][Patch][P2] Preserve every confirmed missing IAM action in collection diagnostics (`cloud/collection.py:203`).
- [x] [Review][Patch][P3] Reconcile the completion record and retain reproducible runtime verification commands (`docs/verification/live-environment-grounding/17-3/README.md:36`).

### Closeout review findings

- [x] [Review][Patch][P1] Screen private values consistently before emitting worker facts, including RDS tag lists and equivalent numeric forms (`cloud/aws/projection.py:75`, `cloud/aws/projection.py:266`).
- [x] [Review][Patch][P1] Apply snapshot address screening to IAM denial diagnostics (`cloud/collection.py:218`, `services/cloud_context_service.py:909`).
- [x] [Review][Patch][P2] Align actual-call accounting and the cancellation fence with SDK dispatch (`cloud/aws/client.py:435`).

See the [code review record](../../docs/verification/live-environment-grounding/17-3/code-review.md) for the evidence and acceptance criteria.

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
Codex with bounded native implementation and independent security review agents.

### Debug Log References
- Prerequisites: Stories17.1/17.2 merged; PR223 merge64ef0fa contains all nine resolved read-only review findings and independent final GO. No live AWS qualification claimed.
- Implementation branch: `feature/17-3-plan-directed-reflection`, based on current develop64ef0fa.

### Implementation Plan
- Execute packet3.1–3.3 sequentially in cloud/reflection.py using approved17.0 producer extraction and frozen17.2 request catalog. Never derive new requests from provider responses.
- Preserve existing snapshot digest/storage/auth-UOW contracts. Add a separate typed plan-aware collection outcome and optional budget metadata rather than changing retained snapshot-v1 bytes.
- Reuse the17.2 bounded reader/single-request SDK fences; add only immutable selected-field projection at its worker boundary as required for actual observations. Preserve constructor-only trusted account/region/session bindings and default-unavailable authorization.
- Apply fail-safe degradation through existing context-uncertainty logic with explicit severity/confidence floors. API/CLI changes remain additive budget serialization; operator enablement/flags and rich surfaces stay in their later stories.
- Keep fixture/fault-injection evidence separate from live-account qualification. No dependency installation or live reads are authorized or needed for this story; independently review before merge.
- Review follow-up keeps plan authority and private values in memory. Use one scheduler and frozen dispatch counters across regions. Supervise the existing authorized transaction through finalization and reserve time to retain timely partial facts. Keep confirmed permission details additive to snapshot-v1.

### Completion Notes List
- Implemented all seven packets: qualified recorded-prior extraction and pure-create success; immutable trusted-target/private-source manifests for25families/42capabilities; bounded static one-hop metadata; screened selected projection and actual SDK-call counters; existing uncertainty-policy floors; optional budget-only API/CLI/agent output. Reused the17.2 scheduler/fences and snapshot-v1 retention/admission contracts; no dependency installation or live reads.
- Independent security review found and verified repairs for twoP1 credential-echo paths (lowercase ECS tag pairs and Lambda dynamic tag names). Added failing-then-passing worker/collector/retained-readback regressions. Final review passed this offline slice with no remainingP1/P2. Legacy SimpleNamespace agent serialization was also repaired; existing compatibility batch138tests/67subtests passed.
- Final validation: root2,314tests (3existing skips); full localCI3,839tests across12shards (3existing skips), plus172isolation tests/skills/prompt-injection checks; exactAPI/CLI/infra pytest838passed (1skip),2,474subtests. Network-disabled rebuilt Python3.11.17 harness passed71new storytests and16SDKtests (14legacy+2native selected-model tests). Repo-wideRufflint/format701files, Bandit zero findings and Python3.10 grammar passed.
- Docker build passed:29a37dc08877e952d257f24eaee9fe084c4532f3eae9e2b8999c8d9e534bce2c. Non-root default image remainsSDK/Node-free; purecreate issueszero requests; AWS registry remainsunavailable until trusted host composition. Fresh container healthHTTP200 passed with networking disabled. No rebuilt-production/live AWS/egress qualification is claimed beyond the documented offline runtime proof.
- Operational report metadata does not create an unheld snapshot evidence reference. Actual collection outcomes remain available at trusted internal ports; user-facing enablement/flags and production authority/profile composition stay in laterstories. UI validation not applicable. Qualified config/model sources, dependency locks, report-v2 and agent-v1 versions remain unchanged.
- Review follow-up excludes unchanged no-ops, handles recorded/deposed identity and tag metadata, reconciles region and queue selectors, and leaves unsupported identities unknown. The collector rejects broader manifests before constructing an SDK client.
- One scheduler applies regional backoff, concurrency and counters. The service preserves timely partial facts, returns a diagnostic budget when no safe retained result is available in time, and fences commits that start after cancellation or expiry.
- Plan-known private values are screened in SDK projection and retained readback. Typed capability-level IAM denials are available on the internal outcome with account masking. The retained snapshot version and public budget schema remain compatible.
- Follow-up validation passed with 166 focused tests and 339 subtests, 838 API/CLI/infra tests and 2,474 subtests (1 skip), and 2,331 root tests (3 skips). Local CI passed all 12 shards with 3,859 tests run and 3 skips, plus 189 SDK-free isolation tests, skill scenarios, and prompt-injection tests.
- The rebuilt network-disabled Python 3.11.17 image passed 162 tests and HTTP 200 health. Ruff lint and repo-wide format, Python 3.10 grammar, and the scoped Bandit scan passed. Initial broad-run recovery failures during host sleep passed in isolation and on the full retries. The optional pinned-SDK suite retains its initial evidence.
- See the [verification packet](../../docs/verification/live-environment-grounding/17-3/README.md) for the checked-in reproduction commands. UI validation not applicable.
- Closeout fixes recognize RDS tag lists and use shared numeric screening before worker fact publication. Collector and service diagnostics use the exact screened snapshot addresses with independent approved-scope validation. Native Botocore admits operations inside the existing allow-list fence and rechecks interruption immediately before transport.
- Closeout validation passed 173 focused tests and 347 subtests, 2,336 root tests with 3 skips, 3,866 local CI tests across 12 shards with 3 skips, and 838 exact API/CLI/infra tests with one skip. The rebuilt Python 3.11.17 image passed 169 SDK-free tests and HTTP 200 health, plus 17 hash-pinned Botocore SDK tests in a separate network-disabled run. Ruff, Bandit and Python 3.10 grammar passed. Independent closeout review passed against the tested runtime source hashes.

### File List
- `_bmad-output/implementation-artifacts/17-3-plan-directed-reflection-and-bounded-collection.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `analysis/cloud_grounding.py`
- `api/schemas.py`
- `cloud/aws/client.py`
- `cloud/aws/projection.py`
- `cloud/aws/session.py`
- `cloud/collection.py`
- `cloud/redaction.py`
- `cloud/reflection.py`
- `docs/live-environment-grounding/README.md`
- `docs/verification/live-environment-grounding/17-3/README.md`
- `docs/verification/live-environment-grounding/17-3/code-review.md`
- `docs/verification/live-environment-grounding/17-3/security-review.md`
- `docs/verification/live-environment-grounding/17-3/test_selected_sdk.py`
- `docs/verification/live-environment-grounding/17-2/test_sdk.py`
- `services/agent_interface_service.py`
- `services/analysis_service.py`
- `services/cloud_context_service.py`
- `tests/test_analysis/test_cloud_grounding.py`
- `tests/test_api/test_cloud_collection_budget.py`
- `tests/test_cli/test_cloud_collection_budget.py`
- `tests/test_cloud/aws/test_projection.py`
- `tests/test_cloud/aws/test_dispatch.py`
- `tests/test_cloud/conformance/test_reflection_scope.py`
- `tests/test_cloud/test_collection.py`
- `tests/test_cloud/test_reflection.py`
- `tests/test_cloud/test_reflection_expansion.py`
- `tests/test_cloud/test_reflection_manifest.py`
- `tests/test_services/test_analysis_cloud_grounding.py`
- `tests/test_services/test_cloud_plan_collection.py`

## Change Log

- 2026-11-18: Implemented packets3.1–3.7 after merged prerequisites. Added plan-bound collection, fail-safe degradation and additive budget serialization; resolved independent security/compatibility findings and passed fresh full-suite/runtime checks. Story moved to review for the scoped offline primitive implementation.
- 2026-11-19: BMad Code Review requested changes. Story and sprint tracking returned to in-progress with eleven review action items for plan scope, screening, collection limits, and acceptance evidence.
- 2026-11-19: Closed all 11 review action items after offline regression coverage and full verification. Story moved to review.
- 2026-11-20: Independent closeout review requested changes on screening and dispatch. Story returned to in-progress.
- 2026-11-20: Fixed and verified all three closeout findings. Story moved back to review.
- 2026-11-20: Independent closeout review approved the offline slice. Story moved to done for the PR into develop.
