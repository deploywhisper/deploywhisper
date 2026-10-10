# Story 16.0: Adopt and Qualify the Infra Automation Contract

Status: done

execution_scope: governance-and-synthetic-qualification-only
release: v1.5.0
priority: highest-feature-priority
dependencies: released-v1.4.0-baseline

**Completion boundary:** The bounded governance and disposable qualification work is complete. RFC0001 is accepted under the recorded maintainer-specific exception; IR-01–04 are resolved for foundation readiness. Only dependency-satisfied prepared stories16.1 and16.3 advance. Production implementation, broader support, browser/operations and stable-release qualification remain with later stories.

## Story

As a maintainer,
I want to settle the supported preflight and handoff contract with governance and executable feasibility evidence,
so that implementation starts with tested trust boundaries rather than assumptions.

## Acceptance Criteria

1. **Given** the canonical parent/feature PRDs, architecture §25 and Epic 16, **when** the scope and threat-model review concludes, **then** supported Tier 0 preflight and Tier 1 approved external handoff are explicit, unsupported modes have a rejection corpus, IA-ADR-01–08 have recorded dispositions, and no apply/destroy/remediation, unattended approval, arbitrary script/plugin, HA or new AI subsystem is admitted into P0.
2. **Given** RFC 0001 requires a real governance decision, **when** acceptance is recorded, **then** the record contains the actual publication URL/open date, reviewer/discussion coverage, decision date and approving maintainer outcome under the ordinary seven-calendar-day process or an explicit RFC-specific maintainer-directed exception. Record the exact exception and decision source; never invent elapsed time, platform reviews or independent human approval. Missing acceptance or rejected/unresolved changes keep downstream implementation NOT READY. A drafted PR body or planning authorization is insufficient.
3. **Given** a disposable local-account/session prototype and synthetic project/workspace memberships, **when** bootstrap replay, forged headers, wrong credential audience, session fixation/expiry/logout/reset/revocation, CSRF/Origin failures and cross-scope requests are exercised, **then** all declared unauthorized cases deny, only server-verified humans obtain human capabilities, and cryptographic parameters/resource limits plus a dependency adequacy decision are recorded.
4. **Given** two independent connections contending for one file-backed SQLite database, **when** claims, lease expiry, overlapping coordinator generations, stale heartbeat/log/upload/completion, abrupt restart and transaction crash points are exercised, **then** one current fenced owner wins, committed transitions survive, stale attempts cannot mutate outputs and recovery does not retry uncertain external work.
5. **Given** admitted synthetic IaC in the selected disposable non-root Linux containment profile, **when** real pinned tool/provider execution and hostile path/symlink/Git-config/environment/egress/resource/descendant-process probes run, **then** declared containment boundaries hold with executable evidence and separated execution identities. Unsupported/unavailable profiles fail the gate; fixed argv or dummy process fixtures alone do not qualify isolation.
6. **Given** an actual saved binary plan produced from synthetic infrastructure and finalized in protected operator-local custody, **when** the receiver verifies its opaque handle/raw digest/expiry across restart, overwrite, symlink/TOCTOU, tamper and changed-plan cases, **then** only the original immutable bytes qualify; redacted JSON has a distinct verified digest, binary plans/state never reach the application/public artifacts, and replanning requires a new evidence/decision tuple. Upload-only advisory requests cannot authorize apply.
7. **Given** a synthetic receiver operation and one-use grant, **when** consume-before-action/start/completion crashes, dropped acceptance response, duplicate delivery, revoked membership/target, disable/restore epoch and expired evidence are injected, **then** durable consumption precedes action, the same operation is recovered without a second action, new action checks live authority, uncertain outcomes remain `delivery_unknown` with their target lock, and reconciliation never reports mere dispatch acceptance as deployment success.
8. **Given** spike results and approved design values, **when** contracts freeze, **then** versioned workflow/runner/receiver/provenance, source variants, report/hash compatibility, API routes/errors, permission matrix and reviewed screen composition have valid/invalid fixtures and named owners. Unknown versions/states fail closed; no proposed schema or mock UI is represented as an implemented route.
9. **Given** independent review, real RFC outcome and reproducible evidence, **when** readiness is rerun, **then** IR-01–03 close only against their actual acceptance evidence, IR-04 has bounded prepared context specifications for all 20 stable-ID stories and revised estimates, and remaining blockers are explicitly carried forward. Story 16.0 cannot be marked done while its mandatory RFC, spike or contract gates are unresolved.

### Requirement Traceability

| Ownership | Requirements | Required proof / boundary |
| --- | --- | --- |
| Primary | IAU15-FR-001 | AC 1–2, accepted bounded scope and unsupported-mode corpus |
| Primary | IAU15-FR-041 | AC 5–7, real local-custody/restart/tamper/expiry/changed-plan and receiver recovery qualification |
| Supporting feasibility, not downstream delivery | IAU15-FR-002–008, 009–013, 016–022, 024–027, 030–033, 035–040, 042–051, 058 | AC 3–8 qualify architecture assumptions; product ownership remains with mapped 16.1–16.18 stories |
| Supporting NFR qualification | IAU15-NFR-001–004, 007, 009–012; NFR-SEC-01–04, 06–07 | Record fault/auth/secret/Evidence Law contract results and future workload/browser/recovery/release proofs; no capacity, universal redaction or production certification from this spike |
| Governance | GOV-09, GOV-11–13 | Public RFC and real area ownership/coverage-gap evidence |
| Coverage intent | Delta | Existing v1.4.0 status and story numbering preserved; 12.5 is a parallel release prerequisite, not replaced |

