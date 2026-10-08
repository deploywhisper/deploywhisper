# Story 16.10: Registered Targets, Outbox, Grants and Locks

Status: backlog
Preparation: refined
Release: v1.5.0

## Story

As a platform administrator, I want to register exact targets and retain durable locked handoff intents, so that destination changes, replay and uncertain work cannot silently release another action.

## Entry gates and slice boundary

- Release priority: P0 feature work for v1.5.0. **Blocked for implementation** until Story 16.0 has recorded public RFC/CODEOWNERS acceptance, executable identity/fencing/isolation/custody/receiver qualification and final interface decisions; planning adoption alone is not authorization evidence.
- Hard earlier dependencies: **16.8**, accepted and verified before advancing this story. These dependency results are currently unresolved; refined preparation does not mean ready-for-dev. No prior implementation learning is available for the new Epic 16 story set.
- Promote only after contract freeze, earlier dependency evidence, bounded task ownership/re-estimation and independent story review. Preserve IDs and backlog status; no feature/release implementation is claimed here.

## Acceptance Criteria

1. **AC1:** Given registered aliases across projects, when a handoff-enabled run starts before collection, then all aliases resolve to one canonical target lock and overlapping requests cannot obtain it.
2. **AC2:** Given an eligible immutable decision, when authorization prepares dispatch, then one short transaction revalidates live identity/membership/feature/target/restore epochs, policy/evidence/custody/deadlines and writes exact payload, stable operation, grant and outbox before network effects.
3. **AC3:** Given a used idempotency key with identical payload, when retried, then the same operation returns; changed payload conflicts; a grant with changed binding/replay/expiry/wrong identity cannot consume authority.
4. **AC4:** Given registered destination DNS rebinding, redirects, IPv4/IPv6 metadata/loopback/private addresses or alias changes, when a connection is attempted, then connection-time validation denies it except an explicit audited administrator-owned internal-origin exception.
5. **AC5:** Given disable, revocation or restore, when new starts, claims, dispatch or outstanding-grant consumption race, then no new authority is exercised; accepted work remains readable/reconcilable and cannot gain a replacement grant.
6. **AC6:** Given unknown external work, cancellation or lease expiry, when unlock/retry is requested, then the lock remains until verified terminal resolution or audited privileged break acknowledging uncertainty without new authorization.

### Requirement Traceability

Coverage intent: Delta over the v1.4.0 baseline. These exact mapped requirements are acceptance obligations; mapping is not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| IAU15-FR-017 | Disable, revoke or restore epoch changes must invalidate unconsumed grants and prevent new run starts, collection claims, dispatch or grant consumption while preserving read and reconciliation for accepted external work. | Disable/revoke/restore-before-dispatch-or-consume race matrix |
| IAU15-FR-031 | Bind approval to authorization kind, revision, source identity and required exact-plan commit, project/workspace/environment, reports, artifact and unit-plan digests, policy version, exact target and payload digest. | Independent mutation of every decision-tuple field |
| IAU15-FR-035 | Invalidate eligibility when evidence, revision, source, scope, target, policy, membership or custody changes, expires or is superseded; no emergency bypass or delegated approval in P0. | Revocation/supersession/custody-loss and bypass-denial matrix |
| IAU15-FR-036 | Register outbound GitHub destinations with administrator-controlled host policy; revalidate DNS/connection addresses and redirects, blocking metadata/loopback/private targets except explicit audited internal-host exceptions. | IPv4/IPv6/DNS/redirect SSRF corpus |
| IAU15-FR-037 | Atomically persist the approved outbound intent and exact payload before network effects, with a stable receiver operation identity. | Transaction/crash-before-send and payload-tamper tests |
| IAU15-FR-038 | Issue one-use scoped receiver grants bound to the decision tuple, operation, expiry and live epoch; reject duplicate/replayed or altered consumption. | Grant replay/expiry/epoch/source/digest tests |
| IAU15-FR-042 | Canonicalize target lock identities across aliases and retain locks during unknown external work until verified resolution or an audited operator break that does not mint a new authorization. | Alias collision/lock expiry/unknown-work/break tests |
| IAU15-NFR-001 | The declared crash/race corpus must lose no committed run/decision state and produce no unauthorized or duplicate receiver action, including stale attempts, unknown delivery and restore epochs. | Published fault-injection results at every persisted boundary |

## Tasks / Subtasks and bounded ownership

- [ ] **Packet 1 — Domain/persistence owner: registry and locks (AC 1,4,6).** Owned output: `infra_automation/targets.py, models/repositories and current-head migration (planned)`.
  - [ ] Persist canonical identity/aliases and administrator host policy; acquire unique target lock before handoff-enabled collection, collision tests across projects, audited target changes.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 2 — Domain/persistence owner: operation/outbox/grant (AC 2,3).** Owned output: `infra_automation/handoff.py and repositories (planned)`.
  - [ ] Atomic exact intent, request digest/idempotency, stable operation and hashed one-use grant; consumption CAS and binding verification; crash-before-commit/send, duplicate and changed-payload tests.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 3 — Security/service owner: live admission and SSRF (AC 2–5).** Owned output: `services/infra_automation_service.py, typed routes and fixed outbound transport`.
  - [ ] Enforce live feature/epoch/membership/custody at dispatch and online consume; connection/DNS/redirect checks with no workflow-supplied arbitrary URL; disable/revoke/restore race corpus.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 4 — Test/documentation owner: recovery qualification (AC 1–6).** Owned output: `tests/test_infra_automation, tests/test_api, docs/infra-automation`.
  - [ ] Fault-inject persisted boundaries, unknown-work retention and explicit audited break; publish grant secret corpus, SSRF corpus and target-lock operating contract.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.

Each packet is a bounded review unit under this stable story ID; split large packets after 16.0 estimation instead of silently broadening scope. One story branch follows Git Flow; coordinate shared-file edits and do not revert other work.

## Dev Notes

### Derived settings UX ownership

This earlier slice owns the feature/configuration or registered-target API and its permission/epoch/validation contracts. It does not depend on a later settings screen to complete: use service/API tests now. Story 16.18 Packet 18.6 explicitly owns the integrated `/settings` browser controls and composed acceptance using these earlier APIs; any backend-for-UI support remains additive in its own labeled PR.



- Only registry/lock/outbox/grant entities needed here may migrate; inspect current Alembic head rather than inventing a revision number. Reuse models/database.py session and existing repositories; network effects never occur inside a SQLite transaction.
- Contracts include registered canonical target/receiver identity, aliases, allowlisted origin; stable operation/request digest; exact action binding; grant verifier, scope, expiry/live epoch and consumption receipt. 16.0 freezes wire names/routes/errors; no general webhook adapter.
- Acquire target lock before collection when handoff is intended, not only at dispatch. Alias mutation cannot evade locks; local cancel/timeout is not proof the remote pipeline stopped. Lock break does not produce a fresh approval or authorization.
- Use a scoped receiver-consumer test double to qualify online admission here; 16.11 owns real receiver durability/network proof. This slice must prove denied outstanding grants after disable/revoke/restore, not merely invalidate future token creation.
- Credentials use environment-backed references in config.py. Plaintext grant values never enter persistent DB/logs/audit. Raw binary saved plans/state never enter the server. Upload advisory grants cannot authorize apply.
- If target settings UI changes, separate backend behavior PR and run the composed UI gate below; otherwise record UI validation not applicable. Reuse existing GitHub URL validation cautiously: it is not complete DNS/connection SSRF proof.

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
