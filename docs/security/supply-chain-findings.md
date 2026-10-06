# Supply-chain findings ledger

Maintainer owner: `@pramodksahoo` (see [MAINTAINERS.md](../../MAINTAINERS.md)).
Review process and private disclosure rules: [scanning guide](supply-chain-scanning.md).

## Baseline

Repository: `deploywhisper/deploywhisper`; default branch: `develop`.
Initial CodeQL setup was not configured and the alerts API reported no analysis.
Absence of analysis does not mean absence of vulnerabilities.

Full repository baseline: official Scorecard CLI **v5.5.0**, 2026-10-06,
commit `495f8452c40788557bf997f7eb2771116089347e`, aggregate **3.8/10**.
[Retained JSON evidence](../verification/story-12-4/scorecard-baseline.json).
The SHA-256-verified official CLI used GitHub credentials only in memory for
read access. This full hosted scan is distinct from PR-local action results.

## High-priority dispositions

| Rule/check | Severity | Scan commit/run | Owner | Disposition | Follow-up or accepted rationale | Next review |
| --- | --- | --- | --- | --- | --- | --- |
| Branch-Protection, 0/10 | High | Baseline `495f845` | @pramodksahoo | Open follow-up | [#131](https://github.com/deploywhisper/deploywhisper/issues/131): default development/release protection not enabled; verify and configure suitable rules separately | 2026-10-13 |
| Code-Review, 0/10 | High | Baseline `495f845` | @pramodksahoo | Open follow-up | [#131](https://github.com/deploywhisper/deploywhisper/issues/131): 0/30 approved changesets; establish independent review policy | 2026-10-13 |
| Dependency-Update-Tool, 0/10 | High | Baseline `495f845` | @pramodksahoo | Open follow-up | [#131](https://github.com/deploywhisper/deploywhisper/issues/131): no update configuration detected; scheduled audits do not replace automated updates | 2026-10-13 |
| Token-Permissions, 0/10 | High | Baseline `495f845` | @pramodksahoo | Open follow-up | [#131](https://github.com/deploywhisper/deploywhisper/issues/131): narrow existing release/analytics write permissions; new scan jobs already use scoped permissions | 2026-10-13 |
| Vulnerabilities, 0/10 | High | Baseline `495f845` | @pramodksahoo | Open follow-up | [#131](https://github.com/deploywhisper/deploywhisper/issues/131): 21 public advisory reports require mapping to current runtime/dev/transitive manifests and verified affected versions; no risk dismissal inferred from CI success | 2026-10-13 |
| Signed-Releases, -1 | High, unknown | Baseline `495f845` | @pramodksahoo | Coverage follow-up | [#131](https://github.com/deploywhisper/deploywhisper/issues/131): no GitHub releases found; verify signed assets/provenance under Story 12.6 | 2026-10-13 |

Rows must reference observed findings. Unknown checks remain coverage gaps;
green scan execution and synthetic examples are not accepted rationales for
production vulnerabilities. Rationale must identify evidence and applicable
scope; decisions expire on the next review date or when that scope changes.

## Verification records

- `Dangerous-Workflow`: **10/10**, no dangerous patterns detected. `Binary-Artifacts`
  and `Maintained` (High) also scored **10/10**. No high-priority failure was accepted
  as safe; the observed gaps above have an assigned follow-up.
- `SAST` and `Pinned-Dependencies`: **0/10**, officially Medium. SAST rollout is
  addressed by this story, with default-branch verification still required after
  integration; existing mutable dependencies/action references remain follow-up
  [#131](https://github.com/deploywhisper/deploywhisper/issues/131).
- `Security-Policy`: **4/10**, Medium. The private reporting boundary in `SECURITY.md`
  remains authoritative; a low score does not justify publishing exploit details.
- PR-local Scorecard and three-language CodeQL execution records are added after
  live validation. Default-branch workflow execution remains a distinct
  post-integration verification event; no badge/public API publication is enabled.
