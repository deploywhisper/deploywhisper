---
title: Story 16.7 backend-for-UI scoped capabilities
type: feature
created: '2026-10-28'
status: done
baseline_commit: 57990443112d472187f2e2e68d0cf754568267ed
context:
  - '{project-root}/_bmad-output/project-context.md'
---

<frozen-after-approval reason="user authorized the necessary separate backend prerequisite on 2026-10-28">

## Intent

**Problem:** Story 16.7 must display permitted authoring and start controls plus
disabled execution state. Story 16.6 supplies real uploaded-preflight/report/evidence
reads, but no resource supplies the caller's live scoped permissions and feature
state. Static role definitions and admin-only memberships are insufficient;
settings reads require project-wide draft permission.

**Approach:** Add one read-only, closed, versioned capability projection using the
existing verified human session, live scope guard and automation policy in a single
authorization transaction. Deliver separately from the React workstream on
`feature/16-7-backend-for-ui-capabilities`; preserve previous behavior.

## Boundaries & Constraints

**Always:** Use existing `/api/v1/infra-automation` envelopes, fixed errors,
no-store headers and the shared authorization guard. Require `automation.read` for
the requested exact scope. Whole-project queries require whole-project membership;
workspace-limited readers supply their concrete authorized workspace. Expose only
the four permissions needed by the editor/start flow. Capabilities describe role
permission, not CSRF validity, resource-specific eligibility or execution grants.
Feature-off preserves authoring and authorized historical reads.

**Ask First:** Any weakening of authority, new dependency or incompatible wire
change. The user has authorized this additive backend support and separate delivery.

**Never:** Modify existing mutation checks, roles, session/CSRF issuance, scoring,
report v2/provenance, run state, database schema or frozen protocol fixtures. Do not
expose tokens, other members, raw uploads or claimed approval eligibility. Do not
add React routes or new settings controls in this workstream.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
| --- | --- | --- | --- |
| Scoped reader | Verified human/member, exact project/workspace | Versioned permissions and actual feature state, no CSRF needed for read | Existing envelope/no-store |
| Feature disabled | Authorized reader, disabled policy | `execution_enabled=false`; permitted draft/publish unchanged | History remains readable; new start still denies |
| Wrong authority | Missing/expired/revoked/nonhuman credential or forged role | No protected scope/capability data | Existing fixed 401/403 |
| Wrong scope | Missing project, foreign/missing workspace or limited member asking project-wide | Same generic denial for inaccessible/missing scope | 403, no existence hints |
| Freshness | Membership/policy changed after previous read | Next read reflects live state or denies | Previous response cannot authorize mutation |
| Malformed/unavailable | Duplicate/unknown/out-of-range query or corrupt/unavailable policy | No partial permission response | Existing 422/503 |

</frozen-after-approval>

## Code Map

- `api/routes/infra_automation.py`: existing authenticated route class and scope query validation.
- `api/schemas.py`: closed typed response declarations and OpenAPI.
- `services/infra_automation_service.py`: public service entrypoint.
- `services/infra_automation_policy.py`: transaction-local policy reads.
- `services/project_service.py`: live scope guard and verified-principal role policy; reuse unchanged.
- `services/infra_automation_preflight.py`: Story 16.6 checks `automation.request` and `analysis.submit`; report relations remain independently protected.
- `tests/test_api/test_infra_automation_workflows.py` and `tests/test_infra_automation/lifecycle_support.py`: isolated identity/membership/database fixtures.

## Tasks & Acceptance

**Execution:**
- [x] `tests/test_api/test_infra_automation_capabilities.py` and service tests: write failing role/scope/feature/live-authority and compatibility tests first; use temporary databases.
- [x] `api/schemas.py`, `api/routes/infra_automation.py`, `services/infra_automation_service.py`, `services/infra_automation_policy.py`: implement the bounded projection with existing guards.
- [x] `docs/infra-automation/ui-capabilities.md`, prerequisite record and readiness assessment: document actual wire contract, Story 16.6 continuity and scope limits.
- [x] Run regression, exact CI shard, local CI, lint/format/security/static checks and independent review; fix introduced findings and record results.

