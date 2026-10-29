# Story 16.8: Evidence Bound Decisions and Freshness

Status: review
Preparation: refined
Release: v1.5.0

## Story

As a reviewer, I want to decide only against current immutable evidence and the exact action and policy packet, so that stale, partial or unrelated approval cannot authorize handoff.

## Entry gates and slice boundary

- Release priority: P0 feature work for v1.5.0. **Blocked for implementation** until Story 16.0 has recorded public RFC/CODEOWNERS acceptance, executable identity/fencing/isolation/custody/receiver qualification and final interface decisions; planning adoption alone is not authorization evidence.
- Hard earlier dependencies: **16.2, 16.6**, accepted and verified before advancing this story. These dependency results are currently unresolved; refined preparation does not mean ready-for-dev. No prior implementation learning is available for the new Epic 16 story set.
- Promote only after contract freeze, earlier dependency evidence, bounded task ownership/re-estimation and independent story review. Preserve IDs and backlog status; no feature/release implementation is claimed here.

## Acceptance Criteria

1. **AC1:** Given an eligible preflight and verified reviewer, when a decision request is created, then a finite durable deadline and the complete versioned binding tuple are persisted, and restart never approves it automatically.
2. **AC2:** Given a DAG with an alternate, skipped, failed or unrelated branch, when handoff eligibility is evaluated, then every executable path requires its own successful mandatory evidence analysis, policy gate and matching human decision; ancestry alone is insufficient.
3. **AC3:** Given mutation of any revision/source/input/scope/report/artifact/unit/policy/target/payload/custody/epoch field, expiration or membership revocation, when a decision is made or eligibility rechecked, then it invalidates with typed reasons and requires recollection/reanalysis/reapproval as applicable.
4. **AC4:** Given stale, missing, unsupported or incomplete mandatory evidence, when policy evaluates eligibility, then it records confidence limitations/context TODOs and denies handoff; optional degraded narrative alone preserves deterministic evidence.
5. **AC5:** Given canonical go/caution/no-go reports, when configured workflow policy evaluates them, then advisory should_block=False remains unchanged and insufficient_context is a separate typed flag; unknown vocabulary fails closed.
6. **AC6:** Given a clock at the earliest evidence/custody/approval deadline, when decision, dispatch or receiver consumption eligibility is checked, then it fails closed; default evidence TTL is 60 minutes or an audited stricter policy, and extending approval never extends evidence validity.

### Requirement Traceability

Coverage intent: Delta over the v1.4.0 baseline. These exact mapped requirements are acceptance obligations; mapping is not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| IAU15-FR-013 | Require every executable path to a handoff to pass its mandatory successful evidence analysis, policy gate and matching approval; skipped/failed or unrelated ancestors do not qualify. | Wrong-branch, skipped-ancestor and alternate-path tests |
| IAU15-FR-028 | Expose missing/partial/stale collection as confidence limitations and context TODOs; failed or incomplete mandatory collection cannot make approval eligible. | Partial/error/stale collection eligibility tests |
| IAU15-FR-030 | Pause for a human decision durably with a finite deadline and never auto-approve on restart, expiry or missing reviewer. | Restart/expiry/missing-reviewer decision tests |
| IAU15-FR-031 | Bind approval to authorization kind, revision, source identity and required exact-plan commit, project/workspace/environment, reports, artifact and unit-plan digests, policy version, exact target and payload digest. | Independent mutation of every decision-tuple field |
| IAU15-FR-032 | Enforce evidence freshness at decision, dispatch and receiver consumption; default collection TTL is 60 minutes unless an audited stricter policy applies. | Clock/TTL boundary and delayed-consume tests |
| IAU15-FR-033 | Evaluate explicit workflow policy separately from advisory report semantics, preserving canonical should_block=False and using existing policy-adapter field meanings where compatible. | Gate decision versus advisory report contract tests |
| IAU15-FR-035 | Invalidate eligibility when evidence, revision, source, scope, target, policy, membership or custody changes, expires or is superseded; no emergency bypass or delegated approval in P0. | Revocation/supersession/custody-loss and bypass-denial matrix |

## Tasks / Subtasks and bounded ownership

- [x] **Packet 1 — Domain owner: immutable binding and clock (AC 1,3,6).** Owned output: `infra_automation/decisions.py and typed contracts (planned), models/tables.py/repositories and current-head migration only for decision snapshots`.
  - [x] Persist exact versioned tuple, finite deadline, requester/reviewer and decision generations; use injected UTC clock and frozen Pydantic values; mutate every field independently.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 2 — Domain owner: all-path gate (AC 2,4).** Owned output: `infra_automation/workflow_validation.py from 16.3 (reuse) and infra_automation/approval_eligibility.py for runtime evidence/policy checks (planned)`.
  - [x] Traverse reachable executable handoff paths with scoped seeded target/custody ports; prove skipped/failed/wrong-branch analysis and decision cannot authorize another target.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 3 — Service/API owner: policy and durable decision (AC 1,3–6).** Owned output: `services/infra_automation_service.py, api/routes/infra_automation.py (planned), services/policy_adapter_service.py reuse`.
  - [x] Revalidate live membership and hard floors transactionally at decision; typed conflicts/expiry/insufficient-context reasons; explicit rejection versus stopped_by_gate; no bypass endpoints.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 4 — Test/documentation owner: adversarial matrix (AC 1–6).** Owned output: `tests/test_infra_automation, tests/test_api and docs/infra-automation (planned)`.
  - [x] Publish tuple mutation, restart, concurrent decision, expiry boundary, supersession, missing-custody, partial evidence and all-path corpus; verify canonical report bytes/hash unchanged.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.

