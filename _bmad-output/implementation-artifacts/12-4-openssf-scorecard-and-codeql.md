# Story 12.4: OpenSSF Scorecard and CodeQL

Status: review

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a maintainer,
I want baseline open-source security checks,
So that supply-chain posture is visible.

## Acceptance Criteria

1. Given repository workflows run, When Scorecard and CodeQL complete, Then results are visible to maintainers and documented. And high-priority findings have follow-up issues or accepted rationale.

### Requirement Traceability

- Primary PRD requirements: Epic 12 coverage: ADM-01..02, NFR-SEC-01..07, NFR-OPS-01..06, GOV-06..07, DOC-11, DOC-12.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 12 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)
- [x] Add the user-requested official Scorecard badge and a restricted default-branch publisher; verify PR scans stay unpublished. (AC: 1)

### Review Findings — 2026-10-07

- [x] [Review][Patch][P2] Require fresh Scorecard report provenance before artifact/code-scanning upload [.github/workflows/scorecard.yml:37; .github/workflows/scorecard-publish.yml:41]. Both workflows select checkout-relative `results.sarif` and upload with `always()` plus file existence alone. The pinned scanner exits before formatting on option/scan errors without clearing a pre-existing file. A repository-supplied valid SARIF therefore passes the upload guard when scanning fails before output, creating misleading scanner evidence or fabricated findings/clean results. Isolate fresh outputs or add a scan-outcome/provenance guard and failure regressions for both workflows; preserve legitimate report retention after publication failure without adding forbidden shell steps to the publishing job.
- [x] [Review][Patch][P3] Include Critical checks in the baseline disposition regression [tests/test_infra/test_supply_chain_workflows.py:185]. The fixed set includes High checks but excludes `Dangerous-Workflow`/`Webhooks`, which the guide prioritizes as Critical. An in-memory mutation making retained `Dangerous-Workflow` score 0 with no corresponding ledger disposition still passes the real test. Extend the priority set/classification and add a negative ownership/disposition case so Critical failures cannot silently escape this guard.

## Dev Notes

### Epic Context

- Epic: 12. Security and Supply Chain Hardening
- Epic goal: Make the project trustworthy to install, operate, and contribute to.
- Epic coverage: ADM-01..02, NFR-SEC-01..07, NFR-OPS-01..06, GOV-06..07, DOC-11, DOC-12

### Architecture and Product Guardrails

- Preserve DeployWhisper's local-first raw artifact boundary: raw IaC, scanner artifacts, incident exports, and sensitive context stay in the user's infrastructure by default.
- Preserve the advisory-first core. Optional adapters may interpret report outputs, but canonical report semantics remain advisory unless explicit story scope says otherwise.
- Reuse the shared analysis core and service layer before adapting UI, API, CLI, GitHub, or future workflow surfaces.
- Keep Evidence Law behavior intact: no high or critical finding without deterministic evidence.
- Keep project/workspace scope explicit for reports, incidents, topology, outcomes, feedback, scanner imports, and connector-related data.
- Do not introduce new dependencies unless the active story explicitly requires and justifies them.

### Source Tree Guidance

- API routes belong under `api/routes/` and should use existing `ApiRoute` / `ApiError` envelope patterns.
- Shared orchestration belongs in `services/`; parsers normalize input, analysis modules score/derive risk, and surfaces adapt outputs.
- UI work belongs under `frontend/src/screens/` and `frontend/src/components/`, following the existing retired Python UI composition style.
- CLI behavior belongs under `cli/` and must call the same service-layer paths as UI/API flows.
- Persistence work belongs under `models/` with Alembic migrations when schema changes are required.
- Documentation required by a story should be updated in the same workstream.

### Testing Requirements

