# Story 16.3: Closed Workflow Schema And Validator

Status: ready-for-dev
Preparation: refined
Release: v1.5.0 — P0 highest-priority feature
Dependencies: 16.0; public RFC and 16.0 qualification required

## Story

As a workflow author, I want to validate a closed, bounded typed workflow definition, so that unsupported commands or unmatched approvals cannot become a handoff path.

## Acceptance Criteria

1. **AC1:** Given workflow_version: 1 and a valid bounded upload/analysis/gate/approval/GitHub-handoff DAG, when validation runs, then typed canonical output/digest and field-level locations are returned without executing handlers or accessing network/files.
2. **AC2:** Given duplicate YAML keys, excessive bytes/depth/aliases, unknown fields/enums/version or more than 50 steps, when parsing runs, then it rejects within configured resource/error bounds before constructing executable domain state.
3. **AC3:** Given cycles, missing dependencies or an unknown reference/output type, when graph/reference validation runs, then the relevant field/step is rejected; functions, evaluation syntax, scripts/plugins, loops and failure/finally execution cannot enter the registry.
4. **AC4:** Given two evidence branches with a handoff on only one branch, when its mandatory analysis, gate and matching target/environment approval are skipped, failed or unrelated, then every possible bypass path is rejected; a matching successful chain is the only admissible structural path.
5. **AC5:** Given apply/destroy/remediation, unattended approval or an unsupported profile, when the definition is validated, then Tier 0/1 scope errors are explicit; schema support for qualified collection never registers a server-side collector executable.
6. **AC6:** Given the declared reference 50-step corpus and hardware, when 1,000 validations run with correctness checks, then recorded p95 is below 500 ms or implementation remains unqualified; no benchmark result is invented during preparation.

### Requirement Traceability

Coverage intent: Delta over accepted v1.4.0; exact canonical requirement text/proof is preserved below. Shared IDs qualify only this owned slice; later mapped stories complete integration.

| Requirement | Contract owned or verified | Required acceptance proof |
| --- | --- | --- |
| IAU15-FR-001 | Support only Tier 0 preflight and Tier 1 human-approved external handoff in v1.5.0; reject apply/destroy, remediation, unattended approvals and unsupported execution profiles. | Scope/RFC review and unsupported-mode rejection corpus |
| IAU15-FR-009 | Publish a versioned workflow schema with typed, bounded inputs and explicit supported step input/output contracts. | Schema valid/invalid fixture corpus |
| IAU15-FR-010 | Validate definitions without side effects using bounded YAML bytes/depth/aliases, duplicate-key rejection and an acyclic graph capped at 50 steps. | Parser resource-abuse and cycle/step-limit corpus |
| IAU15-FR-011 | Accept only the closed P0 registry: supported artifact intake, OpenTofu/Terraform collection, analyze, policy gate, approval and GitHub handoff; reject arbitrary scripts/plugins, loops and generic failure/finally execution. | Registry and unsupported-handler denial corpus |
| IAU15-FR-012 | Resolve only typed substitution references to inputs, declared step outputs and run/project metadata; reject unknown references, functions and code evaluation. | Typed-reference and injection fixture corpus |
| IAU15-FR-013 | Require every executable path to a handoff to pass its mandatory successful evidence analysis, policy gate and matching approval; skipped/failed or unrelated ancestors do not qualify. | Wrong-branch, skipped-ancestor and alternate-path tests |
| IAU15-NFR-008 | Workflow validation must have p95 <500 milliseconds for the declared 50-step workflow corpus under the reference workload. | 1,000-validation timing/correctness benchmark |

## Tasks / Subtasks and bounded work packets

Execute packets in listed dependency order; assign one named owner per packet and review its tests before widening scope. Shared files must accommodate concurrent edits; no global tracker or unrelated story change is authorized by a packet.

- [ ] **Schema contract owner** (AC1/2/3/5)
  - [ ] Owned write scope: `infra_automation/contracts.py and workflow_schema.py (new), schemas/infra-automation/workflow-v1.json (new)`.
  - [ ] Freeze closed Pydantic typed inputs/outputs, IDs/dependencies, source variant, target/environment binding and substitution vocabulary using 16.0 fixtures. Bound every string/list/numeric input. Schema registry describes intake, collection, analyze, policy gate, approval, GitHub handoff only; actual handlers arrive in owning later slices.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **YAML parser and reference owner** (AC1/2/3)
  - [ ] Owned write scope: `infra_automation/workflow_validation.py (new)`.
  - [ ] Use an installed YAML library with an explicit duplicate-key policy and depth/alias/byte budget; inspect chosen safe loader API against the locked version before coding. Typed substitution traverses declared inputs/output/run/project fields; no eval or templating functions. Limit aggregate returned errors and redact reflected values.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Graph safety owner** (AC3/4/5)
  - [ ] Owned write scope: `infra_automation/workflow_validation.py, tests/test_infra_automation workflow fixtures (new)`.
  - [ ] Validate deterministic topological order, exact evidence lineage and all-path matching target/environment analysis→gate→approval coverage. Enumerate diamonds, disconnected ancestors, alternate paths and skipped mandatory nodes. Runtime must still recheck success/freshness/live authority; validator cannot certify a future approval.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [ ] **Qualification and schema docs owner** (AC1–6)
  - [ ] Owned write scope: `tests/test_infra_automation, scripts/ci-local.sh, .github/workflows/ci.yml, docs/infra-automation/workflow-schema.md (new)`.
  - [ ] Register the new test directory explicitly in local CI and services shard before relying on discovery. Publish valid/invalid/hostile examples plus 1,000-case timing script and named hardware/workload. No database migration is required.
  - [ ] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.

