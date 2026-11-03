# Story 16.11: GitHub Receiver and Outcome Reconciliation

Status: in-progress
Preparation: refined
Release: v1.5.0

## Story

As an operator, I want to hand approved evidence to a qualified GitHub receiver and reconcile its outcome, so that remote acceptance is not confused with completion or blindly retried.

## Entry gates and slice boundary

- Release priority: P0 feature work for v1.5.0. **Blocked for implementation** until Story 16.0 has recorded public RFC/CODEOWNERS acceptance, executable identity/fencing/isolation/custody/receiver qualification and final interface decisions; planning adoption alone is not authorization evidence.
- Hard earlier dependencies: **16.9, 16.10**, accepted and verified before advancing this story. These dependency results are currently unresolved; refined preparation does not mean ready-for-dev. No prior implementation learning is available for the new Epic 16 story set.
- Promote only after contract freeze, earlier dependency evidence, bounded task ownership/re-estimation and independent story review. Preserve IDs and backlog status; no feature/release implementation is claimed here.

## Acceptance Criteria

1. **AC1:** Given a permitted bound operation and protected reviewed workflow branch/tag, when the isolated versioned GitHub adapter dispatches, then HTTP 200 run ID/URLs record acceptance only; IaC source SHA and receiver workflow identity/ref remain distinct.
2. **AC2:** Given exact_plan synthetic immutable saved bytes in qualified protected local custody, when the self-hosted receiver admits a grant, then it validates current authority, operation/source/payload/raw digest/handle/expiry and actual file bytes; advisory_request cannot authorize apply and cloud-hosted missing-custody receivers deny.
3. **AC3:** Given crash after server consumption or receiver durable operation creation but before action, when restarted, then the same stable operation recovers from its record and server receipt and returns existing status; no replacement grant, blind redispatch or second action is created.
4. **AC4:** Given changed payload on reused idempotency/operation identity, lost dispatch response, mismatched run/source or replayed callback, when resumed/reconciled, then conflicts/replay deny, possible acceptance becomes delivery_unknown and bounded correlated reads/receipts resolve it.
5. **AC5:** Given disable, revocation, restore, expiry or moved receiver ref before consume/new action, when receiver admission/resumption occurs, then authority denies; already-begun action remains reconciled honestly and target locks survive uncertainty.
6. **AC6:** Given accepted/running/terminal/unknown delivery or cancellation request, when the composed run UI updates, then each fact is distinct, unknown has reconciliation guidance and no blind resend, and cancellation never claims external work was undone.

### Requirement Traceability

Coverage intent: Delta over the v1.4.0 baseline. These exact mapped requirements are acceptance obligations; mapping is not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| IAU15-FR-017 | Disable, revoke or restore epoch changes must invalidate unconsumed grants and prevent new run starts, collection claims, dispatch or grant consumption while preserving read and reconciliation for accepted external work. | Disable/revoke/restore-before-dispatch-or-consume race matrix |
| IAU15-FR-018 | Persist run/step transitions and explicit `stopped_by_gate`, `expired`, `timed_out`, `cancelled`, `failed`, `succeeded` and `delivery_unknown` outcomes across restart. | Crash at each transition with state recovery assertions |
| IAU15-FR-020 | Retry only declared safe/idempotent local work within finite deadlines; persist idempotent outputs and reconcile uncertain external work instead of blind resend. | Retry/deadline/duplicate-completion and dropped-response tests |
| IAU15-FR-032 | Enforce evidence freshness at decision, dispatch and receiver consumption; default collection TTL is 60 minutes unless an audited stricter policy applies. | Clock/TTL boundary and delayed-consume tests |
| IAU15-FR-035 | Invalidate eligibility when evidence, revision, source, scope, target, policy, membership or custody changes, expires or is superseded; no emergency bypass or delegated approval in P0. | Revocation/supersession/custody-loss and bypass-denial matrix |
| IAU15-FR-038 | Issue one-use scoped receiver grants bound to the decision tuple, operation, expiry and live epoch; reject duplicate/replayed or altered consumption. | Grant replay/expiry/epoch/source/digest tests |
| IAU15-FR-039 | Consume grants into a durable receiver operation record before external action so a consume-before-action crash resumes the same operation without a second action. | Receiver crash at consume/start/completion boundaries |
| IAU15-FR-040 | Distinguish dispatch acceptance, externally observed completion and delivery_unknown; reconcile unknown outcomes through receiver receipts and never report dispatch acceptance as successful deployment. | Lost-response/poll/receipt fault matrix and UI semantic tests |
| IAU15-FR-041 | Authorize exact-plan handoff only when the qualified self-hosted receiver can verify the original immutable saved-plan bytes in protected local custody by opaque handle, raw digest and expiry; no server/public-artifact plan storage, and replanning requires fresh evidence/approval. Upload-only advisory receipts never authorize apply or require invented repository provenance. | Real custody access/restart/overwrite/symlink/expiry/replan spike and receiver tests |
| IAU15-FR-043 | Verify receiver callback signatures, operation/run/source identity and replay protection using the pinned GitHub adapter version and protected branch/tag dispatch ref. | API-version, callback replay and mutable-ref substitution contract tests |
| IAU15-NFR-001 | The declared crash/race corpus must lose no committed run/decision state and produce no unauthorized or duplicate receiver action, including stale attempts, unknown delivery and restore epochs. | Published fault-injection results at every persisted boundary |

