# RFC 0001: Infrastructure Preflight and Human-Approved Handoff

## Summary

Introduce Epic 16 as DeployWhisper v1.5.0's highest-priority feature: a self-hosted, bounded preflight workflow that accepts existing supported uploads or collects OpenTofu/Terraform plans on an isolated operator runner, uses the shared analysis core, records an evidence-bound human decision, and hands the exact authorized request to one qualified GitHub Actions receiver. DeployWhisper does not apply, destroy, provision or remediate infrastructure. Canonical reports remain advisory; configured workflow eligibility is a separate output.

The user authorized this planning direction on **2026-10-07** and requested course correction, PRD/architecture updates and readiness review. This RFC remains **Proposed**: planning authorization does not establish public maintainer acceptance or completed security/feasibility evidence. Story 16.0 owns the acceptance and qualification gate before implementation readiness.

## Motivation

DeployWhisper currently briefs reviewers on supplied artifacts, but manual artifact collection, detached approvals and carrying a decision into delivery systems leave evidence and execution disconnected. Durable preflight and human-approved handoff address that gap while preserving its evidence-backed differentiation. Kestra's declarative flows, durable runs and approval pauses inform the design; adopting a general deployment engine or plugin catalog would overextend the current Python/FastAPI/SQLite application and product posture.

The original draft combines automation, multiple collectors, estate planning, package governance and several new AI systems. The bounded first release prioritizes identity, approval integrity, recovery, runner containment and exact-plan custody. Those are necessary security foundations rather than optional enterprise features. Existing story IDs retain historical meaning: **12.5 stays SBOM and Release Checksums**, and the feature uses **16.0–16.19**. Release priority changes delivery order, not shipped numbering.

## PRD and Architecture Links

