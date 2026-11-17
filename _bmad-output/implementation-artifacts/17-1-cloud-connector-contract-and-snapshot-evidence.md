# Story 17.1: Cloud Connector Contract, Registry and Snapshot Evidence

Status: done
Preparation: refined
Release: v1.6.0 (independent release train) | Priority: P0 within the independent Epic 17 lane

## Story

As a maintainer, I want a provider-neutral read-only connector contract and an immutable redacted snapshot that enters the existing evidence system, so that grounding is governed by Evidence Law from the first line of code and new providers never require core changes.

## Implementation gates

- Blocked until Story 17.0 records RFC 0002 acceptance, the approved dependency decision, frozen coverage list and feasibility evidence.
- Hard earlier dependencies: **17.0**. **No Epic 16 dependency; do not import from `infra_automation/` or `services/infra_automation_*`.**
- This slice is proven entirely against a **reference stub provider with no network access**. No live provider calls, no credentials and no AWS SDK are exercised here.
- Promote only after dependency evidence, final interfaces and packet estimates are independently reviewed.

## Acceptance Criteria

1. **AC1:** Given a registered reference stub provider, when grounding runs with no network access, then the connector contract, registry, snapshot model and evidence linkage work end to end without any provider SDK present.
2. **AC2:** Given an unregistered, unimplemented or unknown provider, when grounding is requested, then it fails explicitly with a specific cause and never silently returns a successful empty result.
3. **AC3:** Given a snapshot containing sensitive values, when it is persisted, then redaction removes secret values, credential material, user data and raw state, and account identifiers are maskable by configuration.
4. **AC4:** Given grounding disabled, which is the default, when the full existing suite runs, then every existing report, fixture, schema, API consumer, CLI output and agent output is unchanged and no cloud call is issued.
5. **AC5:** Given the same observation twice, when snapshots are produced, then their digests match, and every grounded claim in a report references its snapshot digest.
6. **AC6:** Given a partial or unreadable read result, when the snapshot is built, then it is labelled partial and each unreadable resource carries its specific cause; completeness is never implied.
7. **AC7:** Given a project that has not explicitly enabled a configured connector, when analysis runs, then grounding is skipped and no connector is instantiated.

### Requirement Traceability

Coverage intent: delta over the current released baseline. Mapping is an acceptance obligation, not implementation evidence.

| Requirement | Canonical requirement text | Required proof |
| --- | --- | --- |
| LEG-FR-001 | Provide a provider-neutral read-only cloud connector contract and registry so a provider can be added without modifying core analysis; unregistered and unimplemented providers fail explicitly. | Registry tests covering stub, unimplemented and unknown provider cases |
| LEG-FR-002 | Produce an immutable `LiveContextSnapshot` recording provider, scope, regions, read window, per-resource read status, issued actions and a content digest. | Snapshot model, immutability and field-coverage tests |
| LEG-FR-003 | Persist the snapshot as project-scoped evidence using `live_state` with `deterministic` determinism; Evidence Law applies unchanged. | Evidence Law runtime gate tests for grounded claims |
| LEG-FR-004 | Redact every snapshot before persistence; no secret values, credential material, user data, raw state or plan bytes; maskable account identifiers. | Sensitive-value corpus over persisted snapshots |
| LEG-FR-005 | Integrate snapshot freshness into `ContextSourceMetadata` using the existing freshness vocabulary. | Freshness state matrix tests |
| LEG-FR-006 | Label partial reads as partial and enumerate every unreadable resource with its cause. | Partial and unreadable result tests |
| LEG-FR-007 | Make grounding opt-in per project and disabled by default. | Default-off and unconfigured-project tests |
| LEG-NFR-006 | Snapshots must be deterministic and auditable; every grounded claim references its snapshot digest. | Digest reproducibility and evidence-linkage tests |
| LEG-NFR-009 | With grounding disabled, all existing outputs must be unchanged. | Full existing suite plus legacy consumer contract tests |
| LEG-NFR-010 | A new provider must be addable without modifying core analysis. | Reference stub added with no core analysis diff |

## Tasks / Subtasks and bounded ownership

Execute one bounded packet at a time on `feature/17-1-connector-contract-and-snapshot`. Each packet owns the named paths; coordinate shared paths and do not revert other edits.

- [x] **Packet 1.1: Connector contract and registry — owner: core implementer.**
  - Owned write paths: `cloud/base.py`, `cloud/registry.py`, `tests/test_cloud/`.
  - Output: `CloudConnector` protocol, `ResourceIdentity`, `ReadStatus`, provider registry mirroring `parsers/registry.py`, explicit unimplemented and unknown provider behaviour mirroring `_build_unimplemented_source_handler`.
  - Acceptance proof: AC1, AC2 — registry and contract tests.
