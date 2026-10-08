# Story 16.13: Isolated Runner Execution Profile

Status: backlog
Preparation: refined
Release: v1.5.0

## Story

As an operator, I want to collect infrastructure evidence inside a qualified disposable execution profile, so that repository and provider code cannot silently cross the approved host and credential boundary.

## Entry gates and slice boundary

- Release priority: P0 feature work for v1.5.0. **Blocked for implementation** until Story 16.0 has recorded public RFC/CODEOWNERS acceptance, executable identity/fencing/isolation/custody/receiver qualification and final interface decisions; planning adoption alone is not authorization evidence.
- Hard earlier dependencies: **16.12**, accepted and verified before advancing this story. These dependency results are currently unresolved; refined preparation does not mean ready-for-dev. No prior implementation learning is available for the new Epic 16 story set.
- Promote only after contract freeze, earlier dependency evidence, bounded task ownership/re-estimation and independent story review. Preserve IDs and backlog status; no feature/release implementation is claimed here.

## Acceptance Criteria

1. **AC1:** Given an approved immutable trusted source and pinned tool/provider/module identities, when a task launches, then only the qualified operator-controlled Linux disposable non-root container profile runs, with validated read-only/scoped mounts and no app or task Docker socket.
2. **AC2:** Given unsupported host enforcement/profile or untrusted PR source, when privileged collection is requested, then it denies before receiving production credentials rather than falling back to unrestricted local execution.
3. **AC3:** Given hostile Git hooks/config/credential helpers, symlink/path escape, catalog mutation or option injection, when checkout or command assembly occurs, then canonical-root containment and operator-protected argument-array catalog prevent arbitrary commands and inherited configuration.
4. **AC4:** Given task execution identity, when credentials/environment are resolved, then only allowlisted least-privilege collector credentials exist at the operator boundary, receiver credentials remain distinct and no secret values reach server payloads/logs/persistence.
5. **AC5:** Given CPU/time/disk/output/egress cap, disk-full/partial upload or descendant process, when the bound limit/failure/cancellation fires, then the full owned process tree terminates, partial evidence cannot finalize, cleanup is bounded and cancellation is persisted.
6. **AC6:** Given the supported hostile collection corpus, when real isolation is exercised, then concrete containment/resource/network evidence and versions/settings are published; a container label or mock alone cannot qualify production collection.

### Requirement Traceability

Coverage intent: Delta over the v1.4.0 baseline. These exact mapped requirements are acceptance obligations; mapping is not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| IAU15-FR-021 | Record cancellation durably and terminate the owned runner process tree; explain that cancellation cannot undo accepted external work. | Cancellation/dispatch races and process-tree termination tests |
| IAU15-FR-047 | Collect only from admitted trusted immutable sources in disposable isolated workspaces with canonical-root/symlink containment and controlled tool/provider installation; reject untrusted PR sources and inherited Git/hooks/config. | Hostile checkout/provider/config and isolation spike |
| IAU15-FR-048 | Execute only operator-protected fixed catalog commands with validated parameters; reject arbitrary shell, server-defined commands and app Docker-socket access. | Catalog tampering/option injection/arbitrary-command denial tests |
| IAU15-FR-050 | Resolve infrastructure credentials only in the operator-owned runner/receiver execution identities under an environment allow-list and least privilege; never send or persist their values in DeployWhisper. | Credential inheritance/transport/persistence corpus and separated-identity spike |
| IAU15-FR-051 | Enforce task CPU/time/disk/output/egress caps and atomic bounded uploads with cleanup after failure; cancellation must terminate the entire owned process tree. | Limit, partial-upload, disk-full, egress and descendant-process tests |

## Tasks / Subtasks and bounded ownership

- [ ] **Packet 1 — Runner/operator owner: launcher enforcement (AC 1,2,6).** Owned output: `infra_automation/runner/sandbox.py and protected reference host launcher (planned)`.
  - [ ] Non-root Linux container, dropped privileges/capabilities, scoped mounts, no Docker socket in app/task and enforceable CPU/memory/disk/time/network controls; deny unsupported host.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 2 — Runner/security owner: checkout and catalog (AC 1–3).** Owned output: `infra_automation/runner/source.py and catalog.py (planned), operator-local protected tool configuration`.
  - [ ] Admit immutable source/trust and pin checksummed tool/provider/module lockfiles; strip hooks/config/helpers, canonicalize paths/no-follow opens, typed allowlisted argv without shell.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 3 — Runner/security owner: environment and execution lifetime (AC 4,5).** Owned output: `runner execution/process module and config.py references (planned)`.
  - [ ] Allowlisted task environment/credential identity, distinct receiver access, process-tree termination and cancellation ownership, bounded streaming output/upload and cleanup.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 4 — Test/documentation owner: real hostile qualification (AC 1–6).** Owned output: `tests/test_infra_automation runner corpus, isolated Linux harness and docs/infra-automation`.
  - [ ] Run provider/external-data subprocess, hook/symlink/options, denied egress, quota/disk-full, child/grandchild cancellation and credential inheritance tests; record supported settings and misses.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.

Each packet is a bounded review unit under this stable story ID; split large packets after 16.0 estimation instead of silently broadening scope. One story branch follows Git Flow; coordinate shared-file edits and do not revert other work.

## Dev Notes

- Operator-owned host launcher owns sandbox creation; no socket is mounted in DeployWhisper app or collector task. A launcher may require operator privileges but that is a distinct host trust boundary. If controls cannot be enforced, privileged collection is unsupported.
- Plan can execute repository/provider/external-data code; describe read-oriented commands without claiming harmlessness. Supported profile is Linux disposable non-root containers, not unqualified macOS/systemd/Kubernetes alternatives.
- No infrastructure tool/provider binary is fetched on server request or unpinned at runtime. Fixed protected local catalog produces argv from strict typed parameters; reject server-specified command, extra shell fragments, executable replacement and unapproved inherited Git/env.
- Allowed mounts are tightly scoped immutable tools/task workspace and separately protected custody access. This story qualifies isolation and execution controls with hostile fixture commands; production OpenTofu/Terraform collector/custody integration belongs to 16.14.
- Cancellation persists first and owns task descendants/process group until stopped; test grandchildren and escape attempts under the profile. It cannot undo remote accepted work, clear unknown-operation locks or claim external stop.
- Raw binary plans/state/credentials never upload to DeployWhisper; collector/receiver credentials remain separate. Bounded atomic sanitized upload must reject stale attempt, truncation and disk-full. Existing Python runtime floor/packaging remains; no new unapproved dependencies.

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
