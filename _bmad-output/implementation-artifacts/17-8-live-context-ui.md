# Story 17.8: Live Context UI

Status: backlog
Preparation: refined
Release: v1.6.0 | Priority: P1 within the independent Epic 17 lane

## Story

As a reviewer, I want grounded evidence presented in the React app alongside the existing briefing, so that I can see what is actually affected, what diverged and what cannot be undone before I decide.

## Implementation gates

- Blocked until 17.4, 17.5 and 17.6 land their API-visible contracts.
- Hard earlier dependencies: **17.4, 17.5, 17.6**. **No Epic 16 dependency. Must render correctly with no automation run present.**
- Bind to real APIs with seeded data. **Never hard-code mockup demo data.** Backend-for-UI gaps ship in a separately labelled PR.
- All verification runs against the composed production app at `http://localhost:8080` on root SPA routes. A Vite dev server is not verification.

## Acceptance Criteria

1. **AC1:** Given a grounded report, when the Live Context tab opens, then the grounding banner, divergence panel, live blast radius, recoverability table and unreadable-resource list render from real API data using existing design primitives.
2. **AC2:** Given an unreadable resource, when it is listed, then the exact missing permission and an actionable remedy are shown, not a generic warning.
3. **AC3:** Given grounding off, disabled, denied, empty, loading, failed, partial or degraded responses, when the view loads, then the actual state and the permitted next action are accessible, and no grounded claim is implied.
4. **AC4:** Given the Settings Cloud Context surface, when an administrator configures a connector, then the credential source is shown but never the secret, and test-connection, dry-run preview and a copyable minimal IAM policy are available.
5. **AC5:** Given a project switch, stale snapshot or connection loss, when queries refresh, then previous project data clears and grounded claims are not carried across projects.
6. **AC6:** Given the composed production app, when a keyboard user reviews a grounded report and configures a connector, then focus, error and tab semantics, the axe critical and serious gate and screenshots pass at 1440 and 760 widths, with the Dashboard information budget unchanged.

### Requirement Traceability

Coverage intent: delta over the current released baseline. Mapping is an acceptance obligation, not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| LEG-FR-034 | Expose grounded results as an optional, separately versioned `live_context` report block without bumping the report schema version. | Serializer and legacy-consumer contract tests |
| LEG-FR-035 | Provide a Live Context tab covering every state, with actionable missing-permission remedies. | Compose-built real-data and state-matrix E2E |
| LEG-FR-036 | Provide a Settings Cloud Context surface showing credential source without the secret, with test-connection, dry-run preview and copyable minimal policy. | Compose-built settings E2E and secret-absence assertions |
| LEG-NFR-002 | No credential material may appear in any output. | Secret-absence assertions in UI responses and DOM |
| LEG-NFR-008 | Accessibility and keyboard gates must pass in the composed production app. | Compose production build, Playwright, axe, screenshots at 1440 and 760 |

## Tasks / Subtasks and bounded ownership

Execute one bounded packet at a time on `feature/17-8-live-context-ui`. Each packet owns the named paths.

- [ ] **Packet 8.1: `live_context` report block — owner: API implementer.**
  - Owned write paths: `api/` serializers and schemas **additive only**, `tests/test_api/`.
  - Output: an optional `live_context` block carrying its own `live_context_version: 1`, with no report schema version bump.
  - Acceptance proof: AC1 — serializer and legacy-consumer contract tests.
  - **Shared-file rule:** additive fields only; existing consumers must be byte-compatible. Ship as a separately labelled backend-for-UI PR.
- [ ] **Packet 8.2: Live Context tab — owner: frontend implementer.**
  - Owned write paths: `frontend/src/` report screen and API adapter, `frontend/src/` tests.
  - Output: grounding banner, divergence panel, live blast radius, recoverability table and unreadable-resource list, built from existing primitives.
  - Acceptance proof: AC1, AC2 — component tests plus exact-permission remedy rendering.
- [ ] **Packet 8.3: State matrix — owner: frontend implementer.**
  - Owned write paths: `frontend/src/` report screen, `frontend/e2e/`.
  - Output: off, disabled, denied, empty, loading, failed, partial and degraded states, each stating the actual state and the permitted next action without implying a grounded claim.
  - Acceptance proof: AC3 — state-matrix E2E against seeded API data.
- [ ] **Packet 8.4: Settings Cloud Context surface — owner: frontend implementer.**
  - Owned write paths: `frontend/src/` settings screen, `frontend/src/` tests.
  - Output: credential-source display without the secret, test-connection, dry-run preview and a copyable minimal IAM policy.
  - Acceptance proof: AC4 — settings tests and secret-absence assertions.
