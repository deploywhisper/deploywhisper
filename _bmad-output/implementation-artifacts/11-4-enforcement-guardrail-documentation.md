# Story 11.4: Enforcement Guardrail Documentation

Status: done

<!-- Generated from updated PRD/architecture/epics plus implementation-readiness-report-2026-05-01.md. -->

## Story

As a reviewer,
I want docs explaining optional enforcement guardrails,
So that teams understand when not to block automatically.

## Acceptance Criteria

1. Given users read policy adapter docs, When they configure enforcement, Then docs explain Evidence Law, benchmark thresholds, false reassurance, human review, and rollback responsibilities. And docs discourage autonomous approval or remediation.

### Requirement Traceability

- Primary PRD requirements: Epic 11 coverage: ADM-07, ADM-09, WRK-07, RSK-07, NFR-SEC-06.
- Supporting PRD / NFR / differentiation requirements: See `_bmad-output/planning-artifacts/prd.md`, `_bmad-output/planning-artifacts/architecture.md`, and `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md`.
- Coverage intent: Baseline + Delta.
- Story alignment note: This story was created from the updated Epic 11 plan after the 2026-05-01 readiness rerun. The readiness report verified 187/187 PRD functional requirement IDs in the epics artifact, 38 NFR IDs present, and no critical or major readiness defects.

## Tasks / Subtasks

- [x] Implement and verify acceptance criterion 1. (AC: 1)
- [x] Reuse existing services, repositories, schemas, and UI/CLI/API helpers before adding new abstractions. (AC: all)
- [x] Add or update deterministic regression coverage for the changed behavior. (AC: all)
- [x] Update relevant docs or examples if the story changes user-visible, operator, API, CLI, integration, or contribution behavior. (AC: all)
- [x] Run required validation and record commands/results in the Dev Agent Record. (AC: all)

### Review Findings

