# Story 16.17 implementation review

Independent native blind, edge-case and acceptance reviews covered signed
transport, authority and CLI. A separate origin-UI review checked decoding,
provenance, scoped visibility and accessibility. All confirmed implementation
findings below are repaired; full regression results are recorded separately.

| Finding | Repair and evidence |
| --- | --- |
| Machine effect authority ignored the durable clock high-water mark | Reserved contexts and live machine stamps now reject rollback. Two-key clock advancement and actual claim/dispatch/consume regressions preserve denial and held locks. |
| Allowlisted project-scoped revisions were rejected before concrete workspace binding | The machine admission/read seam authorizes the configured execution workspace while preserving human behavior and other workspace denials. |
| Known signing-key text could enter retained workflow inputs | Decoded keys/values, resolved snapshots and validation output are screened against the active key's representations. Literal, escaped and mixed-case reflection regressions reject before run retention. |
| Service arguments could differ from authenticated raw bytes or operation | Shared bounded parsing binds the exact supplied model and operation to the authenticated bytes; duplicate/deep/invalid bodies remain rejected. |
| CLI socket inactivity timeouts did not bound total header/DNS time | A finite transport pool, monotonic deadline, sealed outcome and owned socket shutdown bound the whole operation and prevent late sends. |
| Interrupted thread startup could release a still-owned slot | Ambiguous startup interruption retains worker ownership until exit; actual started-worker regression verifies the cap and cleanup. |
| Accepted uppercase HTTPS scheme selected the HTTP cookie | Noncanonical scheme casing is rejected consistently before network credential use. |
| Narrow history rows expanded around full principal IDs | The compact summary retains channel and principal type, with exact identity in details; visual verdict improved from87 to94 without restyling. |

The real-credential suite uses actual provisioned service/agent identities,
verified signatures and durable request admission. Its handoff proof creates a
new machine run and obtains an actual separate human decision; only collector,
material, custody and delivery ports are labelled synthetic doubles. It does not
rewrite a human run into a machine fixture or claim live deployment qualification.

Additional full-CI repairs update assumptions about initial run versions and
admission charges: origin retention is a separate charged record. The tests now
verify persisted version continuity and isolate target-lock allocations while
retaining their longest-reason, quota and whole-transaction rollback assertions.

The composed proof uses actual CLI and HTTP signatures. Signed collected requests
preserve origin through unavailable-runner failures; successful collection and
production TLS are deliberately not claimed. Existing16.15 gates remain open.
