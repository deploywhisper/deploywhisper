---
workflowType: prd
workflow: edit
version: '0.3'
status: adopted-for-planning-not-implementation-ready
release: v1.5.0
priority: highest-feature-priority
canonical_epic: 16
lastEdited: '2026-10-07'
stepsCompleted: [step-e-01-discovery, step-e-02-review, step-e-03-edit, step-e-04-complete]
inputDocuments:
  - docs/deploywhisper-infra-automation-prd.md
  - _bmad-output/planning-artifacts/infra-automation-v1.5.0-release-plan.md
  - _bmad-output/planning-artifacts/research/technical-infra-automation-research-2026-10-07.md
editHistory:
  - date: '2026-10-07'
    changes: Adopt bounded Tier 0/1 release scope with stable Epic 16 IDs and complete original-requirement dispositions.
---

# DeployWhisper Infra Automation — Canonical Feature PRD v0.3

## Executive Summary

**Infra Automation is the highest-priority feature for v1.5.0:** collect or upload preflight evidence, analyze it through DeployWhisper's shared core, record a verified human decision against immutable evidence, and hand off the exact approved request to an operator-owned delivery system. This preserves the product's self-hosted, local-first, fully open-source posture and Evidence Law. Canonical reports remain advisory; workflow policy decisions are separate records.

This whole-document addendum **supersedes the planning scope, old phase/release assumptions, requirement priorities and proposed 16.0–16.33 breakdown in the [original v0.2 draft](../../docs/deploywhisper-infra-automation-prd.md)**. The original remains historical input, not the implementation contract. The [parent PRD](prd.md) retains its original 187 functional and 38 nonfunctional requirements. New IAU15 IDs extend that contract without replacing parent IDs. Adoption means planning scope is accepted in this workstream; it does not mean public RFC approval, completed spikes, implemented functionality or production certification.

The accepted v1.4.0 tracking baseline is 101 stories: 84 done, 15 ready-for-dev and 2 review. Keep existing identifiers, especially 12.5 SBOM and Release Checksums and delivered 12.6/13.8. New Epic 16 contains 20 planning stories 16.0–16.19; release priority changes delivery order, not history. See the [release plan](infra-automation-v1.5.0-release-plan.md), [research](research/technical-infra-automation-research-2026-10-07.md) and [per-ID dispositions](infra-automation-requirement-dispositions.json).

## Success Criteria

The supported release is accepted only when a real authenticated operator completes both uploaded-evidence review and isolated collected-plan review, a second verified operator approves in shared mode, the qualified receiver verifies the exact locally retained plan, and unknown delivery reconciles without a duplicate action. A single-operator profile must explicitly label acknowledgement rather than separation of duties. Multi-unit demonstrations cover only declared preflight dependencies and combined evidence.

Every active requirement below has a named acceptance proof and canonical story mapping. Independent security/code review, composed-browser/a11y checks, fault-injection and operational qualification must pass before stable release. No implementation/runtime proof has been run for this planning update. In particular identity, saved-plan custody, runner isolation and receiver crash recovery remain 16.0 feasibility gates.

## Product Scope

| Profile | v1.5.0 support contract |
| --- | --- |
| Application | One self-hosted FastAPI app instance, Python-first shared analysis core, React production assets, SQLite and local artifact storage. No Node runtime or new mandatory control plane. |
| Uploaded evidence | Existing supported intake formats, immutable reports and authenticated human review. A handoff request may carry an advisory receipt; uploaded JSON alone is not exact saved-plan apply authorization. |
| Collected evidence | One qualified Linux isolated runner profile with operator-installed pinned OpenTofu/Terraform and protected command/provider catalog; outbound HTTPS only. Concrete isolation mechanism/tool versions must be approved and exercised in 16.0 before support is claimed. OpenTofu/Terraform retain their own licenses; DeployWhisper's MIT license does not authorize redistribution of tool binaries. |
| Exact-plan receiver | Operator-owned self-hosted GitHub execution environment with deliberate protected access to the exact immutable saved binary plan in trusted local custody. Cloud-hosted receivers without separately qualified custody are unsupported for exact-plan handoff. |
| Identity | Provisional primary design: minimal local human accounts, secured bootstrap, server-verified sessions and persisted project/workspace memberships. Separate scoped service/agent/runner credentials. Exact password/session/recovery design needs 16.0 threat-model/public-RFC review; existing actor/role headers are insufficient. No SSO claim. |
| Orchestration | Bounded immutable workflows, safe retries, durable approval, GitHub handoff/receipt/reconciliation, human-declared units/preflight waves, manual/API/CLI and signed webhook starts. |

