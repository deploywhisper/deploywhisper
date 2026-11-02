# Story 16.10 code review — 2026-11-02

Latest outcome: **accepted after R4/R5 and supervision corrections**. All
findings are resolved. Current [resolution and qualification](r4-r5-resolution.md)
supersedes the historical review outcomes below.

Original review outcome: **changes requested**. After fixes and completed validation,
all 3 findings are resolved; story and sprint are now `review`.
Triage: 0 decision-needed, 3 patch, 0 deferred; 2 candidate concerns dismissed as intended behavior.
Review target: all working-tree changes on `feature/16-10-targets-outbox-grants`
against `501d789`; 56 files, 11,689 additions and 79 deletions, including untracked
implementation files. Full-spec BMad review used independent Blind Hunter,
Edge Case Hunter and Acceptance Auditor layers. All layers completed. Duplicate
custody findings were merged; conservative lock retention and the documented
one-operation-per-approval restriction were excluded as intended behavior.

## Findings

### R1 — High / patch: refresh custody after workflow-ref callbacks

Location: `services/infra_automation_handoffs.py:471–508`, and preparation at
`647–657` / `757–759`. Violates AC2 and AC5 / IAU15-FR-035.

`recheck_approved` resolves live evidence/custody before `ref_port`. After that
callback, the final checks refresh target, receiver, policy, reviewer and
retained deadlines, but do not re-evaluate current material/custody. Therefore
custody lost during the ref lookup can still authorize preparation, sending,
one-use consumption and the receiver's subsequent action admission.

Reproduced with four independent existing `HandoffServiceTests` fixtures. For
each phase, complete preceding phases normally, then install this ref callback:

```python
def lose_custody(snapshot):
    case.material = replace(
        case.material,
        live=case.material.live.model_copy(update={"custody_available": False}),
    )
    return snapshot.definition.pipeline_workflow_revision
```

All four calls returned success with `authorization_kind=exact_plan` and current
`custody_available=False`: prepare → `prepared`; dispatch → `delivery_unknown`;
consume → `consumed`; authorize_action → `consumed`. The fixture's material port
reads the replaced material, so a fresh material check would deny it. This is
the same admitted callback-mutation model already used by the feature/reviewer
and clock regressions, not a claim that default unavailable ports enable live
production dispatch.

Required fix: ensure live material admission follows ref lookup and any other
callbacks that can invalidate it, while preserving final target, policy, scope,
receiver and clock checks. Add denial/rollback regressions at all four phases.
Standalone local reproduction: `/tmp/story16-10-review-custody.py`; output:
`/tmp/story16-10-review-custody.log`.

### R2 — Medium / patch: retain successful action-admission clock observations

Location: `services/infra_automation_handoffs.py:1035–1036`.
Violates the retained monotonic authority-floor constraint in project context
and the story's claimed refreshed action-boundary checks.

`authorize_action` discards `_live`'s returned observation time. Unlike dispatch
and consume, it never advances the operation's retained `last_observed_at`.
A later clock regression can therefore pass another authority check using an
earlier apparent time rather than fail closed.

Reproduction: prepare, dispatch and consume at t0; authorize_action at t0+60s;
regress the fixture clock to t0+30s and authorize_action again. Both calls return
`consumed`, and the persisted operation floor remains t0. This finding concerns
clock regression, not the intentional repeatability of online admission or
receiver-owned exactly-once fencing.

Required fix: transactionally retain successful authority-observation time and
reject a subsequent earlier clock, including after service restart; add a
regression without creating another grant/receipt/action authorization identity.
Standalone local reproduction: `/tmp/story16-10-review-clock.py`; output:
`/tmp/story16-10-review-clock.log`.

### R3 — Medium / patch: complete the required broad validation record

Location: `docs/verification/infra-automation/16-10/results.md:90–107` and story
Required implementation verification / Dev Agent Record.

The final broad-results marker is empty and the record promises results below
that are absent. No successful final root unittest discovery or `ci-local.sh`
run is recorded. The earlier broad run is explicitly disqualified because it
overlapped source changes. The exact API/CLI/infra shard passed independently
in this review (709 passed, 1 skipped). Focused tests do not discharge the remaining mandatory
story checks. Complete those runs after the fixes, record actual final results,
and reconcile the unchecked task/verification checklist before acceptance.