## Tasks / Subtasks and bounded ownership

- [ ] **Packet 1 — Integration owner: versioned GitHub adapter (AC 1,4).** Owned output: `integrations/github/infra_automation_adapter.py (planned), config.py`.
  - [ ] Pin 2026-03-10 dispatch, parse 200 workflow_run_id/run_url/html_url, protect/resolve branch or tag and bind reviewed workflow identity; sandbox plus legacy-client isolation contract tests.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 2 — Receiver owner: durable online admission (AC 2,3,5).** Owned output: `examples/infra-automation/receiver/ and typed infra_automation receiver protocol (planned)`.
  - [ ] Persist receiver operation before action, server one-use consumption receipt and binding; crash windows at consume/start/completion resume same operation; duplicate returns status, altered bindings conflict.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 3 — Custody/security owner: synthetic exact-byte fixture (AC 2,3,5).** Owned output: `protected temporary local custody fixture, receiver file-admission helper and docs/infra-automation`.
  - [ ] Create owner-restricted immutable synthetic bytes, no-follow handle read, raw digest/expiry/source checks and restart recovery; reject overwrite/symlink/lost custody and no replan under old grant.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 4 — Service owner: receipt/callback reconciliation (AC 3–5).** Owned output: `infra_automation/reconciliation.py, services/infra_automation_service.py and typed route (planned)`.
  - [ ] Verify callback signature/sequence/nonce, operation/run/source binding; bounded polling and delivery_unknown, cancellation request versus confirmed stop; persist outcomes retaining uncertain locks.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.
- [ ] **Packet 5 — UI/test owner: external outcome UX (AC 1,4–6).** Owned output: `existing automation run screen, frontend/e2e, tests/test_api and tests/test_infra_automation`.
  - [ ] Render acceptance/observed completion/unknown separately; test no resend and lock/cancellation messaging, fault matrix plus composed keyboard/axe/screenshots.
  - [ ] Attach focused proof for the referenced ACs, implementation docs and reviewer findings before packet acceptance.

Each packet is a bounded review unit under this stable story ID; split large packets after 16.0 estimation instead of silently broadening scope. One story branch follows Git Flow; coordinate shared-file edits and do not revert other work.

### Review Findings — 2026-11-03 re-review

- [x] [Review][Patch][P2] Aggregate effective tag protections across applicable rulesets — `integrations/github/infra_automation_adapter.py:192` requires update and deletion restrictions inside a single ruleset. Two active applicable no-bypass rulesets that separately prohibit updates and deletion protect the tag under GitHub's aggregated enforcement, but this adapter returns `github_target_unqualified`. Accumulate qualified rule types across rulesets and add a regression for split protection, retaining missing-rule/bypass/condition denial. AC1 protected-tag support. See `docs/verification/infra-automation/16-11/code-review-2026-11-03.md`. Resolved: union qualified applicable rule types, with red/green dispatch regression covering both ruleset orders and 18 pre-POST rejection cases. Independent scoped review found no issues; full verification is in `docs/verification/infra-automation/16-11/review-fixes-2026-11-03.md`.