- [ ] **Packet 8.5: Project isolation and refresh — owner: frontend implementer.**
  - Owned write paths: `frontend/src/` query and ProjectSwitcher integration, `frontend/e2e/`.
  - Output: previous-project data cleared on switch; grounded claims never carried across projects; stale-snapshot and connection-loss handling.
  - Acceptance proof: AC5.
- [ ] **Packet 8.6: Compose acceptance, accessibility and docs — owner: UI verifier and documenter.**
  - Owned write paths: `frontend/e2e/`, `docs/live-environment-grounding/README.md`.
  - Output: composed-app screenshots at 1440 and 760, axe critical and serious gate, keyboard-only walkthrough, Dashboard information budget unchanged.
  - Acceptance proof: AC6 — LEG-NFR-008 evidence.

## Dev Notes

- Reuse `frontend/src/api/client.ts`, ProjectSwitcher, Card, Button, Skeleton, SegmentedTabs, badges and `theme/tokens.css`. Validate tab and focus semantics rather than assuming primitive reuse proves accessibility.
- Use the existing permanent report route and the existing tabbed report screen. Do not add Dashboard surface area; the Dashboard information budget must be unchanged.
- "Actionable remedy" means the exact action name the operator must grant plus a path to the published minimal policy. A generic "access denied" banner fails AC2.
- A degraded or partial state must be visually distinct from a grounded state. If a reviewer can mistake partial coverage for complete coverage, the slice is not done.
- Never render or store credential material. The settings surface shows the credential **source** only, and never persists a secret in browser storage.
- Grounded claims are project-scoped. On project switch, clear rather than reuse; cross-project carryover is a correctness failure, not a caching nuisance.
- Respect the target stack: Vite, React 18, TypeScript and Tailwind, built to static files and served by the existing FastAPI app. Node must not be present in the runtime image. No CDN imports; icons use `lucide-react`.
- Do not restyle or approximate approved design values. Where an exact visual value differs, the mockup wins.
- Prohibited in this slice and in this epic: any write, apply, destroy, tag, provision or remediate affordance; no remediation buttons, no "fix this" actions. Reports remain advisory with `should_block=False`.
- Epic independence: this screen must render correctly when no automation run exists and must not depend on any Epic 16 route, component or endpoint.

### Project Structure Notes

Work stays within the existing React SPA under `frontend/src/` and `frontend/e2e/`. Follow `frontend/src/theme` and `frontend/src/components/ui`.

### Testing requirements

- Run `npm run ui:gen-api` for API changes, then `npm run ui:typecheck`, `npm run ui:test` and `npm run ui:build`.
- Then `docker compose up -d --build`, wait for `http://localhost:8080/api/v1/health`, seed synthetic grounded data, and run `BASE_URL=http://localhost:8080 npm run test:ui-review` and `BASE_URL=http://localhost:8080 RUN_UI_A11Y=1 bash scripts/ci-local.sh`. Capture 1440 and 760 screenshots, axe and keyboard evidence, then `docker compose down`.
- `npm run ui:dev` is a local convenience only and is never UI verification.
- All browser URLs are root SPA routes on the composed FastAPI app, such as `/`, `/history`, `/settings` and `/reports/{id}`. Vite dev-server and legacy prefixed routes are not verification.
- Run `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` for the serializer change, and `bash scripts/ci-local.sh` for the backend lane.

### Completion and integration boundary

- Attach exact commands, results, versions, screenshots and proof artifact locations per AC and mapped requirement. Independent review resolves findings before advancement.
- This slice closes only grounded presentation and connector configuration UX. It does not qualify a production AWS profile and does not claim live-account breadth.

### References

- [RFC 0002](../../docs/rfcs/0002-live-environment-grounding.md)
- [Canonical feature PRD](../planning-artifacts/prd-live-environment-grounding.md)
- [Epic 17 stories](../planning-artifacts/epics.md)
- [Architecture Section 26](../planning-artifacts/architecture.md)
- [Epic 16/17 boundary plan](../planning-artifacts/epic-16-17-boundary-and-parallelization-plan.md)
- [Operator guide](../../docs/live-environment-grounding/README.md)
- [Project implementation context](../project-context.md)

## Dev Agent Record

### Agent Model Used
Planning preparation only; implementation agent records its model at execution.

### Debug Log References
Not executed.

### Completion Notes List
- Story specification prepared; no implementation, UI verification, qualification or runtime test performed.
- Commands and proofs above are future obligations, not results.

### File List
- `_bmad-output/implementation-artifacts/17-8-live-context-ui.md` (story specification only).