## Review validation

- Story-focused pytest: **156 passed**, 380 subtests, 38.52s (host Python 3.14).
  Scope: all 15 modules listed in the development qualification record.
- `./.venv/bin/ruff check .`: passed.
- `./.venv/bin/ruff format --check .`: passed; 474 files formatted.
- `git diff --check`: passed before report edits; rechecked at completion.
- Custody and clock reproductions: both confirmed the defects described above.
- Broader infra-automation pytest: intentionally interrupted after 216 passed,
  816 subtests, 149.13s during existing parent-process recovery coverage to
  prioritize the complete story-focused run. This is a partial run, not a pass
  for that suite and not evidence of a test failure.
- `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: **709 passed, 1 skipped**, 2,316 subtests, 397.40s.
  Log: `/tmp/story16-10-review-api-cli-infra.log`. This closes the review-time
  shard check; rerun after production fixes.
- Root unittest discovery and full local CI were not rerun by this review.
- UI validation not applicable: no rendered UI changes in this backend slice.

## Original review handoff

No production code was modified or simplified during review. Three patch action
items are recorded in the story; no product decision is required. Per BMad Help's
CR → DS cycle, address these findings through `bmad-dev-story`, then rerun
`bmad-code-review`. The existing Git Flow feature branch is compliant; no commit,
remote push or PR was made because story follow-up remains open.


## Fix verification — 2026-11-02

R1 and R2 have been corrected on the existing story branch; R3's final broad
checks completed successfully against frozen source. The original findings above remain
as the review history, not a statement that the corrected source still exhibits
them.

- Final material admission now follows workflow-ref lookup in `_live`, inside
  the receiver-scoped report context. Preparation's final admission follows both
  ref lookup and the retained-byte capacity probe. Target, receiver, human,
  policy, graph and refreshed clock floors remain after material callbacks.
- Successful action admission advances the retained observation using the
  existing same-state operation CAS only when time advances. Its transactional
  `handoff_action_checked` audit preserves before/after state-digest chaining;
  failure rolls back the observation. Repeating at the same instant creates no
  mutation. Grants, receipts, outbox and operation binding identity are unchanged.
- Eight regression methods reproduce all four ref-boundary races for custody,
  evidence and binding changes, both disk-probe custody races, restarted-service
  clock rollback, same-clock repeatability, audit rollback and terminal chaining.
- Red proof before the fixes: 14 failures reproduced in the first six methods.
- Green handoff service suite: 60 tests passed, 30 subtests, 26.20s.
- Independent read-only source/test re-review found no remaining R1/R2 defect.
- Final root unittest: 1,447 tests run, OK (2 skips), 690.308s.
- Exact API/CLI/infra shard after fixes: 709 passed, 1 skipped; 2,316 subtests,
  516.76s.
- Fresh full local CI: exited 0; 2,893 tests across all 10 directories, OK (2 skips),
  including 690 infra-automation and 1,232 service tests. Ruff, pip, Bandit gate,
  compileall, skill and prompt-injection checks passed. Scoped mypy passed 10
  story modules; repo-wide formatting passed 474 files.
- Production Python 3.11 image: all 164 focused tests run, OK (one optional skip),
  88.371s; isolated startup/health/OpenAPI/schema035/nonroot/no-Node smoke passed.
- First CI attempt had one worker-termination test error plus cleanup errors;
  six isolated runs and the fresh full run passed. No supervision guard was
  changed. Both attempts remain documented in `results.md`.
- [x] R1 resolved: final material/custody admission follows ref/disk callbacks.
- [x] R2 resolved: advancing action observations persist transactionally with
  audit chaining and no replacement grant/receipt.
- [x] R3 resolved: required broad checks completed, actual results persisted,
  task/verification checklist and story/sprint status reconciled.
- No outstanding review action item remains. Ready for fresh formal review;
  no remote push or PR was made in this fix workstream.