P0 comprises all 60 FR and 12 NFR below and their operational acceptance. No release date or performance measurement is implied. A versioned manifest must freeze supported tool, runner, app and receiver versions during qualification. Existing nonautomation database/deployment promises in the parent PRD do not imply PostgreSQL multi-instance automation support.

**Post-v1.5 deferred scope:** AI Composer/Mapper/Planner/Diagnostician/Package Advisor, package ledger/governance, additional automated collectors (Ansible/kubectl/Helm/Git/Terragrunt/CloudFormation), generalized plugins/scripts, Git sync, visual builder, graph UI, schedules/drift, environment promotion/deployment stages, Jenkins/GitLab/ITSM/webhook outbound adapters, automatic/inferred unit graphs and PostgreSQL scaling. Existing supported uploads remain available. Tier 2 apply/destroy/remediation, autonomous approval and emergency bypass are excluded; any future change requires separate RFC/product authorization, not a later-story assumption.

## User Journeys

| Journey / need | Required outcome | Requirement groups |
| --- | --- | --- |
| Reviewer receives a plan upload | Scoped authenticated review with immutable report, clear limitations and restart-safe decision | Identity, workflows, evidence, decisions, UX |
| Platform engineer collects from trusted IaC | Qualified isolated runner creates screened evidence, local saved-plan custody and auditable provenance | Runners, evidence, handoff/custody |
| Shared reviewer authorizes exact handoff | Exact source/evidence/policy/target shown; distinct verified approver; freshness rechecked on consume | Identity, decisions, handoff/custody |
| Operator encounters lost dispatch response | Visible delivery_unknown, lock preserved, receipt/reconciliation resolves the same operation | Engine, handoff/custody, UX |
| Operator reviews declared unit bundle | Deterministic preflight waves and combined evidence; no claim that upstream deployment prerequisites have materialized | Workflows, evidence, UX |
| Maintainer upgrades/restores/revokes | State retained, stale grants/leases invalidated, accepted external work reconciled, limits and runbooks usable | Lifecycle, administration, NFRs |

## Domain Requirements and Architectural Boundaries

Collection is privileged execution: Terraform providers/external programs can run during plan. Fixed argv is insufficient without source admission, isolation, controlled dependencies, least-privilege credentials and egress limits. Authenticated runner provenance establishes who submitted output, not whether a compromised runner told the truth. Deterministic evidence comes from supported extraction/rules rather than complete metadata alone.

The saved-plan custody boundary must provide opaque operation handles, owner-restricted files/directories, immutable finalized bytes, explicit encryption/storage policy, digest verification, expiry, cleanup and crash persistence. A bare shared directory is insufficient. Neither DeployWhisper nor public GitHub artifacts receive binary plans/state. The receiver must check current authorization immediately before starting its operation and verify the approved bytes; new plans always require new evidence and decision. P0 must not claim collection order executes infrastructure dependency order.

Human accounts and memberships are a new security boundary, not a rename of existing role headers. Legacy linked-report/settings/policy paths must not undermine it. Immutable run snapshots, fenced durable state, transactional outbound intents, target locks, one-use grants and receiver operation records are release safety constraints. Cancellation/disable/revocation cannot undo already-started external actions; recovery remains available. Restore epochs must make old pending authorizations unusable.

The closed registry exposes only the supported domain path. Public RFC, ADRs, UX/API contracts and executable identity/fencing/isolation/custody/receiver spikes in 16.0 precede feature implementation. No new dependency is approved merely by naming a mechanism here. Backend support for React remains additive with its own labeled PR where behavior changes; migrations and account/automation state are isolated feature work. Existing design tokens and sanctioned flows govern all new screens.

