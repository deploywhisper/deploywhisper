# Story 16.17: Signed Trigger Intake and CLI

Status: done
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

- [x] Packet 17.1: Raw-byte signing and replay — owner: API/security implementer.
  - Owned write paths: `api/routes/infra_automation.py; infra_automation/ trigger contract; tests/test_api/`.
  - Output: versioned canonical signing input, bounded body/time/nonce, key-reference lookup and constant-time validation.
  - Acceptance proof: AC1,2,6: altered/reencoded bytes, skew, nonce race/restart and denial-before-scheduling.
- [x] Packet 17.2: Typed intake and idempotency — owner: Service implementer.
  - Owned write paths: `services/infra_automation_service.py; models/repositories/ existing request records; tests/test_infra_automation/`.
  - Output: scoped revision/source allowlists, atomic request digest and origin audit.
  - Acceptance proof: AC2,3,5: cross-scope/unpinned/oversize/quota/conflicting-replay tests.
- [x] Packet 17.3: CLI adapter and authority parity — owner: CLI implementer.
  - Owned write paths: `cli/ automation command group; cli.py wiring; tests/test_cli/`.
  - Output: validate/run/status/list/decision commands over shared authenticated service/API contract.
  - Acceptance proof: AC4,6: envelope/pagination/exit-code tests, denied nonhuman publish/decision and permitted human exact-bound decision.
- [x] Packet 17.4: Types, origins and examples — owner: Frontend/documentation implementer.
  - Owned write paths: `frontend/src/api/schema.d.ts generated; frontend/src/ run origin rendering; docs/infra-automation/triggers.md; examples/infra-automation/`.
  - Output: OpenAPI-derived types, sender signing recipe, origin UI and version-matched CLI examples.
  - Acceptance proof: AC5,6: generation drift, origin visibility and Compose/browser checks for changed UI.

### Review Findings

- [x] [Review][Patch][P1][CR17-1] Advance durable clock observations at machine-effect boundaries and prove rollback cannot revive stale authority without a later signed request. `_check_clock` only reads the floor; only nonce reservation advances it. See formal review for isolated expiry/rollback and actual engine cross-run probes. [services/infra_automation_trigger_authority.py:169]
- [x] [Review][Patch][P2][CR17-2] Describe all four required signing headers and authentication semantics on every signed OpenAPI operation, regenerate client types, and add header-contract parity assertions while retaining authentication before parsing. Current operations have no parameters/security and generated clients declare `header?: never`. [api/routes/infra_automation_triggers.py:140]


- [x] [Review][Patch] Enforce durable clock high-water at machine credential and effect revalidation.
- [x] [Review][Patch] Bind project-scoped publication admission to the concrete authorized machine workspace.
- [x] [Review][Patch] Reject known signing-key reflection in decoded inputs, snapshots and validation outputs.
- [x] [Review][Patch] Bind service models and operation paths to exact authenticated bytes.
- [x] [Review][Patch] Bound the entire CLI transport and prevent late sends; retain worker ownership after ambiguous startup interruption.
- [x] [Review][Patch] Reject noncanonical scheme casing and keep history origin summaries compact.
- [x] [Review][Patch] Update migration-head/guard and origin-accounting fixtures without weakening their invariants.

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
Codex with bounded native protocol, backend, CLI, privilege-proof, UI, browser,
documentation and independent review lanes.

### Debug Log References
- [PR217 conflict and CI repair](../../docs/verification/infra-automation/16-17/pr217-ci-repair.md): base refreshed after backend squash; stale test request clock repaired without weakening runtime fences.
- [Publication browser proof](../../docs/verification/infra-automation/16-17/closeout-browser-proof.md) and [backend closeout](../../docs/verification/infra-automation/16-17/backend-closeout.md).
- [Entry review](../../docs/verification/infra-automation/16-17/readiness.md).
- [Implementation, commands and validation](../../docs/verification/infra-automation/16-17/results.md).
- [Independent review and repairs](../../docs/verification/infra-automation/16-17/review.md).
- [Composed browser proof](../../docs/verification/infra-automation/16-17/browser-proof.md), [screenshots](../../docs/verification/infra-automation/16-17/screenshots.json) and [visual verdict](../../docs/verification/infra-automation/16-17/visual-verdict.json).
- [Structured results and log hashes](../../docs/verification/infra-automation/16-17/validation-summary.json).

