# Coordinator commit-expiration regression

Story 16.7 composed-app validation exposed queued local runs with no attempts:
the scheduler failed while reading candidate rows after the ownership transaction
committed. Production `SessionLocal` expires ORM attributes on commit, whereas the
lifecycle fixtures normally disable expiration.

The coordinator now detaches its fully loaded, read-only candidate hints before
the ownership transaction commits. Lease validation and the commit still succeed
before the capability is retained or scheduling begins. Scheduling and stopping
continue to re-read durable run state inside their own authorized transactions;
the global session configuration and lifecycle contracts are unchanged.

## Regression evidence

- Added `test_expiring_sessions_schedule_and_complete_queued_run` using
  `expire_on_commit=True` and a real spawned local worker.
- Before the fix, the test failed with `DetachedInstanceError` in `_ownership`
  while reading `candidate.project_id`.
- After the fix, the test verifies `queued -> running -> succeeded`, a durable
  attempt, and successful worker completion.
- `/Users/psaho01/deploywhisper/.venv/bin/python -m unittest
  tests.test_infra_automation.test_engine_coordinator -q`: **18 passed**.
- `/Users/psaho01/deploywhisper/.venv/bin/python -m pytest
  tests/test_infra_automation/test_engine_*.py
  tests/test_api/test_infra_automation_engine.py
  tests/test_api/test_infra_automation_preflight.py -q --tb=short`:
  **248 passed, 459 subtests passed** in 244.49 seconds. Seven existing Alembic
  `path_separator` deprecation warnings were emitted.
- `/Users/psaho01/deploywhisper/.venv/bin/ruff check .`: **passed**.
- `/Users/psaho01/deploywhisper/.venv/bin/ruff format --check .`: **427 files
  already formatted**.
- `git diff --check`: **passed**.
- `/Users/psaho01/deploywhisper/.venv/bin/mypy
  infra_automation/coordinator.py --ignore-missing-imports --no-error-summary
  --follow-imports=silent`: **passed**.
- `/Users/psaho01/deploywhisper/.venv/bin/bandit
  infra_automation/coordinator.py --severity-level medium
  --confidence-level medium`: **no issues identified**.

UI validation not applicable to this backend-only patch. Composed-app browser
validation belongs to the concurrent Story 16.7 UI workstream. All regression
data is synthetic and isolated in temporary databases.