## Functional Requirements

All requirements are P0, planned and not implemented. Named proof columns identify future acceptance evidence, not existing test results.

### Scope and identity

| ID | Requirement | Stories | Acceptance proof |
| --- | --- | --- | --- |
| IAU15-FR-001 | Support only Tier 0 preflight and Tier 1 human-approved external handoff in v1.5.0; reject apply/destroy, remediation, unattended approvals and unsupported execution profiles. | 16.0, 16.3 | Scope/RFC review and unsupported-mode rejection corpus |
| IAU15-FR-002 | Resolve each human decision from a verified human principal; caller actor/role headers cannot establish identity. | 16.1, 16.2 | Authenticated-session and malicious-header tests |
| IAU15-FR-003 | Bootstrap the first local operator through an operator-held one-use setup credential with no default account/password; provide a documented secured account-recovery procedure. | 16.1, 16.18 | Bootstrap replay/default-credential tests and recovery exercise |
| IAU15-FR-004 | Enforce human session expiry, logout and revocation with protected cookies and CSRF defenses for browser mutations. | 16.1 | Session lifecycle, cookie and CSRF test matrix |
| IAU15-FR-005 | Distinguish human, service, agent and runner credentials; nonhuman credentials cannot obtain human sessions, publish workflows or decide approvals. | 16.1, 16.2, 16.17 | Principal-type privilege matrix |
| IAU15-FR-006 | Derive project/workspace capabilities from server-owned memberships, denying absent membership and cross-scope access by default. | 16.2 | Role × project × workspace authorization matrix |
| IAU15-FR-007 | Protect automation-linked report, policy, settings and artifact paths against bypass through legacy caller-controlled scope or role inputs. | 16.2, 16.6 | Legacy-route and linked-object bypass regression tests |
| IAU15-FR-008 | Enforce distinct requester/approver identities in shared mode; label authenticated single-operator decisions as acknowledgement with no separation-of-duties claim. | 16.2, 16.9 | Self-approval denial and acknowledgement-mode E2E |

### Workflows and lifecycle

| ID | Requirement | Stories | Acceptance proof |
| --- | --- | --- | --- |
| IAU15-FR-009 | Publish a versioned workflow schema with typed, bounded inputs and explicit supported step input/output contracts. | 16.3 | Schema valid/invalid fixture corpus |
| IAU15-FR-010 | Validate definitions without side effects using bounded YAML bytes/depth/aliases, duplicate-key rejection and an acyclic graph capped at 50 steps. | 16.3 | Parser resource-abuse and cycle/step-limit corpus |
| IAU15-FR-011 | Accept only the closed P0 registry: supported artifact intake, OpenTofu/Terraform collection, analyze, policy gate, approval and GitHub handoff; reject arbitrary scripts/plugins, loops and generic failure/finally execution. | 16.3 | Registry and unsupported-handler denial corpus |
| IAU15-FR-012 | Resolve only typed substitution references to inputs, declared step outputs and run/project metadata; reject unknown references, functions and code evaluation. | 16.3 | Typed-reference and injection fixture corpus |
| IAU15-FR-013 | Require every executable path to a handoff to pass its mandatory successful evidence analysis, policy gate and matching approval; skipped/failed or unrelated ancestors do not qualify. | 16.3, 16.8 | Wrong-branch, skipped-ancestor and alternate-path tests |
| IAU15-FR-014 | Scope workflow drafts and revisions to one project and optional workspace. | 16.4 | Workflow cross-scope CRUD tests |
| IAU15-FR-015 | Keep published revisions immutable; restore creates a new draft, and drafts cannot execute. | 16.4 | Publish/edit/restore/draft-run lifecycle tests |
| IAU15-FR-016 | Snapshot the published definition, validated inputs, scope and source identity immutably when a run starts; require a repository commit for collected/exact-plan paths and explicitly mark unavailable source for upload-only advisory review. | 16.4, 16.5 | Post-start mutation and rerun snapshot tests |
| IAU15-FR-017 | Disable, revoke or restore epoch changes must invalidate unconsumed grants and prevent new run starts, collection claims, dispatch or grant consumption while preserving read and reconciliation for accepted external work. | 16.4, 16.10, 16.11, 16.18 | Disable/revoke/restore-before-dispatch-or-consume race matrix |

