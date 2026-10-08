# Story 16.8: Evidence Bound Decisions and Freshness

Status: backlog
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

- [ ] **Packet 1 — Domain owner: immutable binding and clock (AC 1,3,6).** Owned output: `infra_automation/decisions.py and typed contracts (planned), models/tables.py/repositories and current-head migration only for decision snapshots`.
  - [ ] Persist exact versioned tuple, finite deadline, requester/reviewer and decision generations; use injected UTC clock and frozen Pydantic values; mutate every field independently.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 2 — Domain owner: all-path gate (AC 2,4).** Owned output: `infra_automation/workflow_validation.py from 16.3 (reuse) and infra_automation/approval_eligibility.py for runtime evidence/policy checks (planned)`.
  - [ ] Traverse reachable executable handoff paths with scoped seeded target/custody ports; prove skipped/failed/wrong-branch analysis and decision cannot authorize another target.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 3 — Service/API owner: policy and durable decision (AC 1,3–6).** Owned output: `services/infra_automation_service.py, api/routes/infra_automation.py (planned), services/policy_adapter_service.py reuse`.
  - [ ] Revalidate live membership and hard floors transactionally at decision; typed conflicts/expiry/insufficient-context reasons; explicit rejection versus stopped_by_gate; no bypass endpoints.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 4 — Test/documentation owner: adversarial matrix (AC 1–6).** Owned output: `tests/test_infra_automation, tests/test_api and docs/infra-automation (planned)`.
  - [ ] Publish tuple mutation, restart, concurrent decision, expiry boundary, supersession, missing-custody, partial evidence and all-path corpus; verify canonical report bytes/hash unchanged.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.

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

- [ ] Register new `tests/test_infra_automation` directories in `scripts/ci-local.sh` and affected GitHub discovery/shards; root discovery alone skips non-package test directories.
- [ ] For every Pydantic/schema/dataclass/constructor change, use repository-wide `rg` searches for direct instantiations/fixtures and update all consumers, including CLI/agent/action/report compatibility where affected.
- [ ] Run `./.venv/bin/python -m unittest discover -q`, story-focused tests and exactly `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` for affected API/CLI/infra contracts.
- [ ] Run `./.venv/bin/ruff check .`, **`./.venv/bin/ruff format --check .` repo-wide**, `bash scripts/ci-local.sh` and `git diff --check`; add applicable static/security/type checks. Record commands and actual results rather than assumed passes.
- [ ] UI validation not applicable only if no rendered surface changes; if a UI surface is touched, use the complete composed-app Playwright/keyboard/axe/screenshot loop required by project context before review.

## References

- [Canonical feature PRD](../planning-artifacts/prd-infra-automation.md), [exact requirement registry](../planning-artifacts/infra-automation-requirement-dispositions.json) and [Epic 16](../planning-artifacts/epics.md).
- [Architecture §25](../planning-artifacts/architecture.md#25-v150-infrastructure-automation-architecture-amendment), especially slice qualification §25.12; [mandatory project context](../project-context.md).
- [Readiness gates IR-01–IR-06](../planning-artifacts/implementation-readiness-report-2026-10-07-infra-automation-v1.5.0.md) and [release sequencing](../planning-artifacts/infra-automation-v1.5.0-release-plan.md).
- [Feature UX contract](../../docs/design/infra-automation-ux.md), [UX authority](../planning-artifacts/ux-design-specification.md), [v3 visual authority](../../docs/design/deploywhisper-redesign-v3.jsx) and [RFC 0001](../../docs/rfcs/0001-infra-automation-preflight-and-handoff.md).

## Dev Agent Record

### Agent Model Used

Documentation preparation only; implementation agent/version to be recorded when gates open.

### Debug Log References

Not executed: application, runner, receiver, Compose, browser, fault/load or production qualification. This preparation records obligations, not passing results.

### Completion Notes List

- Preparation: refined. Status remains backlog. All implementation tasks unchecked; Story 16.0 and earlier dependency acceptance remain unresolved.
- UI validation: Not executed; applicability to be recorded against the actual change.
- Independent review, actual command results, residual risks and release qualification evidence must be recorded during implementation.

### File List

This story specification only; planned ownership paths above are not implemented files.
