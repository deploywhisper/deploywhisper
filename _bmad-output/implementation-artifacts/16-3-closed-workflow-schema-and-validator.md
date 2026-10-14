# Story 16.3: Closed Workflow Schema And Validator

Status: done
Preparation: refined
Release: v1.5.0 — P0 highest-priority feature
Dependencies: 16.0; public RFC and 16.0 qualification required

Review gate (2026-10-12): Story 16.0's findings are resolved and requalified; foundation readiness is restored.

## Story

As a workflow author, I want to validate a closed, bounded typed workflow definition, so that unsupported commands or unmatched approvals cannot become a handoff path.

## Acceptance Criteria

1. **AC1:** Given explicit strict integer workflow_version: 2 and a valid bounded upload/analysis/gate/approval/GitHub-handoff DAG with declared typed inputs, source/profile/environment constraints and typed input/step/run/project references, when validation runs, then typed canonical output/digest and field-level locations are returned without executing handlers or accessing network/files.
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

- [x] **Schema contract owner** (AC1/2/3/5)
  - [x] Owned write scope: `infra_automation/contracts.py and workflow_schema.py (new), schemas/infra-automation/workflow-v2.json (new)`.
  - [x] Freeze closed Pydantic typed inputs/outputs, IDs/dependencies, source variant, target/environment binding and substitution vocabulary using the normative workflow v2 contract and fresh v2 fixtures; retain 16.0 fixtures unchanged as historical evidence. Bound every string/list/numeric input. Schema registry describes intake, collection, analyze, policy gate, approval, GitHub handoff only; actual handlers arrive in owning later slices.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **YAML parser and reference owner** (AC1/2/3)
  - [x] Owned write scope: `infra_automation/workflow_validation.py (new)`.
  - [x] Use an installed YAML library with an explicit duplicate-key policy and depth/alias/byte budget; inspect chosen safe loader API against the locked version before coding. Typed substitution traverses declared inputs/output/run/project fields; no eval or templating functions. Limit aggregate returned errors and redact reflected values.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Graph safety owner** (AC3/4/5)
  - [x] Owned write scope: `infra_automation/workflow_validation.py, tests/test_infra_automation workflow fixtures (new)`.
  - [x] Validate deterministic topological order, exact evidence lineage and all-path matching target/environment analysis→gate→approval coverage. Enumerate diamonds, disconnected ancestors, alternate paths and skipped mandatory nodes. Runtime must still recheck success/freshness/live authority; validator cannot certify a future approval.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.
- [x] **Qualification and schema docs owner** (AC1–6)
  - [x] Owned write scope: `tests/test_infra_automation, scripts/ci-local.sh, .github/workflows/ci.yml, docs/infra-automation/workflow-schema.md (new)`.
  - [x] Register the new test directory explicitly in local CI and services shard before relying on discovery. Publish valid/invalid/hostile examples plus 1,000-case timing script and named hardware/workload. No database migration is required.
  - [x] Attach packet-specific acceptance output, touched-file list, migration/contract fixtures and review notes; leave unchecked until verified.

### Review Findings — 2026-10-14

- [x] [Review][Patch][P2] Preserve JSON string and numeric semantics at intake — the YAML loader rejects valid escaped supplementary Unicode, folds literal NEL during canonical reload, rejects other valid JSON Unicode, and interprets exponent numbers such as project_id `1e3` as strings. Add bounded JSON decoding and round-trip/type regressions. [infra_automation/workflow_validation.py:285]
- [x] [Review][Patch][P2] Preserve Python 3.10 qualification test discovery — use the already locked tomli fallback when tomllib is unavailable. [tests/test_infra_automation/test_workflow_qualification.py:9]

## Dev Notes

Architecture §25.5 and [workflow-contract-v2.md](../../docs/infra-automation/workflow-contract-v2.md) require explicit strict integer workflow_version 2, a 50-step maximum and typed whole-value substitution. The maintainer selected this broader contract in the [2026-10-13 course correction](../planning-artifacts/sprint-change-proposal-2026-10-13-workflow-v2.md); it supersedes the workflow-v1 implementation direction in the historical foundation note below. Keep Python/Pydantic and installed YAML dependencies; no DSL engine or template package. Final byte/depth/alias/input limits belong to reviewed contract fixtures, not arbitrary undocumented defaults. Existing config.py is the environment/limit source. No service capability, runner execution or wire API is introduced by pure validation.

### Contracts and migration boundary