### Engine

| ID | Requirement | Stories | Acceptance proof |
| --- | --- | --- | --- |
| IAU15-FR-018 | Persist run/step transitions and explicit `stopped_by_gate`, `expired`, `timed_out`, `cancelled`, `failed`, `succeeded` and `delivery_unknown` outcomes across restart. | 16.5, 16.11 | Crash at each transition with state recovery assertions |
| IAU15-FR-019 | Fence leader/task attempts so only the current owner may heartbeat, log, upload or complete a task. | 16.5, 16.12 | Overlapping leader and stale-attempt rejection tests |
| IAU15-FR-020 | Retry only declared safe/idempotent local work within finite deadlines; persist idempotent outputs and reconcile uncertain external work instead of blind resend. | 16.5, 16.11 | Retry/deadline/duplicate-completion and dropped-response tests |
| IAU15-FR-021 | Record cancellation durably and terminate the owned runner process tree; explain that cancellation cannot undo accepted external work. | 16.5, 16.13, 16.15 | Cancellation/dispatch races and process-tree termination tests |
| IAU15-FR-022 | Bound per-workflow/project concurrency, backlog, analysis workers and storage usage with explicit quota/backpressure errors. | 16.5, 16.18 | Saturation, queue-cap and storage-exhaustion tests |

### Evidence and analysis

| ID | Requirement | Stories | Acceptance proof |
| --- | --- | --- | --- |
| IAU15-FR-023 | Allow runner-less upload of currently supported artifact formats through existing scoped intake protections. | 16.6 | Uploaded-artifact vertical slice and size/type/traversal tests |
| IAU15-FR-024 | Screen inputs, metadata, streamed logs, errors and artifacts before persistence or analysis; reject state/credential/key/binary-plan uploads and inline secret-looking values. | 16.6, 16.14 | Secret corpus including chunk boundaries and blocked-file tests |
| IAU15-FR-025 | Record authenticated collection provenance with runner/task attempt, command/argv digest, source SHA, exit code, time, raw-local digest, sanitized digest and redaction version; recompute received digests. | 16.6, 16.14 | Tampered digest, stale attempt and redaction-provenance tests |
| IAU15-FR-026 | Invoke the existing shared analysis core without duplicating risk logic; provenance alone cannot turn inferred output into deterministic evidence. | 16.6, 16.14 | Cross-surface report parity and Evidence Law fixtures |
| IAU15-FR-027 | Link runs to immutable reports through a compatible versioned optional provenance contract; retain permanent report URLs and existing report consumers. | 16.6, 16.7 | Serializer/constructor/legacy-consumer contract tests |
| IAU15-FR-028 | Expose missing/partial/stale collection as confidence limitations and context TODOs; failed or incomplete mandatory collection cannot make approval eligible. | 16.6, 16.8, 16.14 | Partial/error/stale collection eligibility tests |
| IAU15-FR-029 | Keep deterministic automation usable with AI disabled or narrative failure, and preserve existing structured-summary/local-only provider boundaries without new AI composition. | 16.6 | AI-off and narrative-failure vertical slice |

### Decisions