### Completion Notes List
- PR217 CI repair: retained complete UI story/sprint records while merging backend squash48a9a9a from develop; resolved tree equals9947f8e before the test repair. Decision-matrix request time now refreshes at signing; deterministic red/green regression verifies real403 denials for all four principal/role pairs after slow setup. Entire privilege module10tests72subtests passes. Production code and negative-clock guards unchanged; UI validation not applicable. Fresh exact-head CI must pass before repair closure.
- 2026-11-09 GitHub analysis follow-up: explicit TLS1.2 minimum added to CLI and TLS fixtures after two CodeQL protocol-default alerts. WholeCLI127/17subtests, automationCLI25/5subtests and productionPython3.11 TLS2tests pass; no certificate/hostname checks disabled. Fresh Compose rerun on corrected CLI1test28.7s/12screens/axe0/visual94; original5970 restored healthy. Final GitHub checks and root smoke validate the publication head; no suppression or support expansion.
- 2026-11-09 Git Flow closeout: both formal findings are resolved and the exact tested runtime/source hashes remain current. Fresh standalone backend51tests/65subtests and generated-contract frontend typecheck pass. Fresh production Compose browser1test28.7s,12screenshots1440/760,zeroaxecritical/serious andvisual94 pass; original container5970d092 restored healthy and private fixtures removed. Separate backend-for-UI and dependent origin-UI PRs target develop, backend first. Story-owned contract is complete; existing production-qualification gates remain with their owning stories. Publication is explicitly authorized; no merge, deployment or release is requested.
- 2026-11-07 review follow-up: CR17-1/CR17-2 resolved. Nine clock regressions plus project/report authorization prove successful-effect clock retention, rollback-only observations under the same SQLite reservation, storage failure, released-savepoint COMMIT failure and lost-driver-reservation replacement preservation. Signed OpenAPI declares all four headers on all five operations; regenerated types and pre-parser denial assertions pass.
- Final review-fix verification: root 1932/3skips; localCI 3402 across ten directories; exactAPI/CLI/infra799pass1skip2433subtests; automation1108pass1skip3236subtests; Python3.11.17 container27; frontend479+2compat/typecheck/build; qualification49 and integrity9tests86subtests; lint/format584/scopedBandit pass. Existing317mypy diagnostics unchanged, none in changed runtime files. Initial date/lost-reservation failures are preserved; all final broad commands passed on the final source.
- UI validation not applicable: generated API types only; no rendered UI/interaction/semantics changed. Existing production qualification gates remain open. See [review-fixes.md](../../docs/verification/infra-automation/16-17/review-fixes.md) and structured results. No public push/PR/release performed. BMad help routes the completed dev-story fix back to code review.
- Independent preparation review cleared the implemented16.0/16.4/16.11 and scoped16.15 history dependencies. The separate16.15 positive HTTPS/real-runner browser gates remain open.
- AC1–3: exact-byte versioned HMAC, fixed paths, bounded skew/body, durable nonce-before-parse reservation, monotonic clock, protected environment key references, typed source/revision allowlists and exact operation idempotency are implemented. Replay survives process restart; invalid/unauthorized input schedules nothing.
- AC4/6: real service/agent credentials remain read/request only. Human session/publication/decision boundaries are preserved. CLI uses actual API/envelopes, private credentials, bounded pagination and total transport deadlines; human decisions remain exact-bound and separate. Human snapshot bytes are unchanged.
- AC5: immutable origin preserves actual principal and server-selected manual/CLI/webhook/PR channel. API/history/detail rendering uses real source data; requested pins are not labelled collected proof. Legacy origins remain unavailable.
- Real privilege/effect proof9tests68subtests uses actual HMAC admission, engine claims, separate human decision and handoff dispatch/consume. Collector/material/custody/delivery ports are explicitly synthetic. Real offline collection qualification49checks and current integrity9tests86subtests pass; production profile coverage is not widened.
- Browser: actual manual andhumanCLI reports plus servicewebhook/agentCLI/PR admissions;1test27.7s,12screenshots1440/760,zeroaxecritical/serious andvisual94/100. Collectedrequests failclosedwithouta runner; this provesadmission/origin only. Originalapp restoredhealthy; privatecredentials/disposable resources removed.
- Fullverification: root1,921tests/3skips; exactAPI/CLI/infra797passed/1skip/2,423subtests; automation1,099passed/1skip/3,236subtests. All ten local-CI targets verified after recorded fixture repairs; initial failures and interrupted stale runs are retained.
- UI479tests+2compatibilitychecks, typecheck/build and current APIgeneration pass. Ruff/repositoryformat and scopedBandit pass. CI mypy retains317existing-code diagnostics, zeroonchangedlines.
- Independent reviews and red/green repairs closed clock, scope, secret-reflection, raw-operation, CLI deadline/interruption/scheme and compact-origin issues. No introduced findings remain open.
- BMad help handoff: code-review closure on separate local backend/CLI and UI branches. No public push, PR, credential setup or release was performed by this development task.