Each packet is a bounded review unit under this stable story ID; split large packets after 16.0 estimation instead of silently broadening scope. One story branch follows Git Flow; coordinate shared-file edits and do not revert other work.

## Dev Notes

Reuse Story 16.3's static schema/reference/DAG validator; do not create a competing generic validation module or repeat its graph semantics. The separate runtime eligibility helper checks the current immutable decision/evidence/policy/authority tuple and calls the shared validator where necessary. The distinction is static definition validity versus current runtime action eligibility.


- Exact binding: authorization_kind, revision/input digests, repository and immutable IaC commit where required, project/workspace/environment, target/receiver, report bytes/digest/schema, artifact/raw-local/unit digests, redaction version, policy version/digest/result, custody handle, exact payload/digest, deadlines and authorization/restore epochs.
- Distinguish upload-only advisory source variant from collected exact_plan. Unavailable upload repository provenance is a limitation, never a fabricated SHA/custody. advisory_request approval cannot authorize apply. A reason cannot bypass hard gate floors.
- Reuse services/policy_adapter_output_contract.py frozen/extra-forbid conventions and services/policy_adapter_service.py interpretation; preserve existing policy-adapter fields rather than repurposing canonical report should_block. No invented no_go or insufficient_context recommendation enum.
- Seed scoped typed target/custody bindings to qualify this slice. Production target registry/grants/receiver belong to 16.10/16.11; unavailable/ineligible targets remain blocked. These ports do not qualify real collection.
- Pending decisions are persistent, not in-memory or background tasks; use CAS/version and unique active generation established earlier. No delegated/emergency approval or unattended decision.

### Project Structure Notes

- Planned modules are additions under the established Python/service/API/repository and React boundaries, not present-day implementation claims. Reuse `api/errors.py` ApiRoute/ApiError, `api/schemas.py`, `models/database.py`, `models/tables.py`, repositories and `migrations/versions/`; inspect head before allocation.
- Introduce only entities necessary for this slice; never precreate all automation tables. Keep deterministic findings in the shared analysis core, optional AI downstream and privileged execution outside FastAPI. No new dependencies without a recorded approved decision.
- Interface names/resources are design obligations pending 16.0 freeze, not permission to invent final route/schema contracts. Add docs and tests with behavior; do not defer slice coverage to 16.19.

## Required implementation verification

- [x] Register new `tests/test_infra_automation` directories in `scripts/ci-local.sh` and affected GitHub discovery/shards; root discovery alone skips non-package test directories.
- [x] For every Pydantic/schema/dataclass/constructor change, use repository-wide `rg` searches for direct instantiations/fixtures and update all consumers, including CLI/agent/action/report compatibility where affected.
- [x] Run `./.venv/bin/python -m unittest discover -q`, story-focused tests and exactly `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` for affected API/CLI/infra contracts.
- [x] Run `./.venv/bin/ruff check .`, **`./.venv/bin/ruff format --check .` repo-wide**, `bash scripts/ci-local.sh` and `git diff --check`; add applicable static/security/type checks. Record commands and actual results rather than assumed passes.
- [x] UI validation not applicable only if no rendered surface changes; if a UI surface is touched, use the complete composed-app Playwright/keyboard/axe/screenshot loop required by project context before review.

## References

