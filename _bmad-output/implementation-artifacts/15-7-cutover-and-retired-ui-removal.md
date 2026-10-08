# Story 15.7: Phase 7 - Cutover and retired UI Removal

Status: review

Reconstructed delivery record: 2026-10-07. This existing planned story was omitted from sprint tracking; no new product scope or UI implementation is introduced.

## Story and Acceptance Criteria

As a maintainer,
I want the React SPA to become the only web UI,
So that retired UI code, dependencies, assets, and tests no longer remain in the runtime.

**Acceptance Criteria:**

**Given** every screen has a React replacement or approved disposition
**When** cutover is performed
**Then** the SPA moves to `/` and legacy routes redirect appropriately
**And** the retired Python UI package, its dependency, old UI tests, old assets, dead CSS, and orphaned static files are removed
**And** Part D2 grep gates pass for retired framework and old test-lane references
**And** README screenshots, runtime badges, CI lanes, a11y routes, CHANGELOG, and final image-size delta are updated.

## Tasks / Subtasks

- [x] Deliver the phase implementation via the merged migration PR.
- [x] Retain historical composed-app validation, documentation and screenshot evidence.
- [ ] Resolve and document the outstanding product/parity acceptance decisions before final closure.

## Dev Agent Record

Delivery: [PR #102](https://github.com/deploywhisper/deploywhisper/pull/102), merge `d726282a5f1b4e3b75ea2d4cbbc40f7528c17a70`; historical merge object confirmed locally; stacked/squashed migration integration is accepted by final PR #102 and the released runtime. Current runtime and historical migration contract are recorded in `docs/ui-migration-plan.md`, `docs/design/ui-parity-audit.md` and `CHANGELOG.md`. Phase 0/1 historical coexistence routes were subsequently superseded by PR #102 root cutover.

Historical browser evidence is retained in the linked PR; final PR #102 records composed-app health/static/redirect checks, eight browser checks, 314 Python tests, 24 frontend tests, screenshots and image size 310→210 MB. Accepted v1.4.0 verification adds 17/17 composed browser checks in `docs/verification/v1.4.0-release.json`. These results are historical and were not rerun during metadata reconciliation. UI validation not applicable to this documentation-only reconciliation.

### Remaining acceptance

Merged implementation is present, but the initiative closure gate is not demonstrated: the historical parity audit still identifies 12 `not-in-demo -> stop-and-ask` labels without a current disposition crosswalk. Some rows have delivered equivalents, so this is an acceptance-documentation gap, not a claim of 12 present functional defects. PR #99 retains history decisions; PR #100 retains dark-mode/provider-capabilities decisions. Part D2/G checklist completion must be reconciled against approved dispositions, not inferred from release publication. Preserve implemented UI and gather decisions in a separate scoped task. This story remains `review` pending acceptance disposition; no UI change is authorized by this administrative correction.

## References

- `../planning-artifacts/epics.md` — existing Epic 15 acceptance criteria.
- `../planning-artifacts/sprint-change-proposal-2026-10-07-v1.4.0-status-reconciliation.md` — reconciliation and handoff.
