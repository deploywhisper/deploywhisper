# Story 15.1: Phase 1 - SPA Serving

Status: done

Reconstructed delivery record: 2026-10-07. This existing planned story was omitted from sprint tracking; no new product scope or UI implementation is introduced.

## Story and Acceptance Criteria

As a maintainer,
I want the built SPA served at `/`,
So that the current UI runs from the same FastAPI container users deploy.

**Acceptance Criteria:**

**Given** the frontend build exists
**When** the FastAPI app and Docker image are updated
**Then** `frontend/dist` is mounted at `/` with SPA fallback routing
**And** the Dockerfile adds a Node 22 Alpine frontend build stage but keeps Node out of the runtime image
**And** `docker compose up -d --build` serves the React SPA at `http://localhost:8080/`, and `/api/v1/health` stays green
**And** the image size delta is recorded in the PR.

## Tasks / Subtasks

- [x] Deliver the phase implementation via the merged migration PR.
- [x] Retain historical composed-app validation, documentation and screenshot evidence.
- [x] Reconcile accepted phase delivery against the current root-SPA baseline.

## Dev Agent Record

Delivery: [PR #92](https://github.com/deploywhisper/deploywhisper/pull/92), merge `4734f9b9372ba9d2928551a52eb961f9f1cfd19f`; historical merge object confirmed locally; stacked/squashed migration integration is accepted by final PR #102 and the released runtime. Current runtime and historical migration contract are recorded in `docs/ui-migration-plan.md`, `docs/design/ui-parity-audit.md` and `CHANGELOG.md`. Phase 0/1 historical coexistence routes were subsequently superseded by PR #102 root cutover.

Historical browser evidence is retained in the linked PR; final PR #102 records composed-app health/static/redirect checks, eight browser checks, 314 Python tests, 24 frontend tests, screenshots and image size 310→210 MB. Accepted v1.4.0 verification adds 17/17 composed browser checks in `docs/verification/v1.4.0-release.json`. These results are historical and were not rerun during metadata reconciliation. UI validation not applicable to this documentation-only reconciliation.

## References

- `../planning-artifacts/epics.md` — existing Epic 15 acceptance criteria.
- `../planning-artifacts/sprint-change-proposal-2026-10-07-v1.4.0-status-reconciliation.md` — reconciliation and handoff.