**Acceptance Criteria:**
- Given each existing project role and valid human session, when the exact authorized scope is read, then returned editor/start permissions match the live server policy independently of global identity-admin flags.
- Given changed authority or policy, when the next read or a protected mutation occurs, then live guards apply and a prior capability response grants no authority.
- Given existing workflow/preflight/report consumers, when their regression suites run, then their prior contracts and behavior remain intact.

## Spec Change Log

## Design Notes

Proposed `GET /api/v1/infra-automation/capabilities?project_id=…&workspace_id=…`
returns `data` with strict `version: 1`, requested `project_id`/nullable
`workspace_id`, `membership_version`, `policy_version`, `execution_enabled` and
`capabilities` limited to `automation.read`, `automation.draft`,
`automation.publish`, `automation.request`. Resolve within `authorized_session`;
use `support.scope(..., "automation.read", mutation=False)` then the existing pure
verified-principal capability policy and `support.policy_state`. Never report
conditional cancel/decision/administration permissions as unconditional actions.
A concrete authorized workspace, immutable permitted revision, inputs, feature
enablement, live mutation credentials and quotas are still required at admission.

## Verification

- Focused capability API/service tests plus workflow/preflight regression suites.
- Repository-wide constructor/fixture search for new models and consumers.
- `./.venv/bin/python -m unittest discover -q`.
- `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`.
- `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- `bash scripts/ci-local.sh`, scoped available static checks and `git diff --check`.
- UI validation not applicable: no rendered UI or browser behavior changes.

## Implementation Record

Implemented the proposed additive read contract; no migration, dependency, role,
mutation, authentication or report-contract changes were necessary. Three native
review layers completed and rechecked the corrections: no remaining actionable
introduced findings. Exact test results, production image identity, initial smoke
failure and final recovery evidence are maintained in the
[verification record](../../docs/verification/infra-automation/16-7-backend-for-ui/results.md).
UI validation not applicable to this backend slice; full Story 16.7 stays pending.

Final validation: local CI 2,607 tests; root smoke 1,161 tests /two expected skips;
exact API/CLI/infra shard 685 tests /2,267 subtests /one opt-in skip; production
Python 3.11 new-test suite 20 passed and app smoke passed. Ruff lint/repo-wide
format, scoped Bandit and diff checks passed; existing type/security debt remains
unchanged as documented. BMad Help next step: refresh the full Story 16.7 context
with this separate support contract, then resume UI dev-story and browser proof.

## File List

- `api/routes/infra_automation.py`
- `api/schemas.py`
- `services/infra_automation_policy.py`
- `services/infra_automation_service.py`
- `tests/test_api/test_infra_automation_capabilities.py`
- `tests/test_infra_automation/test_ui_capabilities.py`
- `docs/infra-automation/ui-capabilities.md`
- `docs/infra-automation/preflight.md`
- `docs/verification/infra-automation/16-7-backend-for-ui/results.md`
- `_bmad-output/implementation-artifacts/spec-16-7-backend-for-ui-capabilities.md`
- `_bmad-output/implementation-artifacts/16-7-workflow-editor-and-run-history-ui.md`
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-28-story-16-7.md`

## Suggested Review Order

**Read boundary and authority**

- Inspect the additive human-authenticated endpoint and existing strict wrapper.
  [infra_automation.py:226](../../api/routes/infra_automation.py#L226)
- Follow the single transaction resolving live membership, permissions and policy.
  [infra_automation_policy.py:30](../../services/infra_automation_policy.py#L30)
- Check the independently versioned closed response and permission-list invariants.
  [schemas.py:2831](../../api/schemas.py#L2831)

**Continuity and failure proof**

- Verify real Story 16.6 history remains readable after feature disable.
  [test_infra_automation_capabilities.py:253](../../tests/test_api/test_infra_automation_capabilities.py#L253)
- Check revocation independently of account disablement or expiry.
  [test_infra_automation_capabilities.py:140](../../tests/test_api/test_infra_automation_capabilities.py#L140)
- Check scope and live-policy changes through the shared service.
  [test_ui_capabilities.py:44](../../tests/test_infra_automation/test_ui_capabilities.py#L44)
- Read the UI contract and verification limits before integration.
  [ui-capabilities.md:1](../../docs/infra-automation/ui-capabilities.md#L1)