- Parent PRD: [product positioning and requirements](../../_bmad-output/planning-artifacts/prd.md), especially §4.4, advisory/enforcement boundaries, Evidence Law, security/operations requirements and the v1.5.0 automation amendment.
- Architecture: [§25 Infrastructure Automation amendment](../../_bmad-output/planning-artifacts/architecture.md#25-v150-infrastructure-automation-architecture-amendment); existing §§2, 4, 8, 19–23 remain constraints.
- Release scope/story sequence: [v1.5.0 release plan](../../_bmad-output/planning-artifacts/infra-automation-v1.5.0-release-plan.md), §§3–8.
- Research: [technical assessment](../../_bmad-output/planning-artifacts/research/technical-infra-automation-research-2026-10-07.md).
- Historical input: [original feature draft](../deploywhisper-infra-automation-prd.md), preserved for per-requirement scope disposition; stale v1.4.0 phase/story assumptions do not authorize implementation.
- Related epics/stories: [canonical epics](../../_bmad-output/planning-artifacts/epics.md), 16.0–16.19; 12.5 runner-distribution prerequisite, reuse done 12.6, automation-specific qualification related to 12.7/12.8. No historic done story is reopened by this RFC.
- Prior decisions: architecture shared-core/advisory/local-first/scale ADRs; proposed **IA-ADR-01–08** in §25.2. No accepted prior automation RFC exists.

Required planning alignment: parent exclusion of a Terraform runner becomes a precise exclusion of provisioning/apply with optional isolated artifact collection; canonical scoped feature requirements, Epic 16 dependency/acceptance mapping, UX contracts, traceability and sprint backlog remain aligned. Accepted RFC status requires links to the final sections and recorded follow-up issues.

## Detailed Design

### Supported scope and boundaries

P0 provides fixed declarative workflow kinds, immutable revisions/run snapshots, uploaded-artifact analysis, durable state/decisions/audit, isolated OpenTofu/Terraform collection, one verified GitHub receiver, human-declared multi-unit preflight waves, manual/API/CLI starts and one signed webhook intake. It works with AI off. Existing optional report narrative is downstream of deterministic scoring. No severity/scoring logic is duplicated under automation.

Excluded from this release: arbitrary scripts/plugins, generic failure/finally handoffs, additional automatic collectors, package ledger, AI Composer/Mapper/Planner/Diagnostician, cron/drift, environment promotion, Jenkins/GitLab/ITSM adapters, Tier 2 execution and unattended approval/handoff. Existing supported upload formats remain usable. PostgreSQL/HA/multi-instance automation and alternate isolation profiles require later measured qualification.

Use `infra_automation/` for typed validation/state/runner/receiver contracts, `services/infra_automation_service.py` for orchestration, existing SQLAlchemy repositories and `migrations/versions/` for durable state, FastAPI `/api/v1/infra-automation/*` resources and existing React primitives/routes. Start the coordinator via `app.py` lifespan; bounded analysis executes outside its event-loop tick with separate sessions. The external Marketplace analysis action remains in `deploywhisper/analyze-action`; this RFC does not move its runtime into the app repository. New `tests/test_infra_automation/` must be registered in local CI and relevant GitHub test shards.

### Identity and authorization

Select local human accounts and server-side opaque sessions as the initial profile. One-use, expiring local CLI bootstrap creates the first administrator. Store salted password verifiers, hashed session/machine/runner credentials and server-owned project memberships; never plaintext reusable tokens/passwords. Require HTTPS cookie protections, CSRF/Origin controls, login abuse limits, expiry/logout/rotation/revocation and password-reset invalidation. Story 16.0 must qualify existing cryptographic facilities and record parameters/resource limits or a separately reviewed dependency decision; no dependency installation is authorized here.

Map existing admin/maintainer/reviewer/contributor/read-only capabilities to explicit automation permissions. Only verified authorized humans publish/decide; shared mode enforces requester separation, while authenticated single-operator mode labels decisions **acknowledgements** and makes no four-eyes claim. Service/agent/runner/receiver tokens have separate audiences and cannot create human sessions, approve or publish. Caller role/actor headers never establish identity. Secure the reused report/artifact/project/policy/settings/target routes that could bypass this boundary. A human credential type is not proof of physical human interaction.

### Workflow persistence and state

Workflow v1 is a bounded closed DAG with YAML size/depth/alias/duplicate-key limits, typed substitution, no executable expression language and side-effect-free validation at draft/publish/start. Published revision bytes/digest, source identity, inputs, policy and unit-map snapshots are immutable. Collected/exact-plan paths require the admitted repository commit; upload-only advisory review records unavailable repository provenance explicitly and cannot invent a saved-plan authorization. Every reachable handoff must bind a matching successful fresh gate/decision to its exact action; approval ancestry alone is rejected.

The singleton SQLite baseline uses short compare-and-swap transactions, transition versions, unique constraints, coordinator generation, monotonically fenced step attempts and scoped leases. Heartbeat/log/upload/completion checks current owner/project/run/attempt/fence/epoch. Recovery never accepts stale workers. Persist outputs before success, bound queue/concurrency/disk/logs/timeouts, and retry only explicitly retry-safe work.

Runs distinguish queued/running/waiting approval/ready handoff/handing off/external running/terminal from **delivery unknown**. Partial/failed analysis may create an advisory report but cannot authorize handoff. Unknown remote acceptance requires reconciliation; cancellation records a request and cannot claim a remote action stopped. Initial proposed qualification profile is 10 active runs, 2 analysis workers, 20 online runners and 50 steps/workflow; named-hardware measurements are required before advertising these limits.

### Approval, locks and external handoff

The versioned decision tuple includes advisory-request versus exact-plan authorization kind and binds workflow revision, source repository/SHA where required, inputs/project/workspace/environment, report digest/schema, policy digest/result, unit map/waves, artifacts/redaction version, raw-local plan identity/custody handle, canonical target/receiver, exact payload and shortest evidence/approval deadline plus authorization/restore epochs. Any substitution, stale evidence, unavailable custody, role/target revocation or stricter safety invalidation requires a new decision. Reasons cannot override hard safety floors; report verdicts remain unchanged. An advisory-request receipt cannot authorize apply; receiver admission rejects mutation under that kind.

Canonical admin-reviewed target aliases resolve to shared collision keys across projects. Lock before handoff-enabled collection; retain across approval, dispatch, accepted/unknown external work. Lease expiry/cancellation is not remote completion proof. Release only on verified terminal outcome or explicit audited privileged reconciliation with acknowledged uncertainty.

Persist authorization, one-use scoped grant and stable outbox operation before dispatch. Receiver protocol v1 authenticates admission online, validates the exact tuple/current epochs, consumes the grant atomically and writes a durable local operation before action. Duplicate operations return existing receipt/status; consume-before-action crashes recover the same operation without minting a fresh grant. The receiver rechecks authority before starting/resuming a new action. Response loss becomes delivery unknown; blind resend is forbidden unless receiver deduplication/reconciliation proves safe. Exactly-once deployment is not promised.

Pin the new adapter to GitHub API **2026-03-10**, test its returned run ID separately from older clients, and protect/resolve the receiver branch/tag separately from immutable IaC SHA. [GitHub dispatch documentation](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event) currently documents HTTP 200 with run ID/URLs, not deployment completion. Authenticate correlated outcomes/callbacks or poll within bounded permission; reject replay/source/receiver mismatches. Registered destinations, DNS/redirect/metadata controls, strict payloads and time/size limits protect outbound traffic. Generic outbound webhook destinations are not P0.

### Runner isolation and exact-plan custody

The supported runner is an outbound HTTPS agent using an operator-controlled **Linux non-root disposable container sandbox** and protected fixed tool catalog. The runner-host launcher owns sandbox creation; app/task never receives a Docker socket. Qualify privileges/capabilities, mounts, source containment, inherited environment, tool/provider identity, egress, per-task least-privilege credentials, resource/time limits and whole-process-tree termination. Pin immutable checkout, disable hooks/unapproved Git config, enforce realpath/no-symlink escapes and reject untrusted PR access to production credentials. Plans/providers/external data sources can execute code: read-oriented command names do not establish safety. Basic isolation is a P0 prerequisite.

Sensitive binary plans/state never travel to DeployWhisper or public GitHub artifacts. A qualified operator self-hosted receiver accesses the exact saved binary plan through a protected local custody store: opaque handles, immutable finalized bytes, owner-restricted access, no-follow file handles, raw digest verification, bounded lifetime, encryption/storage policy and restart-safe custody. Separate collector/receiver identities and credentials; a writable shared folder alone fails the contract. Transport screened/redacted JSON with a distinct server-verified digest/redaction version. Authenticated envelopes establish sender identity, not truthfulness of a compromised collector.

Replanning or changed source/evidence requires fresh analysis/approval. Cloud-hosted execution without qualified custody is unsupported for exact-plan authorization. Uploaded-only paths may request advisory receipt/handoff but cannot assert saved-plan apply authorization. Multi-unit preflight waves order collection/review and do not prove downstream infrastructure exists after upstream changes.

### Versioning, operations and qualification

Workflow/runner/receiver/provenance versions begin at 1, reject unknown majors and negotiate supported capabilities explicitly. Report linkage is relational first; optional versioned provenance is additive to existing v2 only after UI/API/CLI/action/agent/fixture compatibility proof. Otherwise choose an explicit major migration; no invented minor report protocol. API routes reuse existing Pydantic, `ApiRoute`/`ApiError` and `build_meta` contracts, state/conflict/validation/quota codes and bounded pagination/log cursors.

Inbound webhook v1 accepts only pinned workflow revision, project/workspace, registered source repository/commit/origin, typed inputs and idempotency key. Environment-backed HMAC-SHA256 keys, key ID/timestamp/nonce and unambiguous method/path/body-digest signing plus bounded clock skew/persisted nonce protect replay; service-principal scope and quota checks precede scheduling. CLI uses the same authority; event payloads cannot approve.

Feature defaults disabled. Disable/revoke/restore blocks new side effects, invalidates outstanding unconsumed grants and pauses consumed operations awaiting a new action; receipt/poll/reconciliation/read access continues. It cannot undo an already begun remote action. Quiesced coordinated backup/restore changes epoch and invalidates sessions/tokens/leases/grants; operator reconciliation precedes outbound restart. Retention keeps minimal decision digests/tombstones and does not release unknown-operation locks. Append-only API audit is not proof against a host/database administrator.

Story 16.0 gates public acceptance plus executable identity/session/CSRF/revocation, overlapping fenced SQLite claims/restart, hostile-source runner containment and exact-custody/receiver consume-crash-recovery spikes. Subsequent stories include tests/docs per slice. 16.18 covers migration/retention/recovery/restricted-network evidence; 16.19 aggregates full CI, layered security/code/edge review, real pinned tools/receiver pilot, fault injection and composed FastAPI Playwright/axe/keyboard/screenshots. Story 12.5 SBOM and signed app/runner provenance are release blockers. Proposed controls and performance limits are not passed tests or production certifications.

## Security and Privacy

Trust boundaries are human authentication, server memberships, workflow inputs/source, SQL state/authority, collector host/sandbox, local saved-plan custody, registered external receiver, and remote outcomes. Threats include role-header spoofing, cross-project report access, credential leakage, replay/CSRF, malicious IaC/tool/provider execution, stale workers, approval substitution, duplicate/unknown handoff, custody overwrite, restore resurrection and target alias collision.

Fail closed on missing/expired/unknown evidence or authority. Keep cloud/provider/GitHub/webhook secrets in environment-backed operator configuration at the responsible boundary; store only references/hashes/verifiers in application state. Screen artifacts and chunk-spanning logs before transport, prohibit raw plans/state in logs/prompts/URLs/audit, and publish measured redaction limits. External models receive only existing structured summaries if enabled. Local host/DB administrators and compromised collector hosts remain trusted risk boundaries; neither local-first nor signed metadata removes those risks.

Runtime auth, runner isolation and saved-plan receiver proof remain missing implementation evidence. A successful UI demo or completed planning document cannot waive them. Tier 2 or new autonomy requires another RFC, threat model and explicit product amendment.

## Compatibility and Migration

- Upgrade additively from a copy of the released v1.4.0 database and artifact store; verify interrupted upgrade and recovery before stable release. Allocate migrations from the actual current head.
- Existing story IDs/completion records remain intact. New Epic 16 starts backlog; only prepared dependency-satisfied stories become ready-for-dev. Do not claim the original 34 draft stories all ship in v1.5.0.
- Default disabled rollout preserves existing analysis usage while authenticated automation and its sensitive reused paths adopt stronger authority. Enumerate affected old token/header/report-share callers and document a safe migration; legacy headers cannot authorize automation.
- Existing reports/scoring/severity remain canonical. Additive provenance requires exact consumer proof; public schema/version changes require explicit release/migration notes.
- App runtime remains Python/FastAPI serving the static React SPA; Node remains build-only. Runner execution is separately deployed; no IaC binaries or Docker socket enter the application image.
- Singleton SQLite plus qualified Linux runner/local-custody self-hosted receiver is the initial automation support profile. Unsupported DB/OS/receiver modes reject; PostgreSQL/HA remains a later roadmap qualification.
- Docs ship with each story, plus tested bootstrap/session/token rotation, runner/custody/receiver setup, offline tool caches, restore/reconciliation, limits and v1.5.0 release notes. No new dependency is implicitly accepted.

## Alternatives Considered

| Alternative | Decision and reason |
| --- | --- |
| Integration recipes only | Complementary documentation, but does not provide native durable evidence-bound decisions/run state requested for v1.5.0. |
| Embed Kestra/Temporal or recreate broad plugin orchestration | Declined for this release: operational/runtime footprint and product breadth exceed the supported single-instance increment. |
| Replace Story 12.5 with the feature | Declined: corrupts security-epic history/references and removes a runner release prerequisite. Epic 16 gets priority without renumbering. |
| Trust actor/role headers or unauthenticated acknowledgements | Declined: neither establishes verified approver authority or project boundaries. |
| General JWT/OIDC identity plus multi-instance DB first | Deferred breadth; minimal local accounts/opaque sessions reduce initial public contract surface. Revisit with separately qualified integration/dependency decisions. |
| Blind dispatch retries / approval ancestor alone | Declined: neither preserves exact action authorization nor avoids duplicate external action on response loss. |
| Upload binary plans to GitHub/server or replan after approval | Declined: violates locality/secret custody or changes the approved evidence. Exact protected local custody is the initial supported topology. |
| Defer basic isolation to the original Phase C | Declined: collection executes repository/provider code and can expose infrastructure credentials now. |
| Ship new AI/package/estate inference before authority/recovery | Deferred until the deterministic supported path is stable; no AI privilege can solve durable safety requirements. |

## Review Plan

- Required CODEOWNERS reviewers: **@pramodksahoo**, current owner for `docs/`, `_bmad-output/`, API/services/models/migrations/CLI/frontend/integrations/security/governance surfaces in [CODEOWNERS](../../.github/CODEOWNERS). Request applicable area reviews in the public PR; add runner/domain ownership before code delivery.
- Required security, architecture, governance, or roadmap reviewers: maintainers responsible for local-first/raw-artifact security and shared-core architecture, plus governance/roadmap owners. Seek independent security review for identity, containment and receiver/custody boundaries; current single-owner coverage must be disclosed rather than invented as independent approval.
- Minimum review window: **7 calendar days from opening the public RFC review PR**, extendable for disputed/high-impact items under [the RFC process](README.md). No emergency exception is claimed.
- Public discussion: [planning and RFC review PR #154](https://github.com/deploywhisper/deploywhisper/pull/154), opened **2026-10-08T08:06:23Z**. The earliest decision time under the seven-calendar-day minimum is **2026-10-15T08:06:23Z**; review may extend and actual maintainer/security/feasibility acceptance is still required. The author is the currently listed sole CODEOWNER, so no self-review request or independent human approval is claimed.
- Evidence reviewers must examine: Story 16.0 threat model and executable spike results; parent/feature requirement dispositions; API/version/UX contracts; dependency decision if needed; full target-lock/restore/disable/consume-crash matrix; exact tool/receiver/custody support profile and known limits.
- Acceptance checklist: current canonical PRD/architecture/epics agree; no blocking readiness gap; actual principal/fenced-claim/isolation/custody/receiver evidence exists; approving maintainers and public-review dates are recorded.

## Decision Record

- Status: **Proposed**
- Planning authorization date: **2026-10-07**, user request to adopt the release plan through course correction, PRD/architecture updates and readiness review.
- Public review opened: **2026-10-08T08:06:23Z**, [PR #154](https://github.com/deploywhisper/deploywhisper/pull/154).
- Publication observation (2026-10-09): PR #154 merged at **2026-10-08T08:37:29Z**; the retrieved record contains no reviews, comments or outstanding review requests. This early merge is planning publication, not RFC acceptance. A maintainer must establish the public review continuation and record the actual outcome. See the [WP1 review packet](../verification/infra-automation/16-0/README.md) and [sanitized observation](../verification/infra-automation/16-0/governance.json). Independent human review coverage remains missing.
- Review not before: **2026-10-15T08:06:23Z**; elapsed time alone is not acceptance.
- Decision date: **pending public maintainer decision**.
- Approving maintainers: **none recorded**.
- Outcome rationale: selected bounded planning direction fits the shared evidence core; public review and executable trust-boundary qualification remain outstanding. This is not implementation acceptance or production readiness.
- Follow-up issues, stories, or documentation updates: Story **16.0** owns public RFC acceptance, identity/fencing/isolation/custody/receiver spikes, threat-model/dependency/UX closure and readiness; **16.1–16.19** retain dependencies and production qualification; **12.5** remains release prerequisite, with explicit automation-related **12.7/12.8** coverage. Preserve the existing public PR as publication history and link the maintainer-established review continuation; actual approval/decision and qualification records are still pending.
- Future maintainer constraints: preserve shared scoring/Evidence Law/advisory reports, exact action/plan binding, verified authority, local secrets/custody, no direct apply, current-epoch fail-closed receiver actions and conservative unknown-outcome locks. Any accepted deviation requires updated canonical planning and a new or amended public decision.
