# Story 16.17: Signed Trigger Intake and CLI

Status: backlog
Preparation: refined
Release: v1.5.0 | Priority: P0, highest-priority feature

## Story

As a CI or CLI operator, I want scoped runs through signed typed intake and the shared API, so that automation starts resist replay without becoming human approval.

## Implementation gates

- Earlier dependencies: 16.4 immutable workflow/run contracts, 16.11 accepted receiver/authority semantics, 16.15 scoped run-history UI.
- Blocked until Story 16.0 public RFC acceptance and executable identity/fencing/isolation/custody/receiver qualification close the readiness gates; documentation refinement does not satisfy those gates.
- Recheck actual prerequisite records before execution. Downstream release acceptance is not a prerequisite for an earlier owned slice; test-double proofs remain explicitly limited.
- Promote to ready-for-dev only after dependency evidence, final interfaces and packet estimates are independently reviewed. Keep unchecked tasks and backlog until then.

## Acceptance Criteria

1. **Given a scoped key ID, method/path/timestamp/nonce and exact raw body bytes, when webhook intake verifies HMAC-SHA256, then an unambiguous length-delimited signing representation and constant-time comparison precede parsing; bounded skew and durable nonce uniqueness reject replay.**
2. **Given the closed version-1 body with revision/project/workspace/source/typed inputs/idempotency key, when admitted, then server allowlists and immutable source commit match and origin/principal are recorded; unknown fields, unpinned/unauthorized source, oversize and invalid inputs schedule nothing.**
3. **Given an idempotency key, when the same authenticated operation and digest repeat, then its durable original result is returned; changed body with reused key returns 409, saturation returns bounded quota errors, and errors/logs never disclose signing keys.**
4. **Given authenticated API/CLI validation/run/status/list/decision requests, when dispatched, then both use the same versioned authority/envelopes with bounded pagination; agent/service/runner cannot publish, acquire human sessions or decide; human CLI decisions obey exact binding and separation rules.**
5. **Given manual, signed webhook, CLI or admitted PR origin, when run history is read, then exact source and authenticated principal type are visible without forged role/actor-header authority; a nonhuman request never becomes a human acknowledgement.**
6. **Given API/OpenAPI/generated types and CLI, when parity tests run, then valid/invalid cases, byte-reencoding signature failure, clock skew/replay/restart, cross-scope denial and human-versus-agent decisions match the same contract.**

### Requirement Traceability

Coverage intent: Delta against released v1.4.0; full canonical mappings below are acceptance obligations, not delivered proof.

| Requirement | Full canonical requirement | Required proof |
| --- | --- | --- |
| IAU15-FR-005 | Distinguish human, service, agent and runner credentials; nonhuman credentials cannot obtain human sessions, publish workflows or decide approvals. | Principal-type privilege matrix |
| IAU15-FR-057 | Start scoped runs manually or through signed timestamped replay-resistant webhook intake with typed inputs, idempotency, source pinning and bounded errors/quotas; record trigger origin and principal. | Raw-byte HMAC/replay/idempotency/invalid-input/source tests |
| IAU15-FR-058 | Expose versioned automation API and CLI validation/run/status/list/decision commands over the same authority, envelopes and generated SPA types; agent read/request mode cannot decide or publish. | API/CLI/OpenAPI parity and nonhuman-mutation denial tests |

## Tasks / Subtasks

Execute one bounded packet at a time on the story feature branch. Each packet owns the named paths; coordinate shared paths and do not revert other edits. Re-estimate after 16.0 spikes; split packets into reviewable PRs without renumbering the canonical story.

- [ ] Packet 17.1: Raw-byte signing and replay — owner: API/security implementer.
  - Owned write paths: `api/routes/infra_automation.py; infra_automation/ trigger contract; tests/test_api/`.
  - Output: versioned canonical signing input, bounded body/time/nonce, key-reference lookup and constant-time validation.
  - Acceptance proof: AC1,2,6: altered/reencoded bytes, skew, nonce race/restart and denial-before-scheduling.
- [ ] Packet 17.2: Typed intake and idempotency — owner: Service implementer.
  - Owned write paths: `services/infra_automation_service.py; models/repositories/ existing request records; tests/test_infra_automation/`.
  - Output: scoped revision/source allowlists, atomic request digest and origin audit.
  - Acceptance proof: AC2,3,5: cross-scope/unpinned/oversize/quota/conflicting-replay tests.
- [ ] Packet 17.3: CLI adapter and authority parity — owner: CLI implementer.
  - Owned write paths: `cli/ automation command group; cli.py wiring; tests/test_cli/`.
  - Output: validate/run/status/list/decision commands over shared authenticated service/API contract.
  - Acceptance proof: AC4,6: envelope/pagination/exit-code tests, denied nonhuman publish/decision and permitted human exact-bound decision.