| ID | Requirement | Stories | Acceptance proof |
| --- | --- | --- | --- |
| IAU15-FR-030 | Pause for a human decision durably with a finite deadline and never auto-approve on restart, expiry or missing reviewer. | 16.8 | Restart/expiry/missing-reviewer decision tests |
| IAU15-FR-031 | Bind approval to authorization kind, revision, source identity and required exact-plan commit, project/workspace/environment, reports, artifact and unit-plan digests, policy version, exact target and payload digest. | 16.8, 16.10 | Independent mutation of every decision-tuple field |
| IAU15-FR-032 | Enforce evidence freshness at decision, dispatch and receiver consumption; default collection TTL is 60 minutes unless an audited stricter policy applies. | 16.8, 16.11 | Clock/TTL boundary and delayed-consume tests |
| IAU15-FR-033 | Evaluate explicit workflow policy separately from advisory report semantics, preserving canonical should_block=False and using existing policy-adapter field meanings where compatible. | 16.8 | Gate decision versus advisory report contract tests |
| IAU15-FR-034 | Require an explicit authenticated approve/reject decision and reason when the canonical recommendation is `no-go`, severity is high/critical or the separate typed `insufficient_context` flag is true, with typed confirmation for high/critical. | 16.9 | Reason/confirmation API denial and keyboard decision E2E |
| IAU15-FR-035 | Invalidate eligibility when evidence, revision, source, scope, target, policy, membership or custody changes, expires or is superseded; no emergency bypass or delegated approval in P0. | 16.8, 16.10, 16.11 | Revocation/supersession/custody-loss and bypass-denial matrix |

### Handoff and custody

| ID | Requirement | Stories | Acceptance proof |
| --- | --- | --- | --- |
| IAU15-FR-036 | Register outbound GitHub destinations with administrator-controlled host policy; revalidate DNS/connection addresses and redirects, blocking metadata/loopback/private targets except explicit audited internal-host exceptions. | 16.10 | IPv4/IPv6/DNS/redirect SSRF corpus |
| IAU15-FR-037 | Atomically persist the approved outbound intent and exact payload before network effects, with a stable receiver operation identity. | 16.10 | Transaction/crash-before-send and payload-tamper tests |
| IAU15-FR-038 | Issue one-use scoped receiver grants bound to the decision tuple, operation, expiry and live epoch; reject duplicate/replayed or altered consumption. | 16.10, 16.11 | Grant replay/expiry/epoch/source/digest tests |
| IAU15-FR-039 | Consume grants into a durable receiver operation record before external action so a consume-before-action crash resumes the same operation without a second action. | 16.11 | Receiver crash at consume/start/completion boundaries |
| IAU15-FR-040 | Distinguish dispatch acceptance, externally observed completion and delivery_unknown; reconcile unknown outcomes through receiver receipts and never report dispatch acceptance as successful deployment. | 16.11 | Lost-response/poll/receipt fault matrix and UI semantic tests |
| IAU15-FR-041 | Authorize exact-plan handoff only when the qualified self-hosted receiver can verify the original immutable saved-plan bytes in protected local custody by opaque handle, raw digest and expiry; no server/public-artifact plan storage, and replanning requires fresh evidence/approval. Upload-only advisory receipts never authorize apply or require invented repository provenance. | 16.0, 16.11, 16.14 | Real custody access/restart/overwrite/symlink/expiry/replan spike and receiver tests |
| IAU15-FR-042 | Canonicalize target lock identities across aliases and retain locks during unknown external work until verified resolution or an audited operator break that does not mint a new authorization. | 16.10, 16.16 | Alias collision/lock expiry/unknown-work/break tests |
| IAU15-FR-043 | Verify receiver callback signatures, operation/run/source identity and replay protection using the pinned GitHub adapter version and protected branch/tag dispatch ref. | 16.11 | API-version, callback replay and mutable-ref substitution contract tests |

### Runners

