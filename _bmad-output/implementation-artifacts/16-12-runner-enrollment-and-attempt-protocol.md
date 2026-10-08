# Story 16.12: Runner Enrollment and Attempt Protocol

Status: backlog
Preparation: refined
Release: v1.5.0

## Story

As a runner operator, I want to enroll and revoke an attempt-scoped outbound collection agent, so that only the current scoped agent can act on its task.

## Entry gates and slice boundary

- Release priority: P0 feature work for v1.5.0. **Blocked for implementation** until Story 16.0 has recorded public RFC/CODEOWNERS acceptance, executable identity/fencing/isolation/custody/receiver qualification and final interface decisions; planning adoption alone is not authorization evidence.
- Hard earlier dependencies: **16.2, 16.5**, accepted and verified before advancing this story. These dependency results are currently unresolved; refined preparation does not mean ready-for-dev. No prior implementation learning is available for the new Epic 16 story set.
- Promote only after contract freeze, earlier dependency evidence, bounded task ownership/re-estimation and independent story review. Preserve IDs and backlog status; no feature/release implementation is claimed here.

## Acceptance Criteria

1. **AC1:** Given an authenticated project administrator, when a bounded one-use enrollment credential is redeemed over supported HTTPS, then project-scoped expiring runner credentials are issued once, hashed at rest and protected from logs/audit; replay, rotation or revocation cannot reuse old authority.
2. **AC2:** Given wrong audience/project/runner/run/step/attempt/fence or expired lease, when claim/heartbeat/log/upload/complete occurs, then it is denied and cannot advance current work; concurrent claim/restart leaves one fenced owner.
3. **AC3:** Given required tag/tool/profile/version selection, when no eligible runner exists, then no silent fallback occurs and a clear denial or explicit finite wait/timeout is persisted.
4. **AC4:** Given disable/revoke/restore or expired tokens, when queued work is claimed or stale results arrive, then no new claims/results are accepted while authorized history/reconciliation remains accessible.
5. **AC5:** Given compatible runners, when scoped health is read, then last-seen/version/protocol/current task and status are screened and authorized; connectivity alone never certifies execution isolation.
6. **AC6:** Given the named 20-runner reference workload, when 1,000 claims are measured, then timestamped p95 enqueue-to-claim is below 2 seconds or qualification reports failure without advertising capacity.

### Requirement Traceability

Coverage intent: Delta over the v1.4.0 baseline. These exact mapped requirements are acceptance obligations; mapping is not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| IAU15-FR-019 | Fence leader/task attempts so only the current owner may heartbeat, log, upload or complete a task. | Overlapping leader and stale-attempt rejection tests |
| IAU15-FR-044 | Enroll runners using one-use tokens and project-scoped expiring credentials with rotation/revocation and outbound HTTPS protocol-version negotiation. | Enrollment replay/rotation/revocation/TLS/version tests |
| IAU15-FR-045 | Bind every task claim, heartbeat, log, upload and completion to the authorized runner, project, current attempt and live lease. | Wrong-runner/project/expired-lease matrix |
| IAU15-FR-046 | Route collection to eligible runner tags with no silent fallback; fail clearly when none qualify or enforce an explicit finite wait, and expose last-seen/version/task health. | No-runner/tag-mismatch/wait-timeout and health tests |
| IAU15-FR-059 | Record append-only application audit events with verified principal/type, role, scope, target, reason, time and before/after digests; expose scoped UI/JSON export without raw artifacts/secrets and document DB-admin trust limits. | Audit event coverage/export authorization and secret corpus |
| IAU15-NFR-002 | The declared principal × role × project/workspace × object/action matrix must produce zero cross-scope reads or unauthorized mutations. | Published complete authorization matrix results |
| IAU15-NFR-006 | Enqueue-to-claim latency must have p95 <2 seconds with 20 online compatible runners under the reference workload. | Timestamped 1,000-claim runner benchmark |

## Tasks / Subtasks and bounded ownership

- [ ] **Packet 1 — Identity/API owner: enrollment lifecycle (AC 1,4).** Owned output: `infra_automation/runner/protocol.py, runner routes and scoped credential repositories (planned)`.
  - [ ] One-use enrollment, audience/version negotiation, hashes/expiry/rotate/revoke, HTTPS validation and secret-free error/audit corpus.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 2 — Domain owner: fenced attempt operations (AC 2,4).** Owned output: `infra_automation/runner/claims.py (planned), earlier coordinator/repositories`.
  - [ ] Bind all five task operations to runner/project/run/step/attempt/fence/live lease and epoch in short transactions; replay and overlapping-owner matrix.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 3 — Runner/service owner: outbound agent and routing (AC 3,5).** Owned output: `infra_automation/runner/client.py and CLI entrypoint (planned), config.py`.
  - [ ] Bound HTTPS polling/backoff; enforce tags/tool/profile/version, finite no-runner wait and failure; scoped health endpoint without commands or credentials.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 4 — Test/documentation owner: authorization and benchmark (AC 1–6).** Owned output: `tests/test_infra_automation, tests/test_api/test_cli/test_infra, docs/infra-automation`.
  - [ ] Publish full principal×role×scope×action matrix, stale attempt races and reproducible 1,000-claim timing workload with versions/hardware and results.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.

Each packet is a bounded review unit under this stable story ID; split large packets after 16.0 estimation instead of silently broadening scope. One story branch follows Git Flow; coordinate shared-file edits and do not revert other work.

## Dev Notes

- runner_protocol_version 1, enrollment/credential audience, typed claim/task/heartbeat/log-cursor/artifact-upload/completion envelopes and redacted error/correlation shapes must freeze in 16.0. Never let server tasks carry arbitrary commands or infrastructure secret values.
- Add only runner enrollment/credential/attempt lease data required by this slice; reuse 16.5 run/attempt state and audit. Store token verifiers, not reusable plaintext. Credential reveal is transient once; future 16.15 UI owns enrollment screen and cannot make this backend story depend forward.
- Every request rechecks all binding dimensions and live fence/lease; authenticated runner identity alone is insufficient. No runner can publish/approve or obtain a human session. Existing api/dependencies.py is only a placeholder in baseline, not a verified authentication implementation.
- Use compatible runner/test client doubles to qualify protocol and 20-online-runner timing; production isolation is 16.13 and real collection is 16.14. Hash/authentication proves sender, not truthful collected evidence.
- Default off and restore epochs prevent new collection claims even for previously valid credentials; bounded upload is finalized atomically only after digest/attempt validation. Incomplete/truncated upload cannot qualify mandatory evidence.

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