- [ ] Packet 17.4: Types, origins and examples — owner: Frontend/documentation implementer.
  - Owned write paths: `frontend/src/api/schema.d.ts generated; frontend/src/ run origin rendering; docs/infra-automation/triggers.md; examples/infra-automation/`.
  - Output: OpenAPI-derived types, sender signing recipe, origin UI and version-matched CLI examples.
  - Acceptance proof: AC5,6: generation drift, origin visibility and Compose/browser checks for changed UI.

## Dev Notes

- Reuse: Reuse api/errors.py:ApiRoute/ApiError, existing build_meta/schema helpers and cli/analyze.py output conventions. Existing _project_authorization_from_env is not verified automation identity; resolve dedicated credentials through 16.1/2 authority. Use standard-library hmac/hashlib and existing HTTP facilities unless a dependency decision explicitly changes this.
- Owned entities: Add only durable bounded nonce/replay and idempotency records plus origin fields required by this slice; keys remain environment-backed references, not settings secrets.
- Respect Python 3.10-compatible code/3.11 runtime, Pydantic 2, SQLAlchemy 2 and current lockfiles. No dependency installation is authorized by this story. Inspect migration head before allocating changes.
- No apply/destroy/remediation, arbitrary shell/plugins, automatic approval, new AI Composer, Ansible/Kubernetes/Helm collectors, Git sync, PostgreSQL/HA or broad infrastructure engine. Existing reports remain advisory with `should_block=False`.
- OpenTofu/Terraform licenses remain independent; operator supplies pinned tools. Do not bundle proprietary binaries or claim MIT relicensing. Never commit/transport real state, credentials or saved binary plans; test files are synthetic and protected local real-tool custody is disposable.
- Prior-story intelligence: preceding Epic 16 capabilities are planned dependencies, not claimed implemented. Read their actual Dev Agent Records and contracts before coding. Recent release commits emphasize independently verified artifact identity, signing and separate security regression checks; reuse that evidence discipline.

### Testing requirements

- Before changing constructors/schema, search the entire repository for direct instantiations/fixtures; update affected contracts and run `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` plus the automation shard registered in CI.
- Register `tests/test_infra_automation/` explicitly in `scripts/ci-local.sh` and affected GitHub shards; root discovery skips some directories. Run `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh`, `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`. Keep deterministic fixtures separate from real tool/receiver acceptance.
- UI task/gate: run `npm run ui:gen-api` for API changes, `npm run ui:typecheck`, `npm run ui:test`, `npm run ui:build`; then `docker compose up -d --build`, wait for `http://localhost:8080/api/v1/health`, seed synthetic authorized API data and run expanded `BASE_URL=http://localhost:8080 npm run test:ui-review` and `BASE_URL=http://localhost:8080 RUN_UI_A11Y=1 bash scripts/ci-local.sh` as applicable. Capture 1440/760 screenshots, axe and keyboard evidence, then `docker compose down`.
- All browser URLs are root SPA routes on composed FastAPI, including `/infra-automation`; Vite/dev server and legacy prefixes are not verification. Backend-for-UI behavior uses a separate labeled PR.

### Completion and integration boundary

- Attach exact command/results, source/build/tool versions and proof artifact locations per AC and mapped requirement. Independent review resolves findings before review/done advancement.
- A slice may close only its owned contract; future integration or production support claims wait for their explicit real-profile gates. Any missing mandatory proof keeps the relevant status blocked/backlog or in progress. Public GitHub writes, real credential setup and release publication require authority for those actions unless already explicitly authorized in the session; do not request the same authority again.

### References

- [Canonical feature PRD](../planning-artifacts/prd-infra-automation.md)
- [Requirement text and proof map](../planning-artifacts/infra-automation-requirement-dispositions.json)
- [Epic 16 story](../planning-artifacts/epics.md)
- [Architecture Section 25](../planning-artifacts/architecture.md)
- [Feature UX contract](../../docs/design/infra-automation-ux.md)
- [Readiness report](../planning-artifacts/implementation-readiness-report-2026-10-07-infra-automation-v1.5.0.md)
- [Project implementation context](../project-context.md)

## Dev Agent Record

### Agent Model Used
Planning refinement only; implementation agent records its model at execution.

### Debug Log References
Not executed.

### Completion Notes List
- Story specification prepared; no feature implementation, qualification, public RFC acceptance, release publication or runtime tests performed.
- Implementation and validation commands above are future obligations, not test results.

### File List
- `_bmad-output/implementation-artifacts/16-17-signed-trigger-intake-and-cli.md` (story specification only).