Requirement text and proof ownership follow the [72-row active inventory](../planning-artifacts/infra-automation-requirement-dispositions.json) and [feature PRD](../planning-artifacts/prd-infra-automation.md); ranges above are supporting scope, not reassignment or delivery credit. IR-04 refinement links do not prove experiments ran.


### Exact primary acceptance contracts

| Requirement | Canonical contract | Required proof |
| --- | --- | --- |
| IAU15-FR-001 | Support only Tier 0 preflight and Tier 1 human-approved external handoff in v1.5.0; reject apply/destroy, remediation, unattended approvals and unsupported execution profiles. | Scope/RFC review and unsupported-mode rejection corpus |
| IAU15-FR-041 | Authorize exact-plan handoff only when the qualified self-hosted receiver can verify the original immutable saved-plan bytes in protected local custody by opaque handle, raw digest and expiry; no server/public-artifact plan storage, and replanning requires fresh evidence/approval. Upload-only advisory receipts never authorize apply or require invented repository provenance. | Real custody access/restart/overwrite/symlink/expiry/replan spike and receiver tests |

## Tasks / Subtasks

Each numbered packet is independently reviewable. Assign a named responsible contributor before execution; role labels below define responsibility, not invented staffing. Start with a story branch from `develop` under CONTRIBUTING Git Flow. Keep each packet's changes bounded and identify its acceptance evidence in the PR. No production automation tables, app routes, migrations or React screens are authorized by this story.

- [x] **WP1 — Scope, threat model and public governance preparation (AC 1–2).** Responsible: maintainer/architecture with security reviewer.
  - [x] Preconditions: read all References; compare parent exclusions, active requirement inventory and architecture §25; inspect current CODEOWNERS. Writes: RFC/planning corrections and `docs/verification/infra-automation/16-0/` review packet only.
  - [x] Describe assets/actors/trust boundaries and abuse cases for identity, SQL claims, hostile sources, local custody, grants, restore and remote outcomes. Record host/DB-admin/compromised-runner limits; classify IA-ADR-01–08 accepted/revised/rejected with reasons after review.
  - [x] Prepare public RFC PR text, references, reviewer-area requests and an empty outcome record. Publication and review requests follow the actual scope authorized in the session; if already explicitly authorized, proceed without asking again. This preparation itself publishes nothing.
  - [x] On authorized publication, record actual PR URL/open timestamp, applicable area review requests or direct named owner decision, and security/governance/independent-review coverage gaps. Observe the ordinary seven-day process or record the explicit RFC-specific maintainer exception; retain actual review coverage and decision source, never infer timeout acceptance.
  - [x] Output: scope/unsupported corpus, threat model, review links/dates/outcome. Failure: missing outcome or rejected unresolved contract retains IR-01 and downstream NOT READY; no emergency exception is assumed.

- [x] **WP2 — Verified identity/session and route-scope qualification (AC 3).** Responsible: backend/security. Depends: WP1 threat-model inputs, not public acceptance of untested assumptions.
  - [x] Preconditions: isolated temp database, synthetic accounts/tokens and no app database import side effects. Writes: disposable prototype plus safe harness/fixtures under proposed `tests/fixtures/infra_automation/qualification/16_0/identity/`; sanitized evidence only in verification directory.
  - [x] Exercise one-use/expiry bootstrap with no default password; salted password verifier and high-entropy opaque session storage as hashes; compare existing crypto suitability, cost parameters and login abuse/resource bounds. Pin a supported choice with reviewer rationale; if inadequate, document a dependency request and leave that gate open rather than install a package.
  - [x] Test secure HttpOnly/SameSite cookie scope, supported HTTPS Secure policy, login/privilege-change rotation, absolute/idle expiry, logout, reset and revocation; deny missing/incorrect CSRF and Origin on cookie mutations, session fixation and header spoofing.
  - [x] Matrix: human/service/agent/runner/receiver × admin/maintainer/reviewer/contributor/read-only × project/workspace × workflow/publish/run/decision/target/enrollment/report/artifact/policy/settings. Deny absent memberships, cross-project object IDs and legacy share/header bypass. Shared-mode requester cannot approve; authenticated single operator is an acknowledgement.
  - [x] Output: parameter/version decision, route/permission fixture matrix and measured failures. Failure: any unauthorized access, reusable token persistence or unaudited compatibility bypass keeps IR-02 open; prototype is not 16.1/16.2 delivery.

