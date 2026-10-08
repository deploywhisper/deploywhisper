---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments:
  - docs/deploywhisper-infra-automation-prd.md
  - _bmad-output/project-context.md
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/planning-artifacts/epics.md
  - _bmad-output/implementation-artifacts/sprint-status.yaml
workflowType: research
lastStep: 6
research_type: technical
research_topic: DeployWhisper infrastructure automation and Kestra comparison
research_goals: Evaluate product fit, architecture, security, bounded v1.5.0 scope, and delivery sequencing
user_name: psaho01
date: 2026-10-07
web_research_enabled: true
source_verification: true
status: complete
decision_status: planning-recommendation-not-approved
---

# Infrastructure automation for DeployWhisper: technical research

## Executive assessment

An evidence-gated infrastructure preflight capability is a strong adjacent feature for DeployWhisper. It can remove the manual gap between obtaining infrastructure artifacts, analyzing them, recording a human decision, and handing an approved change to the operator's delivery system. The submitted PRD has the right differentiator: evidence-bound decisions through the existing analysis core. Its combined Phase A/B scope is too broad for a credible production-ready v1.5.0 commitment.

Recommend a native, bounded Tier 0/Tier 1 subsystem: uploaded artifacts or isolated OpenTofu/Terraform collection, deterministic analysis, durable human decisions, and controlled external handoff. Exclude direct apply and generalized task execution. Leave deployment ordering, execution and rollback ownership with the external delivery system. Prioritize this as new Epic 16 without rewriting released story identities. Preserve Story 12.5's SBOM work as a release prerequisite.

This document completes research only. It is a planning recommendation, not implementation readiness, an approved architecture, a release certification, or a promise that the full original vision fits one release. The release plan must explicitly choose the supported v1.5 contract before development stories are marked ready.

## 1. Method and scope

The user supplied the topic, comparison target, release priority and desired implementation outcome; these establish scope without another discovery interview. Research combines current official Kestra and tool documentation with direct inspection of DeployWhisper services, API routes, database setup, evidence models, parser registry and application lifecycle. Vendor facts below are cited; proposed DeployWhisper controls and scope choices are recommendations derived from that evidence.

Local evidence uses repository-relative paths and line references from the inspected snapshot. These references can move after editing. The reconciled baseline is 101 existing stories: 84 done, 15 ready-for-dev and two review. Stories 12.3, 12.4, 12.6 and 13.8 are done; v1.4.0 is released. The submitted PRD's assumptions about open prerequisites and a future v1.4.0 Phase A therefore need correction.

The audit did not run a Kestra installation, real cloud planning/apply, customer interviews, load benchmarks or failure-injection tests. It cannot validate product demand, delivery estimates, tool compatibility or production readiness experimentally. Confidence is high on inspected code gaps and documented product capabilities, moderate on recommended scope, and unmeasured on throughput and calendar feasibility.

## 2. Kestra comparison: useful patterns, different product boundary

Kestra's infrastructure offering spans provisioning, plan/apply workflows, approval and drift-related automation. DeployWhisper should adopt the orchestration patterns that make its own preflight decision useful, while preserving its specialized risk-analysis role. Similar user outcomes do not require comparable breadth. [Kestra Infrastructure Automation](https://kestra.io/infra-automation)

