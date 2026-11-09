# Story 16.17 formal code review — 2026-11-07

Initial outcome: **changes requested**. Both findings are now resolved; final fixes and passing validation are recorded in [review-fixes.md](review-fixes.md). Story and sprint entry: `review`.
Review range: `2fef718..51bb952` (100 files, 10,156 insertions / 104 deletions).
Full story/spec review; runtime code was not changed by this review.

The blind adversarial and acceptance layers completed independently. The edge
layer supplied interim path analysis but failed before its final report; the
leader independently reproduced the clock issue below. Do not interpret this as
an all-layers clean review. The overlapping clock observations are consolidated
into CR17-1. Speculative upload/retention concerns were dismissed (two candidate
concerns; no confirmed defect in the changed behavior). No pre-existing findings
were deferred and no product decision is required.

## CR17-1 — P1: effect checks do not advance the durable clock floor

Category: patch. Sources: blind + edge interim analysis + leader verification.
Location: `services/infra_automation_trigger_authority.py:169–176,515–520`.
Constraint: live machine authority and rollback protection, including the explicit
promise in `docs/infra-automation/triggers.md:89` that a backwards clock step
cannot revive stale machine authority.

`_check_clock` only reads the singleton watermark. Only `reserve_nonce` advances
it. Consequently successful machine effects do not make their observed time a
global durable floor. A clock step backwards between effects on different runs
passes both runs' individual floors and the stale ingress floor.

An isolated reproduction used two actual signed admissions, actual coordinator
acquisition and actual `claims.start_run` transactions. The sole seam injected
UTC time into `live_machine_stamp` (its supported `now` argument); no signature,
authorization, nonce, claim or transaction guard was replaced. At t+3 the first
run started; at t+2 the second run also started. The coordinator's t+1 floor and
both individual run floors allowed this sequence. The global clock remained
before both effects. Output:

```text
{'first_effect_succeeded': True, 'earlier_second_effect_succeeded': True, 'global_clock_before_both': True}
```

A separate direct stamp probe across independent committed transactions returned
false just after key expiry and true after stepping back just before expiry,
with the global floor unchanged. This latter probe establishes helper behavior;
it does not claim an external deployment occurred. Existing regression tests
advance another key's nonce before rolling time back, so they cover ingress
observations rather than the no-further-ingress case.

Follow-up: define and enforce durable effect-time observations without weakening
transaction or authority fences. Include cross-run effects and expiry/rollback
without a subsequent signed request in regression coverage. Handle rejected
observations explicitly rather than assuming writes survive a rolled-back effect.
Reproduction: `PYTHONPATH=. ./.venv/bin/python /tmp/story16-17-clock-review-probe.py`
(session-local script; synthetic temporary database and credentials only).

## CR17-2 — P2: signed headers are absent from the published API contract

Category: patch. Source: acceptance auditor + leader verification.
Location: `api/routes/infra_automation_triggers.py:140–157`;
generated consequence: `frontend/src/api/schema.d.ts:17529`.
Acceptance criterion: AC6 / IAU15-FR-058 API, CLI and OpenAPI parity.

All five signed operations expose neither OpenAPI `parameters` nor `security`.
Generated operation types declare `header?: never`, although the runtime requires
four `X-DeployWhisper-*` headers before parsing the body. Generated callers cannot
express a valid signed call using that declared header contract.

Direct `create_app().openapi()` inspection confirmed `parameters=None` and
`security=None` for `/triggers/cli/run`, `/triggers/list`, `/triggers/status`,
`/triggers/validate` and `/triggers/webhook`.

Follow-up: describe the four required headers, formats and signing semantics on
each operation; regenerate types and assert metadata parity. Preserve exact raw
byte authentication and durable nonce reservation before JSON parsing.

## Validation

Fresh checks on the reviewed tree:

- Focused trigger API, CLI, migration, authority, intake, privilege and signing
  tests: **79 passed, 207 subtests passed** (41.02s; 12 warnings).
  Command: `./.venv/bin/python -m pytest tests/test_api/test_infra_automation_triggers.py tests/test_api/test_trigger_admission_parity.py tests/test_cli/test_automation.py tests/test_infra/test_trigger_migration.py tests/test_infra_automation/test_trigger_authority.py tests/test_infra_automation/test_trigger_intake.py tests/test_infra_automation/test_trigger_privileges.py tests/test_infra_automation/test_trigger_signing.py -q --tb=short`.
- `npm run ui:typecheck`: passed.
- `npm run ui:test`: **479 tests passed**, plus two OpenAPI compatibility checks.
- `npm run ui:build`: passed; existing large-chunk advisory emitted.
- `./.venv/bin/ruff check .`: passed.
- `./.venv/bin/ruff format --check .`: **583 files already formatted**.
- Independent acceptance selection: 32 tests / 117 subtests passed.

`./.venv/bin/python -m unittest discover -q` was also started, then deliberately
interrupted after approximately seven minutes during
`test_successor_after_real_lease_expiry_obeys_global_bound_and_cancels`
(`wait_for` its 31-second lease interval). Exit130; no final suite result.
This is incomplete validation, not a passing full-suite run. No test failure was
reported before interruption. Full local CI was not rerun for this review.

Session logs: `/tmp/story16-17-formal-review-{tests,ui,build,smoke}.log`.
No UI code changed; Compose/browser validation was not rerun for this records-only
review. Existing browser evidence remains explicitly limited to its documented
admission/origin proof. Production HTTPS, live runner and delivery qualification
remain under their existing owning gates.

## Handoff

At the initial review handoff, findings were unchecked and `bmad-help` routed
them back to `bmad-dev-story`. No runtime fixes or public push/PR were part of
that initial review. Both findings are now resolved by the follow-up documented
in [review-fixes.md](review-fixes.md), with all final validation passing.

### Clock probe replay

The synthetic probe source (SHA-256 `aff1abd5ea414e5d5a3f88ed38b64ae4a0b41670fde09a07f69bc0220dfbd858`) is retained here for replay from the repository root:

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from infra_automation import claims
from models.tables import InfraAutomationTriggerClock
from services import infra_automation_trigger_authority as authority
from services import project_service as auth
from tests.test_infra_automation.test_trigger_privileges import isolated_case, operation
with isolated_case() as case:
    first = case.admit()
    case.payload['idempotency_key'] = 'second-clock-probe'
    second = case.admit()
    base = datetime.now(timezone.utc)
    case.now = base + timedelta(seconds=1)
    owner = operation(case, claims.acquire_coordinator, project_id=100, workspace_id=100)
    original = authority.live_machine_stamp
    def controlled_clock(db, stamp):
        return original(db, stamp, now=case.now)
    with patch.object(authority, 'live_machine_stamp', controlled_clock):
        case.now = base + timedelta(seconds=3)
        one = operation(case, claims.start_run, owner, run_id=first['id'], expected_version=first['version'])
        case.now = base + timedelta(seconds=2)
        two = operation(case, claims.start_run, owner, run_id=second['id'], expected_version=second['version'])
    with case.factory() as db:
        floor = db.get(InfraAutomationTriggerClock, 1).last_seen_at
    print({'first_effect_succeeded': one is not None, 'earlier_second_effect_succeeded': two is not None, 'global_clock_before_both': floor.replace(tzinfo=timezone.utc) < base})
```

## Review follow-up

Both findings have implementation fixes and regression tests. Full validation
passed; see [review-fixes.md](review-fixes.md). The original review findings
and interrupted review-only smoke result above are preserved as historical
evidence, not reused as passing validation.