Pure validate(definition_bytes, limits, registry_contract) returns typed definition or bounded field/step errors; v2 defines bounded scalar inputs, explicit root environment, uploaded/collected source constraints and application-supplied admitted profile digests, with typed input/step/project/run references; canonical digest algorithm/version is frozen with 16.0. Workflow step contracts distinguish upload advisory source from immutable collected repository source. Every handoff binds the same evidence/target/environment chain; ancestry alone is inadequate. Reject missing, old or unknown workflow majors and nested version fields; no automatic v1 conversion or implicit safety downgrade. A null definition workspace permits project-scoped authoring only: later owners resolve and snapshot a concrete authorized workspace before machine operations. Dependencies are unconditional AND-success prerequisites; exact lineage and matching symbolic target/environment/action are structural obligations, while actual success remains a runtime check. Runner/enrollment, receiver, provenance, state, error and cursor protocols remain independently v1; reports remain v2. Only receiver bindings directly carry workflow revision/input digests, which bind the exact v2 canonical bytes. Do not regenerate or rehash frozen v1 artifacts.

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

- [x] Add regression/contract tests with each packet; do not defer them to 16.19. Use temporary SQLite databases, TestClient and local synthetic fixtures; never real secrets/infrastructure state.
- [x] If adding `tests/test_infra_automation/`, register it in `scripts/ci-local.sh` and `.github/workflows/ci.yml` services pytest shard, and prove discovery includes it; root unittest discovery alone is insufficient.
- [x] Search repository-wide direct instantiations/fixtures whenever changing a constructor/Pydantic/dataclass/API contract; run affected CI shard exactly: `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` and/or `./.venv/bin/python -m pytest tests/test_services -v --tb=short`, plus explicitly registered automation tests.
- [x] Before review run `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh` and `git diff --check`; record actual outputs and resolve failures.
- [x] Keep this slice backend/contract scoped. Record **UI validation not applicable** if no rendered surface changes. If React/browser semantics change, use a separate labeled backend-for-UI PR where required, compose production build (`docker compose up -d --build`), wait for health, seed data and run `BASE_URL=http://localhost:8080 npm run test:ui-review` plus necessary a11y/keyboard/screenshots, then `docker compose down`. Root SPA routes only; Vite is not proof.
- [x] Update version-matched operator/schema/API docs and story file list with the actual implementation. Layered code/security review must examine this slice's trust boundary; no new dependency without explicit approved decision.

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

Codex GPT-6. Root owns course correction, parser/reference/graph integration and final verification. `s163_schema` owns strict models/schema; `s163_v2_design`, `s163_change_impact`, `s163_v2_contract_review` and `s163_readiness` independently established and reviewed the revised contract. `s163_change_docs` aligned planning artifacts. `s163_parser_refs` implemented the bounded loader/reference packet; root implemented and integrated graph safety. `s163_qualification` owned the benchmark harness, corpus qualification and operator guide. `s163_security_review` independently probed the trust boundary; `schema_consistency` independently qualified exported JSON Schema parity.

### Debug Log References

