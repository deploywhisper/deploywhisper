# Independent operator pilot or accountable-maintainer waiver record

Status: WAIVED BY ACCOUNTABLE MAINTAINER — NOT EXECUTED.
No separate human operator performed these procedures. The accountable maintainer
approved a v1.5.0-specific waiver on 2026-11-11 after reviewing the complete
automated technical qualification. The waiver accepts the residual self-service
and runbook-usability risk; it is not human pilot evidence.

Use a disposable synthetic installation and the release-matched
[operator runbook](../../../infra-automation/operations.md). Do not use a production
database or paste passwords, cookies, keys, binary plans or raw state into this record.
Record the exact tested Git SHA/image digest; earlier automated results are references.

## Available engineering proof build

Source `675f127a0c4ad7c3630d3c59cb7412818afd1db8`, local image
`sha256:a0155abf874bd29a798a19e794dd9d2928d17ed701011e655ecc6920cc65d447`.
This identifies the automated prerequisite build, not a published stable release
or a human-tested result. The operator must record the actual build used below.

## Operator and environment

- Operator identity/role: pending
- Date and independent observer, if any: pending
- Tested Git SHA and image digest: pending
- Host/runtime/tool/receiver versions and supported profile: pending
- Reference hardware and network restrictions: pending

## Accountable-maintainer waiver

- Approver: `psaho01` (repository accountable maintainer; Git author identity
  `Pramoda Sahoo`). Durable release-gate acceptance still requires the waiver to
  be carried by an approved CODEOWNERS review, signed commit/tag or equivalent
  repository decision reference before the manifest gate may pass.
- Approval: explicit instruction on 2026-11-11 to approve the human-pilot gate,
  choose the best bounded approach, complete the task and resume Story 16.19.
- Evidence reviewed: `prerequisite-profiles/README.md`, `validation-summary.json`,
  `prerequisite-review.md`, Story 16.18 acceptance/review/capacity evidence and
  the source-bound automated qualification records.
- Accepted residual risk: no independent evidence that a first-time human can
  complete installation/recovery without implementer assistance; runbook ambiguity
  may still be discovered after release.
- Scope: closes only independent human execution for v1.5.0. It does not mark any
  procedure below executed, expand supported profiles, authorize publication or
  waive performance, safety, independent-review, signing or provenance gates.
- Follow-up: retain independent human self-service validation as visible post-release
  work and incorporate any runbook findings without retroactively relabelling this waiver.

## Procedure outcomes

| Procedure | Operator observation and nonsecret evidence | Result |
| --- | --- | --- |
| Install using the supplied guide without implementer intervention | Pending | Not executed |
| Bootstrap administrator with one-use setup credential; establish project membership | Pending | Not executed |
| Recover account and confirm old session rejection | Pending | Not executed |
| Quiesce participating writers and capture database/artifact/custody backup | Pending | Not executed |
| Restore, confirm epoch advancement and stale sessions/grants/leases denied | Pending | Not executed |
| Read retained history and reconcile the same retained operation without replaying action | Pending | Not executed |
| Complete recovery with fresh authorized operator credentials | Pending | Not executed |
| Confirm restricted-network installation/recovery limits and required offline assets | Pending | Not executed |
| Exercise documented unknown-operation handling without silently releasing locks | Pending | Not executed |
| Remove disposable state and verify original installation unaffected | Pending | Not executed |

## Acceptance decision

- Runbook ambiguity, failed steps and required implementer assistance: unknown; pilot not executed.
- Operator acceptance or rejection with reasons: not available; pilot not executed.
- Maintainer disposition and unresolved limits: waiver approved; residual human-usability risk accepted and disclosed.

Each procedure remains unexecuted. Under the approved course correction, this
record closes only the `operator-pilot-or-maintainer-waiver` process gate. It does
not authorize public release, prove human self-service or qualify untested profiles.
