# RFC 0002: Live Environment Grounding

- **Status:** Proposed
- **Created:** 2026-10-19
- **Epic:** 17
- **Target release:** v1.6.0 (independent of the v1.5.0 Epic 16 lane)
- **Supersedes:** nothing
- **Depends on:** nothing in Epic 16

## Summary

Introduce Epic 17 as a **read-only, plan-directed cloud context provider** that grounds DeployWhisper's existing analysis in the operator's actual running environment, starting with AWS and extending through a provider-neutral connector contract.

DeployWhisper today reasons about *declared intent* — a Terraform plan, a Kubernetes manifest — against a topology graph that a human hand-authored or imported from a point-in-time state file. It has no knowledge of what is actually running. This RFC proposes to supply that missing input while preserving every existing product boundary: local-first, advisory-only, self-hosted, no hosted control plane, and **no write, apply, destroy, provision or remediate capability of any kind**.

The feature is strictly read-only. It is an *input* to analysis, not a new output, and not an execution tier.

## Motivation

### The measurable gap

DeployWhisper's flagship claim is that "the real risk often appears only when artifacts are reviewed together." That claim is implemented in `analysis/blast_radius.py`, which walks a topology graph. The graph is populated by `TOPOLOGY_SOURCE_REGISTRY` in `services/topology_service.py`:

| Source | State |
| --- | --- |
| `custom` | Hand-authored by an operator; immediately begins aging |
| `terraform` | Parsed from a state file; point-in-time, no freshness relationship to the plan under review |
| `kubernetes` | **Live** via `kubectl`, deadline-bounded, degrades honestly |
| `cloudformation` | Registered stub, connector not implemented |
| `ansible` | Registered stub, connector not implemented |

There is no cloud provider source at all. `boto3` is not a dependency of this repository. The consequence is visible in the analysis path:

```python
# analysis/blast_radius.py
if not matched_service_ids:
    unmatched_resources.append(change.resource_id)
...
missing_context_warning = (
    f"Blast radius may be incomplete — no topology mapping found for: {unmatched_summary}."
)
```

For a Terraform plan targeting AWS, with no hand-authored topology, **every changed resource falls into `unmatched_resources`** and the differentiating capability degrades to a warning string.

The same starvation affects the rest of the pipeline:

- `analysis/risk_scorer.py` severity derives from `ACTION_BASE_SEVERITY` × `CATEGORY_BASE_SEVERITY`. It knows `destroy` + `data/service` is high. It cannot know that *this* database is production, carries 400 GB, has three read replicas, and is configured with `skip_final_snapshot = true`.
- `analysis/rollback_planner.py` emits complexity signalling, not verified recoverability.
- `analysis/env_classifier.py` infers environment from names and declared tags rather than from the live account.
- `evidence/models.py` classifies most context as `heuristic` or `inferred`; `deterministic` is reserved for facts, and live reads are facts.

### Why this matters now

Epic 16 is building identity, durable approvals, isolated runners, exact-plan custody and a qualified GitHub receiver. That work is valuable and should continue. But governance amplifies evidence quality; it cannot substitute for it. If the briefing an approver reads still says *"no topology mapping found for 47 resources,"* Epic 16 produces a rigorous, auditable, **ceremonial** approval.

Live Environment Grounding supplies the evidence that makes that approval mean something. The two epics are complementary and, as described in §"Relationship to Epic 16", independently deliverable.

### Prior art and why a new design is warranted

- **`terraform plan`/`refresh`** detects divergence between recorded state and reality, but does so silently, inside the apply path, *after* a human has already approved a diff. It is not reviewer-facing evidence.
- **Drift tools** (driftctl — archived, Prowler, CloudQuery, Steampipe) answer "is my estate drifted?" on a schedule. They are estate-wide and asynchronous. They do not answer "is *this pending plan* about to hit something it does not expect?"
- **Atlantis / Terraform Cloud / Spacelift / env0** gate applies but own the run and the state. They do not surface live grounding as independent review evidence, and they require ceding execution.
- **Infracost** is the correct comparison for scope discipline: narrow, read-only, excellent, and something DeployWhisper should integrate with rather than rebuild.

No existing open-source tool surfaces **plan-versus-reality divergence as reviewer-facing evidence at decision time**. That is the novel contribution here, and it is directly aligned with the project's Evidence Law posture.

## Detailed Design

### Core design decision: plan-directed selective reflection