User selected contract revision (option2) on 2026-10-13. Course correction: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-13-workflow-v2.md`. Scoped readiness: READY for workflow-v2 implementation. Frozen-v1 hashes verified unchanged. Installed PyYAML6.0.3 SafeLoader/constructor/composer APIs inspected before parser work. Red-green checks covered parser directives versus quoted data, the resolver semantic-validation gap and exported JSON Schema input-name/newline parity. Independent security review executed 3,660 malformed/reference probes and reverified the resolver fix. Regression execution uses isolated checkouts without the local `.env` or application database. The first root discovery run overlapped schema edits and retained the pre-fix model in memory; it was discarded and rerun against the final snapshot. Final verification evidence is recorded below.

### Completion Notes List

- Implemented strict, closed workflow major 2 with bounded scalar inputs, six declarative step kinds, typed references, uploaded/collected sources and an application-supplied immutable admitted-profile catalog. Frozen v1 artifacts remain byte-identical; independent machine protocols retain their versions.
- Added bounded effect-free YAML/JSON parsing, sanitized diagnostics, typed substitution, deterministic topological validation and exact artifact → analysis → gate → matching decision → handoff lineage. AND-success dependencies prevent structural skip/alternate-branch bypass; runtime success, live authority, freshness and custody remain later-owner checks.
- Canonical bytes materialize defaults/nulls and preserve array order under `tuple-json-utf8-v1`; each result exposes a fresh typed view. No dynamic handler registry, templating, eval, network/file access, database migration, API route or new dependency. Simplification: reuse installed Pydantic/PyYAML and existing application configuration; one shared pure validation port.
- Shipped a generated closed JSON Schema, separate v2 manifest, 8 valid/21 invalid fixtures, hostile parser/reference/graph tests, explicit CI registration, wheel/Docker packaging, configuration bounds and authoring/operator documentation. JSON Schema input-map closure and absolute-end matching are independently checked; optional external-validator checks run locally without adding a dependency to CI.
- Qualified the declared standalone 50-step Linux corpus: 100 warmups and 1,000 measured correct validations, p50 1.502083 ms, p95 1.714917 ms, p99 2.150250 ms (2026-10-14 review requalification; pre-review measurement retained separately), zero failures; four-CPU affinity/quota and 8-GiB cgroup ceiling. Actual Apple M3 Pro/Docker Desktop virtualization and kernel-visible memory are disclosed in `docs/verification/infra-automation/16-3/README.md`; source/harness/corpus hashes match the final implementation. Integrated release-load qualification remains 16.19.
- **UI validation not applicable**: no React route, rendered surface or browser behavior changed. The built production image passed health and validator-import smoke checks using its disposable container filesystem.

### Development verification results — before review fixes

- `./.venv/bin/python -m pytest tests/test_infra_automation -q`: **56 passed, 295 subtests passed**.
- `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`: **629 passed, 1 skipped, 2,146 subtests passed**.
- `./.venv/bin/python -m pytest tests/test_services tests/test_infra_automation -v --tb=short`: **1,288 passed, 2,543 subtests passed**.
- `./.venv/bin/python -m unittest discover -q`: **732 tests, OK, 2 skipped** on the final snapshot.
- `bash scripts/ci-local.sh`: **passed**, all ten explicit directories: analysis 69, API 265, CLI 102, docs 51, infra 263, infra_automation 56, LLM 75, models 22, parsers 43, services 1,232 — **2,178 tests, 2 expected skips**. Additional prompt-injection check: **8 passed, 96 subtests passed**; all skill scenarios, lint/format, dependency consistency, compilation and configured Bandit passed.
- `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, `git diff --check`: passed; **357 Python files** format-clean.
- `./.venv/bin/mypy infra_automation scripts/benchmark_workflow_validation.py --ignore-missing-imports --no-error-summary --disable-error-code=import-untyped`: passed. Exact repository CI mypy remains nonblocking: baseline **311 errors**, current **314**, with only three new missing-PyYAML-stub diagnostics; no new code-type error. No stub dependency or inline suppression was added. Configured Bandit has no new-module findings and passes the high/high gate; the pre-existing medium B104 finding in `services/sample_incident_pack.py:327` remains unchanged.
- `./.venv/bin/python -m pip wheel --no-deps --wheel-dir /tmp/s163-wheels .`: built using the existing pinned build backend; all four packaged modules byte-match the qualified implementation.
- `docker build -t deploywhisper:s163-validation .`: passed; Python 3.11 runtime core unittest invocation: **49 tests, OK, 2 optional jsonschema checks skipped** (both ran and passed in the local suite).
- `docker run --rm --network=none --cpus=4 --cpuset-cpus=0-3 --memory=8g ... python -m scripts.benchmark_workflow_validation --corpus /corpus.json --output /evidence/validator-benchmark.json`: **qualified**, no failures; exact command and allocation in the evidence README.
- Final documentation/contract recheck after completion-note updates: `./.venv/bin/python -m pytest tests/test_docs tests/test_infra_automation/test_workflow_qualification.py -q`: **58 passed, 371 subtests passed**.
- Repository-wide constructor/fixture search covered Settings, Workflow, RegistryContract and ValidationLimits. Frozen-v1 and new-v2 manifest checks, canonical compatibility and future-consumer explicit-major rejection passed.

Remaining scope: publication, persistence, engine/runtime status checks, real collection and UI integration belong to later stories; standalone validation grants no execution authority. Full BMad code review and Git closure remain the next workflow.

### File List

