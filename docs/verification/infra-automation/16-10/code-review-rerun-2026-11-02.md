# Story 16.10 code review rerun — 2026-11-02

**Final outcome: accepted.** R4 and subsequent R5 accounting/supervision findings
are resolved and independently reviewed. The reports below retain the earlier
changes-requested history. Current evidence: [resolution and qualification](r4-r5-resolution.md).

Outcome: **changes requested**. One High patch finding remains; story and sprint
are `in-progress`. The previously fixed ref/disk callback and durable clock-floor
regressions remain fixed, and the missing broad validation record is complete.

Review target: full working tree, including untracked files, on
`feature/16-10-targets-outbox-grants` against accepted Story16.9 baseline
`501d789460adccdb1765313f996df42583dc96a1`: 57 files, 12,251 additions and
98 deletions. This report is a review output, not another implementation file.

All three independent layers completed: Blind Hunter reported no actionable
issue; Edge Case Hunter and Acceptance Auditor independently reproduced the
same graph-material ordering defect. Their findings were merged. Triage:
0 decision-needed, 1 patch, 0 deferred. Four candidate concerns were dismissed:
explicit one-operation-per-approval, conservative lock retention, later-story
parent-run reconciliation and audit accounting outside the documented logical
retained-copy quota scope. No review layer failed.

## R4 — High / patch: later graph material callbacks invalidate earlier admission

Owned admission locations: `services/infra_automation_handoffs.py:478–484`
(dispatch/consume/action) and `:725–728` (prepare).
Underlying helper: `services/infra_automation_decisions.py:565–583` and
`:1105–1115`. Violates AC2/AC5 and IAU15-FR-035.

The final `recheck_approved` still resolves material callbacks sequentially.
`_recheck_graph` retains the selected material before `_eligibility` resolves
required receipts. That loop projects each receipt's eligibility into succeeded
state, then refreshes only clock/deadline facts. A later required ancestor's
material callback can invalidate the selected decision's live custody after its
last material check. The final handoff `_authority_tail` checks retained binding
bytes, reviewer authority, graph and deadlines, without detecting that custody
change. It therefore accepts a stale current-material result.

This is an owned handoff-admission defect even though receipt traversal is shared
with the earlier decision story: Story16.10 introduces the four consumers that
must deny authority after the selected exact-plan custody is revoked. It is not
a demand for the later production collector or receiver integration.

### Reproduction

Use the existing `AncestorDeadlineHandoffTests` fixture, which has required
serial decisions. Complete preceding stages normally, then wrap its material
port before the phase under test:

```python
original = case.service.material_port

def material(session, run, step, previous):
    if step == "decision-a":
        case.material = replace(
            case.material,
            live=case.material.live.model_copy(update={"custody_available": False}),
        )
    return original(session, run, step, previous)

case.service.material_port = material
```

Observed material-call order is `decision`, `decision`, `decision`, `decision-a`.
The last callback returns valid ancestor material while revoking selected
custody. Four separate fixtures reproduce:

```text
PREPARE ACCEPTED with selected custody= False prepared
DISPATCH ACCEPTED custody= False sent= 1
CONSUME ACCEPTED custody= False consumed
ACTION ACCEPTED custody= False consumed
```

The leader reran all four counterexamples independently with
`./.venv/bin/python /tmp/review_acceptance_probe.py`; output is retained in
`/tmp/story16-10-rereview-custody.log`. Edge-layer preparation proof is also in
`/tmp/repro_edge16_10.py`. No production ports, repository edits, uploaded binary
artifacts or real infrastructure are used by these reproductions.

Required correction: make final admission consistent across the selected
material and every mandatory ancestor after all material callbacks, including
current custody/evidence/binding generation checks. Moving ref and disk callbacks
earlier does not close this nested callback edge. Do not rely on an arbitrary
number of repeated callback passes as a proof of a consistent authority snapshot.
Add selected/ancestor invalidation regressions at prepare, dispatch, consume and
action, with transaction rollback/no-send/no-consume assertions.

## Verification and limits

- Fresh focused pytest on handoff service and both new API modules:
  **67 passed**, 39 subtests, 30.77s.