- [Canonical feature PRD](../planning-artifacts/prd-infra-automation.md), [exact requirement registry](../planning-artifacts/infra-automation-requirement-dispositions.json) and [Epic 16](../planning-artifacts/epics.md).
- [Architecture §25](../planning-artifacts/architecture.md#25-v150-infrastructure-automation-architecture-amendment), especially slice qualification §25.12; [mandatory project context](../project-context.md).
- [Readiness gates IR-01–IR-06](../planning-artifacts/implementation-readiness-report-2026-10-07-infra-automation-v1.5.0.md) and [release sequencing](../planning-artifacts/infra-automation-v1.5.0-release-plan.md).
- [Feature UX contract](../../docs/design/infra-automation-ux.md), [UX authority](../planning-artifacts/ux-design-specification.md), [v3 visual authority](../../docs/design/deploywhisper-redesign-v3.jsx) and [RFC 0001](../../docs/rfcs/0001-infra-automation-preflight-and-handoff.md).

## Dev Agent Record

### Agent Model Used

Codex (GPT-6), with independent native agents for bounded domain, eligibility and service work.

### Implementation Plan

1. Persist closed immutable version-1 decision tuples and exact report export bytes through migration034, durable generations and CAS transitions.
2. Reuse workflow-v2 static validation and the existing policy adapter for typed current evidence, own-decision ancestry and full handoff ancestry checks.
3. Derive authority, report/source lineage, policy and deadlines from durable state in one verified human transaction. Use unavailable-by-default scoped target/custody material ports.
4. Recheck latest receipts, reviewer generations, exact evidence and earliest deadlines before dispatch/consumption; preserve historical snapshots and advisory report semantics.
5. Exercise mutation/restart/race/revocation/expiry/graph/API matrices, independent review, actual app startup and repository validation.

### Debug Log References

Entry assessment: accepted dependencies verified against current sprint tracker and frozen contracts; independent reviewer found no unresolved product/interface blocker.

Verification logs for this execution are stored locally under `/tmp/story16-8-*`; final command results are recorded below when checks complete. Actual application startup health returned 200; approval GET/decision POST operations are present in OpenAPI. Production runner/receiver, Compose/browser and load qualification are outside this backend slice; no such result is claimed.

### Completion Notes List

- 2026-10-29 entry reassessment: current sprint records Stories 16.0–16.7 done. Original unresolved-dependency preparation notes are superseded by accepted dependency evidence. Independent native reviewer confirmed the frozen decision/export/route contracts settle the owned implementation choices; no new product or dependency authorization is needed.
- Bounded execution: domain/persistence owner handles Packet 1 (large); eligibility owner handles Packet 2 (large); service/API owner handles Packet 3 (large); root integrates Packet 4 adversarial tests/docs and verification (large). Existing WP7 estimate remains planning guidance, not elapsed delivery evidence. Target/custody ports are scoped fixtures; no collector or receiver production support is claimed.

- Prepared entry-gate text is historical: accepted dependency evidence and the independent 2026-10-29 readiness assessment opened this bounded implementation. Stable IDs and all six ACs are preserved.
- UI validation not applicable: backend behavior and generated API declarations only; no rendered surface or browser interaction changed. Generated TypeScript declarations pass `npm run ui:typecheck`.
- Independent native reviews (`readiness_review`, `eligibility`, `final_review`) identified and closed lineage, strict response conversion, current reviewer generations, pagination, supersession and serial/indirect human prerequisite defects. All 59 final focused tests and 140 subtests pass; full verification and the known worker teardown retry are recorded in `docs/verification/infra-automation/16-8/results.md`.

- Final validation: `./.venv/bin/python -m unittest discover -q` passed 1,194 tests (2 skips). Final affected pytest shard passed 688 tests /2,274 subtests (1 opt-in skip). Final focused matrix passed 59 tests /140 subtests. Serial `LLM_API_BASE=http://127.0.0.1:1 bash scripts/ci-local.sh` passed all 2,670 directory tests after the documented existing worker teardown retry.
- Ruff lint, repo-wide Ruff formatting (438 files), scoped mypy/Bandit, compile checks, actual app health and generated API typecheck passed. Repo-wide mypy retains 312 findings versus 314 on the original archived baseline, with no introduced file/message findings.
- Implementation is committed as `bc05965` on the compliant story branch. Remaining boundaries: production target/custody/collector/receiver support belongs to later stories; database/host administrators remain trusted. Formal BMad code-review and push/PR closure are next; this dev-story does not claim release qualification.

### File List

- `README.md`
- `_bmad-output/implementation-artifacts/16-8-evidence-bound-decisions-and-freshness.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/planning-artifacts/epics.md`
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-29-story-16-8.md`
- `_bmad-output/project-context.md`
- `api/routes/infra_automation.py`
- `api/schemas.py`
- `docs/infra-automation/decisions.md`
- `docs/verification/infra-automation/16-8/results.md`
- `frontend/src/api/schema.d.ts`
- `infra_automation/approval_eligibility.py`
- `infra_automation/decisions.py`
- `migrations/versions/034_add_infra_decisions.py`
- `models/database.py`
- `models/repositories/infra_automation_decisions.py`
- `models/tables.py`
- `services/infra_automation_decisions.py`
- `tests/test_api/test_infra_automation_decisions.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_identity_migration.py`
- `tests/test_infra/test_infra_automation_engine_migration.py`
- `tests/test_infra/test_infra_automation_workflow_migration.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_infra/test_project_membership_migration.py`
- `tests/test_infra_automation/test_approval_eligibility.py`
- `tests/test_infra_automation/test_decision_binding_adversarial.py`
- `tests/test_infra_automation/test_decision_service.py`
- `tests/test_infra_automation/test_decisions.py`
- `tests/test_infra_automation/test_preflight_repository.py`

### Change Log

- 2026-10-29: Implemented evidence-bound decision snapshots, migration034,
  exact-path runtime policy/freshness checks, human decision API/service,
  conservative historical projections and live dispatch/consume rechecks.
  Reused existing static validation, policy adapter and report serialization;
  no dependencies or remote execution were added. Independent review fixes
  cover exact lineage, reviewer generations, pagination, supersession,
  serial/indirect human prerequisites and strict HTTP response conversion.
