# Story16.19 entry-readiness remediation

Current disposition: **preparatory work has started; production approval/handoff
qualification remains blocked by missing authority and handler composition.**
The concurrent approved human-pilot waiver is preserved as **NOT EXECUTED** and
does not waive this technical gap or authorize publication.

The initial e4d6b50 assessment is retained in Git history. The table below
supersedes its resolved or overly broad blocker wording.

| Finding | Current disposition | Evidence / next step |
| --- | --- | --- |
|16.0 governance/technical gate|Already closed|Do not revive copied historical blockers|
|Missing16.18 UI integration|Integrated into this feature branch at a6d59ec; corrected report copy at675f127|Normal reviewed integration into develop remains necessary|
|12.5 SBOM|Source SPDX generation, exact regeneration, checksums and workflow wiring implemented/reviewed;215-package preview verified|Actual signed/public verification awaits the guarded trusted-develop/release workflow; no stable publication claimed|
|12.7/12.8 operations/network|Guides and real nonempty offline core analysis plus SQLite backup/restore verified|Documentation/core-offline ACs do not require adding unsupported PostgreSQL automation or invent a cold-OS gate|
|16.13 review closure|Fresh layered review found creation-acknowledgement gap; repaired and independently verified|172 real isolation checks; unknown creation remains fail-closed|
|16.14 bounded collection|49 real collection/custody/receipt checks refreshed with matching sources|Production material/witness integration is a separate newly confirmed gap, not supplied by these receipts|
|16.15 positive HTTPS/real runner|Actual TLS collection-to-report and administration/expiry/network journeys passed|3 browser journeys,8 screenshots; collected provenance copy corrected|
|16.15 lease/log faults|Actual wire expiry, running OpenTofu revocation and log caps verified|3 fault cases plus3 browser journeys and6 screenshots; no terminal states seeded|
|16.15 accepted/unknown production path|**Open**: production material resolver, qualified witness/lease authority and policy/human/handoff composition absent|Reviewed material-authority proposal requires topology choice and approval; no constant witness or fixture promotion|
|16.18 human pilot|Recorded accountable-maintainer waiver, explicitly not executed|Preserve residual usability risk and durable decision-reference requirement; no technical gate is waived|
|19.1 preparation|Fail-closed72-requirement/9-gate inventory tool implemented|Complete inventory is not publication authorization; actual release evidence remains required|

## Verified implementation

At source675f127: root unittest2096 tests/3skips; full local CI3571 tests across10
directories; exact API/CLI/infra820 passed/1skip/2442subtests; frontend513 tests plus2
compatibility checks, typecheck/build. Actual isolation172, collection49 and TLS
collection49 checks passed. Production-image witness covers243 Python files.
The later lease/log supplement uses the same immutable runtime and a separately
identified fault driver. See [validation](validation-summary.json),
[profile proof](prerequisite-profiles/README.md), [fault proof](prerequisite-profiles/runner-faults/README.md)
and [review](prerequisite-review.md).

Concurrent waiver, version and benchmark changes in the shared checkout are
separately owned work. The675f127 test results do not automatically qualify those
later changes. The current waiver-aware inventory unit suite was separately
rechecked:12 tests and17 subtests passed.

## Required next decision

The [material-authority integration proposal](../../../../_bmad-output/planning-artifacts/sprint-change-proposal-2026-11-11-material-authority-integration.md)
was independently reviewed and is **not approved**. It recommends explicit
integration follow-ups under16.14 before15.3 production accepted/unknown proof,
keeping19.2 as final integrated qualification and preserving all canonical requirements.

Choose co-located or separate-host authority topology and approve the concrete
proposal before enabling production providers. This decision must establish
lifecycle mutation ownership, monotonic generation/domain semantics and
serialization or leases through admission. A source hash, current observation,
constant counter or seeded terminal state cannot substitute for that authority.
The [composition-gap record](prerequisite-profiles/receiver-faults/README.md)
contains direct default-service/registry evidence and receiver component proof.

The earlier conditional5–9-day estimate assumed production ports already existed.
Re-estimate after this design decision; no delivery date or full production
qualification follows from the successful bounded tests. Stablev1.5.0 publication
still needs all declared profile/performance/review/signing gates and the shared
release obligations recorded by the architecture.