- [x] **WP3 — SQLite ownership, fencing and restart qualification (AC 4).** Responsible: backend/persistence. Depends: WP1 failure model.
  - [x] Preconditions: temp file-backed SQLite, two genuinely independent connections (not one mocked session or `:memory:` database). Writes: disposable minimal rows/harness plus synthetic fixtures under `.../qualification/16_0/sqlite/`; no application Alembic migration.
  - [x] Fix transaction/CAS/unique-constraint semantics with state version, coordinator generation, monotonic attempt/fence, lease and authorization/restore epoch. Synchronize contenders at claim/commit and assert one accepted owner; inspect lock/busy handling with bounded retries.
  - [x] Kill/restart at precommit/postcommit/output-before-success, overlap old/new coordinator and expire/reclaim leases; submit old heartbeat/log/upload/completion against the new fence. Assert committed state remains and stale mutations deny. Retry only declared local idempotent work; unknown external effects remain reconciliation work.
  - [x] Output: runnable crash/race corpus with timelines/DB digests, selected SQLite parameters and unresolved limits. Failure: lost committed transition, multiple current owners or stale writes retains IR-02; no 10-run capacity claim from this microspike.

- [x] **WP4 — Real hostile-source Linux containment qualification (AC 5).** Responsible: runner/security. Depends: WP1 threat model and explicit operator tool/profile availability.
  - [x] Preconditions: qualified disposable Linux non-root container sandbox, preinstalled pinned tool/provider catalog, synthetic no-cloud source, no real credentials and controlled offline/local dependencies. If absent, record exact blocker; do not install tools or choose a less isolated profile silently.
  - [x] Writes: private temp workspace/source/binary outputs; commit only harmless source and probe harness under `.../qualification/16_0/isolation/` plus sanitized results. Never mount the app database/artifact store, host secrets or Docker socket into the task.
  - [x] Execute actual OpenTofu/Terraform synthetic plan/provider or external-program probes; record image/tool/provider digests, UID, capabilities, mounts, seccomp/network configuration and source SHA. Reject untrusted PR sources, path traversal/symlink escape, inherited hooks/config and catalog/argv substitution.
  - [x] Probe environment allow-list with synthetic sentinel values, collector/receiver identity separation, blocked egress/metadata and approved local traffic; verify time/CPU/memory/disk/output caps, disk-full/partial-upload cleanup and kill all descendants on cancel/timeout/lease loss.
  - [x] Output: attack/result corpus for real tool execution, supported profile/version matrix and known host trust limits. Failure: any undeclared host/credential/egress access or surviving child keeps IR-02 open. Dummy probes may test harness mechanics but never satisfy this packet's real containment proof.

- [x] **WP5 — Exact-plan local custody and receiver recovery qualification (AC 6–7).** Responsible: receiver/security. Depends: WP3 durable concepts; WP4 real saved-plan fixture for full custody proof.
  - [x] Preconditions: protected temp custody store with separate collector/receiver identities; actual synthetic saved binary plan, screened JSON and raw/sanitized digests. Synthetic byte fixtures may exercise protocol faults first but do not replace real saved-plan verification.
  - [x] Writes: private temp custody/receiver SQLite state and prototype; safe grant/receipt fixtures and harness under `.../qualification/16_0/receiver/`. No real GitHub/cloud mutation. A counted harmless local action models the receiver action boundary.
  - [x] Verify owner-restricted access, atomic immutable finalization, opaque handle, no-follow descriptor-based digest verification, restart persistence, encryption/storage policy and bounded expiry/cleanup. Attack overwrite/symlink swap/TOCTOU/tamper/unauthorized identity/expiry; changes deny. Never persist raw plan/state in app, logs or public artifact locations.
  - [x] Freeze advisory_request versus exact_plan tuple, canonical serialization/hash and shortest deadline (default collection TTL 60 minutes unless stricter). Mutate each source/revision/input/scope/report/policy/unit/target/payload/custody/digest/epoch field independently; require new evidence/approval and reject advisory mutation or replan under an old grant.
  - [x] Persist one-use consume and receiver operation before counted action. Crash before/after consume, before/after start and completion; lose response and replay request; prove operation deduplication and explicit uncertainty where start outcome cannot be established. Recheck membership/target/feature/restore epochs before starting/resuming action; unavailable authority fails closed.
  - [x] Preserve canonical target locks through delivery_unknown, cancellation and lease expiry; reconcile signed sequenced receipt/outcome without a second action. Audited lock break must not mint new authorization. Record accepted versus observed-terminal semantics explicitly.
  - [x] Output: real custody evidence, fault matrix and chosen receiver recovery contract. Failure: duplicate counted action, plan substitution, stale authority or automatic unlock retains IR-02; no exactly-once deployment claim or production receiver integration credit.