- [x] **Packet 1.2: Snapshot model and redaction — owner: core implementer.**
  - Owned write paths: `cloud/base.py` snapshot model, `cloud/redaction.py`, `tests/test_cloud/`.
  - Output: immutable digest-bound snapshot; redaction built on `services/content_security.py`; maskable account identifiers.
  - Acceptance proof: AC3, AC5, AC6 — redaction corpus and digest reproducibility tests.
- [x] **Packet 1.3: Evidence and freshness integration — owner: core implementer.**
  - Owned write paths: `evidence/models.py` **additive enum members only**, `tests/test_evidence/`.
  - Output: `live_state` added to `EvidenceSourceType` and `ContextSourceType`; `deterministic` determinism; freshness reusing the existing vocabulary.
  - Acceptance proof: AC5 — Evidence Law gate and freshness matrix tests.
  - **Shared-file rule:** additive members only. Never remove or reorder existing members. Epic 16 may edit this file concurrently.
- [x] **Packet 1.4: Orchestration service and opt-in gating — owner: services implementer.**
  - Owned write paths: `services/cloud_context_service.py`, `tests/test_services/`.
  - Output: per-project opt-in resolution, disabled-by-default behaviour, snapshot persistence and retrieval, degradation surface.
  - Acceptance proof: AC4, AC7 — default-off and unconfigured-project tests.
- [x] **Packet 1.5: Reference stub provider and conformance seed — owner: test owner.**
  - Owned write paths: `cloud/` reference stub, `tests/test_cloud/conformance/`.
  - Output: a network-free reference provider proving the contract, and the seed of the conformance suite completed in 17.9.
  - Acceptance proof: AC1, and LEG-NFR-010 with no core analysis diff.
- [x] **Packet 1.6: Backward-compatibility proof — owner: test owner.**
  - Owned write paths: `tests/`, CI registration in `scripts/ci-local.sh`.
  - Output: `tests/test_cloud/` registered in local CI and the relevant GitHub shard; full existing suite green with grounding off.
  - Acceptance proof: AC4 — LEG-NFR-009 evidence.

### Review Findings

Independent BMad code review, 2026-11-16: three parallel layers completed (Blind Hunter, Edge Case Hunter, Acceptance Auditor). Three actionable patch findings; one candidate dismissed because direct ORM publication outside admission is explicitly outside the documented boundary and no untrusted production path was established. The review initially left these as action items. All three were resolved and verified in the follow-up below.

- [x] [Review][Patch][P1] Prevent connection-level commit before admission validation (`services/cloud_context_service.py:422`). The Session.before_commit listener does not intercept `admission.session.connection().commit()`. Reproduction mutates a minted summary, publishes with commit=False, flushes and commits the connection; admission then raises invalid_evidence_publication, but report count increases from 1 to 2 and the fabricated summary remains durable. Enforce UOW commit ownership at the exposed connection boundary and regress durable rollback on rejected publication (LEG-FR-003 / same-transaction Evidence Law contract).
- [x] [Review][Patch][P1] Reject changes to pre-existing live-state evidence inside admission (`services/cloud_context_service.py:273`). Validation checks new IDs and minted rows only. An empty admission can update an existing StoredEvidence.summary to a fabricated claim and exit successfully. Protect existing live-state rows against mutation/deletion or validate the full publication write set, including unrelated reports (LEG-FR-003 / evidence admission integrity contract). Both P1 findings require an internal caller using the yielded session; no remotely exploitable route is claimed.
- [x] [Review][Patch][P2] Mask integral floating-point account facts (`cloud/redaction.py:258`). SnapshotFact permits floats, but account masking accepts only ints. With mask_accounts=True, account_id=123456789012.0 survives screening and persistence unchanged. Normalize numeric account comparisons or reject this representation and cover the persisted payload (AC3 / LEG-FR-004).

Review verification: focused pytest suite passed (120 tests, 121 subtests); SDK/network isolation passed (84 tests); repo-wide Ruff lint passed; Ruff format check passed (671 files). Independently reran the two publication reproductions and the float masking reproduction. Full CI and Docker were not rerun for this review; prior implementation evidence remains separate. UI validation not applicable. Next BMad workflow: bmad-dev-story to resolve these findings, followed by bmad-code-review. The original review set the story in-progress; the follow-up below returns it to review. No remote push was performed during this repair task.

## Dev Notes