The connector **must not** inventory the account. Account-wide scanning is slow, expensive, requires sprawling IAM grants, and is precisely what makes competing tools operationally unpopular.

Instead:

```text
Parsed artifacts (UnifiedChange + plan before/prior state)
  → extract ResourceIdentity set (ARNs, physical ids, names, tags)
  → bounded, concurrent, deadline-capped read-only describe/get calls
  → one-hop reverse expansion: what actually references these resources today
  → redact → digest → immutable LiveContextSnapshot
  → feeds topology, blast radius, risk scoring, rollback, env classification
```

For a typical thirty-resource plan this is on the order of 40–80 API calls, completes in seconds, and requires roughly two dozen read-only actions — an IAM policy a security team can review in a single sitting. Scope is derived from the plan, so it grows with the change, not with the estate.

### Trust boundary and the read-only guarantee

The read-only property is the single highest-stakes property in this design. It is enforced in four independent places, so that no single mistake can produce a mutation:

1. **Deny-by-default allow-list in code.** `cloud/aws/allowlist.py` enumerates every permitted API action. The connector refuses to issue any call not present, *before* the call is constructed.
2. **An automated non-mutation assertion.** A test asserts that every allow-listed action name matches the provider's read-only verb set (`Describe*`, `Get*`, `List*`, `BatchGet*`, `Head*`). Introducing a mutating verb anywhere in the allow-list fails CI. This is a build gate, not a code-review convention.
3. **A published minimal IAM policy** shipped in the repository, covering exactly the allow-listed actions and nothing more. Operators are instructed to attach that policy rather than `ReadOnlyAccess`.
4. **Dry-run.** `--dry-run` enumerates the exact calls that would be issued, for a given plan, **without resolving or using credentials at all**. Operators can review intended behaviour before granting anything.

### Credential handling

Credentials are resolved from the operator's ambient chain — `AWS_PROFILE`, SSO, environment, instance role, IRSA — and are **never persisted, never logged, never returned through the API, and never written to a snapshot**. This extends the existing posture in `config.py`, which already redacts `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_SECRET_KEY` and `AWS_SECURITY_TOKEN`. No new credential storage mechanism is introduced by this RFC.

Connector configuration is constrained so that caller-supplied values cannot retarget the client at an arbitrary endpoint, role or host. Endpoints resolve only through provider-canonical resolution; this is the same confused-deputy and SSRF concern that Story 16.10 addresses for outbound handoff, handled independently here because the lanes do not share code.

### Snapshot model and Evidence Law

A `LiveContextSnapshot` is immutable, timestamped, digest-bound, project-scoped and **redacted before persistence** using the existing `services/content_security.py` facilities. It records provider, account/subscription/project scope, region set, read window, per-resource read status, and the exact set of actions issued.

It enters the existing evidence system as a new `EvidenceSourceType` member `live_state`, carrying `DeterminismLevel = "deterministic"` — a stronger classification than the `heuristic`/`inferred` labels that dominate context today. It reuses the existing `ContextSourceFreshness` vocabulary (`current`, `stale`, `missing`, `incomplete`, `conflicting`, `unknown`) rather than inventing a parallel one.

Live state is still a point-in-time observation. It is timestamped and digested, and it is subject to Evidence Law like any other source. **Grounding does not make DeployWhisper omniscient; it makes its uncertainty narrower and better labelled.**

### Fail-safe degradation

This is a hard contract, not a quality goal:

- An unreachable, partially readable, throttled or expired cloud context **never lowers a severity and never raises a confidence**.
- Partial reads are labelled partial, and unreadable resources are enumerated **with the exact missing permission**, so the operator receives an actionable remedy rather than a vague warning.
- Missing grounding produces `insufficient_context`, exactly as a missing topology does today.
- Unknown recoverability is never rendered as recoverable.

This mirrors the already-proven `_read_kubernetes_live_state()` contract, which degrades with explicit `TODO:` warnings rather than silently returning a thin result.

### Plan-versus-reality divergence

The Terraform parser already reaches `change.before` (`parsers/terraform_parser.py`). Comparing that recorded prior state against live state at review time classifies each touched resource as `match`, `diverged`, `unknown` or `unreadable`, and produces a reviewer-facing finding:

> ⚠️ **This plan was computed against stale reality.** Security group `sg-0a3f` was modified 2 hours after this plan was generated (ingress `0.0.0.0/0:22` added out-of-band). The approved diff is not the diff that will apply. Re-plan before proceeding.