- [x] [Review][Patch] [HIGH] Reconcile the README's unconditional successful-analysis exit `0` promise with configured blocking exits, and condition enforcement claims on an installed Action release that actually supports the decision endpoint and outputs. [README.md:769]
- [x] [Review][Patch] [HIGH] Explain that the built-in Evidence Law guarantee covers high and critical findings only; blocking thresholds below high require a separate deterministic-evidence gate or must remain non-blocking. [docs/enforcement-guardrails.md:62]
- [x] [Review][Patch] [HIGH] Require an advisory override or full guardrail review when onboarding a new integration under a blocking project default, not only when changing the project default or deleting an existing override. [docs/enforcement-guardrails.md:34]
- [x] [Review][Patch] [HIGH] Require blocking integrations to be wired as required checks/jobs without `continue-on-error`; otherwise nonzero Action exits or failing check conclusions do not actually prevent merge or deployment. [docs/enforcement-guardrails.md:19]
- [x] [Review][Patch] [MEDIUM] Make the benchmark decision record normative and require rebenchmarking after behavior-affecting parser, evidence, scoring, policy, corpus, or context changes. [docs/enforcement-guardrails.md:95]
- [x] [Review][Patch] [MEDIUM] Define invalid-decision validation conditions plus the operational recovery path: authorized mode change or exception, rerun, and retained audit evidence. [docs/enforcement-guardrails.md:45]
- [x] [Review][Patch] [MEDIUM] Parse and assert the mode table's exact Action/App effects so a generic outage-section phrase cannot satisfy blocking-mode regression coverage. [tests/test_docs/test_enforcement_guardrails.py:43]
- [x] [Review][Patch] [LOW] Validate the new guide's outbound workflow-contract, benchmark, and outcome links in addition to its inbound entry-point links. [tests/test_docs/test_enforcement_guardrails.py:63]
- [x] [Review][Patch] [HIGH] Document that a project-level enforcement mode is inherited by every integration without an override and that deleting an override can expose a blocking project default; the current guide incorrectly implies each integration is always configured directly. [docs/enforcement-guardrails.md:3]
- [x] [Review][Patch] [HIGH] Define fail-safe behavior for unavailable, timed-out, stale, or malformed enforcement decisions so current and future consumers cannot silently convert an operational failure into a passing check. [docs/enforcement-guardrails.md:21]
- [x] [Review][Patch] [MEDIUM] Make benchmark readiness verifiable using the metrics the current runner actually emits, document the calculation and sampling record needed for organization-owned thresholds, and require zero Evidence Law violations rather than treating violations as a configurable tolerance. [docs/enforcement-guardrails.md:53]
- [x] [Review][Patch] [MEDIUM] Clarify that the mode table's per-mode examples do not replace the complete blocking prerequisites; the soft-block row currently appears to authorize blocking once only an exception path exists. [docs/enforcement-guardrails.md:16]
- [x] [Review][Patch] [MEDIUM] Describe observable soft-block and hard-block workflow behavior instead of defining each mode circularly in terms of itself. [docs/enforcement-guardrails.md:18]
- [x] [Review][Patch] [LOW] Remove the contradictory instruction to follow the retired Python UI composition style; project context establishes the React SPA as the only current UI framework. [_bmad-output/implementation-artifacts/11-4-enforcement-guardrail-documentation.md:53]
- [x] [Review][Patch] [HIGH] Reconcile the Action exit contract: retrieval or validation failures exit nonzero too, so README and Action docs must not say nonzero occurs only when validated `should-block` is true. [README.md:769]
- [x] [Review][Patch] [HIGH] Correct the GitHub App onboarding guidance: integrations without overrides inherit a blocking project default and therefore do not necessarily remain advisory until individually opted in. [docs/github-app.md:73]
- [x] [Review][Patch] [HIGH] Make the mode table distinguish configured ceilings from effective statuses and cover non-blocking effective outcomes; a configured `warn` mode with an effective `advisory`/`GO` result is `success`, not always `neutral`. [docs/enforcement-guardrails.md:15]
- [x] [Review][Patch] [HIGH] Define a functional exception flow: identify what control changes or bypasses the required result, when a rerun is needed, and how the replacement result unblocks delivery without implying that an unchanged rerun can change the decision. [docs/enforcement-guardrails.md:24]
- [x] [Review][Patch] [HIGH] Prefer report/integration-scoped break glass and require concurrency controls plus re-evaluation of open heads so a temporary project mode change cannot let unrelated deployments pass. [docs/enforcement-guardrails.md:86]
- [x] [Review][Patch] [HIGH] Keep thresholds below `high` non-blocking with the current shared decision contract; document a future separate deterministic-evidence gate rather than implying an organization policy can alter `should_block` today. [docs/enforcement-guardrails.md:113]
- [x] [Review][Patch] [MEDIUM] Turn mandatory human review into an observable workflow prerequisite by requiring branch-review rules or protected-environment approval for blocking integrations. [docs/enforcement-guardrails.md:168]
- [x] [Review][Patch] [MEDIUM] Define decision freshness using concrete report/settings identity, integration scope, and re-evaluation triggers; do not rely only on a general prohibition against reusing prior decisions or invent revision tokens the API does not expose. [docs/enforcement-guardrails.md:69]
- [x] [Review][Patch] [MEDIUM] Require blocking Action workflows to pin an immutable reviewed revision and run a synthetic fail-closed capability check instead of relying on a one-time inspection of the moving `@v1` tag. [README.md:785]
- [x] [Review][Patch] [MEDIUM] Require the protected check to be bound to the expected GitHub App/source so an unrelated workflow publishing the same check name cannot satisfy protection. [docs/enforcement-guardrails.md:39]
- [x] [Review][Patch] [MEDIUM] Define blocking behavior when no policy decision exists because all changed artifacts are sensitive, unsupported, or otherwise excluded; a neutral result must not silently satisfy enforcement. [docs/enforcement-guardrails.md:69]
- [x] [Review][Patch] [MEDIUM] Require a fresh protected result after an exception expires so a previously passing replacement check cannot remain valid indefinitely. [docs/enforcement-guardrails.md:86]
- [x] [Review][Patch] [MEDIUM] Require organization-owned minimum positive/negative sample sizes by covered change class and a stated statistical confidence method before benchmark readiness can be approved. [docs/enforcement-guardrails.md:126]
- [x] [Review][Patch] [MEDIUM] Define benchmark ground-truth labels, outcome mapping, exclusions, and zero-denominator handling so precision, recall, false-reassurance, and false-positive calculations are reproducible. [docs/enforcement-guardrails.md:126]
- [x] [Review][Patch] [MEDIUM] Tie benchmark approval to an immutable application/action revision and dependency identity, and verify the deployed artifact matches the evaluated build. [docs/enforcement-guardrails.md:134]
- [x] [Review][Patch] [MEDIUM] Expand exception audit evidence to include invocation timestamp, integration/project scope, the full applied-settings snapshot, a canonical decision digest, original decision payload, and the applicable bypass event or replacement run. [docs/enforcement-guardrails.md:86]
- [x] [Review][Patch] [MEDIUM] Strengthen documentation regressions to validate complete structured requirements—including the mode table's prerequisites—and remove the test assertion that currently locks the contradictory Action exit wording. [tests/test_docs/test_enforcement_guardrails.py:23]
- [x] [Review][Patch] [HIGH] Stop describing fail-closed Action enforcement as currently released: published `analyze-action@v1` resolves to `f2e36ce` without enforcement outputs, while enforcement remains in open Action PR #7; capability-gate all behavior claims. [docs/enforcement-guardrails.md:116]
- [x] [Review][Patch] [HIGH] Require manifest-level intake coverage for partially analyzed change sets as well as completely missing decisions so one supported artifact cannot hide sensitive, unsupported, or rejected siblings. [docs/enforcement-guardrails.md:106]
- [x] [Review][Patch] [HIGH] Bind every enforcement decision to the actual protected target, PR head where applicable, workflow invocation, and submitted artifact manifest; the current report-ID/scope checks permit replay of an unrelated report. [docs/enforcement-guardrails.md:95]
- [x] [Review][Patch] [HIGH] State and mitigate the v1 settings race: without a settings revision or atomic evaluate-and-publish contract, immediate retrieval cannot guarantee settings remain unchanged through check publication. [docs/enforcement-guardrails.md:95]
- [x] [Review][Patch] [HIGH] Require authenticated transport, trusted server identity, least-privilege credentials, and a fixed enforcement endpoint so a structurally valid response from a substituted source cannot authorize delivery. [docs/enforcement-guardrails.md:88]
- [x] [Review][Patch] [HIGH] Define authorization, separation-of-duties, and durable audit controls for policy-setting changes and break-glass approval; settings writers must not self-approve bypasses. [docs/enforcement-guardrails.md:64]
- [x] [Review][Patch] [HIGH] Make temporary override expiry operationally safe with an external watchdog, compare-before-restore behavior, and a fail-closed freeze when restoration cannot be verified; the API has no enforced expiry field. [docs/enforcement-guardrails.md:124]
- [x] [Review][Patch] [MEDIUM] Replace undefined “canonical serialization” with a reproducible digest input such as the exact authenticated HTTP response bytes, and record the digest algorithm. [docs/enforcement-guardrails.md:100]
- [x] [Review][Patch] [MEDIUM] Define retention duration, access control, encryption, and redaction for stored decision payloads and settings snapshots so audit evidence does not create a sensitive-data leak. [docs/enforcement-guardrails.md:134]
- [x] [Review][Patch] [HIGH] Make freshness and artifact-identity requirements integration-neutral: in-process GitHub App and future adapters do not retrieve the HTTP endpoint or have an Action SHA; require the actual consumer revision and decision path used. [docs/enforcement-guardrails.md:95]
- [x] [Review][Patch] [MEDIUM] Require an organization-owned observation window and incident-attribution horizon before production outcomes are labeled for false-reassurance or false-positive metrics. [docs/enforcement-guardrails.md:174]
- [x] [Review][Patch] [MEDIUM] Rebenchmark and reapprove after consumer, Action/App revision, dependency, endpoint-schema, workflow, or protection-rule changes—not only parser/scoring/context changes. [docs/enforcement-guardrails.md:205]
- [x] [Review][Patch] [MEDIUM] Make the rollout checklist a complete readiness gate by including source-bound required checks, no `continue-on-error`, pass/block/error smoke cases, and complete/partial intake coverage. [docs/enforcement-guardrails.md:276]
- [x] [Review][Patch] [MEDIUM] Correct inherited-setting onboarding and troubleshooting across README and the self-hosted runbook: inspect setting provenance and create a narrow advisory integration override before installing or upgrading under a blocking project default. [README.md:770]
- [x] [Review][Patch] [HIGH] Require an immutable protected workflow, review ownership for workflow changes, and an explicit failure when the enforcement step is skipped so pull-request changes cannot manufacture a trusted passing check. [docs/enforcement-guardrails.md:47]
- [x] [Review][Patch] [MEDIUM] Bind human approval to the protected commit SHA and dismiss stale approvals after changes so later commits cannot inherit an earlier reviewer decision. [docs/enforcement-guardrails.md:251]
- [x] [Review][Patch] [MEDIUM] Make documentation tests section-aware and reject duplicate mode rows; broad substring matching and global row scanning can pass contradictory or misplaced guidance. [tests/test_docs/test_enforcement_guardrails.py:55]
- [x] [Review][Patch] [LOW] Mark Epic 11 done now that all four stories are done, matching the sprint-status lifecycle definition. [_bmad-output/implementation-artifacts/sprint-status.yaml:146]
- [x] [Review][Patch] [HIGH] Do not recommend an integration-wide advisory override for one new repository or environment when that integration already protects other scopes; require a separate project/integration identity or complete the new-scope review before attachment. [docs/enforcement-guardrails.md:94]
- [x] [Review][Patch] [HIGH] Base required-check troubleshooting on the resolved configured enforcement mode, not one report's effective status; a safe report under a blocking ceiling must not cause protection removal. [docs/github-app-self-hosted-setup.md:201]
- [x] [Review][Patch] [HIGH] Replace pre-analysis “effective mode” instructions with resolved configured mode and setting source; no effective status exists until a report is evaluated. [README.md:770]
- [x] [Review][Patch] [HIGH] Remove the Action guide's unconditional “defaults to advisory” claim because an integration without an override may inherit a blocking project default. [docs/github-action.md:65]
- [x] [Review][Patch] [HIGH] Document that `should-block` is a string Action output and require `fromJSON(...)` or exact comparison with `'true'` before downstream branching. [docs/github-action.md:104]
- [x] [Review][Patch] [HIGH] Treat checkout ref, artifact selection/`changed-files`, project/workspace scope, and working directory as protected enforcement inputs; untrusted overrides can omit risky files. [docs/enforcement-guardrails.md:64]
- [x] [Review][Patch] [HIGH] Expand the guide's activation entry condition to cover onboarding under inherited blocking, override deletion, and scope expansion—not only explicit advisory-to-blocking transitions. [docs/enforcement-guardrails.md:10]
- [x] [Review][Patch] [HIGH] Remove the paper-only new-integration bypass: an existing project review cannot substitute for benchmarking and approving the new consumer revision and scope. [docs/enforcement-guardrails.md:88]
- [x] [Review][Patch] [HIGH] Do not call compare-then-restore safe without atomic CAS; require an enforced exclusive settings lock for temporary overrides or forbid that path and retain the protection-layer bypass. [docs/enforcement-guardrails.md:180]
- [x] [Review][Patch] [MEDIUM] Clarify that a SHA-256 payload digest proves stored-byte integrity only; record authenticated principal, trusted timestamp, and append-only audit receipt to establish provenance and freshness. [docs/enforcement-guardrails.md:190]
- [x] [Review][Patch] [MEDIUM] Make manifest completeness implementable by naming the persisted report `submission_manifest` fields and defining comparison against the trusted changed-file set, including every non-accepted item. [docs/enforcement-guardrails.md:136]
- [x] [Review][Patch] [MEDIUM] Map break glass to concrete protection-layer mechanisms and verification evidence, such as a scoped ruleset bypass or protected-environment approval plus provider audit event. [docs/enforcement-guardrails.md:172]
- [x] [Review][Patch] [MEDIUM] Define false reassurance as a passed deployment later linked to an attributable adverse outcome, and distinguish it from benchmark false negatives. [docs/enforcement-guardrails.md:246]
- [x] [Review][Patch] [MEDIUM] Record immutable snapshots or digests of mutable workflow/protection configuration so reapproval is auditable, not merely tied to an undefined “identity.” [docs/enforcement-guardrails.md:268]
- [x] [Review][Patch] [MEDIUM] Distinguish baseline human approval required for every blocking workflow from elevated specialist review triggered by high-risk conditions. [docs/enforcement-guardrails.md:309]
- [x] [Review][Patch] [HIGH] Document the GitHub App's `neutral` project-scope failure path and require a separate fail-closed scope control or non-blocking App until that runtime path fails. [docs/enforcement-guardrails.md:145]
- [x] [Review][Patch] [MEDIUM] Strengthen onboarding and Epic lifecycle regressions to verify ordering before repository access and all four Story 11 statuses, not only phrase presence and the epic marker. [tests/test_docs/test_enforcement_guardrails.py:269]
- [x] [Review][Patch] [LOW] Reject duplicate normative section headings so a later contradictory section cannot escape section-scoped assertions. [tests/test_docs/test_enforcement_guardrails.py:297]
- [x] [Review][Patch] [MEDIUM] Require fresh approval after application, corpus, configuration, feature-flag, or context changes even when metrics still pass—not only consumer/wiring identity changes. [docs/enforcement-guardrails.md:268]
- [x] [Review][Patch] [HIGH] Do not call moving `@v1` safe for advisory use; pin every Action revision or retain a persistent advisory override because a future tag move can activate inherited blocking. [docs/github-action.md:81]
- [x] [Review][Patch] [HIGH] Define deleted and renamed artifact handling; when current contracts cannot submit/hash tombstones or prior paths, blocking requires a separate diff-coverage control or must remain disabled. [docs/enforcement-guardrails.md:166]
- [x] [Review][Patch] [MEDIUM] Explain that `accepted_artifact_count` includes parser-failed items while `analyzed_artifact_count` counts only successfully parsed items, preventing consumers from treating “accepted” as analyzed. [docs/enforcement-guardrails.md:166]
- [x] [Review][Patch] [HIGH] Remove the circular temporary-settings exception path; restoring blocking before rerun can block the excepted commit again, and v1 lacks atomic CAS, so use a protection-layer bypass instead. [docs/enforcement-guardrails.md:215]
- [x] [Review][Patch] [HIGH] Require automatic expiry/revocation of repository-ruleset bypass access and verify removal; recording an expiry alone does not time-bound the capability. [docs/enforcement-guardrails.md:206]
- [x] [Review][Patch] [HIGH] Add the known GitHub App project-scope `neutral` path and its separate fail-closed control to the normative rollout checklist. [docs/enforcement-guardrails.md:405]
- [x] [Review][Patch] [MEDIUM] Record the resolved setting source, `warn_at`, `soft_block_at`, `hard_block_at`, reporting default, and configured enforcement mode in the rollout approval. [docs/enforcement-guardrails.md:405]
- [x] [Review][Patch] [MEDIUM] Define bounded decision timeouts, capped retries/backoff, and idempotent submission/check keys so failures terminate closed without duplicate reports or hanging checks. [docs/enforcement-guardrails.md:137]
- [x] [Review][Patch] [MEDIUM] Cover event/path filters, job-level conditions, dependency skips, and cancellations; required enforcement must emit a terminal failure instead of remaining missing or pending. [docs/enforcement-guardrails.md:69]
- [x] [Review][Patch] [MEDIUM] Limit context-triggered benchmark reapproval to material changes to benchmark inputs or consumer behavior; ordinary per-report topology/ownership updates require a fresh report, not continuous policy reapproval. [docs/enforcement-guardrails.md:328]
- [x] [Review][Patch] [MEDIUM] Define outcome attribution method, severity boundary, adjudicator, evidence, and dispute/relabeling process for false-reassurance metrics. [docs/enforcement-guardrails.md:296]
- [x] [Review][Patch] [MEDIUM] Define one serialize-once audit boundary for in-process decisions and record serializer/version; “exact decision bytes” is otherwise undefined. [docs/enforcement-guardrails.md:226]
- [x] [Review][Patch] [MEDIUM] Stop hard-coding the moving Action tag observation into regression assertions and remove broad negative substring bans that resist future accurate documentation; retain capability-gated contract checks. [tests/test_docs/test_enforcement_guardrails.py:240]
- [x] [Review][Patch] [LOW] Anchor the Epic 11 done assertion to the exact YAML line, matching the story-status checks. [tests/test_docs/test_enforcement_guardrails.py:349]
- [x] [Review][Patch] [LOW] Link the pre-install GitHub App onboarding step directly to the enforcement guardrail guide. [docs/github-app-self-hosted-setup.md:134]
- [x] [Review][Patch] [HIGH] Bind PR analysis to both current head and base SHAs and rerun when either changes; a stable head with an advanced base can invalidate the analyzed merge result. [docs/enforcement-guardrails.md:131]
- [x] [Review][Patch] [HIGH] Bind submitted artifact bytes to a clean checkout of the protected target using content hashes; path-only manifest equality can approve mutated or substituted bytes. [docs/enforcement-guardrails.md:165]
- [x] [Review][Patch] [HIGH] Freeze delivery before changing enforcement settings, then invalidate/rerun existing results; committing settings first leaves a stale-pass window. [docs/enforcement-guardrails.md:114]
- [x] [Review][Patch] [MEDIUM] Define material report-context invalidation after publication and require a fresh report when topology, ownership, incidents, or other decision inputs change materially. [docs/enforcement-guardrails.md:146]
- [x] [Review][Patch] [HIGH] Resolve non-PR refs to immutable commit/artifact digests, bind the decision to that digest, and deploy the same digest rather than a later-moving ref. [docs/enforcement-guardrails.md:137]
- [x] [Review][Patch] [HIGH] Warn that the current GitHub App does not handle `merge_group`; do not require its check in merge queues without another consumer that analyzes generated merge commits. [docs/github-app.md:62]
- [x] [Review][Patch] [LOW] Make mode-table parsing reject malformed/extra-cell status rows and contradictory rows without backticks, not silently ignore them. [tests/test_docs/test_enforcement_guardrails.py:379]
- [x] [Review][Patch] [HIGH] Disclose that current enforcement routes rely on a trusted proxy/middleware to strip and inject identity headers and otherwise default missing identity to admin; direct exposure must remain non-blocking. [docs/enforcement-guardrails.md:108]
- [x] [Review][Patch] [MEDIUM] Reconcile inherited project blocking across policy-adapter, CI, and Action entry points; “explicit integration opt-in” and unconditional advisory-default claims are false without an override. [docs/workflow-adapter-output-contract.md:127]
- [x] [Review][Patch] [HIGH] Remove protected-environment approval as a claimed bypass for a failed required check; it only gates pending environment jobs and cannot convert an upstream failure into success. [docs/enforcement-guardrails.md:206]
- [x] [Review][Patch] [HIGH] Add `id: deploywhisper` to Action examples so documented `steps.deploywhisper.outputs.should-block` expressions resolve. [docs/github-action.md:35]
- [x] [Review][Patch] [HIGH] Remove the unsupported merge-queue fallback: neither the released App nor Action has a verified generated-merge path, so prohibit requiring either check for merge queues until such a pinned path exists. [docs/github-app.md:64]
- [x] [Review][Patch] [HIGH] Reconcile inherited blocking in GitHub App and README guidance; requiring a check is a separate operator action, but the configured blocking mode may be inherited without integration-specific opt-in. [docs/github-app.md:74]
- [x] [Review][Patch] [HIGH] Remove persistent advisory override as permission to run a moving Action tag; it limits policy mode but cannot mitigate mutable-code token exfiltration or falsified results. [docs/enforcement-guardrails.md:50]
- [x] [Review][Patch] [HIGH] Pin `actions/checkout` to a reviewed full commit SHA in every supplied and scaffolded workflow, not only the DeployWhisper Action. [integrations/github/init_service.py:298]
- [x] [Review][Patch] [HIGH] Add the trusted identity/proxy boundary to the normative rollout checklist. [docs/enforcement-guardrails.md:462]
- [x] [Review][Patch] [HIGH] Add the required durable external idempotency coordinator—or non-blocking fallback—to the rollout checklist. [docs/enforcement-guardrails.md:462]
- [x] [Review][Patch] [HIGH] Add settings-change serialization, pre-change delivery freeze, invalidation, and rerun requirements to the rollout checklist. [docs/enforcement-guardrails.md:462]
- [x] [Review][Patch] [HIGH] Add deletion/rename deterministic diff coverage to the rollout checklist; manifest-only coverage cannot validate tombstones. [docs/enforcement-guardrails.md:475]
- [x] [Review][Patch] [MEDIUM] Separate top-level trigger coverage from job-level `if: always()` handling and require an always-triggered terminal workflow for required contexts. [docs/enforcement-guardrails.md:76]
- [x] [Review][Patch] [MEDIUM] Make App onboarding account for every scope sharing a project/integration key, and grant staged non-required access for smoke tests before enabling protection instead of requiring pre-access validation. [docs/github-app-self-hosted-setup.md:134]
- [x] [Review][Patch] [MEDIUM] Publish full dereferenced Action/checkout commit provenance, validate pinned constants as 40-character SHAs, and give runnable examples plus an explicit revision-resolution/update procedure. [integrations/github/init_service.py:17]
- [x] [Review][Patch] [LOW] Validate outbound Markdown fragment targets, not only their files, so the trusted-identity `#guardrails` link cannot silently break. [tests/test_docs/test_enforcement_guardrails.py:225]
- [x] [Review][Patch] [LOW] Scope the historical exit-contradiction absence check to the Action section instead of removing regression protection entirely. [tests/test_docs/test_enforcement_guardrails.py:242]
- [x] [Review][Patch] [LOW] Replace hard-coded Epic 11 completion state with a consistency invariant: only require every story done when the epic itself is done. [tests/test_docs/test_enforcement_guardrails.py:372]
- [x] [Review][Patch] [MEDIUM] Distinguish benchmark, reviewer-feedback, and deployment-backed false reassurance and keep their denominators separate. [docs/enforcement-guardrails.md:346]
- [x] [Review][Patch] [LOW] Correct the story record's documentation-only/no-runtime-change claims now that the GitHub scaffold behavior changed. [_bmad-output/implementation-artifacts/11-4-enforcement-guardrail-documentation.md:197]
- [x] [Review][Patch] [HIGH] Remove the generated README's unconditional advisory-only claim; scaffolded consumers may inherit blocking project settings. [integrations/github/init_service.py:319]
- [x] [Review][Patch] [LOW] Add a direct enforcement-guardrails URL to the Action-first generated README guidance. [integrations/github/init_service.py:327]
- [x] [Review][Patch] [MEDIUM] Make mode-table parsing validate the separator and every contiguous row shape/status without allowing an extra or unbackticked row to escape. [tests/test_docs/test_enforcement_guardrails.py:416]
- [x] [Review][Patch] [MEDIUM] Require a maximum break-glass expiry as well as automatic revocation, with fail-closed handling when timely revocation cannot be verified; an event-only revocation trigger can remain active indefinitely. [docs/enforcement-guardrails.md:500]
- [x] [Review][Patch] [MEDIUM] Document checkout's exact tag-to-commit provenance and its independent diff-review/update procedure; the README currently promises a two-dependency pin procedure while the Action guide describes only the DeployWhisper Action update path. [docs/github-action.md:98]
- [x] [Review][Patch] [LOW] Correct the checked merge-queue finding to record the implemented safe prohibition, because no released App or Action path can provide the originally requested verified `merge_group` example. [_bmad-output/implementation-artifacts/11-4-enforcement-guardrail-documentation.md:128]
- [x] [Review][Patch] [LOW] Make fragment validation ignore fenced-code pseudo-headings and handle duplicate GitHub heading slugs so a nonexistent target cannot satisfy the outbound-link regression. [tests/test_docs/test_enforcement_guardrails.py:457]
- [x] [Review][Patch] [LOW] Derive the Epic 11 story set from sprint status when enforcing the conditional lifecycle invariant, so a future numbered story cannot remain unfinished while the epic is marked done. [tests/test_docs/test_enforcement_guardrails.py:415]
- [x] [Review][Patch] [MEDIUM] Bind generated README capability wording and all documented workflow pins to the scaffold constants, including the exact advisory-only Action SHA and a required README refresh when consumers change that pin. [integrations/github/init_service.py:327]