| ID | Requirement | Stories | Acceptance proof |
| --- | --- | --- | --- |
| IAU15-FR-044 | Enroll runners using one-use tokens and project-scoped expiring credentials with rotation/revocation and outbound HTTPS protocol-version negotiation. | 16.12 | Enrollment replay/rotation/revocation/TLS/version tests |
| IAU15-FR-045 | Bind every task claim, heartbeat, log, upload and completion to the authorized runner, project, current attempt and live lease. | 16.12 | Wrong-runner/project/expired-lease matrix |
| IAU15-FR-046 | Route collection to eligible runner tags with no silent fallback; fail clearly when none qualify or enforce an explicit finite wait, and expose last-seen/version/task health. | 16.12, 16.15 | No-runner/tag-mismatch/wait-timeout and health tests |
| IAU15-FR-047 | Collect only from admitted trusted immutable sources in disposable isolated workspaces with canonical-root/symlink containment and controlled tool/provider installation; reject untrusted PR sources and inherited Git/hooks/config. | 16.13 | Hostile checkout/provider/config and isolation spike |
| IAU15-FR-048 | Execute only operator-protected fixed catalog commands with validated parameters; reject arbitrary shell, server-defined commands and app Docker-socket access. | 16.13 | Catalog tampering/option injection/arbitrary-command denial tests |
| IAU15-FR-049 | Qualify OpenTofu/Terraform plan and JSON extraction for declared pinned versions, distinguishing exit 0/no-change, 2/change and error; retain the sensitive binary plan locally and transport screened JSON only. | 16.14 | Real-tool compatibility smoke and hostile/sensitive plan fixtures |
| IAU15-FR-050 | Resolve infrastructure credentials only in the operator-owned runner/receiver execution identities under an environment allow-list and least privilege; never send or persist their values in DeployWhisper. | 16.13, 16.14 | Credential inheritance/transport/persistence corpus and separated-identity spike |
| IAU15-FR-051 | Enforce task CPU/time/disk/output/egress caps and atomic bounded uploads with cleanup after failure; cancellation must terminate the entire owned process tree. | 16.13, 16.14 | Limit, partial-upload, disk-full, egress and descendant-process tests |

### UX and interfaces

| ID | Requirement | Stories | Acceptance proof |
| --- | --- | --- | --- |
| IAU15-FR-052 | Provide sanctioned React navigation, validated templates/YAML draft/publish controls and scoped workflow/run lists using actual APIs and existing design primitives without changing Dashboard information budget. | 16.7 | Compose-built workflow creation and scoped-list keyboard/a11y E2E |
| IAU15-FR-053 | Show immutable run timeline, screened logs, artifact digests, linked briefing, uncertainty and permanent report provenance links with loading/empty/error/disabled/degraded states. | 16.7 | Compose-built run/history/report states and real-data E2E |
| IAU15-FR-054 | Provide a scoped approval inbox and keyboard-operable decision screen showing exact evidence, target/payload, freshness, policy, confidence, blast radius and rollback context with acknowledgement labeling. | 16.9 | Compose-built approve/reject/self-approval/freshness E2E |
| IAU15-FR-055 | Expose runner health, collection/cancel progress and unknown/reconciliation state with advisory copy that never claims Tier 0/1 deploys infrastructure. | 16.15 | Real-runner composed E2E and unknown-state copy checks |
| IAU15-FR-056 | Accept only human-declared unit inventory and dependencies; validate exact unit coverage/cycles/unknown identities, persist deterministic preflight waves and combined evidence digest, and show accessible scope/lock tables without claiming deployment ordering. | 16.16 | Multi-unit exact-cover/cycle/digest tests and accessible table E2E |
| IAU15-FR-057 | Start scoped runs manually or through signed timestamped replay-resistant webhook intake with typed inputs, idempotency, source pinning and bounded errors/quotas; record trigger origin and principal. | 16.17 | Raw-byte HMAC/replay/idempotency/invalid-input/source tests |
| IAU15-FR-058 | Expose versioned automation API and CLI validation/run/status/list/decision commands over the same authority, envelopes and generated SPA types; agent read/request mode cannot decide or publish. | 16.17 | API/CLI/OpenAPI parity and nonhuman-mutation denial tests |

### Administration

| ID | Requirement | Stories | Acceptance proof |
| --- | --- | --- | --- |
| IAU15-FR-059 | Record append-only application audit events with verified principal/type, role, scope, target, reason, time and before/after digests; expose scoped UI/JSON export without raw artifacts/secrets and document DB-admin trust limits. | 16.4, 16.9, 16.12, 16.18 | Audit event coverage/export authorization and secret corpus |
| IAU15-FR-060 | Let authorized operators configure feature enablement, targets, quotas, retention, TTL and credential lifetimes; reject unsafe reductions, protect pending evidence or invalidate its decision before deletion, and audit each change. | 16.4, 16.18 | Configuration permissions, pending-retention and floor-change tests |

