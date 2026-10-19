---
workflowType: prd
workflow: create
version: '0.1'
status: proposed-for-planning-not-implementation-ready
release: v1.6.0
priority: independent-parallel-workstream
canonical_epic: 17
lastEdited: '2026-10-19'
stepsCompleted: [step-c-01-discovery, step-c-02-scope, step-c-03-requirements, step-c-04-complete]
inputDocuments:
  - docs/rfcs/0002-live-environment-grounding.md
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
---

# DeployWhisper Live Environment Grounding — Canonical Feature PRD v0.1

## Executive Summary

**Live Environment Grounding is an independent feature workstream, canonically Epic 17, targeting v1.6.0.** It supplies DeployWhisper's existing analysis core with read-only knowledge of the operator's actual running infrastructure, starting with AWS and extending through a provider-neutral connector contract.

DeployWhisper currently reasons about declared intent — a Terraform plan, a Kubernetes manifest — against a topology graph that a human hand-authored or imported from a point-in-time state file. Grounding replaces that starved context supply with plan-directed, read-only observation of reality, and uses it to produce real blast radius, plan-versus-reality divergence detection, verified recoverability, and grounded environment classification.

The feature is strictly **read-only, local-first, advisory and opt-in**. It introduces no write, apply, destroy, provision or remediate capability, no hosted control plane, and no credential storage. It is an *input* to analysis, not a new output and not an execution tier.

This PRD extends the [parent PRD](prd.md) without replacing any parent requirement ID. New `LEG` IDs are additive. This document is the canonical requirement authority for Epic 17. Adoption of this PRD means planning scope is accepted; it does **not** mean RFC approval, completed feasibility spikes, an approved dependency decision, implemented functionality, or production certification.

## Relationship to Epic 16

Epic 17 is **independent of Epic 16 in both directions**. Neither epic's acceptance depends on the other, and they are intended to proceed concurrently with separate branches, separate module trees and separate test directories. The authoritative conflict analysis is the [boundary and parallelization plan](epic-16-17-boundary-and-parallelization-plan.md).

| Dimension | Epic 16 — Evidence-Gated Infra Automation | Epic 17 — Live Environment Grounding |
| --- | --- | --- |
| Question answered | Who authorized this, and did the exact approved bytes reach delivery? | What is actually running, and will this plan hit what it expects? |
| Data direction | Outbound dispatch | Inbound read-only observation |
| Product posture | Governance, custody, approval integrity | Evidence, context, grounding |
| Owned modules | `infra_automation/`, `services/infra_automation_*` | `cloud/`, `services/cloud_context_service.py` |
| Credentials | Issues grants, runner and receiver tokens | Consumes ambient operator credentials; issues none |
| Can it mutate anything? | Dispatches to an operator-owned external system | **Never** |
| Release lane | v1.5.0 | v1.6.0 |

The single intended integration is **one-directional, optional and presentation-time**: Epic 16's approval inbox may render Epic 17's additive `live_context` report block when both are present. Epic 17 does not reuse Epic 16's runner, enrollment, attempt fencing or receiver protocol, and must not acquire a dependency on them.

## Success Criteria

The feature is accepted only when all of the following hold on the supported profile:

1. A real operator, using existing ambient AWS credentials and the published minimal IAM policy, analyzes a Terraform plan and receives a report whose blast radius is derived from live dependency edges rather than a hand-authored topology.
2. A plan computed against stale reality is detected and surfaced as reviewer-facing evidence **before** a decision, and the same check is enforceable as a CI gate.
3. A destructive change with no restore path is classified `irreversible` with the specific protection attributes that establish it.
4. An unreachable, partially readable or unauthorized cloud context degrades honestly: partial labelled partial, unreadable resources enumerated with the exact missing permission, severity never lowered, confidence never raised.
5. An air-gapped operator achieves identical grounding semantics through an exported and imported snapshot.
6. With grounding disabled, every existing report, fixture, schema, API consumer, CLI output and agent output is unchanged.
7. An independent security review of credential handling and read-only enforcement passes before Story 17.3 merges.
8. A published before/after backtesting delta on the benchmark corpus demonstrates the value claim empirically.