## Dev Notes

- This broad story has five bounded owned packets; each needs its own reviewable PR/output/proof. Freeze receiver_protocol_version 1, typed operation/consumption receipt, callback state/sequence and redacted error contract in 16.0 before coding.
- 16.11 qualifies protected immutable synthetic custody before 16.14; no forward collector acceptance dependency. 16.14 and 16.19 must later prove real collected-plan integration. A test-double receiver alone cannot satisfy actual local custody admission.
- Server grant consumption and receiver durable creation have a crash gap: recover the same operation through the server consumption receipt, never mint a new grant. Recheck current authority before beginning/resuming any new action. A started uncertain action is reconciled rather than automatically re-executed.
- Existing integrations/github/app_service.py pins 2022-11-28 in _github_api_request; isolate new adapter version, test old behavior unchanged and never upgrade unrelated OAuth/check-run callers silently.
- GitHub REST dispatch documentation reviewed 2026-10-07 confirms 2026-03-10 request examples, protected branch/tag ref semantics and 200 response containing workflow_run_id/run_url/html_url. Ref is a receiver workflow branch/tag, not the immutable IaC commit. Restrict dispatch inputs to the frozen schema and documented limit.
- Use operator-owned self-hosted receiver with exact immutable saved-plan bytes accessible under opaque custody handle. No public/server plan storage, reconstruction from sanitized JSON or replan using old approval. Collector and receiver infrastructure credentials are separate, never sent to DeployWhisper.
- The app owns integration/protocol/example only; Marketplace action runtime remains deploywhisper/analyze-action. No universal exactly-once deployment claim. Real sandbox tests require operator-configured test credentials; record unavailable proof honestly rather than treating mocks as live dispatch.

### Project Structure Notes

- Planned modules are additions under the established Python/service/API/repository and React boundaries, not present-day implementation claims. Reuse `api/errors.py` ApiRoute/ApiError, `api/schemas.py`, `models/database.py`, `models/tables.py`, repositories and `migrations/versions/`; inspect head before allocation.
- Introduce only entities necessary for this slice; never precreate all automation tables. Keep deterministic findings in the shared analysis core, optional AI downstream and privileged execution outside FastAPI. No new dependencies without a recorded approved decision.
- Interface names/resources are design obligations pending 16.0 freeze, not permission to invent final route/schema contracts. Add docs and tests with behavior; do not defer slice coverage to 16.19.

## Required implementation verification

- [ ] Register new `tests/test_infra_automation` directories in `scripts/ci-local.sh` and affected GitHub discovery/shards; root discovery alone skips non-package test directories.
- [ ] For every Pydantic/schema/dataclass/constructor change, use repository-wide `rg` searches for direct instantiations/fixtures and update all consumers, including CLI/agent/action/report compatibility where affected.
- [ ] Run `./.venv/bin/python -m unittest discover -q`, story-focused tests and exactly `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` for affected API/CLI/infra contracts.
- [ ] Run `./.venv/bin/ruff check .`, **`./.venv/bin/ruff format --check .` repo-wide**, `bash scripts/ci-local.sh` and `git diff --check`; add applicable static/security/type checks. Record commands and actual results rather than assumed passes.
- [ ] Run `npm run ui:typecheck`, `npm run ui:test`, `npm run ui:build`; then `docker compose up -d --build`, wait for `http://localhost:8080/api/v1/health`, seed synthetic authorized API data and run `BASE_URL=http://localhost:8080 npm run test:ui-review` with new journey coverage.
- [ ] Run `BASE_URL=http://localhost:8080 RUN_UI_A11Y=1 bash scripts/ci-local.sh` for keyboard/axe critical/serious coverage; capture required 1440/760-width screenshots from root SPA routes and permanent `/reports/{id}` links, then `docker compose down`.
- [ ] Record browser commands/results/screenshots before review. Vite dev server, legacy prefixed routes and existing report tests alone do not establish this story's browser acceptance. Backend-for-UI behavior requires a separate labeled PR.