## Dev Notes

### Epic Context

- Epic: 11. Optional Enforcement Adapters
- Epic goal: Expose optional enforcement interpretation without changing the advisory core.
- Epic coverage: ADM-07, ADM-09, WRK-07, RSK-07, NFR-SEC-06

### Architecture and Product Guardrails

- Preserve DeployWhisper's local-first raw artifact boundary: raw IaC, scanner artifacts, incident exports, and sensitive context stay in the user's infrastructure by default.
- Preserve the advisory-first core. Optional adapters may interpret report outputs, but canonical report semantics remain advisory unless explicit story scope says otherwise.
- Reuse the shared analysis core and service layer before adapting UI, API, CLI, GitHub, or future workflow surfaces.
- Keep Evidence Law behavior intact: no high or critical finding without deterministic evidence.
- Keep project/workspace scope explicit for reports, incidents, topology, outcomes, feedback, scanner imports, and connector-related data.
- Do not introduce new dependencies unless the active story explicitly requires and justifies them.

### Source Tree Guidance

- API routes belong under `api/routes/` and should use existing `ApiRoute` / `ApiError` envelope patterns.
- Shared orchestration belongs in `services/`; parsers normalize input, analysis modules score/derive risk, and surfaces adapt outputs.
- UI work belongs under `frontend/src/screens/` and `frontend/src/components/`, following the current React SPA theme and component conventions.
- CLI behavior belongs under `cli/` and must call the same service-layer paths as UI/API flows.
- Persistence work belongs under `models/` with Alembic migrations when schema changes are required.
- Documentation required by a story should be updated in the same workstream.