## Dev Notes

Architecture §25.5 fixes workflow_version 1, 50-step maximum and typed substitution. Keep Python/Pydantic and installed YAML dependencies; no DSL engine or template package. Final byte/depth/alias/input limits belong to reviewed contract fixtures, not arbitrary undocumented defaults. Existing config.py is the environment/limit source. No service capability, runner execution or wire API is introduced by pure validation.

### Contracts and migration boundary

Pure validate(definition_bytes, limits, registry_contract) returns typed definition or bounded field/step errors; canonical digest algorithm/version is frozen with 16.0. Workflow step contracts distinguish upload advisory source from immutable collected repository source. Every handoff binds the same evidence/target/environment chain; ancestry alone is inadequate. Reject unknown major versions; no implicit safety downgrade.

Use the locked Python-first stack (SQLAlchemy/Alembic/Pydantic and existing libraries), opaque IDs and UTC timestamps. Inspect current migration head and freeze wire/schema fixtures before coding. Existing accepted story capabilities are reused; no full future automation schema, new runtime SDK, Node server or risk-engine fork.

### Acceptance and regression matrix

| Input/condition | Required result |
| --- | --- |
| Valid supported 50-step workflow | Canonical schema-valid DAG; no external effect |
| 51 steps; duplicate key; alias/depth bomb | Bounded validation error and no execution |
| Reference to unknown output/function/injection | Field-located type/reference error |
| Diamond handoff with unrelated approval ancestor | Deny structural bypass |
| Matching chain versus skipped/failed mandatory branch | Only matching structural path accepted; runtime success remains required |

## Implementation verification requirements

- [ ] Add regression/contract tests with each packet; do not defer them to 16.19. Use temporary SQLite databases, TestClient and local synthetic fixtures; never real secrets/infrastructure state.
- [ ] If adding `tests/test_infra_automation/`, register it in `scripts/ci-local.sh` and `.github/workflows/ci.yml` services pytest shard, and prove discovery includes it; root unittest discovery alone is insufficient.
- [ ] Search repository-wide direct instantiations/fixtures whenever changing a constructor/Pydantic/dataclass/API contract; run affected CI shard exactly: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` and/or `./.venv/bin/python -m pytest tests/test_services -v --tb=short`, plus explicitly registered automation tests.
- [ ] Before review run `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh` and `git diff --check`; record actual outputs and resolve failures.
- [ ] Keep this slice backend/contract scoped. Record **UI validation not applicable** if no rendered surface changes. If React/browser semantics change, use a separate labeled backend-for-UI PR where required, compose production build (`docker compose up -d --build`), wait for health, seed data and run `BASE_URL=http://localhost:8080 npm run test:ui-review` plus necessary a11y/keyboard/screenshots, then `docker compose down`. Root SPA routes only; Vite is not proof.
- [ ] Update version-matched operator/schema/API docs and story file list with the actual implementation. Layered code/security review must examine this slice's trust boundary; no new dependency without explicit approved decision.

## Readiness and advancement

Preparation means the work is decomposed, not authorized as implementation-ready. Keep **backlog** until public RFC acceptance (IR-01), executable 16.0 feasibility (IR-02), finalized owning interface/crypto/error fixtures (IR-03), earlier dependencies and packet estimates/ownership are recorded. Re-run implementation readiness before promotion; missing evidence cannot be waived by creating this file. Later 16.11/16.14/16.19 integration does not block owned slice acceptance, but remains required for supported production claims.

## References

- [Project context](../project-context.md#v150-infra-automation-planning-authority)
- [Canonical feature PRD](../planning-artifacts/prd-infra-automation.md)
- [Exact active requirement text/proof](../planning-artifacts/infra-automation-requirement-dispositions.json)
- [Epic 16](../planning-artifacts/epics.md#epic-16-evidence-gated-infrastructure-automation)
- [Architecture §25](../planning-artifacts/architecture.md#25-v150-infrastructure-automation-architecture-amendment)
- [Release plan](../planning-artifacts/infra-automation-v1.5.0-release-plan.md)
- [Readiness gates IR-01–04 and slice boundary IR-06](../planning-artifacts/implementation-readiness-report-2026-10-07-infra-automation-v1.5.0.md)
- [Feature UX](../../docs/design/infra-automation-ux.md)

## Dev Agent Record

### Agent Model Used

Story preparation only; implementation agent/model must be recorded when execution starts.

### Debug Log References

Not executed. No application, migration, test, browser, runner, receiver or benchmark result is claimed by this story preparation.

### Completion Notes List

Prepared implementation context and owned acceptance matrix on 2026-10-07. Governance/feasibility/interface gates remain open; Status is backlog.

### File List

This story file only. Planned write scopes above are prospective, not an implemented file list.

### Foundation readiness — 2026-10-10

Story16.0 qualification and final validation are complete. Its maintainer decision, frozen contracts and final readiness report satisfy this story's earlier dependency. This context is ready for its own implementation workflow; all implementation tasks remain unchecked. Use `docs/infra-automation/contract-v1.md` and the qualified evidence boundaries; no production work in this story is claimed by promotion.