- Ruff lint: passed. Repo-wide Ruff formatting:474 files passed.
  `git diff --check`: passed.
- Verified source hashes match the completed fix-workstream evidence; no
  production Python/config/generated-TypeScript source changed in this review.
- Retained complete broad evidence: root unittest1,447 tests, OK (2 skips);
  exact API/CLI/infra pytest709 passed/1 skipped; fresh full local CI2,893 tests
  across10 directories, OK (2 skips); production Python3.11 focused164 tests,
  OK (1 optional skip), plus runtime smoke. Commands/results remain in
  `results.md`. These passing suites do not cover the new R4 counterexample.
- The earlier one-off worker-shutdown error and successful six isolated checks
  plus full rerun remain documented, rather than reclassified as a handoff bug.
- AC1/AC3/AC4/AC6 showed no additional concrete defect in the declared scoped
  registry/grant/transport/lock contract. UI validation not applicable.
- Real receiver, collector custody and host-power-loss qualification remain
  outside this story's declared scope.

One unchecked patch action item was added to the story. Production code was not
modified or simplified. No commit, push or PR was performed because a High
review follow-up remains open. **Blocked: story still in-progress after review.**
BMad Help's next step is `bmad-dev-story` for R4, followed by a fresh review.


## Third review run — unchanged source, 2026-11-02

Outcome remains **changes requested**. All reviewed production, configuration,
generated TypeScript and test hashes match the preceding review: no R4 fix has
been applied. The full current diff contains58 files,12,379 additions and96
removals; the additional file is the prior review report.

All three fresh review layers completed and identified the same High R4. Edge
and acceptance reviewers independently reran all four counterexamples; the blind
review confirmed the open defect from the diff without executing source. The
leader reran `./.venv/bin/python /tmp/review_acceptance_probe.py` and recorded
`/tmp/story16-10-rereview-round3-custody.log`: prepare, dispatch, consume and
action admission still succeed with selected custody unavailable (2.087s total).
These are unsafe behavior reproductions, not passing acceptance assertions.

No additional distinct actionable finding was confirmed. Equivalent reports
were merged into the existing R4; no duplicate action item was added. Triage:
1 High patch,0 decision-needed,0 deferred. No layer failed.

`./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .` (474 files) and
`git diff --check` passed. Broad suites were not repeated because their reviewed
source is unchanged and the confirmed R4 already prevents acceptance. The
completed prior broad evidence and its coverage limitations remain recorded in
`results.md`.

Only review documentation/runtime state was updated. The story and sprint remain
`in-progress`, with R4 unchecked. No production code was modified or simplified;
no commit/push/PR was performed because R4 remains open. Next BMad Help step:
`bmad-dev-story` to address R4, followed by a fresh review.


## Final closeout review — 2026-11-02

R4 is fixed with the exact-scope, qualified source-domain/generation fence around
all material callbacks; selected/ancestor/ABA invalidations deny all four
boundaries. New tests and all three independent review layers confirm closure.
A subsequent Medium R5 accounting finding is fixed by reserving future mutable
handoff/lock metadata up front; quota boundaries and rollback are tested.
The validation-derived macOS EPERM exit-sentinel race is fixed without relaxing
positive group-death confirmation, dirty-slot or deadline requirements; its
negative/positive tests and20 real cancellation repetitions passed.

Final qualified Linux/Python3.11 full CI exited0:2,912 tests,6 optional skips;
root1,466 tests,6 skips; exact shard709 passed/1 skip. The post-run562-file source
manifests matched. Optional schema checks separately passed on the host.
Nonroot production image196 tests, OK (one optional skip), plus startup smoke.
Mypy13 source modules, Ruff lint/format474 files, security gate and whitespace
checks passed. Full commands, scope and logs are in r4-r5-resolution.md.

No remaining actionable High/Medium finding. All prior findings are resolved;
story/sprint are done for the declared scoped contract. Real provider/receiver/
collector and host-power-loss qualification remain later-story ownership.
Git Flow feature branch verified; the user authorized commit/push/PR to develop.