- `_bmad-output/implementation-artifacts/16-3-code-review-2026-10-14.md`
- `.github/workflows/ci.yml`
- `Dockerfile`
- `README.md`
- `_bmad-output/implementation-artifacts/16-3-closed-workflow-schema-and-validator.md`
- `_bmad-output/implementation-artifacts/16-4-scoped-workflows-and-immutable-revisions.md`
- `_bmad-output/implementation-artifacts/16-5-durable-engine-and-fenced-recovery.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/planning-artifacts/architecture.md`
- `_bmad-output/planning-artifacts/epics.md`
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-13-story-16-3.md`
- `_bmad-output/planning-artifacts/infra-automation-v1.5.0-release-plan.md`
- `_bmad-output/planning-artifacts/prd-infra-automation.md`
- `_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-13-workflow-v2.md`
- `_bmad-output/project-context.md`
- `config.py`
- `docs/design/infra-automation-ux.md`
- `docs/infra-automation/workflow-contract-v2.md`
- `docs/infra-automation/workflow-schema.md`
- `docs/rfcs/0001-infra-automation-preflight-and-handoff.md`
- `docs/verification/infra-automation/16-3/README.md`
- `docs/verification/infra-automation/16-3/validator-benchmark-dev.json`
- `docs/verification/infra-automation/16-3/validator-benchmark.json`
- `infra_automation/__init__.py`
- `infra_automation/contracts.py`
- `infra_automation/workflow_schema.py`
- `infra_automation/workflow_validation.py`
- `pyproject.toml`
- `schemas/infra-automation/workflow-v2-manifest.json`
- `schemas/infra-automation/workflow-v2.json`
- `scripts/benchmark_workflow_validation.py`
- `scripts/ci-local.sh`
- `tests/fixtures/infra_automation/workflow_v2/invalid.json`
- `tests/fixtures/infra_automation/workflow_v2/valid.json`
- `tests/test_infra_automation/__init__.py`
- `tests/test_infra_automation/test_workflow_config.py`
- `tests/test_infra_automation/test_workflow_graph.py`
- `tests/test_infra_automation/test_workflow_parsing.py`
- `tests/test_infra_automation/test_workflow_qualification.py`
- `tests/test_infra_automation/test_workflow_references.py`
- `tests/test_infra_automation/test_workflow_schema.py`

### Foundation readiness — 2026-10-10

Story16.0 qualification and final validation are complete. Its maintainer decision, frozen contracts and final readiness report satisfy this story's earlier dependency. This context is ready for its own implementation workflow; all implementation tasks remain unchecked. Use `docs/infra-automation/contract-v1.md` and the qualified evidence boundaries; no production work in this story is claimed by promotion.


## Change Log

- 2026-10-13: Maintainer chose the broader contract revision. Introduced workflow-only major 2, aligned planning and downstream consumer notes, preserved frozen-v1 history, and implemented the bounded pure schema/parser/reference/graph slice with independent review and measured qualification.
- 2026-10-14: Final regression evidence reconciled; all implementation tasks and required gates complete. Story and sprint moved to **review** on `feature/16-3-closed-workflow-validator`. Work remains uncommitted for the separate `bmad-code-review` workflow and its Git closure. Definition of Done: **PASS for the owned slice**, with existing nonblocking type/stub and Bandit debt explicitly recorded; integrated runtime/release qualification remains with later owners.


## Senior Developer Review (AI) — 2026-10-14

The requested `bmad-code-review` ran all three independent layers under full Story16.3 context. Triage: **2 P2 patches, 0 decisions, 0 deferred, 1 dismissed**. See the [review report](16-3-code-review-2026-10-14.md).

The parser patch preserves strict JSON numeric/Unicode semantics with a bounded standard-library decoder before the existing YAML path. Inert parse hooks defer policy decisions until complete JSON syntax is established, preserving YAML flow syntax. New tests prove Unicode representation/canonical parity, exponent-number rejection, surrogate/duplicate/integer/depth guards and all-eight-vector YAML/JSON parity. The qualification suite now uses the already-locked `tomli` fallback when `tomllib` is unavailable. No dependency or frozen contract change was needed.

Independent follow-up closed both findings: 42 Blind Hunter probes and 380 Edge Case Hunter assertions passed; acceptance-lane Python3.10 missing-module regression passed (actual Python3.10 interpreter unavailable). The internal normalization helper finding was dismissed because all its callers supply revalidated models; public substitution revalidates its inputs.

Fresh verification: **62 workflow tests / 324 subtests**, **94% statement coverage**; **738 root-discovery tests, OK (2 skips)**; production Python3.11 core tests **54, OK (2 optional jsonschema skips)**; lint, repository-wide format, targeted Bandit and scoped mypy pass. The wheel byte-matches reviewed source. The same Linux reference corpus/harness is requalified at **p95 1.714917 ms**, zero failures; current source hashes match the new artifact. Fresh `bash scripts/ci-local.sh` passed **2,184 tests across all ten directories**, plus **8 prompt-injection tests / 96 subtests**, dependency checks, compilation, skill scenarios and configured Bandit. Review outcome: **APPROVE**; all ACs and findings are satisfied. Story/sprint are **done**. Git Flow closure uses `feature/16-3-closed-workflow-validator`, with a Lore commit, push to origin and PR targeting `develop`; the workflow completion message records the resulting commit/PR.

**UI validation not applicable.** Existing nonblocking repository type/stub debt and pre-existing Bandit warning remain unchanged. The pure validator grants no authority; runtime/integrated release proof remains with later stories.

- 2026-10-14 review closure: fixed both P2 findings, independently reverified the parser boundary, refreshed source-matched qualification evidence, and approved Story16.3 after all fresh regression gates passed. Next BMad step is scoped Story16.4 readiness/development; downstream stories remain backlog until their own gates pass.