### Testing Requirements

- Use standard-library `unittest` in the existing `tests/test_*` layout.
- Add focused regression tests for the layer changed by the story before broad refactors.
- For Python changes, run `./.venv/bin/ruff check .`, `./.venv/bin/ruff format --check .`, and `./.venv/bin/python -m unittest discover -q` before closing implementation.
- Use `bash scripts/ci-local.sh` for broader or cross-layer changes.

### Project Structure Notes

- Follow the current repository shape documented in `_bmad-output/project-context.md` and `AGENTS.md`.
- If implementation reveals a conflict between this story and the current code baseline, keep the smallest compatible change and update the story notes rather than silently drifting from the PRD.

### References

- `_bmad-output/planning-artifacts/epics.md` - source Epic 11 / Story 11.4 definition.
- `_bmad-output/planning-artifacts/prd.md` - functional and non-functional requirements.
- `_bmad-output/planning-artifacts/architecture.md` - target architecture, boundaries, and guardrails.
- `_bmad-output/planning-artifacts/ux-design-specification.md` - UX expectations for user-facing stories.
- `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-01.md` - readiness verdict and residual story-format concern.
- `_bmad-output/project-context.md` - repository-specific implementation rules.

## Dev Agent Record

### Agent Model Used

OpenAI Codex (GPT-5)