- Use standard-library `unittest` in the existing `tests/test_*` layout.
- Add focused regression tests for the layer changed by the story before broad refactors.
- For Python changes, run `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, and `./.venv/bin/python -m unittest discover -q` before closing implementation.
- Use `bash scripts/ci-local.sh` for broader or cross-layer changes.

### Project Structure Notes

- Follow the current repository shape documented in `_bmad-output/project-context.md` and `AGENTS.md`.
- If implementation reveals a conflict between this story and the current code baseline, keep the smallest compatible change and update the story notes rather than silently drifting from the PRD.

### References

- `_bmad-output/planning-artifacts/epics.md` - source Epic 12 / Story 12.4 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

Codex with native subagents for official-source research and bounded workflow/test implementation.

### Debug Log References

- `/private/tmp/story12-4-red.log`: workflow safety regressions failed before workflow creation.
- `/private/tmp/story12-4-infra.log`: 106 infrastructure tests plus 103 subtests passed for the initial workflow slice.
- `/private/tmp/story12-4-tools/repository-baseline.json`: full official Scorecard v5.5.0 baseline, SHA-256-verified release binary.
- `/private/tmp/story12-4-ci.log`, `story12-4-unittest.log`, `story12-4-shard.log`: broad local validation.

### Completion Notes List

- Implementation plan: add SHA-pinned, least-privilege CodeQL/Scorecard workflows with safe PR behavior and retained SARIF; document coverage and weekly owner-based triage; verify workflow contracts/actionlint, actual full repository baseline and live PR execution.
- CodeQL default setup was not configured; repository is public and its default branch is `develop`. Advanced analysis covers Python, JavaScript/TypeScript and Actions with no-build mode and extended security queries.
- Scorecard PR mode is local/partial; repository/API checks require the default branch. The initial implementation disabled external publication. The subsequent user-requested badge uses a separate restricted publisher as recorded below; PR-local scans retain no publication/OIDC privileges. Full hosted CLI baseline at `495f845` scored 3.8/10; observed high-priority/unknown signing checks have assigned follow-up [#131](https://github.com/deploywhisper/deploywhisper/issues/131), with no unsupported claim that they are safe.
- No product/backend/UI behavior, runtime dependency, constructor/schema or release-policy setting changed. UI validation not applicable.
- A draft PR is used to verify real GitHub analysis, processing and artifacts before marking this story ready for review. Default-branch workflow verification remains a separate post-integration event.

### Validation and Outcome

- Definition of Done: PASS. Workflows, safety regressions, maintainer docs, baseline evidence and high-priority dispositions complete; story/sprint moved to `review`. [Draft PR #132](https://github.com/deploywhisper/deploywhisper/pull/132) targets `develop` on `feature/12-4-openssf-scorecard-codeql` and remains draft pending BMad code review/closeout.
- Tests first failed for missing workflows. Meaningful regressions enforce pinning, minimum job permissions, no dangerous PR trigger/PAT/OIDC or repository-code execution in CodeQL, default-branch Scorecard limits, artifact retention/failure visibility, trusted literal summaries and owned High/unknown baseline dispositions. Final focused suite: **7 passed + 12 subtests**. The first broad smoke/shard runs cached a documentation-wording assertion while it was corrected; final reruns below passed. No product behavior failure was suppressed.
- `bash scripts/ci-local.sh`: **1,765 tests passed across all nine directories**, plus compilation, dependency consistency, deterministic Skill/prompt gates and configured Bandit. `./.venv/bin/python -m unittest discover -q`: **493 passed**, one optional live-provider skip. `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: **430 passed + 164 subtests**. Logs: `/private/tmp/story12-4-ci.log`, `/private/tmp/story12-4-unittest-final.log`, `/private/tmp/story12-4-shard-final.log`.
- Final `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`: passed, **295 Python files**. Official SHA-256-verified actionlint **1.7.12** passed both new workflows. `git diff --check`: passed. Existing medium sample-data Bandit B104 remains unchanged; high-severity gate passes. UI validation not applicable; application source/routes/schemas and production UI unchanged.
- Live validation head `df01ebd`, analyzed PR merge `0e33ca4`: [CodeQL run](https://github.com/deploywhisper/deploywhisper/actions/runs/37489620206) completed all three language jobs, retained nonempty per-language SARIF artifacts and uploaded/processed **zero results** in each category. [Scorecard run](https://github.com/deploywhisper/deploywhisper/actions/runs/37489620101) completed local PR mode, retained `scorecard-sarif` and uploaded/processed **70 results**. GitHub alerts API confirms all 70 are maintainer-visible, including five High results (alerts #1/#3/#4/#5/#70), all mapped to assigned follow-up #131. No analysis processing errors. [PR CI](https://github.com/deploywhisper/deploywhisper/actions/runs/37489620053) also passed.
- Full repository CLI baseline at `495f845`, Scorecard **v5.5.0**, scored **3.8/10**; high-priority posture gaps and unknown release-signing coverage are recorded with owner, next review date and [follow-up #131](https://github.com/deploywhisper/deploywhisper/issues/131). SAST and pinning are Medium per official definitions. No unknown/failed control is treated as passing or accepted as safe. A green scanner execution is not a clean security posture.
- Independent read-only verifier passed focused tests and found no workflow/security blocker; it confirmed least privilege, pins, safe triggers, scoped/default behavior, artifacts and finding ownership. No new dependencies or custom report abstractions. Official action versions and pins were verified through release metadata and peeled tags.
- Limits: full default-branch workflow execution is a post-integration event and is not inferred from the PR-local scan. The baseline's advisory reports still require version/manifest triage under #131. PR-local Scorecard publication stays disabled; the later requested default-branch badge publisher requires post-integration verification. Reviewer Git Flow closeout remains the next step after code review; no protected-branch merge was performed by this workflow.
- `bmad-help` next step: `bmad-code-review` for Story 12.4; Story 12.5 remains ready-for-dev until this review/closeout is handled.

### File List

- `.github/workflows/codeql.yml`
- `.github/workflows/scorecard.yml`
- `.github/workflows/scorecard-publish.yml`
- `tests/test_infra/test_supply_chain_workflows.py`
- `tests/test_infra/test_supply_chain_report_provenance.py`
- `README.md`
- `SECURITY.md`
- `docs/ci.md`
- `docs/security/supply-chain-scanning.md`
- `docs/security/supply-chain-findings.md`
- `docs/verification/story-12-4/scorecard-baseline.json`
- `docs/verification/story-12-4/pr-scan-summary.json`
- `_bmad-output/implementation-artifacts/12-4-openssf-scorecard-and-codeql.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

### User-requested Scorecard Badge — 2026-10-06

- Added the official Scorecard API badge and viewer link beside the README badges. User request supersedes the original no-publication choice. PR-local scans remain unpublished and lack OIDC; a separate `scorecard-publish.yml` single job runs only on the non-fork default branch, with job-scoped OIDC/security-events write and only approved SHA-pinned actions. It has no PR trigger, environment/default overrides, shell steps, services or repository execution, satisfying upstream publication-provenance restrictions.
- Updated guide and ledger to distinguish PR artifacts, full repository scans and public badge publication. The official API currently returns 404/no published result; the badge SVG shows `invalid repo path` until the first repository publication. The repository itself is public/non-fork and the URL matches upstream's documented badge format. No score or successful publication is fabricated. First publication is a post-integration default-branch event; no merge/default-branch setting change was made to bypass that boundary.
- Badge-specific regressions first failed (**7 failing cases**), then passed: **8 tests +15 subtests**. They enforce the separate restricted publisher, no PR/OIDC/publication crossover, action whitelist, credential-free checkout, default/fork guard and official badge/viewer URLs. Independent reviewer verified the addon with no blocker. actionlint passed all three scan workflows.
- Final badge-source verification: `bash scripts/ci-local.sh`: **1,766 tests across all nine directories**; `./.venv/bin/python -m unittest discover -q`: **494 passed**, one optional skip; `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: **431 passed +167 subtests**. Ruff lint/format (**295 files**) and diff checks passed. Logs: `/private/tmp/story12-4-badge-ci.log`, `/private/tmp/story12-4-badge-unittest.log`, `/private/tmp/story12-4-badge-shard.log`. UI validation not applicable.
- The badge update is included in the same Story 12.4 draft PR. PR-local Scorecard/CodeQL will be rechecked on the updated branch; trusted publisher execution and badge score population remain pending the first integrated default-branch run.

### Code Review Record — 2026-10-07

- Full review scope: `495f845..c8fb694`, **13 files, 749 added / 1 removed lines**, clean original working tree. Frozen diff: `/private/tmp/story12-4-code-review.diff`. Story/project/security context loaded for acceptance; blind reviewer received the diff only.
- All three independent BMad review layers completed. Triage: **two patches (P2/P3), zero decision-needed, zero new deferrals, one dismissed category candidate**. The acceptance layer verified AC1 result visibility and assigned High follow-ups; edge tracing exposed a failed-scan provenance branch. The baseline-practice gaps in #131 remain existing tracked findings rather than new workflow defects.
- Report-provenance evidence: the pinned [Scorecard entrypoint](https://github.com/ossf/scorecard-action/blob/2d1146689b8cda280b9bc96326124645441f03bc/main.go) returns on option/scan failures before formatting. An isolated temporary directory with a pre-seeded valid SARIF and scan outcome `failure` still satisfies the existing `always()/hashFiles` predicate. This is a reproduced conditional failure path, not a claim that observed successful runs were forged. CodeQL's pinned `runFinalize` clears its output directory before generating/uploading results, so the analogous successful-analysis auto-upload concern was rejected.
- Critical-triage evidence: parent invoked the actual `test_baseline_high_priority_findings_have_owned_followups` with a patched in-memory baseline where `Dangerous-Workflow` score changed from 10 to 0. The test passed despite no Critical ledger row. No fixture or operator data was changed on disk.
- Category candidate dismissed as an unestablished contract violation: actual uploaded Scorecard SARIF carries native `supply-chain/local` automation metadata, rather than the literal upload input; PR-local and hosted coverage are intentionally distinct and documented. No introduced-only attribution is promised. Avoid inferring a full repository posture or public badge value from the PR-local analysis.
- Fresh validation: workflow regressions **8 passed +15 subtests**; Ruff lint/format (**295 files**), actionlint on all three workflows and diff checks passed. Exact-head GitHub PR checks for `c8fb694` were all successful, including three CodeQL jobs, local Scorecard, security, test shards, migrations and Docker build. This review changes tracking documents only; broad CI/live scanners were not rerun because workflow code was unchanged.
- Publisher layout/permissions/pins match upstream restrictions and badge/viewer URLs target the correct repository. Public badge API remains without a published score; first trusted default-branch publication and numeric badge verification are still post-integration work, not evidence supplied by the 3.8 CLI baseline. This limitation remains explicit rather than being waived or claimed complete.
- Findings recorded as action items; story/sprint reopened to `in-progress`. No code fix, commit or push performed during this review because follow-up work remains open. `bmad-help` next step: repair the two Story 12.4 findings and rerun review before Git Flow closeout/default-branch integration.


### Review Fix Implementation — 2026-10-07

- Fixed both review findings. Scorecard producer and consumers now use report filenames bound to the immutable checkout SHA, run ID and attempt. Default checkout without a ref/repository override means a tracked report cannot pre-seed its own commit-dependent filename; previous-run/attempt files also miss the exact guard. PR uploads require scanner success, while the restricted publisher preserves fresh formatted output after publication failure without shell cleanup/environment overrides.
- Added four temporary-filesystem provenance regressions: valid seeded SARIF, prior commits/runs/attempts and scan failure before output cannot upload; fresh successful PR output can upload; failed/skipped PR scans are blocked; publisher publication failure retains fresh output. Tests initially reproduced 10 failing cases, then passed.
- Extended ownership assertions to Critical `Dangerous-Workflow`/`Webhooks`. Negative fixtures invoke the actual baseline validator with failed/unknown Critical checks and require the specific missing-disposition failure; positive owned rows pass. Four Critical cases failed before repair. No baseline evidence or live finding is forged or waived.
- Focused tests: **14 passed +29 subtests**. actionlint and Ruff lint/format (**296 files**) pass. Smoke **500 tests** (one optional skip), API/CLI/infra **437 +181 subtests** pass; full local CI/live updated-PR verification recorded on completion below. Independent reviewer found no residual blocker. UI validation not applicable.
- Temporary SARIF fixture content was strengthened to include a valid Scorecard driver/run; predicates and behavior unchanged. Source changes remain on the existing draft PR #132. The first trusted badge publication remains post-integration verification.


### Review Fix Verification — 2026-10-07

- Both P2/P3 findings resolved and checked. Independent reviewer reran the guarded failure/retention paths and Critical ownership cases with no residual blocker. Publisher still obeys the approved-action-only layout, default/fork guard, minimum permissions and no repository cleanup/execution.
- Final `bash scripts/ci-local.sh`: **1,772 tests passed across all nine directories**, plus Skill/prompt checks, compilation, dependency consistency and configured Bandit. `./.venv/bin/python -m unittest discover -q`: **500 passed**, one optional live-provider skip. `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: **437 passed +181 subtests**. Logs: `/private/tmp/story12-4-reviewfix-ci.log`, `/private/tmp/story12-4-reviewfix-unittest.log`, `/private/tmp/story12-4-reviewfix-shard.log`. Focused workflow/provenance tests: **14 passed +29 subtests**. Ruff lint/format (**296 files**), actionlint on all three workflows and diff checks passed.
- Live implementation head `f81f699`, PR merge `17d91ea`: [Scorecard run](https://github.com/deploywhisper/deploywhisper/actions/runs/37573610812) succeeded and its artifact contains exactly one `scorecard-17d91ea87f8a391171a2bfd9e003c9037554dfe5-37573610812-1.sarif`, proving producer/consumer binding to the actual merge/run/attempt. All 70 findings processed without errors; existing five High findings remain tracked under #131.
- [CodeQL](https://github.com/deploywhisper/deploywhisper/actions/runs/37573610852) succeeded in all three languages; [PR CI](https://github.com/deploywhisper/deploywhisper/actions/runs/37573610799) succeeded. Failure-path tests—not a live malicious upload—verify stale data cannot pass either workflow's guards. Updated documentation explains fresh-report handling and Critical triage.
- UI validation not applicable. Existing medium sample-data Bandit B104 remains unchanged; high-severity gate passed. No new dependencies, app/API/schema behavior or extra publisher privileges. First integrated default-branch publisher/badge population is still pending integration and not claimed from PR-local success.
- Definition of Done: PASS for these fixes. Story/sprint returned to `review`; fixes and evidence included in existing draft PR #132. `bmad-help` next step: rerun `bmad-code-review` before final Git Flow closeout. The baseline's high-priority follow-ups remain assigned/open under #131.


## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-10-06: Started baseline security workflows, owner-based finding dispositions, static regressions and live validation on the dedicated feature branch.
- 2026-10-06: CodeQL/Scorecard live runs, SARIF visibility/artifacts, full local CI and high-priority follow-up verified; story/sprint moved to review on draft PR #132.
- 2026-10-06: Added requested official Scorecard badge and isolated OIDC-backed default-branch publisher; badge safety regressions and full local CI passed; first publication remains post-integration verification.
- 2026-10-07: Three-layer code review found two actionable report-provenance/critical-triage regression gaps; recorded findings and reopened story/sprint to in-progress.
- 2026-10-07: Implemented commit/run/attempt-bound report uploads and Critical ownership regressions; full/local and live PR validation underway.
- 2026-10-07: Both review fixes verified by full local tests, live fresh-report upload, CodeQL and PR CI; story/sprint returned to review.