Divergence on a security-relevant attribute establishes a severity floor and forces at least `caution`. A reason or acknowledgement cannot silently clear it. `--fail-on-divergence` exposes the same check as a CI gate, which gives Story 17.4 standalone value in a GitHub Action with no UI and no Epic 16 dependency.

### Air-gapped and restricted-network parity

Snapshots are exportable and importable as digest-bound, provenance-carrying files. An operator in a restricted network can collect on a connected host and analyze on a disconnected one, with identical grounding semantics and an explicit `imported` label plus age check. This gives Epic 17 the same operational honesty that Story 12.8 requires of the rest of the product.

### Repository placement

```text
cloud/
  base.py            CloudConnector protocol, LiveContextSnapshot, ResourceIdentity
  registry.py        provider registry, mirrors parsers/registry.py
  redaction.py       snapshot redaction over services/content_security.py
  aws/
    connector.py     session resolution, client construction
    reflector.py     plan identity -> bounded read-only calls
    graph.py         live dependency edges
    recoverability.py protection and restore-path facts
    allowlist.py     permitted actions, deny by default
  azure/  gcp/       registered stubs, same shape as the cloudformation stub

services/cloud_context_service.py   orchestration, caching, freshness, degradation
tests/test_cloud/                   registered in local CI and the relevant GitHub shard
```

All integration is **additive**. `TOPOLOGY_SOURCE_REGISTRY["aws"]` replaces a registry slot that already anticipates unimplemented providers. The report gains an optional, separately versioned `live_context` block (`live_context_version: 1`) on the existing report v2 schema; no report minor-version bump is proposed, consistent with IA-ADR-06.

## Relationship to Epic 16

**Epic 17 has no dependency on Epic 16, and Epic 16 has no dependency on Epic 17.** The two epics can be developed, reviewed, merged and released independently and concurrently. The full conflict analysis is maintained in the [boundary and parallelization plan](../../_bmad-output/planning-artifacts/epic-16-17-boundary-and-parallelization-plan.md); the summary:

| Concern | Epic 16 | Epic 17 |
| --- | --- | --- |
| Question answered | *Who authorized this change, and did the exact approved bytes reach delivery?* | *What is actually out there, and will this plan hit what it expects?* |
| Direction of data | Outbound — dispatch to a receiver | Inbound — read-only observation |
| Posture | Governance and custody | Evidence and context |
| Primary modules | `infra_automation/`, `services/infra_automation_*` | `cloud/`, `services/cloud_context_service.py` |
| Credentials | Issues and consumes grants, runner and receiver tokens | Consumes ambient operator credentials; issues nothing |
| Writes anywhere? | Dispatches to an external system | **Never** |

Epic 17 deliberately does **not** reuse Epic 16's runner, enrollment, attempt-fencing or receiver protocol. Grounding is a short, synchronous, inbound read performed by the application itself; routing it through an enrolled runner would import an entire protocol for no benefit and would create exactly the dependency this RFC avoids. Operators who want grounding executed closer to a private network can use snapshot import (Story 17.7).

The intended integration point is **one-directional and optional**: once both epics land, Epic 16's approval inbox renders Epic 17's `live_context` block. That is a presentation-time read of an additive, optional field. Neither epic's acceptance depends on the other.

## Alternatives Considered

| Alternative | Why rejected |
| --- | --- |
| Account-wide inventory / estate scan | Slow, costly, requires broad IAM, duplicates Steampipe and CloudQuery, and answers a different question than pre-deployment review. |
| Continuous drift daemon | Off-mission. DeployWhisper is a pre-deployment reviewer, not a monitoring product. Scheduled drift also misses the exact case that matters: a pending plan computed against stale reality. |
| More parsers (Pulumi, CDK, Terragrunt, Helm) | Adds breadth without addressing context starvation. Each new parser inherits the same empty blast radius. |
| Write access for remediation or apply | Violates an explicit product non-goal and destroys the "we never touch your apply" trust position, which is the project's strongest differentiator. |
| A policy-as-code engine | Commoditized by OPA, Conftest and Checkov; `services/policy_adapter_service.py` already provides the integration seam. |
| Cost estimation | Infracost owns this well, under Apache-2.0. Integrate later; do not rebuild. |
| AI-generated IaC or AI-inferred topology | Explicitly deferred product scope, and directly dilutes the deterministic-evidence posture this RFC strengthens. |
| Route grounding through Epic 16's runner | Creates a hard cross-epic dependency, imports the enrollment and fencing protocol for a short inbound read, and blocks all Epic 17 value behind Stories 16.12–16.14. |
| Ship AWS only, no connector contract | Forfeits the community contribution surface that makes multi-cloud coverage sustainable for a volunteer-maintained project. |