### Implementation Plan

- Lock the required guardrail topics and document discoverability with a failing documentation-contract regression.
- Publish one canonical enforcement guide rather than duplicating safety policy across integration-specific documents.
- Link every current enforcement entry point to the guide and preserve the existing advisory-first runtime contract.
- Run focused documentation coverage, repository smoke tests, quality/security gates, and full local CI before moving the story to review.

### Debug Log References

- RED: `./.venv/bin/python -m pytest tests/test_docs/test_enforcement_guardrails.py -q --tb=short` - expected failure because the guide and entry-point links did not exist (`6 failed, 1 passed`).
- GREEN: the same focused command passed after the guide and links were added (`2 passed, 20 subtests passed`); the expanded self-hosted GitHub App entry-point regression was also confirmed red before its link was added.
- Focused final documentation contracts: `./.venv/bin/python -m pytest tests/test_docs/test_enforcement_guardrails.py tests/test_docs/test_github_action_integration_contract.py tests/test_docs/test_workflow_adapter_output_contract.py -q --tb=short` - `12 passed, 79 subtests passed`.
- Documentation suite: `./.venv/bin/python -m pytest tests/test_docs -q --tb=short` - `25 passed, 138 subtests passed`.
- Required smoke: `./.venv/bin/python -m unittest discover -q` - `416 tests` passed, `1 skipped`.
- Quality gates: `./.venv/bin/ruff check .`, repo-wide `./.venv/bin/ruff format --check .`, and `git diff --check` passed; Ruff reported all 273 files formatted.
- Full local CI: `bash scripts/ci-local.sh` passed Ruff, dependency integrity, Bandit with zero high-severity findings, compileall, skill and prompt-injection gates, and every backend/docs test directory; final services directory reported `930 tests` passing.
- UI validation not applicable: this story changes documentation, documentation contracts, and GitHub workflow scaffolding only; no React route, component, rendered surface, interaction, keyboard behavior, or accessibility semantics changed.
- Review RED: the strengthened enforcement-contract regression reproduced all missing inheritance, failure-policy, benchmark-verifiability, Evidence Law, and concrete mode-effect guidance (`11 failed, 2 passed, 25 subtests passed`).
- Review GREEN: `./.venv/bin/python -m pytest tests/test_docs/test_enforcement_guardrails.py -q --tb=short` - `2 passed, 36 subtests passed`.
- Review documentation and metadata suite: `./.venv/bin/python -m pytest tests/test_docs tests/test_infra/test_ai_safety_documentation.py tests/test_infra/test_requirements_traceability_matrix.py -q --tb=short` - `39 passed, 226 subtests passed`.
- Review required smoke: `./.venv/bin/python -m unittest discover -q` - `416 tests` passed, `1 skipped`.
- Review full local CI: `bash scripts/ci-local.sh` passed Ruff, dependency integrity, Bandit with zero high-severity findings, compileall, all skill and prompt-injection gates, and every backend/docs test directory; final services directory reported `930 tests` passing.
- Review quality gates: `./.venv/bin/ruff check .`, repo-wide `./.venv/bin/ruff format --check .`, `git diff --check`, and `git diff --cached --check` passed; Ruff reported all 273 files formatted.
- Final review RED: expanded contract coverage reproduced the README/action-release contradiction, missing low-threshold Evidence Law warning, incomplete onboarding and required-check controls, non-normative benchmark/reapproval language, undefined recovery audit path, weak mode-table assertions, and unvalidated outbound links (`12 failed, 3 passed, 39 subtests passed`).
- Final review GREEN: `./.venv/bin/python -m pytest tests/test_docs/test_enforcement_guardrails.py -q --tb=short` - `6 passed, 46 subtests passed`.
- Final review documentation and metadata suite: `./.venv/bin/python -m pytest tests/test_docs tests/test_infra/test_ai_safety_documentation.py tests/test_infra/test_requirements_traceability_matrix.py -q --tb=short` - `43 passed, 236 subtests passed`.
- Final review required smoke: `./.venv/bin/python -m unittest discover -q` - `420 tests` passed, `1 skipped`.
- Final review full local CI: `bash scripts/ci-local.sh` passed Ruff, dependency integrity, Bandit with zero high-severity findings, compileall, all skill and prompt-injection gates, and every backend/docs test directory; final services directory reported `930 tests` passing.
- Final review quality gates: Ruff initially identified the expanded test for formatting; `./.venv/bin/ruff format tests/test_docs/test_enforcement_guardrails.py` corrected it, after which `./.venv/bin/ruff check .`, repo-wide `./.venv/bin/ruff format --check .`, and `git diff --check` passed with all 273 files formatted.
- Review rerun RED: strengthened documentation contracts reproduced the remaining mode-matrix, inherited-setting, failure-path, exception-audit, benchmark-reproducibility, Action-revision, and human-approval gaps (`22 failed, 4 passed, 43 subtests passed`).
- Review rerun GREEN and metadata suite: `./.venv/bin/python -m pytest tests/test_docs/test_enforcement_guardrails.py tests/test_docs tests/test_infra/test_ai_safety_documentation.py tests/test_infra/test_requirements_traceability_matrix.py -q --tb=short` - `44 passed, 256 subtests passed`; the focused guardrail file reported `7 passed, 66 subtests passed`.
- Review rerun required smoke: `./.venv/bin/python -m unittest discover -q` - `421 tests` passed, `1 skipped`.
- Review rerun full local CI: `bash scripts/ci-local.sh` passed Ruff, dependency integrity, Bandit with zero high-severity findings, compileall, skill and prompt-injection gates, and every backend/docs test directory; final services directory reported `930 tests` passing.
- Review rerun quality gates: `./.venv/bin/ruff check .`, repo-wide `./.venv/bin/ruff format --check .`, and `git diff --check` passed; Ruff reported all 273 files formatted.
- Review rerun independent verification: a read-only checklist pass confirmed all 17 findings and four follow-up residuals were resolved with no remaining concrete defects.
- Subsequent review RED: section-scoped contracts reproduced the published-Action, partial-intake, target-binding, settings-race, transport/authz, expiry, audit-retention, integration-neutrality, outcome-horizon, reapproval, rollout-checklist, onboarding, workflow-integrity, stale-approval, and Epic 11 lifecycle gaps (`33 failed, 6 passed, 67 subtests passed`).
- Subsequent review GREEN: `./.venv/bin/python -m pytest tests/test_docs/test_enforcement_guardrails.py -q --tb=short` - `10 passed, 62 subtests passed`.
- Subsequent review documentation and metadata suite: `./.venv/bin/python -m pytest tests/test_docs tests/test_infra/test_ai_safety_documentation.py tests/test_infra/test_requirements_traceability_matrix.py -q --tb=short` - `47 passed, 252 subtests passed`.
- Subsequent review required smoke: `./.venv/bin/python -m unittest discover -q` - `424 tests` passed, `1 skipped`.
- Subsequent review full local CI: `bash scripts/ci-local.sh` passed Ruff, dependency integrity, Bandit with zero high-severity findings, compileall, skill and prompt-injection gates, and every backend/docs test directory; final services directory reported `930 tests` passing.
- Subsequent review quality gates: `./.venv/bin/ruff check .`, repo-wide `./.venv/bin/ruff format --check .`, and `git diff --check` passed; Ruff reported all 273 files formatted.
- Subsequent review external verification: published `analyze-action@v1` remained tag object `f2e36ce` without enforcement outputs and Action PR #7 remained open/unmerged on 2026-09-09.
- Subsequent review independent verification: a read-only checklist pass confirmed all 18 findings and all follow-up residuals were resolved with no remaining concrete defects.
- Latest review RED: expanded section-scoped contracts reproduced the configured/effective-mode, shared-scope onboarding, inherited Action, string-output, protected-input, activation, non-atomic restore, audit-provenance, manifest-completeness, break-glass, metric-taxonomy, mutable-configuration, project-scope, and regression-strength gaps (`23 failed, 9 passed, 64 subtests passed`).
- Latest review GREEN: `./.venv/bin/python -m pytest tests/test_docs/test_enforcement_guardrails.py -q --tb=short` - `11 passed, 89 subtests passed`.
- Latest review documentation and metadata suite: `./.venv/bin/python -m pytest tests/test_docs tests/test_infra/test_ai_safety_documentation.py tests/test_infra/test_requirements_traceability_matrix.py -q --tb=short` - `48 passed, 279 subtests passed`.
- Latest review required smoke: `./.venv/bin/python -m unittest discover -q` - `425 tests` passed, `1 skipped`.
- Latest review full local CI: `bash scripts/ci-local.sh` passed Ruff, dependency integrity, Bandit with zero high-severity findings, compileall, skill and prompt-injection gates, and every backend/docs test directory; final services directory reported `930 tests` passing.
- Latest review quality gates: `./.venv/bin/ruff check .`, repo-wide `./.venv/bin/ruff format --check .`, and `git diff --check` passed; Ruff reported all 273 files formatted.
- Latest review independent verification: a read-only checklist pass confirmed all 19 findings and follow-up residuals were resolved with no remaining substantive defects.
- Current review RED: expanded contracts reproduced moving-tag, deletion/rename, counter-semantics, break-glass, scope-control, timeout/idempotency, filter/cancellation, context/attribution, audit-serialization, target/content-binding, proxy-auth, merge-queue, inherited-default, and table-parser gaps (`27 failed, 8 passed, 89 subtests passed`).
- Current review GREEN: `./.venv/bin/python -m pytest tests/test_docs/test_enforcement_guardrails.py tests/test_docs/test_github_action_integration_contract.py tests/test_services/test_github_init_service.py -q --tb=short` - `28 passed, 140 subtests passed`.
- Current review documentation, metadata, and scaffold suite: `./.venv/bin/python -m pytest tests/test_docs tests/test_infra/test_ai_safety_documentation.py tests/test_infra/test_requirements_traceability_matrix.py tests/test_services/test_github_init_service.py -q --tb=short` - `57 passed, 303 subtests passed`.
- Current review required smoke: `./.venv/bin/python -m unittest discover -q` - `426 tests` passed, `1 skipped`.
- Current review full local CI: `bash scripts/ci-local.sh` passed Ruff, dependency integrity, Bandit with zero high-severity findings, compileall, skill and prompt-injection gates, and every backend/docs test directory; final services directory reported `930 tests` passing.
- Current review quality gates: `./.venv/bin/ruff check .`, repo-wide `./.venv/bin/ruff format --check .`, and `git diff --check` passed; Ruff reported all 273 files formatted.
- Current review independent verification: a read-only checklist pass confirmed all 25 findings and three follow-up residuals were resolved with no remaining substantive defects.
- Latest review final RED checkpoint: the strengthened contracts still exposed three unresolved documentation/scaffold conditions (`3 failed, 27 passed, 149 subtests passed`) before the final corrections.
- Latest review focused GREEN: `./.venv/bin/python -m pytest tests/test_services/test_github_init_service.py tests/test_docs/test_enforcement_guardrails.py tests/test_docs/test_github_action_integration_contract.py -q --tb=short` - `29 passed, 150 subtests passed`.
- Latest review expanded documentation, metadata, and scaffold suite: `./.venv/bin/python -m pytest tests/test_docs tests/test_infra/test_ai_safety_documentation.py tests/test_infra/test_requirements_traceability_matrix.py tests/test_services/test_github_init_service.py -q --tb=short` - `58 passed, 313 subtests passed`.
- Latest review required smoke: `./.venv/bin/python -m unittest discover -q` - `427 tests` passed, `1 skipped`.
- Latest review full local CI: `bash scripts/ci-local.sh` passed Ruff, dependency integrity, Bandit with zero high-severity findings, compileall, skill and prompt-injection gates, and every backend/docs test directory; final services directory reported `930 tests` passing.
- Latest review quality gates: `./.venv/bin/ruff check .`, repo-wide `./.venv/bin/ruff format --check .`, and `git diff --check` passed; Ruff reported all 273 files formatted.
- Latest review independent verification: a separate verification pass confirmed all 20 findings and the generated-README capability residual were resolved with no remaining substantive defects.
- New review RED: the added contracts reproduced missing checkout provenance, incomplete break-glass expiry, the fenced-heading parser escape, and stale generated capability wording (`4 failed, 20 passed, 125 subtests passed`).
- New review focused GREEN: `./.venv/bin/python -m pytest tests/test_docs/test_enforcement_guardrails.py tests/test_docs/test_github_action_integration_contract.py tests/test_services/test_github_init_service.py -q --tb=short` - `31 passed, 156 subtests passed`.
- New review expanded documentation, metadata, and scaffold suite: `./.venv/bin/python -m pytest tests/test_docs tests/test_infra/test_ai_safety_documentation.py tests/test_infra/test_requirements_traceability_matrix.py tests/test_services/test_github_init_service.py -q --tb=short` - `60 passed, 319 subtests passed`.
- New review required smoke: `./.venv/bin/python -m unittest discover -q` - `429 tests` passed, `1 skipped`.
- New review full local CI: `bash scripts/ci-local.sh` passed Ruff, dependency integrity, Bandit with zero high-severity findings, compileall, skill and prompt-injection gates, and every backend/docs test directory; final services directory reported `930 tests` passing.
- New review quality gates: `./.venv/bin/ruff check .`, repo-wide `./.venv/bin/ruff format --check .`, and `git diff --check` passed; Ruff reported all 273 files formatted.
- New review external verification: `actions/checkout@v4` remained lightweight commit `11d5960a326750d5838078e36cf38b85af677262`; `analyze-action@v1` remained annotated tag `f2e36cef443129e85c55882b9dafc1f20d409284` dereferencing to `3b37ed72bfb2d201030bef873268f2170794b160`; Action enforcement PR #7 remained open on 2026-09-09.
- New review independent verification: a separate pass confirmed all six findings and the adversarial fenced-heading residual were resolved with no remaining substantive defects.

