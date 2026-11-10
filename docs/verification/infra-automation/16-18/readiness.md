# Story 16.18 entry review

2026-11-10. Actual dependency records were inspected before implementation:
[16.0 readiness](../16-0/wp7-readiness.md), the completed
[16.16 story](../../../../_bmad-output/implementation-artifacts/16-16-declared-multi-unit-preflight-planning.md),
and the completed [16.17 entry and interfaces](../16-17/readiness.md).
Historical backlog wording alone is not a current dependency failure.

Independent native review initially cleared bounded work, then corrected that
disposition after inspecting immutable manifest triggers and restored-session
semantics. The existing retention predicate and project restore-epoch endpoint
are insufficient to implement physical retention or coordinated restore.
That correction was incorporated before persistence changes.

The root reviewed the concrete [retention interface](retention-design.md) and
[restore interface](restore-design.md). These authorize conservative scoped
implementation under the existing architecture. Pending/approved evidence and
unknown external work remain protected. Restore requires a protected generation
ledger outside restored roots, participating-writer quiescence, crash recovery,
credential invalidation and a deny-only outbound reconciliation barrier.

Estimated implementation/review units: 18.1 retention 4–6; 18.2 restore 4–6;
18.3 recovery 2–4; 18.4 network/cache 2–4; 18.5 operations/proof 3–5;
18.6 settings/browser 3–5. These are scope estimates, not calendar promises.

Entry evidence integrity command:

```sh
./.venv/bin/python -m pytest tests/test_infra_automation/test_runner_isolation_qualification.py tests/test_infra_automation/test_collection_qualification.py -q
```

Result: 9 tests and 86 subtests passed. This checks retained evidence and source
hashes, not fresh operational qualification. Migration head was inspected using
`./.venv/bin/python -m alembic heads`: `039_add_signed_trigger_intake`.

Production limits remain explicit: offline Linux ARM64/OpenTofu only; no claim of
Terraform/cloud IAM/remote-state support, host-power-loss durability, complete
live receiver integration, a self-service pilot or twenty real online runners.
The separate positive HTTPS/real-runner browser gates in 16.15 remain open.
Story 16.18 is in progress; none of its packet checkboxes is closed by this review.
