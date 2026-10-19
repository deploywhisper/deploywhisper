# Sprint Change Proposal — Epic 17: Live Environment Grounding

Date: 2026-10-19
Status: Proposed — pending maintainer decision on [RFC 0002](../../docs/rfcs/0002-live-environment-grounding.md)
Author: Planning preparation
Scope: Addition of a new independent epic. **No Epic 16 de-scoping is proposed.**

## 1. Trigger

Analysis of the current codebase against the released product promise surfaced a structural gap that no in-flight work closes.

DeployWhisper reasons well about change but has no supply of real environment facts:

- `analysis/blast_radius.py` matches planned resources against a hand-authored topology graph. Resources with no mapping fall into `unmatched_resources` and produce a missing-context warning. For a Terraform or OpenTofu plan against a cloud account with no hand-authored topology, this is effectively the whole plan.
- `analysis/risk_scorer.py` derives severity from action and category base tables. Severity is therefore a statement about a resource **class**, not about the specific instance being changed.
- `services/topology_service.py` registers `custom`, `terraform` state and live `kubernetes` sources, with explicit unimplemented handlers for `cloudformation` and `ansible`. Live grounding exists for Kubernetes only.
- No cloud SDK or cloud API client exists anywhere in the repository. The only AWS-related code is credential-name redaction in `config.py`.

The consequence: the product's flagship blast-radius capability degrades to a warning for the most common deployment target, and recoverability and environment classification are category inferences rather than verified facts.

## 2. Why this is a sprint change proposal rather than a backlog item

The gap is not a defect in any existing story and cannot be closed by refining one. It requires a new capability area with its own trust boundary, its own extension contract and its own security review posture. Under the BMad operating model that is an epic-level change, and it must be recorded as a course correction rather than absorbed silently.

## 3. Proposed change

Add **Epic 17: Live Environment Grounding** — a read-only, plan-directed cloud context provider, starting with AWS, that supplies verified environment facts to the existing analysis core.

Four capabilities:

1. **Grounded blast radius** — real dependency edges replace a missing-mapping warning.
2. **Plan-versus-reality divergence** — detect that a plan was computed against stale reality before it is approved. This capability has no equivalent in comparable open-source pre-deployment tooling.
3. **Grounded recoverability** — classify a destructive change as recoverable, recoverable with loss, irreversible or unknown from actual protection attributes.
4. **Grounded environment and ownership** — classify environment from declared and live signals, reporting `conflicting` on disagreement.

Delivered as ten stories, 17.0 through 17.9, defined in [epics.md](epics.md), with requirements `LEG-FR-001..040` and `LEG-NFR-001..012` in the [feature PRD](prd-live-environment-grounding.md) and architecture in [architecture.md §26](architecture.md).

## 4. What is explicitly not proposed

- **No change to Epic 16 scope, priority, sequencing or ownership.** Epic 16 continues as planned under its current agent.
- No write, apply, destroy, tag, provision or remediate capability. Epic 17 is read-only by construction and by mechanical CI enforcement.
- No account-wide inventory, no scheduled drift daemon, no cost estimation, no policy-as-code engine, no AI infrastructure generation.
- No change to the advisory posture. Reports remain advisory with `should_block=False`. The only gate introduced is a caller-opted CLI exit code.
- No report schema version bump. Grounded output is an additive `live_context` block with its own `live_context_version`.

## 5. Impact analysis

