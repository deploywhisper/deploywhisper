# Story 16.16 review record

Native independent reviewers performed domain/readiness review and BMad blind,
edge-case and acceptance layers for the backend and UI separately. The blind
reviewers received only the diffs; the other layers inspected source and acceptance
context. This record is interim until composed proof and all fixes close.

| Finding | Resolution |
| --- | --- |
| Oversized direct-dictionary keys bypass pre-serialization byte accounting | Count keys and values before UTF-8 serialization; five regression variants and independent verification pass. |
| Inventory retention excluded from shared logical engine quota | Include inventory retention in inventory admission and engine charges; scoped/global quota tests pass. |
| Earlier failed-attempt report link could hide successful retry evidence | Resolve the newest attempt first and its exact report link; retained-link retry regression passes. |
| Whole-bundle freshness and expiry test isolation | Bound decisions by every unit's policy/source/custody deadlines; reset deliberately invalid digest before expiry assertions. Production intake already requires source deadline no later than custody expiry; the explicit custody minimum is defense in depth. |
| Workflow analysis ordering could exceed declared dependencies | Require exact cross-unit prerequisite closure at both intake and analysis; handoff ancestors reject as unsupported collection order. |
| UI confirmed run prevented another preflight | Explicit new-preflight action resets request, artifacts, bindings and confirmation after durable success. |
| Remounted UI missed save settlement | Observable request continuity handles late confirmed success/rejection. Lost-response reconciliation remains under final verification. |
| Unit evidence could remain current after same-version expiry/supersession | Periodic and manual authoritative refresh independent of run version. |
| Duplicate unit evidence accepted as complete | Require unique exact evidence coverage and consistent digest/state fields. |
| Keyboard test bypassed navigation | Actual Tab/Shift+Tab, arrow keys and keyboard activation replace programmatic focus/selection; file injection is an explicit fixture operation after keyboard reachability. |

Dismissed candidate: malformed-success response decoding was already ambiguous,
because confirmed HTTP rejection requires a server error code. Regression coverage
preserves that distinction; no new exception hierarchy was introduced.

Backend focused proof: 42 tests/27 subtests, plus 69-test integrated decision/target
run and six API tests. Domain 12 tests/25 subtests; migration startup/recovery 36
tests/two subtests. Full CI and browser acceptance are recorded separately when
complete. No public GitHub operation or release is part of this review record.