## Security Considerations

| Risk | Control | Owning story |
| --- | --- | --- |
| Accidental mutation | Four-layer read-only enforcement; CI gate on mutating verbs | 17.2 |
| Credential leakage | No persistence, no logging, no API echo; secret-corpus regression test | 17.2 |
| Sensitive data in snapshots | Redaction before persistence; no secret values, user data or raw state | 17.1 |
| Confused deputy / SSRF via connector config | Provider-canonical endpoint resolution only; no caller-supplied endpoints or roles | 17.2 |
| Over-broad IAM grant | Published minimal policy; per-capability permission map; dry-run before grant | 17.2, 17.9 |
| Rate limiting, throttling or cost surprise | Plan-directed scope, concurrency caps, call budget, visible budget reporting | 17.3 |
| Over-trusting live reads | Snapshots are timestamped, digested and Evidence-Law governed like any other source | 17.1 |
| Information disclosure through grounded reports | Existing project scoping and report authorization apply unchanged; account ids maskable | 17.1, 17.8 |

An independent security review is a **required gate before Story 17.3 merges**, because 17.3 is the first story that issues live calls with real credentials.

## Drawbacks and Risks

- The AWS API surface is enormous. This RFC deliberately covers roughly the top twenty-five risk-bearing resource families rather than attempting completeness, and relies on the connector contract to let the community extend coverage.
- Credential handling is the highest-stakes code the project will have shipped. This is mitigated by the enforcement layers above, a required security review, and dry-run.
- Grounding competes for maintainer capacity with Epic 16. This is a genuine tradeoff and is addressed explicitly in the accompanying course correction, which does not propose cancelling or de-scoping Epic 16.
- Live state is itself a snapshot. The design labels it as such rather than presenting it as ground truth.

## Adoption and Migration

Grounding is **opt-in per project and disabled by default**. No existing deployment changes behaviour on upgrade. With grounding off, reports, fixtures, schemas, API consumers, CLI output and agent output are byte-compatible with current behaviour — this is an explicit acceptance obligation (LEG-NFR-009), not an aspiration.

## Measurable Success Criteria

These are verifiable against machinery the repository already has:

1. `unmatched_resources` rate on an AWS plan corpus falls from effectively 100% to below 10% with grounding enabled.
2. Measurable increase in the share of report evidence classified `deterministic` rather than `heuristic` or `inferred`, via the confidence ledger.
3. A counted, non-zero rate of plan-versus-reality divergence detections on the benchmark corpus — a class of catch that currently cannot occur.
4. A counted, non-zero rate of irreversible-destroy detections surfaced before approval.
5. A published before/after accuracy delta from `services/backtesting_service.py` on the benchmark corpus. **The repository already has this harness; the value claim must be proven with it rather than asserted.**

## Unresolved Questions

Each is owned by Story 17.0 and must be closed by executable evidence, not discussion:

1. Which AWS SDK dependency decision is approved — `boto3` as a runtime dependency, an optional extra, or a thin signed-request client? This is a **new runtime dependency** and requires an explicit approved dependency decision under the existing guardrail.
2. What is the exact initial resource-family coverage list, and what is the per-family permission map?
3. What default total deadline, concurrency cap and call budget are defensible on a measured large plan?
4. How is `prior_state` reliably extracted across Terraform and OpenTofu plan JSON format versions, and what is the fallback when it is absent?
5. What snapshot retention and purge policy applies, and how does it interact with existing retention guidance?
6. Does credential resolution need an explicit allow-list of resolution mechanisms to prevent unintended instance-role escalation on a shared host?

## Decision Record

| Date | Decision | Authority |
| --- | --- | --- |
| 2026-10-19 | RFC drafted and opened for public review; Epic 17 scoped as an independent, parallel workstream | Proposed — awaiting maintainer decision |

**No implementation is authorized by this RFC.** Acceptance of this RFC authorizes Story 17.0 qualification only. Downstream stories require their own dependency evidence, the Story 17.0 feasibility results, an approved dependency decision, and an independent security review before Story 17.3.
