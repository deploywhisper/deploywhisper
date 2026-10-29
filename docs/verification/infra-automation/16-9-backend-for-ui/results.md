# Story16.9 backend-for-UI prerequisite verification

Baseline: `5693c09` (merged Story16.8). Maintainer approval on 2026-10-29
explicitly authorized delivering this prerequisite first and then continuing the
UI story. Scope: immutable approval packet read, current reviewer context,
high/critical confirmation and versioned decision-state audit digests.

## Implemented boundary

- Scoped `GET /approvals/{id}` recovers the exact retained generation/receipt and
  bounded report/action summaries. Canonical bytes/hashes remain unchanged.
- Historical reads survive feature-off, unavailable material and unavailable
  decision clocks; current context cannot authorize when unavailable.
- Prospective shared/acknowledgement mode is server-selected. High/critical
  submissions require exact outcome-sensitive typed phrases; reasons and phrases
  cannot bypass hard floors, CSRF, CAS or separation of duties.
- Existing append-only audit/export is reused. Before/after state digests retain
  actual attribution and legacy events are not rewritten. Audit export remains
  admin-only and scoped; DB/host administrators remain trusted.
- No migration, dependency, production collector, target registry, custody
  implementation, receiver or remote action was added.

## Independent review

Separate read-packet and confirmation/audit reviewers inspected the approved
contract, actual code and tests. Review corrections cover a helper signature
mismatch, pre-screened redaction markers causing history errors, unavailable
clock history recovery, strict integer/Boolean literals and uploaded-source
identity absence. Live eligibility reads do not create false audit events.

Independent probes confirmed real HTTP reads without CSRF, immutable severity
confirmation despite changed live decorations, legacy attribution and read-safe
authority checks that cannot be reused as mutation credentials. No blocking
findings remain in either lane.

## Actual validation

| Check | Result |
| --- | --- |
| Final focused new+existing decision/API matrix | 72 passed, 57 subtests |
| Root unittest smoke | 1,271 tests passed, 2 skips |
| Exact API/CLI/infra pytest shard | 693 passed, 1 opt-in skip, 2,279 subtests |
| Every-directory local CI | Passed, exit 0; 2720 directory tests |
| Ruff lint / repo-wide formatting | Passed, 445 files |
| New service/model scoped mypy and Bandit | Passed |
| Repository mypy | 312 existing findings; no introduced file/message findings versus Story16.8 baseline |
| Generated API declarations / frontend typecheck | Passed |
| Constructor search / diff check | Passed |

Verification uses an unavailable local model endpoint to keep optional narrative
fallback deterministic. UI validation is not applicable to this prerequisite:
no React screen or browser behavior changed; TypeScript changes are generated
API declarations only. Actual Compose/browser/keyboard/axe/screenshots remain
mandatory for the following separate UI branch.

## Delivery

Dedicated branch: `feature/16-9-approval-review-prerequisite`.
This support must be independently reviewed and delivered in its own
`backend-for-ui` PR before the Story16.9 UI branch. Final broad validation passed. The separately labeled PR and actual integration
commit are recorded below once published.
