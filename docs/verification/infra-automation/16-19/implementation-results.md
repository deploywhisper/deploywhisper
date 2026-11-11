# Prerequisite remediation and Story16.19 preparation

Bounded automated prerequisite fixes are implemented and verified on the
qualification branch. The production composition gap found during qualification
is repaired through the approved co-located material authority. A concurrent
course correction records a bounded human-pilot waiver, explicitly NOT EXECUTED.
Trusted-develop integration is still needed for signed-preview verification.
No stable release or human acceptance is claimed.

## Changes

- Integrated the previously omitted settings UI into this branch.
- Added deterministic source SPDX2.3 SBOM generation, regeneration checking and
  checksum/attestation/upload wiring. Legacyv1.4.0 verification stays compatible.
- Added core lifecycle/network guides with actual nonempty offline analysis and
  SQLite backup/restore proof. Conditional PostgreSQL and cold-host limitations
  remain honest; neither is an invented requirement to add a newv1.5 runtime.
- Closed the missing container-creation acknowledgment and production-session
  mailbox bugs found by fresh review and genuine TLS integration.
- Corrected collected-report origin copy without granting approval authority.
- Added fail-closed qualification inventory tooling for72 requirements and9gates.
  Its initial inventory remains incomplete and never authorizes publication.
- Added the default-off co-located production authority: signed monotonic ledger,
  live split-UID custody probe, exact retained-fact binding, fixed policy worker,
  operator CLI publication and one shared decision/handoff service graph.

## Verification

| Check | Result |
| --- | --- |
| Root unittest | 2117 tests,3skips |
| Full local CI | 3592 tests across10directories;exit0 |
| API/CLI/infra pytest | 820 passed,1skipped,2442subtests |
| Automation pytest | 1260 passed,1skipped,3382subtests |
| Frontend | 513 tests+2compatibility checks;typecheck/build passed |
| Real isolation / collection | 172 /49 checks passed |
| Actual TLS collector | 49 checks passed; one retained report/link |
| Composed HTTPS browser | 3 journeys,8screenshots,axe0 serious/critical,visual94/pass |
| Reviews | No remaining actionable code finding after repairs |
| Reference performance | validation p951.668459ms; claim p9590.855916ms; 1800.138s capacity at10/2/20 with0errors |
| Exact local candidate | commit`1adf00f`; app/runner archives, SPDX SBOM/checksums verified; image`sha256:7a6afd...f2323` healthy atv1.5.0 |

See [commands and digests](validation-summary.json), [profile proof](prerequisite-profiles/README.md),
[review](prerequisite-review.md), [SBOM preview](../../12-5/source-preview-results.json)
and [operations scope/proof](../../operations/scope-and-verification.md).

The exact-commit local candidate is technically qualified but unsigned. Hosted
attestations, signed OCI verification and public release writes were not run.

## Remaining external gates

The [human pilot record](human-pilot-record.md) now records the concurrent
accountable-maintainer waiver, explicitly NOT EXECUTED. Its durable approval
reference must be established before the manifest process gate may pass. The
[production composition gap](prerequisite-profiles/receiver-faults/README.md) is
implemented and focused integration-tested; accepted/unknown external carrier
effect and reconciliation qualification remains open under Story16.14 Packet14.8.
The signed-artifact workflow permits previews only from trusted develop or
release tags; feature-branch signing is not enabled to bypass that boundary.
The code is prepared for normal review/integration, followed by actual signed
preview verification. Stable release remains separately authorized and requires
all16.19 performance, safety, browser and supported-profile acceptance.


The [lease/log supplement](prerequisite-profiles/runner-faults/README.md) adds
three actual TLS fault cases and three browser journeys with six captures.
Production material, decision and durable handoff preparation are now composed;
public GitHub dispatch remains separately credentialed and unauthorized. The reviewed
[architecture proposal](../../../../_bmad-output/planning-artifacts/sprint-change-proposal-2026-11-11-material-authority-integration.md)
records the selected co-located topology. No false witness or success handler was
installed to bypass the remaining carrier/publication gates.