### Completion Notes List

- Added a canonical enforcement guardrail guide that explains Evidence Law, organization-owned benchmark thresholds, false reassurance, mandatory human review, rollback responsibility, staged rollout, and break-glass controls.
- Explicitly states that DeployWhisper defines no universal numeric enforcement threshold because the PRD leaves that policy decision open; teams must approve thresholds using representative benchmark evidence before blocking.
- Linked the guide from the README, policy adapter contract, CI guide, GitHub Action guide, GitHub App guide, and self-hosted GitHub App runbook so operators encounter it before configuring required checks.
- Added deterministic documentation regressions for every acceptance-criterion topic and every enforcement entry-point link.
- GitHub init scaffolding now emits reviewed immutable Action/checkout pins and accurate resolved-enforcement guidance. Analysis, API, persistence, UI, and dependency behavior did not change. Implementation is stacked on the verified but unmerged Story 11.3 branch because this story documents and safely scaffolds that enforcement contract.
- Resolved all six review findings: project-default inheritance and override deletion are explicit; invalid or unavailable decisions cannot become passes; benchmark inputs, calculations, and strict zero Evidence Law violations are documented; mode prerequisites and observable GitHub effects are unambiguous; and stale UI guidance now points to the React SPA conventions.
- Resolved all eight final-review findings: README and Action-guide semantics are capability-gated; low blocking thresholds cannot borrow the high/critical Evidence Law guarantee; new inherited integrations start advisory; required-job wiring is explicit; benchmark reapproval and failure recovery are auditable; and structured tests lock mode effects plus inbound and outbound links.
- Resolved all 17 review-rerun findings: effective-status behavior is distinct from configured ceilings; Action errors fail closed; blocking Action refs are immutable and smoke-tested; inherited GitHub App settings are explicit; stale, missing, and excluded decisions cannot pass; exception handling is scoped, time-bound, concurrency-safe, and reconstructible; lower-than-high blocking remains disabled under the current decision contract; benchmark evidence is reproducible and tied to deployed artifacts; and automated checks no longer substitute for mandatory human approval.
- Resolved all 18 subsequent-review findings: published Action behavior is accurately capability-gated; missing and partial intake cannot silently pass; decisions bind to the actual protected PR-head, merge-queue, or non-PR target and manifest; v1 settings-race limitations are explicit; transport, authorization, separation-of-duties, expiry, audit integrity, and retention controls are complete; benchmark identity and production labels are reproducible; reapproval covers every consumer/wiring change; onboarding begins advisory under inherited blocking; tests enforce section placement and duplicate-row rejection; and Epic 11 is now done.
- Resolved all 19 latest-review findings: scope onboarding cannot downgrade existing consumers; protection removal keys off configured mode; Action inheritance and string outputs are explicit; every enforcement input is protected; guide entry conditions cover inherited and expanding scope; break glass uses scoped provider controls or a genuinely exclusive settings lock; audit digests no longer overclaim provenance; manifest completeness matches runtime counters exactly; project-scope `neutral` is treated as fail-open; benchmark labels and mutable configuration are reproducible; baseline and elevated review are distinct; and regressions enforce section uniqueness, ordering, and complete Epic 11 status.
- Resolved all 25 current-review findings: Action usage and the GitHub scaffold pin immutable commits; deletion/rename and byte-level coverage limitations are explicit; accepted-versus-analyzed counters are unambiguous; temporary settings are no longer a break-glass path; ruleset bypasses revoke automatically; project scope and resolved thresholds are checklist gates; timeouts, retries, idempotency gaps, skipped jobs, base/head changes, moving deployment refs, material context, and merge queues fail safely; proxy-auth prerequisites and inherited defaults are consistent across entry points; and tests reject malformed tables without freezing moving external state.
- Resolved all 20 latest-review findings: documented and scaffolded workflows pin both checkout and DeployWhisper Action commits; examples identify the Action step; current merge-queue and published-Action capability limits are explicit; inherited modes are separated from required-check wiring; every mandatory identity, idempotency, settings-freeze, and diff-coverage control appears in the rollout checklist; false-reassurance signals retain separate denominators; generated guidance accurately describes the current advisory-only pin; and stricter regressions validate links, prose contradictions, lifecycle invariants, pin shape, and complete mode-table structure.
- Resolved all six new-review findings: break glass now has a maximum expiry and fail-closed revocation verification; checkout provenance and independent pin review are reproducible; the merge-queue audit record states the implemented prohibition; fragment validation ignores fenced pseudo-headings and suffixes duplicate slugs; Epic 11 lifecycle checks discover future stories; and generated capability guidance plus documented pins stay synchronized with scaffold constants.