- [x] **WP6 — Versioned contracts, report compatibility and UX freeze (AC 8).** Responsible: architecture/API with UI reviewer. Depends: WP2–5 evidence; draft fixtures may precede final freeze.
  - [x] Writes: reviewed secret-free `schemas/infra-automation/` fixtures, `docs/infra-automation/` protocol notes and feature design references; actual production handlers/schema classes/React changes belong to later stories. Name the owning story for each contract and freeze content digests/version change rules.
  - [x] Specify workflow v1 valid/invalid fixtures, closed step registry, typed references, bounded YAML/cycles/50-step ceiling and matching gate/decision coverage. Define uploaded unavailable-source versus admitted immutable collected/exact-plan source variants; never invent a SHA for upload-only evidence.
  - [x] Freeze runner v1 enrollment/claim/heartbeat/log/upload/complete fields, attempt/fence/epoch/audience checks; receiver v1 consume/receipt/status/outcome/reconcile and exact grant/tuple/source/target/custody binding. Unknown major/capability or unknown enum denies without safety downgrade.
  - [x] Freeze run progression and stopped_by_gate/rejected/expired/timed_out/cancelled/failed/succeeded/delivery_unknown distinctions, step states, permission/route matrix, paginated/log-cursor contracts and ApiError fixtures: 401/403/non-disclosure, 409 conflict, 422 invalid, 429 quota and fail-closed unavailable authority with retryability/correlation metadata.
  - [x] Prove report v2 optional provenance v1 tolerance and canonical hash behavior with existing API/UI/CLI/agent/fixture consumers; inspect external analysis-action consumer contract separately without copying its runtime into this repo. Prefer relational linkage first; incompatibility requires an explicit reviewed major migration, never invented report v2.1.
  - [x] Review compositions for automation root/workflow/run/approval/runner/inventory/settings journeys using actual `frontend/src/theme` and UI primitives plus approved v3 values. Record exact decision fields, acknowledgement copy, disabled/denied/stale-project/unknown/recovery states, focus/keyboard behavior and future 1440/760-width Compose screenshot cases; do not add Dashboard cards or new libraries.
  - [x] Output: versioned wire fixtures, permission matrix, compatibility decision and composition review. Failure: unresolved wire/schema/hash/UX choice retains IR-03; token reuse alone is not pixel parity.

- [x] **WP7 — Independent review, bounded downstream refinement and readiness (AC 9).** Responsible: maintainer with independent architecture/security reviewer. Depends: WP1–6 mandatory results.
  - [x] Writes: evidence summaries/readiness updates, canonical corrections only if warranted, and context/specification references for 16.0–16.19. Review named packets for broad 16.5/16.11/16.18 with responsibility/write scope/preconditions/proofs and re-estimate from spikes; preserve IDs and earlier-only dependency order.
  - [x] Link all 20 prepared story specifications through the canonical epic/tracker/map; verify each owns needed entities only, tests/docs per slice and scoped doubles versus later integration. Refinement closes only IR-04's preparation gap, not runtime proof or dependency readiness.
  - [x] Independent reviewer reruns the reproducible negative/crash/containment/custody corpus, checks evidence custody, contract digests and RFC actual outcome. Resolve defects; preserve dissent, known limits and unfinished gates in the report.
  - [x] Rerun implementation readiness with evidence-linked IR-01/02/03/04 dispositions and `bmad-help` handoff. Promote only individually prepared dependency-satisfied downstream stories, never all stories because this file exists. Stable release still requires 16.19 and 12.5 plus scoped 12.7/12.8 acceptance.

- [x] **Validation record (AC 1–9).** Record exact executed commands, versions, exit codes and acceptance findings; executed evidence is indexed in the Dev Agent Record.
  - [x] Run relevant documentation checks and `git diff --check`. For any retained Python harness/fixture change run `./.venv/bin/ruff check .`, **repo-wide** `./.venv/bin/ruff format --check .`, `./.venv/bin/python -m unittest discover -q` and affected registered discovery/CI shard; root discovery alone is insufficient. Use `bash scripts/ci-local.sh` for broad retained changes.
  - [x] Production UI remains unchanged: record **UI validation not applicable** for this scope. If scope is explicitly widened to real React changes, use a separate sanctioned UI story/PR and Compose production build, seed actual APIs, root-SPA Playwright/axe/keyboard/screenshots at `http://localhost:8080`, then Compose down; Vite cannot prove acceptance.

## Dev Notes

### Evidence custody and execution limits

Proposed sanitized evidence destination: `docs/verification/infra-automation/16-0/`. Use a versioned manifest with `phase`, `status` (`planned`, `passed`, `failed`, `blocked`), timestamp, command, tool/image versions, synthetic input digests, exit codes, case results, sanitized log path, reviewer and open issues. A planned manifest is not executed evidence. Store prototype databases, credentials, raw logs, binary plans/state, generated sandbox outputs and disposable source checkouts in private temp directories and never commit them. Commit harmless harnesses/fixtures and screened summaries only; provide reproducible commands and reviewer access instructions without embedding secrets.

This story permits local reversible synthetic qualification; no infrastructure mutation, real cloud credential use, app route/migration or dependency installation by default. A dependency addition needs its explicit approved decision. Public PR publication/review requests need authority for those actions unless already explicitly authorized in the session; honor existing authorization without asking again. An unavailable prerequisite is a recorded failed/blocked qualification, never an assumed pass. Do not change support profiles or downgrade controls to meet a deadline.

### Verified brownfield reuse and boundaries