- Mirror existing extension patterns deliberately: `parsers/registry.py` for registration shape, and `_build_unimplemented_source_handler` in `services/topology_service.py` for explicit unimplemented behaviour. Do not invent a new pattern.
- Reuse `services/content_security.py` redaction helpers (`redact_text`, `redact_value`, `sensitive_artifact_values`) rather than writing new redaction logic.
- Reuse the existing freshness vocabulary `current`/`stale`/`missing`/`incomplete`/`conflicting`/`unknown` from `evidence/models.py`. A parallel vocabulary is a review rejection.
- Live state is a point-in-time observation. Timestamp and digest it; do not present it as ground truth.
- Only add the persistence and entities this slice needs. Do not create the full grounding schema in one foundational migration. Inspect the migration head before allocating changes.
- Respect Python 3.10-compatible code on a 3.11 runtime, Pydantic 2, SQLAlchemy 2 and current lockfiles. **No dependency installation is authorized by this story**; this slice must work with no provider SDK installed.
- Prohibited in this slice and in this epic: any write, apply, destroy, tag, provision or remediate capability; account-wide inventory; scheduled drift; cost estimation. Reports remain advisory with `should_block=False`.
- Epic independence: a grep for `infra_automation` under `cloud/` must return nothing.

### Project Structure Notes

New trees `cloud/` and `tests/test_cloud/` follow architecture §26.3. `tests/test_cloud/` must be explicitly registered in `scripts/ci-local.sh` and the relevant GitHub shard, because recursive root discovery skips directories that are not Python packages.

### Testing requirements

- Before changing constructors or schema, search the entire repository for direct instantiations and fixtures; update all of them. `evidence/models.py` changes are high-blast-radius — run the affected shards exactly as CI does.
- Run `./.venv/bin/python -m unittest discover -q`, `bash scripts/ci-local.sh`, `./.venv/bin/ruff check .` and `./.venv/bin/ruff format --check .`.
- Run `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short` for any serializer or constructor contract change.
- UI validation not applicable.

### Completion and integration boundary

- Attach exact commands, results, versions and proof artifact locations per AC and mapped requirement. Independent review resolves findings before advancement.
- This slice closes only the contract, registry, snapshot and evidence integration against a stub provider. It does not qualify any production provider profile and must not claim AWS support.

### References

- [RFC 0002](../../docs/rfcs/0002-live-environment-grounding.md)
- [Canonical feature PRD](../planning-artifacts/prd-live-environment-grounding.md)
- [Epic 17 stories](../planning-artifacts/epics.md)
- [Architecture Section 26](../planning-artifacts/architecture.md)
- [Epic 16/17 boundary plan](../planning-artifacts/epic-16-17-boundary-and-parallelization-plan.md)
- [Connector contract guide](../../docs/live-environment-grounding/connector-contract.md)
- [Project implementation context](../project-context.md)

## Dev Agent Record

### Agent Model Used
Codex with bounded native implementation and independent read-only interface/security/acceptance reviewers.