Every requirement below has a named acceptance proof and a canonical story mapping. **No implementation or runtime proof has been produced for this planning document.** Credential handling, read-only enforcement, divergence extraction, and latency/cost bounds are Story 17.0 feasibility gates.

## Product Scope

| Profile | v1.6.0 support contract |
| --- | --- |
| Application | Existing self-hosted FastAPI app, Python-first shared analysis core, React production assets, SQLite and local storage. No new control plane, no new runtime service, no Node runtime. |
| Providers | **AWS supported.** Azure and GCP ship as registered stubs with a documented connector contract and conformance suite, mirroring the existing `cloudformation`/`ansible` topology stubs. |
| Access mode | Read-only, deny-by-default action allow-list. No write, apply, destroy, tag, or remediate capability exists in the codebase. |
| Credentials | Resolved from the operator's ambient chain only. Never persisted, never logged, never returned through the API, never written to a snapshot. |
| Collection scope | Plan-directed selective reflection plus one-hop reverse dependency expansion. **No account-wide inventory.** |
| Resource coverage | Approximately the top twenty-five risk-bearing AWS families, finalized in Story 17.0. Breadth beyond that is a community contribution surface. |
| Evidence | Immutable, redacted, digest-bound, timestamped snapshots entering the existing evidence system as `live_state` with `deterministic` determinism. |
| Network | Direct operator-to-provider calls over HTTPS. Air-gapped operation supported through snapshot export and import. |
| Enablement | Opt-in per project, disabled by default. |

P0 comprises all 40 functional and 12 nonfunctional requirements below. No release date or performance figure is implied; a versioned manifest must freeze supported SDK, provider API and application versions during qualification.

**Explicitly excluded from v1.6.0:** any write or mutate capability; automatic remediation; continuous or scheduled drift monitoring; account-wide inventory; cost estimation; a hosted or multi-tenant collection service; cross-account assume-role chaining beyond the operator's own ambient profile; Kubernetes rework (the existing `kubectl` source is unchanged); and reuse of or dependency on Epic 16 runner, enrollment, fencing or receiver protocols.

## User Journeys

| Journey | Required outcome | Requirement groups |
| --- | --- | --- |
| Reviewer analyzes a Terraform plan for an existing AWS estate | Blast radius derived from live edges, with owners and liveness facts, instead of a "no topology mapping" warning | Reflection, Graph |
| Reviewer receives a plan generated hours earlier | Divergence between recorded prior state and live reality surfaced before the decision | Divergence |
| Reviewer evaluates a destructive change | Verified recoverability with the exact protection attributes and restore path, or an explicit no-restore-path statement | Recoverability |
| Platform engineer gates CI on stale plans | `--fail-on-divergence` fails the pipeline deterministically | Divergence, Surfaces |
| Security engineer reviews what DeployWhisper will do | Dry-run enumerates exact API calls without credentials; published minimal IAM policy | Credentials and safety |
| Restricted-network operator | Collect on a connected host, analyze on a disconnected host, identical semantics | Portability |
| Contributor adds Azure or GCP | Implements the connector contract and passes the conformance suite without touching core analysis | Extensibility |
| Operator without cloud access | Product behaves exactly as today; nothing degrades, nothing is implied | Fail-safe, Compatibility |

## Functional Requirements

### Connector framework and snapshot model

