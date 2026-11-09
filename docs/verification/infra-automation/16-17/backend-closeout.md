# Story 16.17 backend/CLI publication — 2026-11-09

This backend-for-UI slice is ready for a separate PR to `develop` from
`feature/16-17-signed-trigger-intake-backend`. Merge it before the dependent
`feature/16-17-trigger-origin-ui` PR. No rendered React screen or browser flow is
changed in this backend slice; the generated API declaration is its contract
artifact. Full-story status and fresh composed UI proof belong to the UI branch.

## Behavior

Exact-byte HMAC admission reserves durable nonces before parsing, enforces live
key/principal/scope/revision/source policy, and retains idempotency and origin.
Service and agent credentials remain read/request-only and cannot become human
sessions, publishers or approvers. The CLI uses the same API and authority with
private credentials and a bounded transport deadline. Migration039 retains only
bounded replay/clock/origin facts; signing secrets remain environment references.

Both formal findings are repaired: checked clock maxima survive business and
nested rollbacks under the same SQLite reservation, while loss of the reservation
preserves replacement-writer data; all five signed operations describe their
four required headers, including generated client types. Nine clock regressions
cover the transactional boundaries. Advisory reports retain `should_block=False`.

## Evidence and provenance

All seven runtime/test/generated-contract/qualification hashes in
[review-fixes-results.json](review-fixes-results.json) match this backend branch.
The full November7 validation was executed on the combined integration tree;
production Python/backend code is byte-identical here. That record contains
3402 local-CI cases across ten directories, root1932/3skips, exact API/CLI/infra
799pass1skip2433subtests and automation1108pass1skip3236subtests. It does not
mislabel the combined origin-UI frontend tests as this branch's own UI proof.

Fresh November9 standalone branch checks:

- `LLM_API_BASE=http://127.0.0.1:1 ./.venv/bin/python -m pytest tests/test_infra_automation/test_trigger_clock.py tests/test_api/test_infra_automation_triggers.py tests/test_api/test_trigger_admission_parity.py tests/test_cli/test_automation.py -q --tb=short`: **51 passed, 65 subtests, 17.45s**.
- `npm run ui:typecheck`: passed against the unchanged pre-origin frontend and new generated API contract.
- Ruff lint, repository-wide formatting and diff whitespace checks: passed.
- Collection/isolation evidence remains current:49 checks plus9integritytests/86subtests; Python3.11.17 selection27tests passed.

UI validation not applicable to this backend-only PR. The dependent UI PR owns
its fresh Compose build, actual HTTP/CLI admission, keyboard/axe and1440/760
screenshots. Existing317mypy diagnostics remain outside the changed runtime
files. Production TLS/live-runner browser and wider collection/delivery support
remain under their existing qualification gates; this PR does not close them.