| Area | Impact | Mitigation |
| --- | --- | --- |
| Analysis core | Additive grounded paths in blast radius, risk floor, recoverability, environment classification | Grounding is opt-in and disabled by default; with it off, all existing outputs are unchanged and proven so by LEG-NFR-009 |
| Evidence model | Additive `live_state` member in `EvidenceSourceType` and `ContextSourceType` | Additive enum members only; never remove or reorder existing members |
| Topology service | Additive `aws` registry entry | Existing handlers untouched; follows the established `kubernetes` live-source precedent |
| Dependencies | A provider SDK is a new runtime dependency | Blocked behind an explicit approved dependency decision in Story 17.0 Packet 0.2 |
| Security surface | New outbound cloud access with operator credentials | Four-layer read-only enforcement, ambient-only credentials, no caller-controlled targeting, published minimal policy, independent security review gating 17.3 |
| Privacy | Snapshots record environment facts | Redaction before persistence; no secrets, credential material, user data, raw state or plan bytes; maskable account identifiers |
| Epic 16 | Potential file-level contention | Governed by the [boundary and parallelization plan](epic-16-17-boundary-and-parallelization-plan.md): separate branch, separate module tree, append-only edits to shared files |

## 6. Parallelization with Epic 16

Epic 17 is developed on `feature/epic-17-live-environment-grounding`, cut from `develop`, in a new `cloud/` module tree with its own `tests/test_cloud/` shard.

- Epic 17 has **zero dependency on any Epic 16 story**. It deliberately does not reuse the Epic 16 runner (architecture §26.2, LEG-ADR-10), because doing so would import the enrollment, fencing and lease protocol and block all grounding value behind 16.12–16.14. Private-network operators are served by snapshot import in Story 17.7 instead.
- Exactly one integration point exists, and it is one-directional and optional: if both epics ship, Epic 16's preflight may consume grounded context produced by Epic 17. Epic 17 never calls into Epic 16.
- Shared-file edits are append-only and additive. The full contention rules, owned paths and pre-PR checklist are in the boundary plan, which must be read before editing any shared file.

## 7. Sequencing and value checkpoints

| Checkpoint | Stories | Value delivered |
| --- | --- | --- |
| Governance and feasibility | 17.0 | Decision, dependency approval, measured defaults, frozen coverage |
| Safe foundation | 17.1, 17.2, 17.3 | Read-only grounding exists and is mechanically safe; no end-user feature yet |
| **First shippable value** | **17.4** | **Divergence detection and CI gate, usable with the CLI alone, no UI required** |
| Grounded analysis | 17.5, 17.6 | Real blast radius and verified recoverability |
| Reach and presentation | 17.7, 17.8 | Air-gapped parity and the Live Context UI |
| Qualification | 17.9 | Extensibility contract, measured deltas, release gates |

Story 17.4 is the recommended early release checkpoint. If the epic must be paused, pausing after 17.4 still leaves a complete, demonstrable capability in users' hands.

## 8. Risks

| Risk | Severity | Response |
| --- | --- | --- |
| Read-only guarantee weakens over time | Critical | Mechanical CI verb assertion including a deliberate failing case; any weakening finding is a blocking gap |
| False divergence findings erode trust | High | Precision prioritized over coverage; hostile fixture corpora; unknown and unreadable kept distinct from match |
| Grounding does not measurably improve accuracy | Medium | Story 17.9 Packet 9.6 publishes the measured delta honestly, including a null or negative result |
| Dependency and supply-chain expansion | Medium | Explicit approved dependency decision in 17.0 with option analysis |
| Merge contention with Epic 16 | Medium | Separate branch and module tree; append-only shared-file rule; boundary plan as the contract |
| Scope creep toward remediation | High | Prohibited-capability list repeated in every story; advisory posture preserved |

## 9. Decision required

Maintainers are asked to decide on RFC 0002. Until that decision is recorded:

- Epic 17 remains **backlog** with all stories unpromoted.
- No implementation work begins.
- Story 17.0 is the only story eligible for execution once the decision is positive, and it must complete before any downstream story is promoted.

No implementation proof has been run. Everything in this proposal is a plan and a set of future obligations, not a result.

## 10. References

- [RFC 0002](../../docs/rfcs/0002-live-environment-grounding.md)
- [Feature PRD](prd-live-environment-grounding.md)
- [Architecture Section 26](architecture.md)
- [Epic 17 stories](epics.md)
- [Epic 16/17 boundary and parallelization plan](epic-16-17-boundary-and-parallelization-plan.md)
- [Project implementation context](../project-context.md)