## References

- [Canonical feature PRD](../planning-artifacts/prd-infra-automation.md), [exact requirement registry](../planning-artifacts/infra-automation-requirement-dispositions.json) and [Epic 16](../planning-artifacts/epics.md).
- [Architecture §25](../planning-artifacts/architecture.md#25-v150-infrastructure-automation-architecture-amendment), especially slice qualification §25.12; [mandatory project context](../project-context.md).
- [Readiness gates IR-01–IR-06](../planning-artifacts/implementation-readiness-report-2026-10-07-infra-automation-v1.5.0.md) and [release sequencing](../planning-artifacts/infra-automation-v1.5.0-release-plan.md).
- [Feature UX contract](../../docs/design/infra-automation-ux.md), [UX authority](../planning-artifacts/ux-design-specification.md), [v3 visual authority](../../docs/design/deploywhisper-redesign-v3.jsx) and [RFC 0001](../../docs/rfcs/0001-infra-automation-preflight-and-handoff.md).

## Dev Agent Record

### Agent Model Used

Codex — bmad-dev-story; ordered packet implementation with bounded native
readiness, integration and independent review lanes.

### Implementation Plan

- Entry reassessment: clean develop0e197ce includes accepted/merged16.10 PR206;
  accepted16.9 is501d789 and16.0 qualification/governance is done. Original
  unresolved preparation prose is historical; owning interface refinement and
  per-packet proof are being recorded before coding.
- Freeze additive server HTTP/auth/observation contracts around unchanged
  receiver-v1 wire, and preserve legacy GitHub2022 API calls. Implement packets
  in story order; each gets separate reviewable output/proof. Isolate backend
  and UI work so backend-for-UI behavior can ship in its own labeled PR.
- Real GitHub sandbox identifiers/credential reference were requested. Continue
  deterministic adapter/custody/receiver/recovery tests while waiting; do not
  substitute doubles for live dispatch acceptance or expose bearer/secret values.


### Debug Log References

- Entry and packet-order assessment:
  `docs/verification/infra-automation/16-11/entry-readiness.md`.
- Packet 1 focused proof and independent review:
  `docs/verification/infra-automation/16-11/packet-1-review.md`.
- Adapter contract, operator configuration and explicit sandbox invocation:
  `docs/infra-automation/github-adapter-v1.md`.
- Local red/green scratch output:
  `/tmp/story16-11-packet1-red.log`, `/tmp/story16-11-packet1-green.log`.
- Broad regression output: `/tmp/story16-11-unittest.log` (1,484 tests, 2 skips),
  `/tmp/story16-11-ci-shard.log` (709 passed, 1 skipped, 2,316 subtests), and
  `/tmp/story16-11-ci-local.log` (exit 0; 2,931 tests in all 10 directories,
  2 existing skips). Root/shard preceded the last internal strict-version fix;
  final focused 46-test host/Linux runs and full CI include that fix.
- Final scoped mypy and Bandit, repository Ruff lint/format (477 files), pip
  consistency, compileall, skill matrix, prompt-injection and diff checks pass.
  See the packet proof for exact commands, profile limits and review corrections.

### Completion Notes List

- Dependencies 16.0/16.9/16.10 are accepted; story and sprint tracking are now
  in progress on the Git Flow feature branch. Original preparation-only
  dependency statements above are superseded by the entry assessment.
- Packet 1 local implementation adds a version-isolated adapter, typed internal
  acceptance/observation facts and bounded fixed-resource GET support. Reuses
  existing credential/origin configuration and pinned transport. No dependency,
  frozen receiver wire, legacy App client or production delivery-port change.
- Focused red/green verification: final 46 tests passed, including the added
  strict-integer DTO version regression. Independent local packet
  review found no remaining actionable findings. Ruff, repository formatting
  and focused Bandit checks passed; full command results are in the packet proof.
- Full local CI passed all 10 test directories (2,931 tests; 2 existing skips).
  All checks available for the current adapter-only diff are complete. These
  results do not qualify live GitHub dispatch or the unimplemented packets.
- Packet 1 remains unchecked: its required real sandbox proof has not run.
  Operator-owned repository/workflow, protected reviewed ref/SHA and a dedicated
  configured credential reference were requested; secret values were not.
  General GitHub CLI authentication does not select this qualification target.
- The dev-story workflow requires completion of the current task before the
  next, and halts when required configuration is missing. Packets 2–5 remain
  unimplemented and unchecked behind this gate. No receiver, custody, callback,
  parent reconciliation or external action qualification is claimed.
- UI validation not applicable to the current adapter-only changes. Whole-story
  AC6 and required composed browser/UI validation remain outstanding; the story
  is not ready for review or closure.

### Review Fix Verification — 2026-11-03

- Resolved the sole P2 finding by accumulating effective tag restrictions across
  qualified applicable rulesets. Existing admission checks remain intact.
- Regression reproduced the failure before the fix; final focused unittest and
  pytest runs passed 47 tests (270 pytest subtests). Independent review: no findings.
- Exact API/CLI/infra pytest shard: 709 passed, 1 skipped, 2,316 subtests.
- Final root unittest: 1,486 tests, 2 skips. Full local CI: exit 0,
  2,932 tests across all ten directories, 2 skips. Mypy, focused Bandit,
  repository Ruff lint/format and diff checks passed.
- Sandbox process inspection restrictions caused the first broad runs to fail
  worker termination checks; a representative failure passed outside the
  sandbox. Final broad runs used that access plus test-only
  `LLM_API_BASE=http://127.0.0.1:1` to avoid live local inference. No configuration
  files changed. Full command/results and limitations:
  `docs/verification/infra-automation/16-11/review-fixes-2026-11-03.md`.
- UI validation not applicable. Live sandbox dispatch and Packets 2–5 remain
  outstanding; story stays in progress. No commit/push performed.

### File List

- `_bmad-output/implementation-artifacts/16-11-github-receiver-and-outcome-reconciliation.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `infra_automation/github_contracts.py`
- `infra_automation/target_transport.py`
- `integrations/github/infra_automation_adapter.py`
- `tests/test_infra_automation/test_github_adapter.py`
- `tests/test_infra_automation/test_target_transport.py`
- `docs/infra-automation/github-adapter-v1.md`
- `docs/verification/infra-automation/16-11/entry-readiness.md`
- `docs/verification/infra-automation/16-11/packet-1-review.md`
- `docs/verification/infra-automation/16-11/code-review-2026-11-03.md`
- `docs/verification/infra-automation/16-11/review-fixes-2026-11-03.md`

External contract: [GitHub REST workflow dispatch](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event), checked 2026-10-07; reverify before implementation if the API contract changes.

## Change Log

- 2026-11-02: Reassessed merged dependencies; began ordered Packet 1 with local
  adapter/transport regression proof and independent review. Live sandbox
  configuration/evidence remains required before packet acceptance and Packet 2.

- 2026-11-03: Re-ran bmad-code-review over the current Packet 1 diff with
  blind, edge-case and acceptance review layers. One reproduced P2 tag-rule
  aggregation defect recorded as an action item; no production edits applied.
  Story remains in progress; live sandbox and Packets 2–5 remain outstanding.

- 2026-11-03: Fixed the sole reviewer P2 tag-rule aggregation finding, added
  red/green safety regressions and completed independent review plus full
  validation. Review checkbox resolved; live qualification/later packets remain.

### Git Flow Publication Scope — 2026-11-03

The owner requested staging, commit, push and PR after the reviewer fixes.
Publication covers only the locally verified Packet 1 adapter, regression tests,
contracts and review evidence on `feature/16-11-github-receiver-reconciliation`,
targeting `develop`. The PR is a draft because Packet 1 live sandbox proof and
Packets 2–5 remain open. This publication does not close the story or qualify a
production receiver. The branch matched fetched `origin/develop` at `0e197ce`
before committing; final Ruff lint/format and diff checks passed.