### File List

- README.md
- _bmad-output/implementation-artifacts/11-4-enforcement-guardrail-documentation.md
- _bmad-output/implementation-artifacts/sprint-status.yaml
- docs/ci-advisory-consumption.md
- docs/enforcement-guardrails.md
- docs/github-action.md
- docs/github-app-self-hosted-setup.md
- docs/github-app.md
- docs/workflow-adapter-output-contract.md
- integrations/github/init_service.py
- tests/test_docs/test_enforcement_guardrails.py
- tests/test_docs/test_github_action_integration_contract.py
- tests/test_services/test_github_init_service.py

## Change Log

- 2026-05-01: Story created/aligned from updated PRD, architecture, epics, sprint status, and readiness report.
- 2026-09-07: Added canonical optional-enforcement guardrails, linked all enforcement entry points, added deterministic documentation coverage, completed full validation, and moved the story to review.
- 2026-09-08: Addressed all six code-review findings, strengthened the documentation contract, completed full validation, and moved the story to done.
- 2026-09-08: Addressed all eight findings from the final review rerun, reconciled published Action capability guidance, strengthened operational guardrails and structured tests, and retained done status after full validation.
- 2026-09-09: Addressed all 17 findings from the subsequent review rerun, expanded fail-closed enforcement and benchmark guardrails, completed full validation, and retained done status.
- 2026-09-09: Addressed all 18 findings from the next review rerun, aligned guidance with the unreleased Action capability and integration-neutral enforcement limits, completed full validation, closed Epic 11, and retained done status.
- 2026-09-09: Addressed all 19 findings from the latest review rerun, closed remaining scope, manifest, audit, and GitHub integration guardrail gaps, completed full validation, and retained Story 11.4 and Epic 11 as done.
- 2026-09-09: Addressed all 25 findings from the current review rerun, pinned generated Action workflows, documented the remaining enforcement capability boundaries, completed full validation, and retained Story 11.4 and Epic 11 as done.
- 2026-09-09: Addressed all 20 findings from the latest review rerun plus the verifier's generated-README capability residual, completed repository-wide validation, and retained Story 11.4 and Epic 11 as done.
- 2026-09-09: Addressed all six findings from the new review rerun plus the verifier's fenced-heading residual, completed repository-wide validation, and retained Story 11.4 and Epic 11 as done.
