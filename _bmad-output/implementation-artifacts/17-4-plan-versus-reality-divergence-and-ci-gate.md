# Story 17.4: Plan-Versus-Reality Divergence Detection and CI Gate

Status: done. **Highest standalone value in the epic; shippable without any UI.**
Preparation: refined
Release: v1.6.0 (independent release train) | Priority: P0 within the independent Epic 17 lane

## Story

As a reviewer or CI operator, I want to know when a plan was computed against stale reality before I approve it, so that I never approve a diff that is not the diff which will apply.

## Implementation gates

- Blocked until 17.3 lands plan-directed reflection, bounded collection and fail-safe degradation.
- Hard earlier dependencies: **17.3**. **No Epic 16 dependency.**
- This slice proves comparison, severity floor and gate semantics against **recorded divergence fixtures** covering out-of-band modification, deletion, recreation and tag-only change. UI presentation is owned by 17.8.
- This story is the first slice that delivers end-user value on its own. It must be shippable and demonstrable with the CLI alone.

## Acceptance Criteria

1. **AC1:** Given recorded plan prior state and live state, when comparison runs, then each touched resource is classified `match`, `diverged`, `unknown` or `unreadable`.
2. **AC2:** Given a diverged resource, when the report is produced, then a `plan_reality_divergence` finding carries per-attribute recorded, live and planned values linked to the snapshot digest and the specific resource.
3. **AC3:** Given a plan generated earlier than the configured threshold, when grounding runs, then plan freshness is computed and the stale plan is flagged.
4. **AC4:** Given divergence on a security-relevant or destructive attribute, when the recommendation is computed, then a severity floor applies and the recommendation is at least `caution`; no reason, acknowledgement or narrative can clear the floor.
5. **AC5:** Given `--fail-on-divergence`, when the CLI or API runs in CI, then the gate fails deterministically with a distinct documented exit code and requires no web UI.
6. **AC6:** Given an unreadable or unknown comparison, when results are rendered, then it is never reported as `match`.

### Requirement Traceability

Coverage intent: delta over the current released baseline. Mapping is an acceptance obligation, not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| LEG-FR-017 | Compare recorded plan prior state against observed live state and classify each touched resource as `match`, `diverged`, `unknown` or `unreadable`. | Comparison matrix over recorded divergence fixtures |
| LEG-FR-018 | Emit a `plan_reality_divergence` finding carrying per-attribute recorded, live and planned values, linked to the snapshot digest and the specific resource. | Finding shape and Evidence Law tests |
| LEG-FR-019 | Compute plan freshness and flag a plan generated earlier than the configured staleness threshold. | Plan-age fixture tests |
| LEG-FR-020 | Apply a severity floor for divergence on security-relevant or destructive attributes that no reason, acknowledgement or narrative can clear. | Floor-enforcement and override-attempt tests |
| LEG-FR-021 | Provide a deterministic `--fail-on-divergence` CI gate with a distinct documented exit code, usable without the web UI. | CLI gate tests and a documented exit-code contract |
| LEG-NFR-004 | Degradation must be fail-safe; unknown and unreadable are never presented as match. | Negative-path assertions |

## Tasks / Subtasks and bounded ownership

Execute one bounded packet at a time on `feature/17-4-plan-reality-divergence`. Each packet owns the named paths.

- [x] **Packet 4.1: Divergence fixture corpus — owner: test owner.**
  - Owned write paths: `tests/fixtures/` divergence corpus, `tests/test_analysis/`.
  - Output: synthetic recorded fixtures for out-of-band modification, deletion, recreation, tag-only change, unknown and unreadable.
  - Acceptance proof: fixture coverage underpinning AC1 and AC6.
- [x] **Packet 4.2: Comparison engine — owner: analysis implementer.**
  - Owned write paths: `analysis/divergence.py`, `tests/test_analysis/`.
  - Output: four-way classification over recorded prior state versus live state, with attribute-level diffs.
  - Acceptance proof: AC1, AC6 — comparison matrix and negative-path assertions.
- [x] **Packet 4.3: Finding emission and evidence linkage — owner: analysis implementer.**
  - Owned write paths: `analysis/divergence.py`, `evidence/` consumption only, `tests/test_analysis/`, `tests/test_evidence/`.
  - Output: `plan_reality_divergence` finding with recorded, live and planned attribute triples linked to the snapshot digest and the specific resource.
  - Acceptance proof: AC2 — finding shape and Evidence Law gate tests.
