# Story 15.6: Phase 6 - Settings, Incidents, and Skills

Status: review

Reconstructed delivery record: 2026-10-07. This existing planned story was omitted from sprint tracking; no new product scope or UI implementation is introduced.

## Story and Acceptance Criteria

As an administrator,
I want the remaining retired UI operational screens rebuilt in the React design system,
So that configuration, incidents, topology, reviewer feedback, and Skills management are migrated before cutover.

**Acceptance Criteria:**

**Given** the Part D parity audit is complete
**When** Phase 6 screens are implemented
**Then** settings, incidents, and skills list/detail flows match the design system
**And** provider settings, topology upload and drift cadence, reviewer-feedback stats, and custom-skills management preserve current behavior unless Part A2 sanctions a change
**And** any retired UI callback-only behavior is extracted into `/api/v1` as Part A3-sanctioned backend work
**And** the retired Dashboard Result Display Duration setting is recorded as `sanctioned-change (A2)`.

## Tasks / Subtasks

- [x] Deliver the phase implementation via the merged migration PR.
- [x] Retain historical composed-app validation, documentation and screenshot evidence.
- [ ] Resolve and document the outstanding product/parity acceptance decisions before final closure.

## Dev Agent Record

Delivery: [PR #100](https://github.com/deploywhisper/deploywhisper/pull/100), merge `60eb18f39fc7c36acd8d4100030c04875ae0d5b7`; historical merge object confirmed locally; stacked/squashed migration integration is accepted by final PR #102 and the released runtime. Current runtime and historical migration contract are recorded in `docs/ui-migration-plan.md`, `docs/design/ui-parity-audit.md` and `CHANGELOG.md`. Phase 0/1 historical coexistence routes were subsequently superseded by PR #102 root cutover.

Historical browser evidence is retained in the linked PR; final PR #102 records composed-app health/static/redirect checks, eight browser checks, 314 Python tests, 24 frontend tests, screenshots and image size 310→210 MB. Accepted v1.4.0 verification adds 17/17 composed browser checks in `docs/verification/v1.4.0-release.json`. These results are historical and were not rerun during metadata reconciliation. UI validation not applicable to this documentation-only reconciliation.

### Remaining acceptance

Merged implementation is present, but the initiative closure gate is not demonstrated: the historical parity audit still identifies 12 `not-in-demo -> stop-and-ask` labels without a current disposition crosswalk. Some rows have delivered equivalents, so this is an acceptance-documentation gap, not a claim of 12 present functional defects. PR #99 retains history decisions; PR #100 retains dark-mode/provider-capabilities decisions. Part D2/G checklist completion must be reconciled against approved dispositions, not inferred from release publication. Preserve implemented UI and gather decisions in a separate scoped task. This story remains `review` pending acceptance disposition; no UI change is authorized by this administrative correction.

## References

- `../planning-artifacts/epics.md` — existing Epic 15 acceptance criteria.
- `../planning-artifacts/sprint-change-proposal-2026-10-07-v1.4.0-status-reconciliation.md` — reconciliation and handoff.