| ID | Requirement |
| --- | --- |
| LEG-FR-001 | Provide a provider-neutral read-only cloud connector contract and registry, mirroring `parsers/registry.py` and `TOPOLOGY_SOURCE_REGISTRY`, so a provider can be added without modifying core analysis. Unregistered and unimplemented providers fail explicitly and never silently no-op into a successful result. |
| LEG-FR-002 | Produce an immutable `LiveContextSnapshot` recording provider, account/subscription/project scope, region set, read window start and end, per-resource read status, the exact set of API actions issued, and a content digest. |
| LEG-FR-003 | Persist the snapshot as project-scoped evidence using a new `EvidenceSourceType` member `live_state` with `DeterminismLevel = "deterministic"`. Evidence Law applies unchanged; a grounded claim without a retained snapshot reference is invalid. |
| LEG-FR-004 | Redact every snapshot through `services/content_security.py` before persistence. No secret values, credential material, user data, raw state or plan bytes may be stored. Account identifiers must be maskable by configuration. |
| LEG-FR-005 | Integrate snapshot freshness into `ContextSourceMetadata` using the existing `current`/`stale`/`missing`/`incomplete`/`conflicting`/`unknown` vocabulary. Do not introduce a parallel freshness vocabulary. |
| LEG-FR-006 | Label partial reads as partial and enumerate every unreadable resource with the exact missing permission or failure cause. Completeness must never be implied from a partial read. |
| LEG-FR-007 | Make grounding opt-in per project and disabled by default. No cloud call may be issued for a project that has not explicitly enabled a configured connector. |

### Credentials, safety and bounded execution

| ID | Requirement |
| --- | --- |
| LEG-FR-008 | Resolve credentials exclusively from the operator's ambient provider chain. Never persist, log, echo through the API, include in a snapshot, or accept credentials as request parameters. |
| LEG-FR-009 | Enforce read-only access through a deny-by-default action allow-list evaluated before any call is constructed, backed by a published minimal IAM policy covering exactly the allow-listed actions. |
| LEG-FR-010 | Provide a dry-run mode that enumerates the exact API calls that would be issued for a given plan **without resolving or using credentials**. |
| LEG-FR-011 | Constrain connector configuration so caller-supplied values cannot retarget the client at an arbitrary endpoint, host, role or account. Endpoints resolve only through provider-canonical resolution. |
| LEG-FR-012 | Bound every collection with a per-call timeout, total deadline, concurrency cap, call budget and backoff, support cancellation, and report the actual call count and elapsed time with the result. |

### Plan-directed reflection

| ID | Requirement |
| --- | --- |
| LEG-FR-013 | Extract a `ResourceIdentity` set from parsed artifacts, including recorded prior state, resource addresses, physical identifiers, ARNs, names and tags, without issuing any call. |
| LEG-FR-014 | Resolve identities that have no physical counterpart — for example pure creates — as `no_live_counterpart` rather than as a failure or an unreadable resource. |
| LEG-FR-015 | Read only the resources the plan touches. Account-wide or region-wide enumeration is prohibited, and a connector that performs it fails conformance. |
| LEG-FR-016 | Expand exactly one reverse hop to discover what currently references the touched resources, with an explicit bound and a recorded reason for each expansion. |

### Plan-versus-reality divergence

| ID | Requirement |
| --- | --- |
| LEG-FR-017 | Compare recorded plan prior state against live state for every touched resource and classify each as `match`, `diverged`, `unknown` or `unreadable`. |
| LEG-FR-018 | Emit a `plan_reality_divergence` finding carrying per-attribute recorded, live and planned values, linked to the snapshot digest and the specific resource. |
| LEG-FR-019 | Compute and surface plan freshness as the interval between plan generation and live read, and flag plans older than a configured threshold. |
| LEG-FR-020 | Establish a severity floor for divergence on security-relevant or destructive attributes and force at least a `caution` recommendation. A reason, acknowledgement or narrative must not clear a divergence floor. |
| LEG-FR-021 | Expose divergence as a deterministic CI gate through CLI and API (`--fail-on-divergence`), with a distinct documented exit code, usable without the web UI. |

### Live dependency graph and grounded blast radius

