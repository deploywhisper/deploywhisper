# Story 16.13: Isolated Runner Execution Profile

Status: review
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

- [x] **Packet 1 — Runner/operator owner: launcher enforcement (AC 1,2,6).** Owned output: `infra_automation/runner/sandbox.py and protected reference host launcher (planned)`.
  - [x] Non-root Linux container, dropped privileges/capabilities, scoped mounts, no Docker socket in app/task and enforceable CPU/memory/disk/time/network controls; deny unsupported host.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 2 — Runner/security owner: checkout and catalog (AC 1–3).** Owned output: `infra_automation/runner/source.py and catalog.py (planned), operator-local protected tool configuration`.
  - [x] Admit immutable source/trust and pin checksummed tool/provider/module lockfiles; strip hooks/config/helpers, canonicalize paths/no-follow opens, typed allowlisted argv without shell.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 3 — Runner/security owner: environment and execution lifetime (AC 4,5).** Owned output: `runner execution/process module and config.py references (planned)`.
  - [x] Allowlisted task environment/credential identity, distinct receiver access, process-tree termination and cancellation ownership, bounded streaming output/upload and cleanup.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [x] **Packet 4 — Test/documentation owner: real hostile qualification (AC 1–6).** Owned output: `tests/test_infra_automation runner corpus, isolated Linux harness and docs/infra-automation`.
  - [x] Run provider/external-data subprocess, hook/symlink/options, denied egress, quota/disk-full, child/grandchild cancellation and credential inheritance tests; record supported settings and misses.
  - [x] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.

### Review Findings

- [x] [Review][Patch][P1][R1] Preserve the original execution deadline in the bootstrap [`infra_automation/runner/bootstrap.py:277`] — actual delayed-setup/controller-death reproduction exceeded a six-second budget and exited at 9.50s.
- [x] [Review][Patch][P2][R2] Validate or reject OpenTofu .tofu/.tofu.json configuration [`infra_automation/runner/source.py:491`] — actual pinned-tool execution admitted an outside module and finalized evidence after resolving credentials.
- [x] [Review][Patch][P2][R3] Require private staging before exposing read-only snapshot files [`infra_automation/runner/source.py:540`] — accepted 0755 staging exposes private repository copies as 0555/0444 to other host users.
- [x] [Review][Patch][P2][R4] Retain ambiguous create outcomes until safely reconciled [`infra_automation/runner/sandbox.py:239`] — one empty lookup currently clears pending ownership before a potentially late daemon create.
- [x] [Review][Patch][P2][R5] Repair or remove the nonfunctional standalone provider_probe command [`infra_automation/runner/catalog.py:184`] — it requires JSON stdin but the bootstrap supplies DEVNULL.

[Formal BMad review and reproduction evidence](../../docs/verification/infra-automation/16-13/code-review.md). These findings superseded the development-only clean conclusion. They are now resolved with fresh [repair and qualification evidence](../../docs/verification/infra-automation/16-13/review-fixes.md); original counterexamples remain recorded.

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

Codex with native implementation and independent verification subagents; 2026-11-04.

### Debug Log References