## Non-Functional Requirements

All targets are **planned, not measured**. Reproducible reference profile: one Linux app host with 4 vCPU, 8 GiB RAM and local SSD, singleton SQLite; 20 compatible Linux runner processes, 10 active workflows, at most 2 concurrent deterministic analysis jobs, 50-step definitions; a fixed versioned synthetic corpus of screened artifacts. Record OS/CPU, container/tool/database versions, dataset digest, queue/storage limits and all timestamps. Warm up for 100 samples then measure 1,000 samples for latency, separately reporting p50/p95/p99 and failures. Run capacity for 30 minutes including saturation. Pin sample sizes and artifact sizes in 16.0; approval/network wait is excluded only where explicitly stated. If targets are missed, optimize or explicitly correct advertised limits before release acceptance; never silently call them achieved.

| ID | Requirement | Stories | Acceptance proof |
| --- | --- | --- | --- |
| IAU15-NFR-001 | The declared crash/race corpus must lose no committed run/decision state and produce no unauthorized or duplicate receiver action, including stale attempts, unknown delivery and restore epochs. | 16.5, 16.10, 16.11, 16.19 | Published fault-injection results at every persisted boundary |
| IAU15-NFR-002 | The declared principal × role × project/workspace × object/action matrix must produce zero cross-scope reads or unauthorized mutations. | 16.1, 16.2, 16.12, 16.19 | Published complete authorization matrix results |
| IAU15-NFR-003 | The versioned sensitive-data corpus must yield zero known secret patterns in stored artifacts/logs/metadata/errors/audit or transmitted narrative summaries; no universal-redaction claim follows. | 16.6, 16.14, 16.19 | Stored/output corpus scans including chunk boundaries |
| IAU15-NFR-004 | Automation-originated fixture reports must produce zero Evidence Law violations and preserve deterministic/inferred labels and advisory report semantics. | 16.6, 16.14, 16.19 | Evidence Law and cross-surface contract CI results |
| IAU15-NFR-005 | Ready-step server orchestration overhead must have p95 <1 second, excluding collection/network/analysis duration, under the reproducible reference workload. | 16.5, 16.19 | Timestamped 1,000-transition overhead benchmark |
| IAU15-NFR-006 | Enqueue-to-claim latency must have p95 <2 seconds with 20 online compatible runners under the reference workload. | 16.12, 16.19 | Timestamped 1,000-claim runner benchmark |
| IAU15-NFR-007 | The singleton SQLite profile must sustain 10 active runs with at most 2 concurrent analysis jobs and 20 online runners, with bounded queue/storage and no corrupted transitions. | 16.5, 16.18, 16.19 | 30-minute capacity/saturation run with resource and error report |
| IAU15-NFR-008 | Workflow validation must have p95 <500 milliseconds for the declared 50-step workflow corpus under the reference workload. | 16.3, 16.19 | 1,000-validation timing/correctness benchmark |
| IAU15-NFR-009 | All new React routes must pass the composed-app axe critical/serious violation gate and keyboard-only create/run/review/decision/recovery journeys, using real API-backed seeded data and required screenshots. | 16.7, 16.9, 16.15, 16.16, 16.19 | Compose production build, Playwright/axe/keyboard results and screenshots |
| IAU15-NFR-010 | Upgrade from a v1.4.0 database copy, interrupted upgrade, coordinated DB/artifact backup/restore, token rotation and restricted-network recovery must preserve auditable state while invalidating outstanding authorization/leases until reconciled. | 16.18, 16.19 | Recorded upgrade/restore/rotation/offline exercises |
| IAU15-NFR-011 | Publish version-matched schema/API/CLI/operator/security/support-limit docs with CI link/drift checks and secret-free run/queue/step/runner/approval/delivery metrics plus troubleshooting runbooks. | 16.18, 16.19 | Docs CI and operator self-service installation/recovery pilot |
| IAU15-NFR-012 | Stable v1.5.0 requires signed app/runner artifacts, SBOM/checksums/provenance, named tool/receiver support matrix, full application CI, independent review and supported-profile pilot with no unresolved introduced critical/high defect. | 16.19, 12.5 | Signed release manifest, CI/security/review/pilot evidence |