### File List
- `docs/verification/infra-automation/16-17/pr217-ci-repair.md`
- `docs/verification/infra-automation/16-17/backend-closeout.md`
- `docs/verification/infra-automation/16-17/closeout-browser-output.txt`
- `docs/verification/infra-automation/16-17/closeout-browser-proof.json`
- `docs/verification/infra-automation/16-17/closeout-browser-proof.md`
- `docs/verification/infra-automation/16-17/closeout-build.txt`
- `docs/verification/infra-automation/16-17/closeout-compose-down.txt`
- `docs/verification/infra-automation/16-17/closeout-compose-up.txt`
- `docs/verification/infra-automation/16-17/closeout-screenshots/origin-agent-cli-1440.png`
- `docs/verification/infra-automation/16-17/closeout-screenshots/origin-agent-cli-760.png`
- `docs/verification/infra-automation/16-17/closeout-screenshots/origin-history-1440.png`
- `docs/verification/infra-automation/16-17/closeout-screenshots/origin-history-760.png`
- `docs/verification/infra-automation/16-17/closeout-screenshots/origin-human-cli-1440.png`
- `docs/verification/infra-automation/16-17/closeout-screenshots/origin-human-cli-760.png`
- `docs/verification/infra-automation/16-17/closeout-screenshots/origin-manual-1440.png`
- `docs/verification/infra-automation/16-17/closeout-screenshots/origin-manual-760.png`
- `docs/verification/infra-automation/16-17/closeout-screenshots/origin-service-pr-1440.png`
- `docs/verification/infra-automation/16-17/closeout-screenshots/origin-service-pr-760.png`
- `docs/verification/infra-automation/16-17/closeout-screenshots/origin-service-webhook-1440.png`
- `docs/verification/infra-automation/16-17/closeout-screenshots/origin-service-webhook-760.png`
- `docs/verification/infra-automation/16-17/closeout-visual-verdict.json`
- `docs/verification/infra-automation/16-17/git-flow-closeout.md`
- `tests/test_infra_automation/test_trigger_clock.py`
- `docs/verification/infra-automation/16-17/formal-code-review.md`
- `docs/verification/infra-automation/16-17/review-fixes.md`
- `docs/verification/infra-automation/16-17/review-fixes-results.json`
- `README.md`
- `_bmad-output/implementation-artifacts/16-17-signed-trigger-intake-and-cli.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/project-context.md`
- `api/routes/infra_automation_triggers.py`
- `api/schemas.py`
- `app.py`
- `cli/analyze.py`
- `cli/automation.py`
- `config.py`
- `docs/infra-automation/browser-ui.md`
- `docs/infra-automation/triggers.md`
- `docs/verification/infra-automation/16-14/results.json`
- `docs/verification/infra-automation/16-17/browser-cli-invocation-failure.txt`
- `docs/verification/infra-automation/16-17/browser-navigation-wait-failure.txt`
- `docs/verification/infra-automation/16-17/browser-prior-success.txt`
- `docs/verification/infra-automation/16-17/browser-proof.md`
- `docs/verification/infra-automation/16-17/browser-roving-tab-failure.txt`
- `docs/verification/infra-automation/16-17/browser-source.json`
- `docs/verification/infra-automation/16-17/browser-verified.txt`
- `docs/verification/infra-automation/16-17/initial-origin-history-760.png`
- `docs/verification/infra-automation/16-17/readiness.md`
- `docs/verification/infra-automation/16-17/results.md`
- `docs/verification/infra-automation/16-17/review.md`
- `docs/verification/infra-automation/16-17/screenshots.json`
- `docs/verification/infra-automation/16-17/screenshots/origin-agent-cli-1440.png`
- `docs/verification/infra-automation/16-17/screenshots/origin-agent-cli-760.png`
- `docs/verification/infra-automation/16-17/screenshots/origin-history-1440.png`
- `docs/verification/infra-automation/16-17/screenshots/origin-history-760.png`
- `docs/verification/infra-automation/16-17/screenshots/origin-human-cli-1440.png`
- `docs/verification/infra-automation/16-17/screenshots/origin-human-cli-760.png`
- `docs/verification/infra-automation/16-17/screenshots/origin-manual-1440.png`
- `docs/verification/infra-automation/16-17/screenshots/origin-manual-760.png`
- `docs/verification/infra-automation/16-17/screenshots/origin-service-pr-1440.png`
- `docs/verification/infra-automation/16-17/screenshots/origin-service-pr-760.png`
- `docs/verification/infra-automation/16-17/screenshots/origin-service-webhook-1440.png`
- `docs/verification/infra-automation/16-17/screenshots/origin-service-webhook-760.png`
- `docs/verification/infra-automation/16-17/validation-summary.json`
- `docs/verification/infra-automation/16-17/visual-initial.json`
- `docs/verification/infra-automation/16-17/visual-verdict.json`
- `examples/infra-automation/triggers/README.md`
- `examples/infra-automation/triggers/cli-run.example.json`
- `examples/infra-automation/triggers/human-run.example.json`
- `examples/infra-automation/triggers/key-manifest.example.json`
- `examples/infra-automation/triggers/signed-credentials.example.json`
- `examples/infra-automation/triggers/signing_recipe.py`
- `examples/infra-automation/triggers/webhook-request.example.json`
- `frontend/e2e/infra-automation-triggers.spec.ts`
- `frontend/src/api/infraAutomation.ts`
- `frontend/src/api/infraAutomationOrigins.test.ts`
- `frontend/src/api/schema.d.ts`
- `frontend/src/screens/InfraAutomation.tsx`
- `frontend/src/screens/InfraAutomationOrigin.test.tsx`
- `frontend/src/screens/InfraAutomationOrigin.tsx`
- `frontend/src/screens/InfraAutomationRun.tsx`
- `infra_automation/claims.py`
- `infra_automation/lifecycle.py`
- `infra_automation/state.py`
- `infra_automation/trigger_contracts.py`
- `infra_automation/trigger_signing.py`
- `migrations/versions/039_add_signed_trigger_intake.py`
- `models/database.py`
- `models/repositories/infra_automation_runs.py`
- `models/repositories/infra_automation_triggers.py`
- `models/tables.py`
- `schemas/infra-automation/engine-v1.json`
- `schemas/infra-automation/trigger-v1.json`
- `schemas/infra-automation/workflow-lifecycle-v1.json`
- `scripts/compose-story16-17.yaml`
- `scripts/qualify_collection.py`
- `scripts/trigger_ui_fixture.py`
- `services/infra_automation_engine_service.py`
- `services/infra_automation_engine_support.py`
- `services/infra_automation_policy.py`
- `services/infra_automation_service.py`
- `services/infra_automation_snapshots.py`
- `services/infra_automation_trigger_authority.py`
- `services/infra_automation_triggers.py`
- `services/project_service.py`
- `tests/test_api/test_infra_automation_triggers.py`
- `tests/test_api/test_trigger_admission_parity.py`
- `tests/test_cli/test_automation.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_identity_migration.py`
- `tests/test_infra/test_infra_automation_engine_migration.py`
- `tests/test_infra/test_infra_automation_handoff_migration.py`
- `tests/test_infra/test_infra_automation_workflow_migration.py`
- `tests/test_infra/test_migrations.py`
- `tests/test_infra/test_project_membership_migration.py`
- `tests/test_infra/test_receiver_reconciliation_migration.py`
- `tests/test_infra/test_runner_enrollment_migration.py`
- `tests/test_infra/test_trigger_migration.py`
- `tests/test_infra_automation/test_collection_qualification.py`
- `tests/test_infra_automation/test_preflight_evidence.py`
- `tests/test_infra_automation/test_preflight_repository.py`
- `tests/test_infra_automation/test_target_capacity.py`
- `tests/test_infra_automation/test_trigger_authority.py`
- `tests/test_infra_automation/test_trigger_intake.py`
- `tests/test_infra_automation/test_trigger_privileges.py`
- `tests/test_infra_automation/test_trigger_signing.py`

## Change Log
- 2026-11-09: Refreshed PR217 from develop after backend squash; corrected stale decision-matrix fixture time and added deterministic regression for coverage-loaded CI.
- 2026-11-09: Verified unchanged tested source and fresh production Compose proof; accepted story closeout and separate backend/UI publication layout; marked done.
- 2026-11-07: Resolved both formal review findings; repaired loss-of-SQLite-reservation cleanup compatibility; completed full final validation and returned to review.
- 2026-11-06: Implemented all four packets, repaired independent review and verification findings, completed required checks and advanced to review.

### Formal Code Review — 2026-11-07

The initial formal review covered baseline `2fef718` through `51bb952` with blind adversarial, edge-case and acceptance layers. It recorded two actionable findings and returned the story to `in-progress`; that initial task changed review records only. The follow-up resolved both findings and completed full final validation, as recorded in the Dev Agent Record and [review-fixes.md](../../docs/verification/infra-automation/16-17/review-fixes.md). Story is now `review`. No public push, PR or release was performed.
