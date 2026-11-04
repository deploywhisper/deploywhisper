# Story 16.12 independent implementation review

Date: 2026-11-04. Scope: enrollment/runner protocol, outbound client, service and engine integration, migration and HTTP boundaries. This review supports development verification; the separate BMad code-review/Git Flow closure remains the next workflow.

An independent read-only reviewer verified the completed 16.0, 16.2 and 16.5 prerequisites and frozen v1 contracts before implementation. Review found and implementation repaired:

- A connectivity-only CLI poll consumed one-time task authority and discarded it. CLI execution now denies before polling when no qualified local handler exists; an installed handler receives work only after claim acknowledgement.
- The coordinator treated remote attempts as missing local workers. It now checks durable remote ownership/liveness and never dispatches collection to a local worker.
- Enrollment and task operations sampled time before waiting for a database transaction. Production clocks now refresh after transaction/mutex acquisition and after upload screening; coordinator assignment passes a clock callable. Contention-expiry tests exercise the actual reserved SQLite boundary.
- Runner logs could retain live runner/task credentials. Current secrets, known enrollment/runner prefixes, accumulated log chunks, upload bytes/decoded content and operation metadata now deny before persistence.
- Contextual HCL sensitive variable defaults were missed by generic screening. The installed HCL parser and existing sensitive-key rules now reject these defaults, sensitive output values and malformed HCL before upload persistence.
- Migration head assumptions and unversioned schema recognition required explicit 037 support. Tests cover fresh, prior-head, downgrade/re-upgrade, unversioned and incomplete schema cases.

The reviewer independently passed 16 tests/21 subtests for migration/enrollment/sensitive defaults and 35 tests/95 subtests for attempts/client/HTTP, reporting no unresolved actionable high-priority defects after repairs. The task owner additionally passed 39 tests/136 subtests for final callable-clock and coordinator behavior. Whole-repository command results are recorded in the story Dev Agent Record.

The frozen v1 completion requirement intentionally remains: even failed completion carries a reference to a finalized upload. Failure before upload is handled by bounded coordinator cleanup/lease recovery, never a fabricated evidence reference.

A final boundary regression also demonstrated that fractional database lease timestamps could outlive the whole-second wire deadline. Operations, upload finalization and task delivery now enforce the advertised exclusive deadline; credential/enrollment checks also floor imported fractional deadlines. Post-repair task/coordinator verification passed 42 tests/141 subtests and enrollment/API verification passed 18 tests/4 subtests.

Reference capacity, production sandbox isolation, real infrastructure collection and signed runner distribution remain unqualified. Diagnostic latency results do not close those release gates.