- `api/dependencies.py` is a dependency placeholder, not working authentication. `api/routes/projects.py` accepts `X-DeployWhisper-Project-Role`/`-Keys`; `services/project_service.py::normalize_project_role(None)` returns admin. These are negative-baseline cases; reuse role/capability vocabulary, never caller identity authority.
- `models/database.py` owns `engine`, `SessionLocal` and SQLite foreign-key initialization. Isolate prototype database construction; importing app DB helpers must not touch real `data/deploywhisper.db`. Product SQLAlchemy/repositories/migrations are later-slice reuse; allocate future migrations from actual head.
- `services/intake_service.py` and `services/content_security.py` already classify/screen inputs; `services/artifact_snapshot_service.py` applies report-directory/name/symlink restrictions. Reuse their contract knowledge; snapshots are not a sensitive binary-plan custody store and regex redaction is not complete secrecy proof.
- `services/analysis_service.py`, `analysis/`, `evidence/` and `services/policy_adapter_service.py` remain the shared scoring/advisory path. Approval eligibility is separate; `should_block=False`, go/caution/no-go and typed insufficient_context retain actual meanings.
- `api/errors.py`, `api/schemas.py`, existing API-client/generated-type patterns and `services/report_service.py` guide additive envelopes and report compatibility. Search all constructor/serializer/hash consumers before any later contract change; run API/CLI/infra pytest shard exactly as CI when affected.
- `integrations/github/app_service.py` currently pins API `2022-11-28`; the proposed automation adapter pins `2026-03-10` under §25.7. Keep adapters/tests version-specific; HTTP acceptance/run ID is not deployment completion. This preparation adds no live network adapter or action runtime.
- Actual pins in `pyproject.toml`/`requirements.txt` include FastAPI 0.136.1, SQLAlchemy 2.0.49, Pydantic 2.13.3 and cryptography 50.0.2. Mandatory project context now matches Pydantic 2.13.3; actual locked files still prevail if later edits diverge. Inspect installed versions before spikes; no upgrade or latest-version assumption. Existing verified primary research is the API/tool starting point; reverify official sources if a contract assumption changes.
- Python runtime targets 3.11 with declared floor >=3.10; Node is build-only. Proposed Linux runner is separately deployed. Marketplace action runtime/package remains external in `deploywhisper/analyze-action`.

### Prior work and handoff

16.0 is the first story in this epic; no earlier Epic 16 implementation supplies these capabilities. Recent baseline commits `ff7191f`, `f2d540b`, `d634bca`, `935f3bb` preserve independently verified release/artifact identity, while `36b7109` protects security regressions from module reload order. Carry that evidence discipline forward; do not treat old release proof as automation proof. Governance qualification may progress concurrently with 12.5 SBOM, but feature gates cannot be waived by its completion. Later slices own production code; 16.14/16.15/16.19 must prove real integrated collector/custody/receiver and composed UI support.

### References