- [x] **Packet 4.4: Plan freshness — owner: analysis implementer.**
  - Owned write paths: `analysis/divergence.py`, `services/` settings consumption, `tests/test_analysis/`.
  - Output: plan age computation against a configurable staleness threshold and a stale-plan flag.
  - Acceptance proof: AC3 — plan-age fixture tests.
- [x] **Packet 4.5: Severity floor — owner: analysis implementer.**
  - Owned write paths: `analysis/risk_scorer.py` **additive floor application only**, `tests/test_analysis/`.
  - Output: an unclearable severity floor for security-relevant and destructive divergence, raising the recommendation to at least `caution`.
  - Acceptance proof: AC4 — floor-enforcement plus explicit override-attempt tests through reason, acknowledgement and narrative paths.
  - **Shared-file rule:** apply the floor additively; do not alter existing `ACTION_BASE_SEVERITY` or `CATEGORY_BASE_SEVERITY` semantics.
- [x] **Packet 4.6: CI gate and exit-code contract — owner: CLI implementer and documenter.**
  - Owned write paths: `cli/`, `api/` additive fields, `tests/test_cli/`, `tests/test_api/`, `docs/live-environment-grounding/README.md`.
  - Output: `--fail-on-divergence` with a distinct documented exit code, deterministic in CI and usable with no web UI.
  - Acceptance proof: AC5 — gate tests and a published exit-code contract.

### Review Findings

- [x] [Review][Patch][P1] Keep changes to unobserved attributes from clearing the CI gate (`analysis/divergence.py:475`, `analysis/divergence.py:581`).
- [x] [Review][Patch][P1] Require account and region binding before matching scope-local resource identities (`analysis/divergence.py:300`).
- [x] [Review][Patch][P1] Keep stale observations and unverifiable plan chronology from clearing the CI gate (`services/divergence_service.py:99`, `services/divergence_service.py:155`).
- [x] [Review][Patch][P2] Reject errored plans and account for deferred changes before passing CI (`analysis/divergence.py:619`).
- [x] [Review][Patch][P2] Preserve report-level uncertainty when confirmed drift coexists with missing facts (`services/analysis_service.py:2564`).
- [x] [Review][Patch][P2] Preserve unreadable status and permission when the observation predates the plan (`analysis/divergence.py:516`).
- [x] [Review][Patch][P3] Select the deterministic caution briefing before invoking the narrative provider (`services/analysis_service.py:2610`).

See the [review report](../../docs/verification/live-environment-grounding/17-4/code-review.md) for evidence and acceptance criteria.

### Re-review Findings

- [x] [Review][Patch][P1] Bind the divergence gate to the plan admitted by shared artifact intake (`services/divergence_service.py:105`).
- [x] [Review][Patch][P1] Treat conflicting prior-state and change-before facts as unverified (`analysis/divergence.py:677`).
- [x] [Review][Patch][P2] Verify resource scope before attaching a retained read denial (`analysis/divergence.py:654`).
- [x] [Review][Patch][P2] Enforce observation freshness through admission finalization (`services/analysis_service.py:2828`).
- [x] [Review][Patch][P2] Preserve report persistence errors after grounded analysis rolls back (`services/divergence_service.py:60`, `services/cloud_context_service.py:548`).
- [x] [Review][Patch][P2] Reject out-of-range timestamp offsets before chronology checks (`analysis/divergence.py:34`, `analysis/divergence.py:218`).