| Capability | Verified vendor behavior | Recommended DeployWhisper treatment |
|---|---|---|
| Tool orchestration | Infrastructure examples connect existing infrastructure tooling into workflows. | Adopt a closed preflight collector catalog; retain external execution ownership. |
| Durable pause and decisions | Pause can survive restart; the richer HumanTask mechanism is an Enterprise capability. | Adopt durable evidence-bound decisions in the native product; distinguish authenticated approval from single-operator acknowledgement. [Approval processes](https://kestra.io/docs/use-cases/approval-processes) |
| Workflow revisions | Drafts do not execute; revisions support inspection, differences and rollback. | Adopt immutable published revisions and pinned run snapshots; restoring a definition does not reverse an external deployment. [Revisions](https://kestra.io/docs/concepts/revision) |
| Worker routing | Enterprise worker groups support tag selection; ALL and FAIL are defaults. IGNORE permits relaxed routing; the OSS default worker pool differs. | Adopt strict all-of matching and fail-closed routing. Do not claim Kestra worker groups are a universal OSS capability, or implement a fallback that silently broadens privileged runner selection. [Worker groups](https://kestra.io/docs/enterprise/scalability/worker-group) |
| Audit | The referenced governance audit-log offering is Enterprise. | Build scoped automation audit as a native control; distinguish append-only application APIs from protection against database-admin tampering. [Audit logs](https://kestra.io/docs/enterprise/governance/audit-logs) |
| Distributed runtime | Architecture separates repository, queue and storage; deployment options vary by edition/backend. | Adopt durable state and queue semantics, simplify deployment to the existing app/database baseline. [Main components](https://kestra.io/docs/architecture/main-components), [Deployment architecture](https://kestra.io/docs/architecture/deployment-architecture) |
| Copilot | Edit, Ask and Plan patterns include confirmation around modifications. | Defer AI composition; if added, produce validated drafts without publishing, approving or dispatching. [AI Copilot](https://kestra.io/docs/ai-tools/ai-copilot) |
| Provision/apply/drift and broad plugins | The infrastructure offering includes wider execution-oriented use cases. | Direct mutation, generalized plugins, unattended remediation and comprehensive drift stay outside v1.5 P0. Uploaded supported artifacts can still be analyzed. |

The value proposition should be concrete: “collect evidence, explain risk, record a decision against that evidence, and hand off the exact approved change.” Positioning as a smaller general workflow platform would increase operational obligations while weakening the existing differentiator.

## 3. Product and PRD fit

The existing architecture explicitly preserves one shared analysis core and separates optional enforcement adapters from advisory report semantics (`architecture.md:74`, `:84`, `:1086`). New workflow gates can stop an automation run without rewriting a canonical report into a deployment authorization. This boundary requires an explicit PRD amendment describing preflight orchestration and external handoff; Tier 2 execution remains a separate RFC/ADR decision.

The submitted document usefully specifies immutable revisions, constrained templates, evidence pinning, local credentials, an outbound runner, fail-closed expiry and uncertainty. Its weaknesses are release scope, optimistic reuse assumptions and several security details hidden behind words such as “read-only,” “idempotent” and “human.” Phase A/B together introduce identity, a durable engine, remote agents, collectors, approvals, integrations, inventory, graph planning, package governance, promotion, schedules, AI and operational scaling. That is a platform roadmap rather than one qualified release increment.

Define v1.5 production readiness for a declared support matrix: uploaded existing artifact formats, OpenTofu/Terraform collection, explicit manually declared multi-unit preflight, one controlled GitHub dispatch adapter, and a signed inbound trigger contract and GitHub receiver reference implementation/test double. Do not advertise unsupported collection formats or end-to-end deployment guarantees. Multi-unit preflight may collect/analyze an explicit group, but it does not infer or execute estate deployment stages.

## 4. Existing architecture: reusable code and actual gaps

| Repository evidence | Reuse or constraint |
|---|---|
| `services/analysis_service.py:2663` | `analyze_uploaded_files()` resolves scope, builds analysis and persists reports with workspace/audit context. Invoke it through a service adapter; avoid duplicate scoring and self-HTTP calls. It is synchronous and must run outside the engine tick with bounded concurrency. |
| `services/project_service.py:93`, `:264`, `:686`, `:790` | Reuse project/workspace resolution and permission vocabulary. Current role names are admin, maintainer, reviewer, contributor and read-only; map proposed roles deliberately. |
| `services/policy_adapter_service.py:27`, `:60`, `:80` | Reuse the separate integration-decision model and configured policy ceiling; keep workflow state distinct from advisory report output. |
| `services/intake_service.py:117`, `:150`, `:319`, `:365` | Reuse traversal handling, trusted artifact path checks, sensitive-file blocking and intake classification for runner uploads. |
| `services/content_security.py:286`, `:602`, `:634` | Reuse text/value credential screening and Terraform/Kubernetes-sensitive-value detection; expand the corpus to automation credentials and streamed outputs. |
| `services/artifact_snapshot_service.py:75`, `:110` | Reuse local-storage conventions. Snapshot content can become a blocked marker, so existing stored bytes cannot silently stand for the original collected digest. |
| `services/scanner_import_service.py:237`, `:268` | Reuse SARIF/Semgrep import; imported scanner evidence remains external evidence. |
| `llm/providers.py:187` | Reuse provider selection, local mode, screening and timeout boundary. JSON-output requests do not establish universally enforced IR schemas; validate returned data in application code. |
| `integrations/github/app_service.py:284`, `:995`, `:1088`, `:1130` | Reuse webhook-signature ideas, installation-token acquisition and constrained authenticated requests. Arbitrary webhook SSRF defense needs a stronger separate outbound-client contract. |
| `app.py:75`, `:99` | Reuse lifecycle startup/shutdown wiring. Existing maintenance polling is not a durable job engine or leader election mechanism. |
| `models/database.py:34`, `:76`, `:99` | Reuse SQLAlchemy sessions, foreign-key setup and additive Alembic migration conventions. No reusable fenced task/leader lease was found. |
| `parsers/registry.py:20`, `:60`, `:114` | Existing Terraform plan and Kubernetes/Ansible source parsers are useful. Ansible check events and unified kubectl diff output need dedicated adapters; Helm-rendered manifests can feed Kubernetes parsing once supported/tested. |

### Identity is a release-blocking prerequisite

`api/routes/projects.py:43–56` and `api/routes/analyses.py:232–244` accept role/project scope directly from request headers. `services/project_service.py:237–239` defaults missing role to admin. `api/dependencies.py:1` is a placeholder; actor metadata at `api/routes/analyses.py:838` is caller-supplied. Inspection did not find a persisted authenticated user/session/membership subsystem.

These are authorization primitives, not verified identity. Production decisions require an authenticated principal, project membership and separate human, service and runner credential types. A single-operator mode must still authenticate the operator; naming a request “human” does not prevent automation self-approval. Separation of duties needs distinct verified identities and cannot be advertised in acknowledgement-only mode.

## 5. Architecture options and recommended baseline

| Option | Benefit | Cost / conclusion |
|---|---|---|
| Native bounded domain subsystem | Fits Python, shared core, local storage and project semantics; owns evidence-specific decisions. | New durability/security work remains substantial. Recommended for the bounded support matrix. |
| Embed Kestra | Mature general orchestration capabilities. | Adds a second runtime/control plane, storage/deployment concerns, identity integration and edition-sensitive feature dependencies. Poor baseline fit for the current lightweight product. |
| External Kestra/CI integration only | Keeps execution ownership outside DeployWhisper and limits engine scope. | Less integrated UX, but valuable interoperability path. Offer report/intake/handoff contracts, not mandatory Kestra deployment. |
| Build broad Kestra-like platform | One product owns everything. | Greatest scope and credential blast radius; reject for v1.5. |

Recommended structure: `infra_automation/` owns schemas, validators, state transitions and closed step handlers; services own scope/orchestration facades; API/CLI/UI remain adapters. Published definitions and run snapshots are immutable. Resolve templates by substitution only. A database-backed scheduler persists transitions and an outbound-intent outbox; bounded workers perform analysis/network work. The runner independently validates each task against an operator-controlled catalog.

SQLite remains suitable for a qualified one-app-instance baseline with short transactions and explicit operating limits; WAL still has one writer. PostgreSQL supports row-locking queue patterns such as SKIP LOCKED but does not itself solve ownership, retries or external delivery ambiguity. These facts motivate benchmarked support profiles, not an assumed throughput claim. [SQLite WAL](https://www.sqlite.org/wal.html), [PostgreSQL SELECT](https://www.postgresql.org/docs/current/sql-select.html)

FastAPI's ordinary background-task hook is useful lifecycle machinery, not a substitute for the proposed persisted job/lease design. Recovery must come from domain state stored before side effects. [FastAPI background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)

## 6. High-impact security and durability amendments

### Collection is privileged execution, even without apply

Section 11.4's fixed argv is useful but cannot prove non-mutation. Terraform external data sources execute programs during refresh and inherit environment variables; Ansible tasks can opt out of check mode. A saved Terraform plan can contain cleartext sensitive values. Consequently, “read-only” describes intended workflow behavior, not sandbox enforcement. [External data source](https://raw.githubusercontent.com/hashicorp/terraform-provider-external/main/docs/data-sources/external.md), [Ansible check mode](https://raw.githubusercontent.com/ansible/ansible-documentation/devel/docs/docsite/rst/playbook_guide/playbooks_checkmode.rst), [Terraform plan](https://developer.hashicorp.com/terraform/cli/commands/plan)

Require immutable source SHA, trusted-source admission, isolated disposable workspaces, controlled tool/provider installation, least-privilege planning credentials, bounded egress/process/time/disk resources, environment allow-listing and no automatic hooks. The proposed path regex allows `../`; validate resolved paths against configured roots and reject symlink escapes, dangerous Git configuration and option-like arguments. Never transport binary plans/state to the server. Document unsupported behaviors rather than claiming every provider is side-effect-free.

Prefer operator-installed OpenTofu/Terraform for containment and supportability. OpenTofu's MPL-2.0 license and HashiCorp's use-dependent licensing terms differ; the PRD should not claim that an MIT project universally cannot distribute Terraform. Distribution decisions need a specific terms review. [OpenTofu license](https://github.com/opentofu/opentofu/blob/main/LICENSE), [HashiCorp licensing FAQ](https://www.hashicorp.com/en/license-faq), [FAQ clarification](https://www.hashicorp.com/en/blog/hashicorp-updates-licensing-faq-based-on-community-questions)

### Durable tasks and external effects

Leader/task leases need monotonic fencing or equivalent attempt ownership. Every heartbeat, upload, log and completion must verify runner, project, current attempt and lease; reject stale worker results. Acquire claims atomically. Persist approval decisions and state transitions using compare-and-swap/transaction controls so concurrent requests cannot release two handoffs.

An idempotency key is not a universal exactly-once guarantee. A dispatch can succeed upstream while its response is lost. Use durable outbox intents and receiver-specific deduplication/reconciliation. Unsupported receivers must pause as `delivery_unknown` after ambiguous outcomes, requiring recovery rather than blind retry. Cancellation after accepted handoff cannot undo the external operation.

The current GitHub workflow API requires a branch/tag dispatch ref; the referenced 2026-03-10 contract returns workflow-run identifiers. DeployWhisper's existing client pins 2022-11-28. Version the new adapter explicitly and test its actual response contract; do not assume either historical 204 behavior or current 200 behavior for every API version. Pin the approved source SHA inside the downstream verification contract even where dispatch itself uses a branch/tag. [GitHub workflow API](https://docs.github.com/en/rest/actions/workflows)

### Approval, evidence and handoff binding

The Section 10.6 approval-ancestor rule is insufficient alone: the ancestor may approve different evidence or target. Bind each decision to workflow revision, source SHA, project/workspace/environment, report/artifact digest, policy version and exact handoff target/payload. Every mandatory ancestor must succeed; skipped/expired/cancelled approval cannot qualify. Recheck identity, pins, freshness and target immediately before dispatch.

Example A approves a collected ref but dispatches an apply workflow on `main`. Require the external receiver to verify the approved commit and exact plan/evidence digest. Replanning or substitution requires fresh analysis/decision. Define handoff success as accepted delivery unless downstream completion is independently observed; do not label it successful deployment. The saved binary plan remains in an operator-controlled trusted custody store accessible by the qualified self-hosted receiver, with opaque handle, raw digest, expiry and storage protections. A cloud-hosted receiver cannot recover those bytes from sanitized JSON; replanning demands a fresh decision. Grant consumption must create a durable operation record, so a crash before action reconciles the same operation rather than generating another one. Disable/revocation/restore epoch changes prevent outstanding grants from starting new side effects while reconciliation continues.

Specify runner-local raw digest versus transported sanitized digest and redaction version. Recompute received hashes server-side; use atomic file writes, bounded uploads/chunks, cleanup on failure, retention compatible with pending decisions, protected permissions and backup/restore consistency. Authenticated provenance does not prove truthful output from a compromised runner.

Story 16.14 in the submitted PRD conflates complete provenance with deterministic evidence. Determinism comes from supported extraction semantics/rules. `evidence/models.py:33–45` lacks `automation_collection`; either retain artifact source with added provenance or deliberately extend models/migrations/serializers and all constructor fixtures. Never promote model-inferred output solely because collection metadata is complete.

The draft's automatic minor report-schema bump also assumes a lifecycle the code does not currently expose. `services/report_service.py:102–103` names v1/v2 contracts, with major-oriented compatibility. Prefer a separately versioned optional automation-provenance block and run-to-report relationship. Choose a compatible additive v2 change or deliberate v3 only after contract review; do not invent minor-version behavior without updating consumers and tests.

### Outbound, audit and operations

Enforce outbound destination policy after DNS resolution and on connection, including IPv4/IPv6, metadata/private/loopback addresses and redirect handling; define deliberate internal-host exceptions. Disable credential forwarding on redirects, cap responses and revalidate targets at dispatch. Verify inbound HMAC over raw bytes, enforce timestamps/replay protection and rate limits.

Make target locks and bounded concurrency P0 before handoff, even with manual units. Define restart/deadline handling, shutdown, clock policy, revocation mid-run, process-tree termination, lock TTL/renewal and audited lock breaks. Append-only API methods do not protect against DB administrators; document audit trust and export integrity honestly. Pending evidence deletion should invalidate approval or be disallowed until resolution.

Back up database state and artifact metadata/content consistently; copying a live database file is not an adequate recovery specification. Restore must invalidate outstanding grants, leases and delivery assumptions until reconciled, so replaying an old snapshot cannot release a previously consumed approval or duplicate an external operation.

## 7. Scope and sequencing recommendation

Use Epic 16 as the highest-priority v1.5 feature. Story identity should describe its epic, not release ordering: renaming Story 12.5 would mix automation into the existing hardening epic and damage traceability. Keep released records stable and move deferred work by priority/release fields. Complete 12.5 SBOM as a qualification dependency for new server/runner artifacts.

These are capability work packages, not canonical story numbers. The authoritative proposed breakdown is the companion [v1.5.0 release plan](../infra-automation-v1.5.0-release-plan.md), which splits backend, UI and security work into reviewable stories.

| P0 work package | Outcome / dependency |
|---|---|
| Scope and ADRs | Amend canonical posture; approve support matrix, acceptance boundaries and external execution ownership. |
| Verified identity | Human/service/runner principals, memberships, authorization and acknowledgement-mode contract. |
| Schemas and revisions | Closed registry, strict validators, immutable published revision and input/output contracts. |
| Durable engine | Atomic transitions, fenced claims, restart recovery and bounded workers. |
| Uploaded-artifact vertical slice | Intake → shared analysis → report-linked run; first deterministic end-to-end proof. |
| Evidence-bound decisions | Expiry, rejection, concurrency, separation of duties and exact pin validation. |
| Controlled handoff | Outbox, SSRF controls, explicit API version and downstream digest verification. |
| Runner lifecycle | Scoped enrollment/rotation/revocation, strict routing, attempt ownership and protocol negotiation. |
| Hardened OpenTofu/Terraform collector | Isolated immutable checkout, least-privilege collection and sanitized artifact integrity. |
| Manual multi-unit preflight | Explicit unit groups/dependencies and scoped target locking; no automatic estate deployment ordering. |
| Triggers and CLI | Signed/replay-resistant webhook plus authenticated manual/CLI execution; human decisions stay explicit. |
| Operations | Retention, recovery, metrics, quotas, backup/restore and operator runbooks. |
| Qualification | Security/fault tests, composed-browser validation, release artifacts and signed support-matrix results. |

Sequence the uploaded-artifact proof before remote collectors; prove decision integrity before enabling external handoff; qualify runners before connecting privileged infrastructure. UI and backend increments follow existing PR boundaries. Existing artifact uploads remain supported; native Ansible/kubectl/Helm collectors are outside P0. AI composer, packages and read-only drift are post-v1.5 candidates, while inferred estate planning, promotion, broad adapters and Tier 2 remain later roadmap.

## 8. Validation and decision gates

No effort estimate is defensible from story count alone. Identity, engine recovery, runner isolation and receiver enforcement require implementation spikes and qualification evidence. Do not commit a release date before these are sized.

Release blockers should include cross-project/principal authorization, stale/duplicate approval races, restart recovery, stale lease result rejection, ambiguous dispatch recovery, substituted commit/plan rejection, secret leakage, collector containment, artifact limits and retention, supported tool compatibility, and migration/backup recovery. Include receiver and runner test doubles, real supported-tool integration tests, fault injection around every persisted external intent, and composed-app Playwright/a11y/keyboard checks. Exercise the full CI test directories; root unittest discovery is only smoke coverage.

Operational acceptance must publish tested concurrency and resource limits, supported database profile, runner/server versions, tool/version matrix, cancellation semantics, recovery steps and deployment ownership. AI safety rates should not be release criteria for features intentionally deferred; when AI is introduced, measure them against a declared corpus rather than claiming universal zero-risk behavior.

Before implementation, translate these findings into PRD/architecture amendments, UX contracts and dependency-linked stories; update traceability and run BMad implementation-readiness review. Current research supports proceeding to that planning work. It does not mark any new story implemented or production-ready.