- [Mandatory project context](../project-context.md), [parent PRD](../planning-artifacts/prd.md), [feature PRD](../planning-artifacts/prd-infra-automation.md), [active/original dispositions](../planning-artifacts/infra-automation-requirement-dispositions.json).
- [Architecture §25.1–25.12](../planning-artifacts/architecture.md#25-v150-infrastructure-automation-architecture-amendment), [Epic 16 and complete sequence](../planning-artifacts/epics.md#story-160-adopt-and-qualify-the-infra-automation-contract), [release plan](../planning-artifacts/infra-automation-v1.5.0-release-plan.md).
- [Readiness IR-01–04](../planning-artifacts/implementation-readiness-report-2026-10-07-infra-automation-v1.5.0.md#6-final-assessment-and-blocker-registry), [research](../planning-artifacts/research/technical-infra-automation-research-2026-10-07.md).
- [RFC 0001 and Review Plan](../../docs/rfcs/0001-infra-automation-preflight-and-handoff.md#review-plan), [public RFC process](../../docs/rfcs/README.md), [CODEOWNERS](../../.github/CODEOWNERS), [contribution workflow](../../CONTRIBUTING.md).
- [Feature UX](../../docs/design/infra-automation-ux.md), [canonical UX](../planning-artifacts/ux-design-specification.md), [approved v3 mockup](../../docs/design/deploywhisper-redesign-v3.jsx).

## Dev Agent Record

### Agent Model Used

Story preparation: Codex. WP1 execution (2026-10-09): GPT-6-based Codex with an independent native read-only agent for technical review inputs; no public maintainer approval claimed.

### Debug Log References

Story preparation (2026-10-07) executed no spikes, public publication, application changes or qualification. The authorized Git Flow closeout subsequently opened [PR #154](https://github.com/deploywhisper/deploywhisper/pull/154) on 2026-10-08T08:06:23Z for planning/RFC review. Reuse that PR rather than opening a duplicate. Its minimum review window ends no earlier than 2026-10-15T08:06:23Z; real reviewer outcome and all spike/contract evidence remain pending.

### Completion Notes List

Context specification prepared for governance and synthetic qualification only. Acceptance tasks remain unchecked. RFC 0001 remains Proposed; IR-01–04 evidence and downstream production implementation remain outstanding. Story status denotes permission to begin this bounded work, not completed governance or production readiness.

### WP1 execution — 2026-10-09

- Started from clean `develop` on `feature/16-0-infra-automation-qualification`. Responsible preparation contributor: Codex; accountable public maintainer remains @pramodksahoo. Independent human review and future contributor assignments are not fabricated.
- Loaded project context and story References; BMad Help catalog confirms the bounded Dev Story lane. Prepared scope/threat-model inputs, 34 planned admission/rejection scenarios, conditional IA-ADR-01–08 recommendations, area-review continuation text and an empty public outcome record under `docs/verification/infra-automation/16-0/`.
- Read-only `gh pr view 154 --json url,state,createdAt,headRefName,baseRefName,author,reviewRequests,reviews,comments,mergedAt` returned exit 0: opened 2026-10-08T08:06:23Z; merged 2026-10-08T08:37:29Z; no reviews/comments/outstanding requests. Corrected RFC/readiness publication history. Merge is not qualifying acceptance; original minimum decision time remains 2026-10-15T08:06:23Z, with actual continuation/window and maintainer outcome still required.
- WP1 remains incomplete. No final ADR disposition, public review request or acceptance is claimed. WP2–7 and runtime qualification remain unrun; ordered Dev Story task completion stops at unresolved WP1 governance. All downstream statuses remain backlog. UI validation not applicable: no rendered surface or browser behavior changed.
- Validation: documentation discovery 51 passed; RFC guardrails 6 passed; root unittest smoke 555 run, OK with 1 skip; Ruff lint passed and repo-wide format check reports 306 files formatted; whitespace and packet digest/link/status checks passed. Full local CI and runtime spikes were not run for this documentation-only packet. Exact commands, versions, exit codes and input digests are in the manifest. Internal technical review passed after epic-status and explicit bypass-case corrections; it supplies no public human approval.

### Synthetic qualification resume — 2026-10-09

- Corrected the earlier blanket WP1 halt: WP2 explicitly depends on threat-model inputs, not public acceptance; WP3 needs the failure model, and WP5 permits synthetic faults before real saved-plan proof. Public RFC acceptance remains open and no downstream story is promoted.
- Named responsible contributors: Codex native `identity_spike` for WP2, `sqlite_spike` for WP3, `receiver_spike` for partial WP5, `contract_assessment` for WP6 drafts; root Codex integrates and owns WP4 prerequisite/readiness/verification records. Internal reviewers `blind_hunter`, `edge_hunter` and `acceptance_auditor` supply technical input, not public human approval.
- WP2: disposable account/session/HTTPS TestClient prototype, 18 tests and 2,000 permission outcomes (1,946 unauthorized denials). Selected existing PBKDF2-HMAC-SHA256 at 600,000 iterations with bounded parsing/concurrency/abuse windows, 128-bit salts and 256-bit session/bootstrap/CSRF material; actual median 79.190 ms on local ARM64. Existing primitives are adequate for this bounded experiment; production hardware/abuse persistence and public adequacy acceptance remain pending. No new dependency or application authentication is delivered.
- WP3: 11 tests against private file-backed SQLite, including synchronized independent-process ownership, state versions/unique constraints, fences/generations/epochs, bounded busy retries, stale heartbeat/log/upload/completion and abrupt precommit/postcommit/output-before-success restart. Unknown external work retains locks and never retries. Local SQLite version/PRAGMAs/timelines/digests are recorded; no capacity, power-loss or HA claim.
- WP4 blocked: Docker CLI is present but daemon image enumeration exited 1; OpenTofu/Terraform are absent on PATH and no approved pinned preinstalled Linux tool/provider profile is supplied. No tools/images were installed and no fallback profile was selected. No actual saved plan or containment probe exists.
- WP5 partial: 12 tests, 30 tuple mutation denials, five real abrupt child crash points, hashed one-use consumption, live authority checks, custody descriptor integrity doubles, unknown-outcome locks and authenticated sequenced receipts. Reconciliation requires independently observed exact durable synthetic effect evidence, never dispatch acceptance or signature alone. Real saved-plan custody, separate OS identities, encryption policy and network integration remain blocked. Checked WP5 subtasks apply only to the explicitly permitted synthetic counted-action/protocol slice.
- WP6: draft contract inventory with 20 planned cases and source-linked report/API/UI/CLI/agent/external-action compatibility and UX composition assessment. Several consumers drop undeclared provenance; no established report-byte hash is claimed. Relational-first recommendation, final wire/permission/hash and reviewed compositions remain unfrozen. External action was inspected read-only at commit `3b37ed72bfb2d201030bef873268f2170794b160`; no runtime copied into this repository.
- Verified all 20 stable context links and 42 earlier-only dependency references across the 19 downstream contexts; backlog remains unchanged. Real spikes are insufficient for a complete re-estimate, so IR-04 execution sizing/named downstream assignments remain open.
- Final integrated qualification: 41 tests passed. Relevant full CI, smoke/shard/security/format results are recorded in the manifest after execution. UI validation not applicable: no production rendered surface or browser behavior changed. Story remains in-progress; mandatory WP1/WP4/full WP5/WP6/WP7 gates cannot be marked complete.

### Review Findings

The BMad layered review found five deduplicated patch items; automatic fixes are authorized by the implementation request. All are covered by passing regressions. No decision-needed finding was waived and no public governance outcome is inferred.

- [x] [Review][Patch] Preserve the original authentication deadline through session rotation — identity prototype and rotation-boundary regression.
- [x] [Review][Patch] Deny unencodable UTF-8 credentials instead of raising — verifier/bootstrap/reset and HTTP lone-surrogate regression.
- [x] [Review][Patch] Fail closed when tests or measured password verification fail — measurement preserves prior evidence and derives totals from completed assertions; both failure triggers tested.
- [x] [Review][Patch] Deny malformed/non-object/oversized JSON and non-scalar scope IDs — bounded 4,096-byte HTTP parsing and request regressions.
- [x] [Review][Patch] Bind signed terminal receipts to the configured and authorized receiver — nondefault receiver and malformed-receipt regressions retain locks on denial.

### Final qualification and closure — 2026-10-10

Publication: [PR155](https://github.com/deploywhisper/deploywhisper/pull/155) targets `develop` from `feature/16-0-infra-automation-qualification`; completed work is pushed for review.

- Maintainer @pramodksahoo directly accepted RFC0001 on2026-10-09 and reaffirmed on2026-10-10. The current authenticated GitHub account matches CODEOWNERS. The specific early-window exception is recorded in the decision/course-correction artifacts; seven days did not elapse and no GitHub approval or second human review is fabricated. This updates AC2/WP1 governance only; technical gates were executed.
- Named final owners: root Codex integrates; native `real_linux_qualification` executed WP4/real WP5, `freeze_contracts` completed WP6, `final_readiness` completed WP7. Independent `real_qualification_review` reran actual Linux qualification; `contract_review` reran contracts and adversarial permutations. The maintainer is accountable for all later stories, with Codex-assisted execution and independent review as recorded in WP7.
- WP4/full WP5: actual OpenTofu1.13.1 and external2.3.5 under Linux ARM64, immutable image/catalog/source, UID10001 collector and UID10002 receiver. Egress/environment/capability/seccomp/mount, CPU/memory/pids/disk/output/time and descendant probes passed. AES256GCM custody verified the original saved binary plan through a sealed memfd after actual receiver restart; seven attacks, five crash boundaries, 30 tuple mutations and changed-plan rejection passed. Both stores are bounded8MiB anchored tmpfs; host power-loss durability remains downstream.
- WP6: eight closed schemas, frozen content hashes, qualified-profile digest, source/permission/route/error/state/hash contracts and reviewed compositions. Reportv2 remains unchanged through relational linkage and exact-byte snapshot hashing. 15 tests/185 subtests, 25valid/28invalid vectors, CLI6/raw React3/pinned action3 consumer cases passed. Reversed graph validation and strict enrollment-boolean defects were fixed tests-first; independent review additionally accepted240 workflow orders and denied725 negative cases. A real-profile wording correction narrows runtime verification to image/schema/catalog/source/control checks.
- WP7: all20contexts and72active requirements retained, earlier-only dependencies verified; bounded16.5/16.11/16.18 packets, named accountability and revised planning estimates recorded. Final readiness resolves IR01–04 for the foundation; only16.1/16.3 become ready-for-dev. No production/release readiness is inferred.
- Final commands/results: `bash scripts/ci-local.sh` exit0 after rerun of a daemon-interrupted attempt; `./.venv/bin/python -m unittest discover -q`614 tests, OK with2skips; `./.venv/bin/python -m pytest tests/test_api tests/test_cli tests/test_infra -v --tb=short`550passed/1skipped/1023subtests; separate `DW16_REAL_LINUX=1 ./.venv/bin/python -m pytest tests/test_infra/test_infra_automation_real_linux_qualification.py -q`3passed/6subtests, independently repeated; repo Ruff lint, repo-wide format322files, qualification Bandit and whitespace passed. Ordinary CI intentionally skips realDocker execution, covered by the explicit actual run. UI validation not applicable; no rendered surface changed.
- All seven packets are complete for this story's declared scope. Retained limitations include one-human governance coverage, host/daemon/receiver trust, ephemeral process/container restart scope, unqualified alternate tools/platforms, production integration/capacity/redaction/browser/release obligations. They are assigned to later owning stories rather than counted as delivered here. Evidence and exact hashes are indexed in the final manifest.

### File List

- `_bmad-output/implementation-artifacts/16-0-adopt-and-qualify-infra-automation-contract.md`
- `_bmad-output/implementation-artifacts/16-1-verified-human-principal-and-session-lifecycle.md`
- `_bmad-output/implementation-artifacts/16-3-closed-workflow-schema-and-validator.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/story-implementation-status-map.md`
- `_bmad-output/planning-artifacts/architecture.md`
- `_bmad-output/planning-artifacts/epics.md`
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-07-infra-automation-v1.5.0.md`
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-10-infra-automation-v1.5.0.md`
- `_bmad-output/planning-artifacts/infra-automation-v1.5.0-release-plan.md`
- `_bmad-output/planning-artifacts/prd-infra-automation.md`
- `_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-09-rfc-0001-maintainer-adoption.md`
- `_bmad-output/project-context.md`
- `docs/infra-automation/contract-v1.md`
- `docs/rfcs/0001-infra-automation-preflight-and-handoff.md`
- `docs/verification/infra-automation/16-0/README.md`
- `docs/verification/infra-automation/16-0/governance.json`
- `docs/verification/infra-automation/16-0/maintainer-decision-2026-10-09.md`
- `docs/verification/infra-automation/16-0/manifest.json`
- `docs/verification/infra-automation/16-0/public-review-text.md`
- `docs/verification/infra-automation/16-0/scope-corpus.json`
- `docs/verification/infra-automation/16-0/technical-review.md`
- `docs/verification/infra-automation/16-0/threat-model.md`
- `docs/verification/infra-automation/16-0/wp2-identity-results.json`
- `docs/verification/infra-automation/16-0/wp2-identity.md`
- `docs/verification/infra-automation/16-0/wp3-sqlite-results.json`
- `docs/verification/infra-automation/16-0/wp3-sqlite.md`
- `docs/verification/infra-automation/16-0/wp4-containment-results.json`
- `docs/verification/infra-automation/16-0/wp4-containment.md`
- `docs/verification/infra-automation/16-0/wp5-real-custody-results.json`
- `docs/verification/infra-automation/16-0/wp5-real-custody.md`
- `docs/verification/infra-automation/16-0/wp5-receiver-results.json`
- `docs/verification/infra-automation/16-0/wp5-receiver.md`
- `docs/verification/infra-automation/16-0/wp6-contract-assessment.md`
- `docs/verification/infra-automation/16-0/wp6-contract-results.json`
- `docs/verification/infra-automation/16-0/wp7-readiness.md`
- `schemas/infra-automation/cursor-v1.json`
- `schemas/infra-automation/enrollment-v1.json`
- `schemas/infra-automation/error-v1.json`
- `schemas/infra-automation/frozen-v1.json`
- `schemas/infra-automation/provenance-v1.json`
- `schemas/infra-automation/qualification-16-0-draft.json`
- `schemas/infra-automation/receiver-v1.json`
- `schemas/infra-automation/runner-v1.json`
- `schemas/infra-automation/state-v1.json`
- `schemas/infra-automation/workflow-v1.json`
- `tests/fixtures/infra_automation/qualification/16_0/contracts/action_consumer_probe.py`
- `tests/fixtures/infra_automation/qualification/16_0/contracts/cli_consumer_probe.py`
- `tests/fixtures/infra_automation/qualification/16_0/contracts/invalid.json`
- `tests/fixtures/infra_automation/qualification/16_0/contracts/permissions.json`
- `tests/fixtures/infra_automation/qualification/16_0/contracts/prototype.py`
- `tests/fixtures/infra_automation/qualification/16_0/contracts/react_consumer_probe.cjs`
- `tests/fixtures/infra_automation/qualification/16_0/contracts/routes.json`
- `tests/fixtures/infra_automation/qualification/16_0/contracts/valid.json`
- `tests/fixtures/infra_automation/qualification/16_0/identity/measure.py`
- `tests/fixtures/infra_automation/qualification/16_0/identity/prototype.py`
- `tests/fixtures/infra_automation/qualification/16_0/isolation/Dockerfile`
- `tests/fixtures/infra_automation/qualification/16_0/isolation/harness.py`
- `tests/fixtures/infra_automation/qualification/16_0/isolation/probe.py`
- `tests/fixtures/infra_automation/qualification/16_0/isolation/profile.json`
- `tests/fixtures/infra_automation/qualification/16_0/isolation/provider_probe.py`
- `tests/fixtures/infra_automation/qualification/16_0/isolation/source/main.tf`
- `tests/fixtures/infra_automation/qualification/16_0/isolation/tofurc`
- `tests/fixtures/infra_automation/qualification/16_0/real_custody/probe.py`
- `tests/fixtures/infra_automation/qualification/16_0/receiver/prototype.py`
- `tests/fixtures/infra_automation/qualification/16_0/sqlite/prototype.py`
- `tests/test_infra/test_infra_automation_contract_qualification.py`
- `tests/test_infra/test_infra_automation_identity_qualification.py`
- `tests/test_infra/test_infra_automation_real_linux_qualification.py`
- `tests/test_infra/test_infra_automation_receiver_qualification.py`
- `tests/test_infra/test_infra_automation_sqlite_qualification.py`

### Change Log

- 2026-10-10: Completed actual Linux/custody and contract qualification, recorded maintainer adoption, resolved final review findings, reran readiness/validation and closed the bounded story.
- 2026-10-09: Resumed explicit packet prerequisites; qualified WP2/WP3 and partial WP5 with 41 tests, resolved layered review findings and prepared WP6 drafts. WP4 and public/real-custody/freeze/readiness gates remain unresolved.
- 2026-10-09: Began WP1 preparation; recorded early merge without qualifying review, kept mandatory gates open and Story 16.0 in-progress. No production automation or executable spike delivered.

### Publication record — 2026-10-08

RFC 0001 was published for review by the separately authorized closeout. This records publication only: no acceptance criterion is marked complete, no maintainer approval is fabricated, and Status remains ready-for-dev for the declared governance/synthetic-qualification scope. The author is also the listed CODEOWNER; independent review is not yet established.