### Debug Log References
- Full evidence/reproduction: `docs/verification/live-environment-grounding/17-1/README.md` and `final-verification.json`.
- Review and repairs: `docs/verification/live-environment-grounding/17-1/review-record.md`.
- Storage correction: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-11-13-cloud-storage-isolation.md` and `implementation-plan.md` in the evidence packet.
- Final logs: `/tmp/story17-1-unittest.log`, `/tmp/story17-1-ci.log`, `/tmp/story17-1-api-cli-infra.log`, `/tmp/story17-1-focused-final.log`, `/tmp/story17-1-isolation-final.log`, `/tmp/story17-1-mypy-final.log`, `/tmp/story17-1-bandit-final.log`, `/tmp/story17-1-docker-build-final.log`, `/tmp/story17-1-docker-smoke.log`.
- Rejected shared-head approach: `/tmp/story17-1-shared-head-approach-ci.log`; it is failure evidence, not the final validation result.

### Implementation Plan
- Preserve SDK-free, advisory-first, project-scoped extension contracts. Append only live_state source Literal values; leave legacy constructors and default serialized fields unchanged.
- Keep snapshot internals deeply immutable, revalidate retained/copied models, screen selected data before digesting and preserve opaque authorized scope identity independently of masked account display.
- Install independent cloud schema/version metadata only during explicit enabled configuration in the checked server UOW. Preserve qualified shared source bytes, core metadata and global migration history.
- Publish retained actual facts inside the same authorized transaction; verify every minted field, real report/workspace ownership and the full live-state publication/ref set before commit.
- Qualify all owned contracts against injected reference observations with imports/network blocked, then run existing suites, exact affected pytest shard, static analysis and real runtime packaging checks.

### Review Follow-up — 2026-11-16

- Resolved all three review findings with failing-before regressions and minimal changes to existing admission/redaction paths. No dependencies, shared schema/migration or existing API fields changed.
- Connection, root transaction and explicit SQL commit attempts are refused before durability; caught attempts invalidate admission. Persisted report/evidence rollback is verified from fresh sessions.
- Existing evidence is compared by full stored row values, covering ORM edits, bulk SQL edits, deletion, source relabeling and cross-project mutation.
- Integral floating-point account IDs are masked in persisted snapshots; disabled masking, unrelated values and idempotence remain covered.
- Independent follow-up reviewer confirmed commit reproductions leave zero reports and reported no remaining issue in these fixes.
- Final focused suite: **125 tests and 137 subtests passed**. Isolation: **88 tests passed**. Root: **2,228 tests, 3 skipped, OK**. Exact API/CLI/infra shard: **834 passed, 1 skipped, 2,456 subtests passed**. Full local CI: **3,728 tests across 12 targets, 3 skipped, OK**. Ruff lint/format, scoped mypy, configured Bandit, compilation and dependency checks passed.
- Exact commands, test environment, per-target results, logs and limits: `docs/verification/live-environment-grounding/17-1/review-fixes-2026-11-16.json`. Broad runs used a closed local LLM endpoint and a 0.1 second request timeout. UI validation not applicable; Docker was not rerun for these fixes.
- BMad help routing: findings resolved; next workflow is bmad-code-review. Story/sprint status returned to review; no commit/push performed in this repair task.

### Git Flow Closeout — 2026-11-16

- Final review confirmed all recorded findings resolved; Story 17.1 is done within its reference-provider foundation scope.
- Branch is `feature/17-1-connector-contract-and-snapshot`, current with `origin/develop`; PR target is `develop`.
- Refreshed focused suite passed: 125 tests and 137 subtests. Repo-wide Ruff lint/format and staged diff checks passed.
- Refreshed source-only Docker build passed. Offline built-image smoke passed on non-root Python 3.11.17 with no Node/provider SDKs, masked float accounts and default-closed authorization.
- Closeout evidence: `docs/verification/live-environment-grounding/17-1/git-flow-closeout-2026-11-16.json`. Full validation remains in the review-fixes record. UI validation not applicable; live provider qualification remains outside this story.
- Generated Bandit/test output files are excluded from the commit.

### PR 222 CodeQL Follow-up — 2026-11-16

- Fixed high-severity `py/redos` alert 127 without suppressing the query: replaced ambiguous repeated comment matching with a linear SQLite prefix scan and a bounded keyword match.
- The isolated hostile-comment regression failed against the original matcher (10-second timeout), then passed with the fix. Added long-prefix commit rollback, mixed-prefix and comment-only/literal regressions.
- Focused suite: 127 tests and 145 subtests passed. Isolation: 90 tests passed. Repo-wide Ruff lint/format, scoped mypy and Bandit passed; independent review found no remaining issue.
- Reproduction and verification: `docs/verification/live-environment-grounding/17-1/codeql-redos-fix-2026-11-16.md`. No dependencies, schemas or external contracts changed; UI validation not applicable. Existing broad qualification remains valid; a fresh root run and remote CodeQL rescan are being checked for this revision.

### Completion Notes List
- All six packets and AC1–7 implemented and independently reviewed; status is review, not production provider qualification.
- Added cloud Protocol/registry, frozen identities/facts/read states and digest-bound snapshots. Default AWS/Azure/GCP slots remain unimplemented; reference provider is never globally selected by default.
- Shared redaction plus raw-content alias/numeric-credential/key/identity corpus passes. Sensitive removal is partial, masking precedes digesting, and idempotence/tampered-copy/serializer-warning tests pass.
- Added live_state last to existing ContextSourceType/EvidenceSourceType Literals only. Existing determinism/freshness vocabulary and exact legacy serialized fixtures remain unchanged. Repository-wide constructor search found248direct EvidenceItem/ContextSourceMetadata/Finding call sites; no new required legacy fields or fixture rewrites were introduced.
- Implemented constructor-only trusted UOW gating, default-off no-factory/noDDL behavior, explicit failure causes, immutable persistence, seven-day unreferenced retention, report-reference holds, historical reads after disable/rotation, lawful tombstones and project lifecycle cleanup.
- Evidence admission verifies retained project/digest/scope/read status, derives claim text from actual facts, prevents mutable claim/early commit/publication-set/workspace bypasses and enforces durable same-transaction report/evidence publication.
- The initial global043/shared-model approach broke existing qualified recovery/source assumptions. Independently reviewed minor correction moved storage into its own metadata/schema namespace. models/database.py and models/tables.py are byte-identical to released sources; core head remains042. No execution-epic code/tests/evidence was modified to bless changes.
- Added explicit local/GitHub cloud/evidence/storage targets, SDK-free isolation runner, cloud package/runtime COPY and documentation. No dependency or provider SDK installed into the host application environment. Docker used unchanged locked baseline dependencies; local environment files were excluded from its source-only build context.
- Independent review repairs include numeric secrets, encoded/prefixed raw fields, SQL REPLACE/rowid resurrection, actual workspace ownership, unsupported live-state publication sets and false successful collection of unretained snapshots. Each had failing regressions; reviewers independently reran original reproductions and confirmed closure.
- Focused foundation: **120 tests and 121 subtests passed**.
- SDK/network/execution-module isolation: **84 tests passed**.
- Root smoke: **2,224 tests, 3 skipped**, passed.
- Full local CI: **3,723 tests across 12 targets, 3 skipped**, passed, plus isolation, skill and prompt-injection checks.
- Exact API/CLI/infra pytest shard: **834 passed, 1 skipped, 2,456 subtests passed**.
- Ruff lint/format, scoped mypy, compilation/syntax and configured Bandit gate passed.
- Real non-root Python3.11.17 Docker reference workflow, default-off zeroDDL, no Node/provider SDK and core restart checks passed.
- UI validation not applicable. No existing analysis/scoring/report/API/CLI flow or schema-default fields changed. Live provider IAM/transport, production auth adapters and user-facing surfaces remain owned by later stories.

### File List
- `docs/verification/live-environment-grounding/17-1/codeql-redos-fix-2026-11-16.md`
- `docs/verification/live-environment-grounding/17-1/git-flow-closeout-2026-11-16.json`
- `docs/verification/live-environment-grounding/17-1/review-fixes-2026-11-16.json`
- `_bmad-output/planning-artifacts/epics.md`
- `.github/workflows/ci.yml`
- `Dockerfile`
- `_bmad-output/implementation-artifacts/17-1-cloud-connector-contract-and-snapshot-evidence.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/planning-artifacts/architecture.md`
- `_bmad-output/planning-artifacts/sprint-change-proposal-2026-11-13-cloud-storage-isolation.md`
- `_bmad-output/project-context.md`
- `cloud/__init__.py`
- `cloud/base.py`
- `cloud/redaction.py`
- `cloud/reference.py`
- `cloud/registry.py`
- `cloud/schema.py`
- `docs/ci.md`
- `docs/live-environment-grounding/README.md`
- `docs/live-environment-grounding/connector-contract.md`
- `docs/verification/live-environment-grounding/17-1/README.md`
- `docs/verification/live-environment-grounding/17-1/docker-runtime-result.json`
- `docs/verification/live-environment-grounding/17-1/final-verification.json`
- `docs/verification/live-environment-grounding/17-1/implementation-plan.md`
- `docs/verification/live-environment-grounding/17-1/review-record.md`
- `evidence/models.py`
- `models/cloud_snapshots.py`
- `models/repositories/cloud_snapshots.py`
- `pyproject.toml`
- `scripts/ci-local.sh`
- `scripts/verify_cloud_isolation.py`
- `services/cloud_context_service.py`
- `tests/fixtures/cloud/legacy_evidence_models.json`
- `tests/test_cloud/__init__.py`
- `tests/test_cloud/conformance/__init__.py`
- `tests/test_cloud/conformance/helpers.py`
- `tests/test_cloud/conformance/test_reference_conformance.py`
- `tests/test_cloud/test_contract.py`
- `tests/test_cloud/test_redaction.py`
- `tests/test_cloud/test_registry.py`
- `tests/test_cloud/test_snapshots.py`
- `tests/test_evidence/__init__.py`
- `tests/test_evidence/test_live_state_admission.py`
- `tests/test_evidence/test_live_state_sources.py`
- `tests/test_infra/test_cloud_snapshot_migration.py`
- `tests/test_infra/test_container_contract.py`
- `tests/test_infra/test_supply_chain_remediation.py`
- `tests/test_models/test_cloud_snapshot_storage.py`
- `tests/test_services/test_cloud_context_service.py`

## Change Log

- 2026-11-13: Implemented and qualified the SDK-free contract/snapshot/evidence foundation. Resolved independent security findings, isolated storage from qualified core metadata/history and completed all validation; story moved to review.