See the [re-review report](../../docs/verification/live-environment-grounding/17-4/code-review.md#re-review-on-2026-11-23).

### Closeout Review Findings

- [x] [Review][Patch][P2] Keep post-write evidence verification storage errors on the report persistence path (`services/cloud_context_service.py:1025`, `services/divergence_service.py:64`).
- [x] [Review][Patch][P3] Avoid truncating nonzero sub-microsecond plan timestamp precision into verified chronology (`analysis/divergence.py:219`).

See the [closeout review](../../docs/verification/live-environment-grounding/17-4/code-review.md#closeout-review-on-2026-11-23).

### 2026-11-26 Re-review Findings

- [x] [Review][Patch][P1] Keep uncovered security-critical prior attributes from clearing the gate during another change to the same resource (`analysis/divergence.py:63`, `analysis/divergence.py:660`).
- [x] [Review][Patch][P2] Validate no-op consistency and change identity before skipping no-op rows (`analysis/divergence.py:848`, `analysis/divergence.py:861`).

Both closeout findings above were also reproduced. See the [re-review evidence](../../docs/verification/live-environment-grounding/17-4/code-review.md#re-review-on-2026-11-26).

### 2026-11-27 Re-review Findings

- [x] [Review][Patch][P1] Check recorded EC2 security group attachments against the qualified observation before allowing a match (`analysis/divergence.py:541`, `analysis/divergence.py:647`).
- [x] [Review][Patch][P2] Preserve operational errors from inside the retained-snapshot repository during post-write verification (`models/repositories/cloud_snapshots.py:203`, `models/repositories/cloud_snapshots.py:215`, `services/divergence_service.py:71`).

See the [re-review evidence](../../docs/verification/live-environment-grounding/17-4/code-review.md#re-review-on-2026-11-27).

## Tasks note on value demonstration

Packets 4.2 through 4.6 are sufficient for a demonstrable release increment. Record a reproducible walkthrough: a recorded plan, an out-of-band change, and a CI gate failure with the exact exit code.

## Dev Notes

- Divergence is the capability no competing open-source pre-deployment tool provides as a first-class finding. Precision matters more than coverage; a false `diverged` erodes trust faster than a missed one.
- Narrative generation must never be able to soften a floored severity. Verify the floor holds through the LLM narrative path, not only in the scorer unit test.
- A tag-only change is an intentional fixture case. Decide and document whether it floors; do not leave the behaviour implicit.
- Unknown and unreadable are distinct from `match` and from each other. Collapsing them is a defect.
- Exit codes are a public contract once documented. Choose a code that does not collide with existing CLI exit codes, and record it in the operator guide in the same PR.
- Reuse the existing finding, evidence and confidence models. Do not bump the report schema version; the grounded block is additive and carries its own `live_context_version`.
- Respect Python 3.10-compatible code on a 3.11 runtime, Pydantic 2, SQLAlchemy 2 and current lockfiles. **No dependency installation is authorized by this story.**
- Prohibited in this slice and in this epic: any write, apply, destroy, tag, provision or remediate capability; account-wide inventory; scheduled drift; cost estimation. Reports remain advisory with `should_block=False`; the CI gate is a caller-opted exit code, not a blocking report.
- Epic independence: no import from `infra_automation/` or `services/infra_automation_*`.

### Project Structure Notes

`analysis/divergence.py` is a new analysis module consuming grounding results from `services/cloud_context_service.py`. It must not construct connectors or issue calls directly.

### Testing requirements

- Before changing constructors or schema, search the entire repository for direct instantiations and fixtures; update all of them. `analysis/risk_scorer.py` is high-blast-radius.
- Run `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh`, `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- Run `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` for the CLI gate and additive API fields.
- All fixtures are synthetic. Never commit real plans, real account identifiers, real ARNs or raw state.
- UI validation not applicable; divergence presentation is owned by 17.8.

### Completion and integration boundary

- Attach exact commands, results, versions and proof artifact locations per AC and mapped requirement. Independent review resolves findings before advancement.
- This slice closes only divergence detection, plan freshness, the severity floor and the CI gate. It does not qualify a production AWS profile and does not deliver blast radius, recoverability or UI value.

### References

- [RFC 0002](../../docs/rfcs/0002-live-environment-grounding.md)
- [Canonical feature PRD](../planning-artifacts/prd-live-environment-grounding.md)
- [Epic 17 stories](../planning-artifacts/epics.md)
- [Architecture Section 26](../planning-artifacts/architecture.md)
- [Epic 16/17 boundary plan](../planning-artifacts/epic-16-17-boundary-and-parallelization-plan.md)
- [Operator guide](../../docs/live-environment-grounding/README.md)
- [Project implementation context](../project-context.md)

## Dev Agent Record

### Agent Model Used
Codex with independent comparison, scoring, CLI, API and verification lanes.

### Debug Log References
- Story 17.3 merged into develop at `495d1d4` via PR #224. Story 17.4 runs on `feature/17-4-plan-reality-divergence`.
- Baseline integration tests failed before the CLI flags and retained analysis path existed. An independent review also identified the whole-submission screening gap. The synthetic cross-artifact regression failed before its fix and passed after it.

### Completion Notes List
- Compare a recorded plan with an already-retained same-project snapshot. Only known comparable facts enter the result. Explicit observed facts prove deletion and recreation in fixtures. Missing, partial, unsupported and denied observations remain unknown or unreadable.
- Divergence findings carry recorded, live and planned values. The report keeps exactly the evidence IDs minted for the retained snapshot and resource in the authorization transaction. The comparison screens private values from all submitted artifacts and configured provider credentials.
- Plan age uses the observation start time and configurable threshold. The default is 3,600 seconds. Security-relevant and destructive divergence applies a medium/caution floor with a deterministic briefing. Tags alone apply the floor when the planned operation is destructive. Narrative and reviewer feedback tests preserve the floor.
- The CLI gate exits 3 for confirmed divergence and 2 for an unresolved comparison. The API returns HTTP 409 with the advisory report ID and the corresponding code. Existing opt-out responses and report v2 remain compatible.
- Validation passed with 3,894 tests across 12 local CI shards and 3 skips, 2,342 root tests with 3 skips, 850 exact API/CLI/infra tests with 1 skip, and 204 focused tests. The network-disabled Python 3.11.17 image passed 16 tests and returned HTTP 200. Repo-wide Ruff, scoped Bandit, Python 3.10 grammar, and the comparison tests with execution-epic imports blocked passed.
- The [verification packet](../../docs/verification/live-environment-grounding/17-4/README.md) records commands and the headless walkthrough. UI validation not applicable. Production AWS acquisition and user-facing snapshot import stay in their owning stories.
- Review follow-up requires coverage of planned mutations to report a match. Name-based AWS identities need verified account and region scope. Stale observations, unproven chronology and incomplete planner output cannot pass the CI gate. The saved report preserves uncertainty for mixed outcomes and denial diagnostics for unusable observations. The deterministic caution path bypasses the narrative provider.
- Review follow-up passed 216 focused tests and 391 subtests, 3,906 tests across 12 local CI shards with 3 skips, and 851 API/CLI/infra tests with one skip. Root discovery ran 2,342 tests with three skips on retry. The initial run hit an unrelated process-tree recovery timeout that passed in isolation and in local CI. The SDK-free, network-disabled Python 3.11.17 image ran 27 tests and returned HTTP 200. Independent scoped verification passed 37 tests and 35 subtests. Full code review remains the next workflow.
- Re-review follow-up binds the gate and report to one shared parsed plan, rejects ambiguous or excluded plan selections, and leaves conflicting recorded states unverified. Denials require scope proof, and out-of-range UTC offsets cannot establish chronology.
- Report publication rechecks freshness after admission verification and on commit. Filesystem and DB write or commit failures roll back and preserve the HTTP 500 and CLI exit 1 persistence contract. The integrated tests cover the real HTTP/CLI error envelopes, rollback, and shared parse reuse.
- Re-review verification passed 257 focused tests and 405 subtests, 3,922 full local CI tests across 12 shards with 3 skips, 2,342 root tests with three skips, and 851 API/CLI/infra tests with one skip. The rebuilt network-disabled Python 3.11.17 image passed 43 tests and returned HTTP 200. Python 3.10 grammar, Ruff, scoped Bandit and an independent verification of the publication and error boundary passed.
- The 2026-11-27 follow-up leaves recorded AWS security group rules unresolved when the projection cannot verify them and preserves independently confirmed drift. It rejects contradictory no-ops and duplicate change identities, prevents pure creates from borrowing prior state, and leaves timestamps with nonzero sub-microsecond precision unverified. The existing report persistence error path now covers post-write evidence verification and retention rechecks through rollback.
- Six regression tests reproduced the four findings on the pre-fix sources. The fixed sources passed 268 focused tests and 422 subtests, all 12 local CI suites with 3,928 tests and three skips, root discovery with 2,343 tests and three skips, and the exact API/CLI/infra shard with 852 passes and one skip. The rebuilt offline Python 3.11.17 image passed 62 story tests and returned HTTP 200. Ruff, scoped Bandit, and Python 3.10 syntax validation passed. Mypy reported 13 fewer errors and zero new diagnostics. UI validation not applicable. See the [2026-11-27 verification packet](../../docs/verification/live-environment-grounding/17-4/README.md#2026-11-27-review-follow-up-verification).
- EC2 attachment drift now uses unordered recorded and observed VPC security group IDs and retains evidence for every live group. It applies the caution floor and gate exit 3. Missing, malformed, or screened evidence stays unresolved. Typed storage errors from snapshot row and schema reads survive repository translation, so post-write faults roll back and return HTTP 500 or CLI exit 1. Pre-write lookup faults still use the unavailable-evidence contract.
- The updated [verification packet](../../docs/verification/live-environment-grounding/17-4/README.md#ec2-attachment-and-snapshot-storage-fix-verification) records 286 focused passes and 446 subtests, all 12 local CI suites with 3,934 tests and three skips, root discovery with 2,345 tests and three skips, and the exact API/CLI/infra shard with 853 passes and one skip. The offline Python 3.11.17 image passed 100 tests and returned HTTP 200. Ruff, scoped Bandit, Python 3.10 syntax and OpenAPI checks passed. The 345 existing mypy errors were unchanged. UI validation not applicable.
- Git Flow closeout verified the full 27-file candidate against the prior validation, confirmed `origin/develop` still pointed to `495d1d4`, and independently rechecked both findings. Fresh closeout pytest passed 67 tests and 53 subtests. Ruff, scoped Bandit, and the complete diff whitespace check passed.

### File List
- `_bmad-output/implementation-artifacts/17-4-plan-versus-reality-divergence-and-ci-gate.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `analysis/divergence.py`
- `analysis/risk_scorer.py`
- `api/routes/analyses.py`
- `api/schemas.py`
- `cli/analyze.py`
- `cloud/aws/projection.py`
- `cloud/schema.py`
- `docs/live-environment-grounding/README.md`
- `docs/verification/live-environment-grounding/17-4/README.md`
- `docs/verification/live-environment-grounding/17-4/code-review.md`
- `models/repositories/cloud_snapshots.py`
- `services/analysis_service.py`
- `services/cloud_context_service.py`
- `services/divergence_service.py`
- `services/report_service.py`
- `tests/fixtures/live_environment_divergence/plan.json`
- `tests/fixtures/live_environment_divergence/snapshot.json`
- `tests/test_analysis/test_divergence.py`
- `tests/test_analysis/test_divergence_floor.py`
- `tests/test_api/test_divergence_gate.py`
- `tests/test_cli/test_divergence_gate.py`
- `tests/test_cloud/test_collection.py`
- `tests/test_services/test_divergence_observation_freshness.py`
- `tests/test_services/test_divergence_plan_intake.py`
- `tests/test_services/test_plan_reality_divergence.py`

## Change Log

- 2026-11-20: Implemented and verified the six divergence and CI-gate packets. Moved Story 17.4 to review.
- 2026-11-23: BMad Code Review requested changes. Story and sprint tracking returned to in-progress with seven action items.
- 2026-11-23: Fixed and verified all seven review findings. Story moved back to review.
- 2026-11-23: BMad re-review found six remaining issues and returned Story 17.4 to in-progress.
- 2026-11-23: Fixed and verified all six re-review findings. Story and sprint tracking returned to review.
- 2026-11-23: Closeout review found a remaining publication error boundary and a timestamp precision edge. Story returned to in-progress.
- 2026-11-26: BMad re-review reproduced both closeout findings and added two gate findings. Story remains in progress.
- 2026-11-27: Addressed all four open review findings, verified the regression and CI suites, and returned Story 17.4 to review.
- 2026-11-27: Re-review found two remaining gaps in EC2 comparison coverage and retained-snapshot database error handling. Story returned to in progress.
- 2026-11-27: Fixed EC2 attachment comparison and post-write repository error handling, completed validation, and returned Story 17.4 to review.
- 2026-11-27: Closed local review after independently verifying both fixes and checking the complete validated feature candidate for a PR to `develop`.