## Requirement Dispositions and Traceability

The machine-readable [disposition inventory](infra-automation-requirement-dispositions.json) contains exactly 179 original requirement-table IDs: IAU families, UX-DR11–22, DOC-28–34 and NFR-IAU-01–17. Every row carries original text, disposition, explicit rationale and active IDs/story IDs where applicable. `adopted-revised` retains the capability with this contract; `partial-revised` retains only the named subset; `deferred` is outside v1.5.0 P0. These are scope dispositions, never delivery statuses. No original 179-row fulfillment claim is made. Deferred scope stays visible for later planning, without fabricated completed stories.

The active requirement list in the same JSON records ID/text/stories/proof for all 72 requirements. [Epics](epics.md) and [traceability](requirements-traceability-matrix.md) must refer to these canonical IDs. Original 16.0–16.33 draft proposals are replaced rather than renumbered shipped stories.

## Implementation Sequencing and Release Exit

1. **16.0:** accepted public RFC, threat model, identity/fenced claim/isolation/custody/receiver spikes, ADRs and UX/contracts, followed by readiness with no blocking finding. Planning adoption does not satisfy this story by itself.
2. **16.1–16.5:** verified identity/memberships, closed schema, immutable lifecycle and durable engine. 12.5 runs as a release-enabler lane.
3. **16.6–16.9:** uploaded-evidence vertical slice, actual React run/editor/inbox and evidence-bound human decisions.
4. **16.10–16.15:** target controls/outbox/receiver and isolated runner/real tool collection; qualify local custody before exact-plan handoff acceptance. 12.5 must pass before runner distribution.
5. **16.16–16.19:** explicit unit bundle, signed triggers/API/CLI, operational recovery/docs, full production qualification and signed stable release.

[Release-plan §6](infra-automation-v1.5.0-release-plan.md#6-recommended-story-breakdown-and-sequencing) gives exact dependencies; numeric order alone is insufficient. 12.7/12.8 retain their full original acceptance and can be closed only if met; automation-relevant recovery/restricted-network acceptance is mandatory regardless. 13.x documentation gaps and 15.6/15.7 parity reviews stay visible, with only feature-blocking dependencies pulled forward. CNCF work remains after P0 blockers.

Implementation is barred pending 16.0 public-RFC and spike acceptance and a nonblocking readiness review. Each implementation story must receive its own context-filled story file, tests/docs and layered review. Release qualification runs root unittest smoke, every-directory local CI, relevant exact CI pytest shards, Ruff lint and repo-wide formatting; React typecheck/unit/build plus Compose-built FastAPI Playwright/axe/keyboard/screenshots. Document tasks do not pretend those future runtime checks ran. A pilot and published support/limit evidence, signed release assets and no unresolved introduced critical/high defect are required for stable v1.5.0.

## Change Record and Planning Evidence

2026-10-07: User requested course correction using the researched release plan, followed by PRD/architecture updates and implementation-readiness review. The original baseline/release assumptions and broad Phase A/B priorities are superseded by this bounded contract. Stable IDs 12.5 and delivered 12.6/13.8 are preserved; new stories 16.0–16.19 remain planning/backlog until their gates pass. All original 179 rows are dispositioned; 60 new functional and 12 new nonfunctional requirements are adopted for planning.

This documentation update contains no application changes, production support claim, public RFC acceptance, executed identity/custody/isolation spike or benchmark result. Readiness must report outstanding blockers honestly.

## Story preparation follow-up — 2026-10-07

All 20dedicated Epic 16contexts are prepared under [the story-preparation report](../implementation-artifacts/epic-16-story-preparation-report.md). Story 16.0 is ready-for-dev only for governance and disposable synthetic qualification;16.1–16.19 remain backlog while real RFC/spike/interface/dependency evidence is missing. This changes preparation metadata, not the 60 FR/12 NFR contract, original 179 dispositions or released history.