| ID | Requirement |
| --- | --- |
| LEG-FR-022 | Build real dependency edges from live reads for the supported resource families, including security-group references, load-balancer to target-group to instance paths, DNS to load-balancer paths, IAM trust relationships, event-source mappings and database replica topology. |
| LEG-FR-023 | Register an `aws` handler in `TOPOLOGY_SOURCE_REGISTRY` producing a live-derived topology change set compatible with the existing topology payload contract and import metadata. |
| LEG-FR-024 | Consume live edges in `compute_blast_radius` so grounded resources match, while genuinely unmatched resources remain explicitly reported. Grounding must never conceal an unmatched resource. |
| LEG-FR-025 | Derive ownership signals from live tags and feed `ownership_service` as an additional source. Live tags must not override CODEOWNERS or declared ownership; conflicts are surfaced, not resolved silently. |
| LEG-FR-026 | Attach liveness facts to blast-radius nodes, including running instance count, availability-zone spread and last observed activity where available, each carrying its own freshness and source. |

### Recoverability

| ID | Requirement |
| --- | --- |
| LEG-FR-027 | Collect protection and recoverability attributes for destructive changes, including deletion protection, final-snapshot behaviour, automated backup configuration and recovery-point age, object versioning, MFA delete, termination protection and most recent snapshot age. |
| LEG-FR-028 | Classify each destructive change as `recoverable`, `recoverable_with_loss`, `irreversible` or `unknown`, citing the specific attributes that establish the classification. |
| LEG-FR-029 | Consume recoverability facts in `rollback_planner`, replacing complexity signalling with verified guidance and producing an explicit no-restore-path statement for `irreversible`. |
| LEG-FR-030 | Never present `unknown` recoverability as recoverable, and never allow absent data to improve a recoverability classification. |

### Grounded environment classification

| ID | Requirement |
| --- | --- |
| LEG-FR-031 | Ground environment classification in the real account, live tags and network placement rather than name heuristics, and surface disagreement between declared and live classification as `conflicting` rather than silently preferring one. |

### Portability and air-gapped operation

| ID | Requirement |
| --- | --- |
| LEG-FR-032 | Support snapshot export and import as digest-bound files carrying provenance, with imported snapshots explicitly labelled `imported` and subject to an age check. |
| LEG-FR-033 | Produce identical grounding semantics from an imported snapshot as from a live read, so restricted-network operators receive equivalent evidence without connectivity. |

### Surfaces

| ID | Requirement |
| --- | --- |
| LEG-FR-034 | Add an optional, separately versioned `live_context` block (`live_context_version: 1`) to the report API without bumping the report schema version, preserving every existing consumer and fixture. |
| LEG-FR-035 | Provide a React Live Context tab on the report screen showing the grounding banner, divergence panel, live blast radius, recoverability table and the unreadable-resource list with actionable permission remedies, using existing design primitives and without changing the Dashboard information budget. |
| LEG-FR-036 | Provide a project-scoped Settings surface for connector configuration showing the credential source but never the secret, with test-connection, dry-run preview and a copyable minimal IAM policy. |
| LEG-FR-037 | Provide CLI grounding commands and flags using the same API authority and the same read-only enforcement as the web surface, including dry-run, snapshot export and import, and the divergence gate. |
| LEG-FR-038 | Expose grounded facts through the existing agent and MCP-compatible interface with explicit determinism and freshness labels, so agent consumers cannot present grounded and inferred claims as equivalent. |

### Extensibility

| ID | Requirement |
| --- | --- |
| LEG-FR-039 | Ship Azure and GCP as registered stubs that fail explicitly and identically to the existing unimplemented topology sources, with no partial or misleading behaviour. |
| LEG-FR-040 | Publish a connector contributor guide and an executable provider conformance suite covering read-only enforcement, bounded execution, honest degradation, redaction and snapshot shape, so a community provider can be validated without maintainer-specific knowledge. |

## Nonfunctional Requirements

