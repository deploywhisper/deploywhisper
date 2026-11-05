---
title: 'Allow services CI to finish after its tests pass'
type: 'bugfix'
created: '2026-11-05'
status: 'done'
route: 'one-shot'
---

# Allow services CI to finish after its tests pass

## Intent

**Problem:** PR #213's [push run](https://github.com/deploywhisper/deploywhisper/actions/runs/41981220621/job/127091923970) passed all 1,232 services tests and 2,248 subtests in 866 seconds, then exceeded the 15-minute job budget during finalization. GitHub's annotation explicitly reports the maximum execution time; the required summary correctly failed the cancelled job.

**Approach:** Give only the services shard a 25-minute budget, including setup, coverage upload, cleanup, and hosted-runner variation. Preserve the other four 15-minute budgets, test targets, test-level deadlines, and failure gates. Update the existing workflow guard and CI documentation. UI validation not applicable: no application or UI behavior changes.

Focused verification: 30 workflow/dependency/governance tests and 25 subtests passed; repository-wide Ruff lint and format checks passed (555 files), as did `git diff --check`. Independent adversarial review identified the old literal-timeout assertion; its repair passed re-review and the focused test. Full smoke and API/CLI/infra verification run separately; the new hosted run is the final timeout check.

## Suggested Review Order

1. [Workflow budget](../../.github/workflows/ci.yml) — services override with a 15-minute default for other shards.
2. [Existing workflow guard](../../tests/test_infra/test_supply_chain_remediation.py) — enforce all five effective shard budgets.
3. [CI guide](../../docs/ci.md) — record the observed timeout and budget rationale.