- CI follow-up for CodeQL alert121, verified on commit `5c15810`: console logging now emits only fixed boolean JSON through a strict emitter; detailed report fields are not logged. Console/evidence tests: 9 passed, 33 subtests. `./.venv/bin/python -m unittest discover -q`: 1,708 tests, 3 skips, OK in 742.615s. `./.venv/bin/python scripts/qualify_runner_isolation.py --output /tmp/story16-13-codeql-qualification`: all 172 real qualification assertions passed, with the console containing only the fixed success JSON. Repository Ruff check/format, scoped Bandit and diff checks passed. [Full branch CI attempt 2](https://github.com/deploywhisper/deploywhisper/actions/runs/41819820843) and [all three CodeQL languages](https://github.com/deploywhisper/deploywhisper/actions/runs/41820545909) passed. Downloaded Python SARIF contains no finding in the qualification script; no alert dismissal or suppression was used. UI validation not applicable.
- PR check synchronization remains a separate release gate: at 2026-11-04T12:26Z, PR210 still reported old head `6fc1ef7` and its original CodeQL check126529892093, although the remote branch and passing reruns referenced `5c15810`. Branch checks alone do not establish PR merge readiness; require refreshed PR checks on the latest head.

- Latest review repair verification: real qualification passed **172 assertions** (19 task, 3 controller-death, 17 admission cases); delayed setup stopped at 6.092s against original 6s budget plus 0.75s tolerance. Current source/image pins match; no owned containers remain. Independent focused repair suite: **68 tests, 135 subtests**, no residual actionable findings.
- Latest root unittest: **1,701 tests, 3 skips**, OK in 831.172s. Exact API/CLI/infra pytest shard: **734 passed, 1 skipped, 2,353 subtests**, 523.49s. Full `bash scripts/ci-local.sh`: **exit 0, no retries**, all ten directories (3,151 test executions) passed. Final Ruff check/format (532 files), scoped six-module mypy, configured Bandit medium/high gate and diff check passed. Full commands/results and preserved failure history: [review repair record](../../docs/verification/infra-automation/16-13/review-fixes.md).

- `./.venv/bin/python scripts/qualify_runner_isolation.py --build`: accepted actual Linux run at 2026-11-04T08:19:15Z, 17 task cases + two host-controller death/recovery cases + nine admission cases; all 130 assertions passed. An unchanged-source repeat passed the same corpus. Current image/source pins and runtime source hashes match; no owned containers remain. [Qualification evidence](../../docs/verification/infra-automation/16-13/README.md) and [results](../../docs/verification/infra-automation/16-13/results.json).
- Final focused command: `./.venv/bin/python -m pytest tests/test_infra_automation/test_runner_source.py tests/test_infra_automation/test_runner_catalog.py tests/test_infra_automation/test_runner_sandbox.py tests/test_infra_automation/test_runner_execution.py tests/test_infra_automation/test_runner_execution_boundaries.py tests/test_infra_automation/test_runner_isolation_qualification.py -q` — 43 passed, 83 subtests, 14.01s.
- `./.venv/bin/python -m unittest discover -q` — 1,677 tests, three skips, OK in 809.576s.
- Exact `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` — 734 passed, one skipped, 2,353 subtests in 520.97s.
- `bash scripts/ci-local.sh` — exit 0 with no retries; all ten directories passed (69 analysis, 343 API, 102 CLI, 51 docs, 290 infra, 897 automation, 76 LLM, 22 models, 43 parsers, 1,232 services; 3,125 test executions, three existing skips). Dependency checks, compilation, skill/prompt-injection checks and configured security gates also passed.
- Repo-wide Ruff check and format check (532 files), scoped mypy for the six new runtime modules, configured Bandit medium/high gate and diff checks passed. A broader imported-module mypy run exposed pre-existing PyYAML-stub/content_security issues; no unrelated typing/dependency changes were made.
- Independent lifecycle review and regression repairs: [development review](../../docs/verification/infra-automation/16-13/review.md). Unit subprocess tests are not misrepresented as live containment proof.

### Completion Notes List

- Latest review repairs: R1–R5 resolved, all action items checked, story returned to review. Reused bounded source/command validators, ownership primitives and existing transaction boundaries. No new dependency or app database migration; the private operator journal adds a nullable immutable-container acknowledgement without discarding history. Original execution budgets now survive setup/controller death; all OpenTofu formats are admitted consistently; snapshots stay private; unknown creates remain pending; unsupported standalone provider command is removed. Current real qualification has 172 assertions; earlier 130-assertion development results below are historical.

- 2026-11-04 formal BMad code review: changes requested (one P1, four P2); story returned to in-progress. Five patch actions were opened at that review and are now resolved. Earlier development verification below is historical and does not establish coverage of the new counterexamples.

- Readiness: PR209 merged Story16.12 as e2690a7 after its findings were repaired and CI passed. The prior review tracker state is reconciled to done; no GitHub approval review is invented. Story16.0 accepted qualification/contracts remain unchanged. Historical unresolved-entry wording above is superseded by this evidence.
- Implemented separate operator-owned catalog/source admission, Linux container launch, fixed in-container precredential verification and bounded execution lifetime. The application/default runner handler remains unable to launch production collection; no app route, app Docker socket, new dependency or app database migration was introduced.
- Reuse: existing closed-model/task-scope contracts, content screening and private-file primitives; the same durable engine remains authoritative. Local SQLite stores only execution identity/status/ownership metadata. Source snapshots are explicit caller-owned immutable resources with bounded no-follow cleanup.
- Source admission ignores original Git configuration/hooks/helpers and processes a bounded object snapshot with fixed commands; module checks run in bounded subprocesses. Only pinned, contained vendored modules are supported. Catalog/registration mutation, untrusted PR inputs, path/option injection and links deny before credential resolution.
- The same task container proves real UID/capability/seccomp/cgroup/mount/network and file-pin controls before receiving collector-only values through stdin. A non-dumpable fixed PID1 and stacked scheduling/process-control filter enforce the original wall/lease bound even after controller death and under CPU load.
- Repaired review findings: finalization cancellation/expiry, journal lock contention, mutable lease identity, container-name ownership and uncertain recovery. Final cancellation wins transactionally; unknown cleanup never produces finalizable evidence. Completed-writer overflow and raw/URL/split credential echoes are rejected without retained output or credential values.
- Qualification applies only to the recorded offline Linux ARM64, Docker29.1.3, LinuxKit6.12.54 profile and image sha256:6a19e2ca78fd94aa2e6610ebe2229217f1a6836dd251ca910c811141cb06c4a2. Dormant kernel tunnels must be down/addressless/routeless. No native macOS sandbox, arbitrary network, production cloud credential/IAM, collector/custody integration or universal provider-safety claim is made. Story16.14 and release qualification own those remaining integrations.
- New test files use the existing registered infra-automation directory; no CI discovery directory was omitted. Repository-wide searches covered new source/profile/execution/journal/credential constructors and fixtures. The evidence drift guard requires real requalification when isolation runtime or image-source pins change.
- UI validation not applicable: no rendered surface or browser interaction changed. Documentation and schema/state compatibility remain aligned with the scoped operator profile.
- Development verification is complete; story and sprint status are review. All packet/verification checkboxes are complete. BMad help routes the next major workflow to bmad-code-review; no commit, push or PR is claimed by this development pass.

### File List

- `tests/test_infra_automation/test_runner_qualification_console.py`

- `README.md`
- `_bmad-output/implementation-artifacts/16-12-runner-enrollment-and-attempt-protocol.md`
- `_bmad-output/implementation-artifacts/16-13-isolated-runner-execution-profile.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/project-context.md`
- `docs/infra-automation/runner-isolation-v1.md`
- `docs/verification/infra-automation/16-13/README.md`
- `docs/verification/infra-automation/16-13/code-review.md`
- `docs/verification/infra-automation/16-13/results.json`
- `docs/verification/infra-automation/16-13/review-deadline-repro.json`
- `docs/verification/infra-automation/16-13/review-fixes.md`
- `docs/verification/infra-automation/16-13/review.md`
- `infra_automation/runner/bootstrap.py`
- `infra_automation/runner/catalog.py`
- `infra_automation/runner/execution.py`
- `infra_automation/runner/execution_profile.py`
- `infra_automation/runner/sandbox.py`
- `infra_automation/runner/source.py`
- `scripts/qualify_runner_isolation.py`
- `tests/fixtures/infra_automation/qualification/16_13/Dockerfile`
- `tests/fixtures/infra_automation/qualification/16_13/Dockerfile.dockerignore`
- `tests/fixtures/infra_automation/qualification/16_13/probe.py`
- `tests/fixtures/infra_automation/qualification/16_13/provider_probe.py`
- `tests/fixtures/infra_automation/qualification/16_13/source/.terraform.lock.hcl`
- `tests/fixtures/infra_automation/qualification/16_13/source/main.tf`
- `tests/fixtures/infra_automation/qualification/16_13/source/source.lock`
- `tests/fixtures/infra_automation/qualification/16_13/tofurc`
- `tests/test_infra_automation/test_runner_catalog.py`
- `tests/test_infra_automation/test_runner_execution.py`
- `tests/test_infra_automation/test_runner_execution_boundaries.py`
- `tests/test_infra_automation/test_runner_isolation_qualification.py`
- `tests/test_infra_automation/test_runner_sandbox.py`
- `tests/test_infra_automation/test_runner_source.py`

## Change Log

- 2026-11-04: Implemented isolated operator profile and real hostile qualification; completed fresh focused/root/API/full-CI validation and real hostile qualification; ready for code review.

- 2026-11-04: Layered BMad code review recorded five patch findings, including two real Linux counterexamples; returned story/sprint status to in-progress. No runtime edits or publication.

- 2026-11-04: Resolved all five review findings and adjacent real qualification cleanup/timeout races; refreshed pinned-image evidence and completed clean full CI. Ready for re-review.

- 2026-11-04: Addressed CodeQL clear-text logging dataflow in qualification console output; local regression, real qualification, full branch CI and CodeQL passed. PR check synchronization remains pending.