| ID | Requirement | Verification |
| --- | --- | --- |
| LEG-NFR-001 | The read-only guarantee must be mechanically enforced. Every allow-listed action is asserted non-mutating by an automated test; introducing a mutating verb fails CI. | Allow-list verb assertion and mutation-attempt corpus |
| LEG-NFR-002 | No credential material may be persisted, logged, echoed or serialized anywhere. | Secret-corpus regression across logs, snapshots, API responses and CLI output |
| LEG-NFR-003 | Collection must be bounded and interruptible, returning partial labelled results within the total deadline and never blocking the analysis path indefinitely. | Deadline, cancellation and slow-provider fault injection |
| LEG-NFR-004 | Grounding must be fail-safe: an unreachable, partial, throttled or unauthorized context never lowers severity and never raises confidence, and triggers `insufficient_context`. | Degradation matrix across unreachable, partial, denied, throttled and expired cases |
| LEG-NFR-005 | Access must be minimal-privilege, with a published policy covering only allow-listed actions and a documented per-capability permission map. | Policy-to-allow-list equivalence test and per-capability denial tests |
| LEG-NFR-006 | Snapshots must be deterministic and auditable: the same observation yields the same digest, and every grounded claim references its snapshot digest. | Digest reproducibility and evidence-linkage tests |
| LEG-NFR-007 | The feature must remain local-first: all calls are direct operator-to-provider with no DeployWhisper-hosted or third-party intermediary. | Egress inspection in the composed app |
| LEG-NFR-008 | New React routes must pass the composed-app axe critical and serious gate and keyboard-only journeys using real API-backed seeded data at 1440 and 760 widths. | Compose production build, Playwright, axe and screenshots |
| LEG-NFR-009 | With grounding disabled, all existing reports, fixtures, schemas, API consumers, CLI output and agent output must be unchanged. | Full existing suite plus legacy consumer contract tests with the feature off |
| LEG-NFR-010 | A new provider must be addable without modifying core analysis, scoring, blast radius or report code. | Conformance suite executed against a reference stub provider |
| LEG-NFR-011 | Air-gapped operators must achieve grounding parity through snapshot import. | Disconnected-host equivalence exercise |
| LEG-NFR-012 | Call count, elapsed time and budget consumption must be visible to the operator for every collection. | Budget reporting assertions in API, CLI and UI |

## Requirement to Story Mapping

| Story | Owned requirements |
| --- | --- |
| 17.0 Adopt and qualify the grounding contract | Verifies LEG-FR-009, LEG-FR-010, LEG-NFR-001, LEG-NFR-003, LEG-NFR-005 by executable spike; owns the dependency decision and the unresolved questions |
| 17.1 Connector contract, registry and snapshot evidence | LEG-FR-001–007; LEG-NFR-006, LEG-NFR-009, LEG-NFR-010 |
| 17.2 AWS read-only session, allow-list and dry-run | LEG-FR-008–012; LEG-NFR-001, LEG-NFR-002, LEG-NFR-005, LEG-NFR-007 |
| 17.3 Plan-directed reflection and bounded collection | LEG-FR-013–016; LEG-NFR-003, LEG-NFR-004, LEG-NFR-012 |
| 17.4 Divergence detection and CI gate | LEG-FR-017–021; LEG-NFR-004 |
| 17.5 Live dependency graph and grounded blast radius | LEG-FR-022–026, LEG-FR-031 |
| 17.6 Grounded recoverability and rollback | LEG-FR-027–030 |
| 17.7 Snapshot portability and air-gapped grounding | LEG-FR-032, LEG-FR-033; LEG-NFR-011 |
| 17.8 Live context UI | LEG-FR-034–036; LEG-NFR-008 |
| 17.9 Extensibility, CLI/agent surfaces and qualification | LEG-FR-037–040; LEG-NFR-010, and release-wide verification of all NFRs |

Mapping expresses acceptance obligation, not implementation evidence. Release-wide proof of every requirement is owned by Story 17.9.

## Out of Scope and Deferred

Deferred to a later separately authorized workstream: additional providers beyond the shipped AWS connector; additional AWS resource families beyond the qualified set; cost estimation or Infracost integration; scheduled or continuous drift monitoring; cross-account role chaining; live Kubernetes rework; automatic topology inference; AI-assisted interpretation of grounded facts; and any write capability whatsoever.

Any future change to the read-only boundary requires a separate RFC and explicit product authorization. It must never be introduced as a later-story assumption.
