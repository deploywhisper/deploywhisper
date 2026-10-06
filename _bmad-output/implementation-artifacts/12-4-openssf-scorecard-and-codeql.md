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
- Scorecard PR mode is local/partial; repository/API checks require the default branch. The job follows default-branch metadata and disables external badge/API publication, PAT inputs and OIDC privileges. Full hosted CLI baseline at `495f845` scored 3.8/10; observed high-priority/unknown signing checks have assigned follow-up [#131](https://github.com/deploywhisper/deploywhisper/issues/131), with no unsupported claim that they are safe.
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
- Limits: full default-branch workflow execution is a post-integration event and is not inferred from the PR-local scan. The baseline's advisory reports still require version/manifest triage under #131. External Scorecard publication is intentionally disabled. Reviewer Git Flow closeout remains the next step after code review; no protected-branch merge was performed by this workflow.
- `bmad-help` next step: `bmad-code-review` for Story 12.4; Story 12.5 remains ready-for-dev until this review/closeout is handled.

### File List

- `.github/workflows/codeql.yml`
- `.github/workflows/scorecard.yml`
- `tests/test_infra/test_supply_chain_workflows.py`
- `README.md`
- `SECURITY.md`
- `docs/ci.md`
- `docs/security/supply-chain-scanning.md`
- `docs/security/supply-chain-findings.md`
- `docs/verification/story-12-4/scorecard-baseline.json`
- `docs/verification/story-12-4/pr-scan-summary.json`
- `_bmad-output/implementation-artifacts/12-4-openssf-scorecard-and-codeql.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-10-06: Started baseline security workflows, owner-based finding dispositions, static regressions and live validation on the dedicated feature branch.
- 2026-10-06: CodeQL/Scorecard live runs, SARIF visibility/artifacts, full local CI and high-priority follow-up verified; story/sprint moved to review on draft PR #132.
