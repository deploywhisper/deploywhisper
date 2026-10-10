# WP7 final readiness and bounded delivery sizing

Assessment date: **2026-10-10**. Responsible contributor: **Codex**, separate readiness lane from the qualification implementers. Accountable maintainer: **@pramodksahoo**. Final integration owner: root Codex. The maintainer explicitly accepted RFC 0001 and requested completion; the [decision record](maintainer-decision-2026-10-09.md) preserves the early-window exception and absence of a second independent human reviewer.

The [final implementation-readiness assessment](../../../../_bmad-output/planning-artifacts/implementation-readiness-report-2026-10-10-infra-automation-v1.5.0.md) reassesses all 20 contexts, 72 active requirements, parent preservation, UX, dependencies and IR-01–04. **The foundation is qualified for sequential feature implementation after Story 16.0 final validation passes. v1.5.0 production/release readiness is not established.**

## Evidence and acceptance boundary

| Story AC | Current evidence | Exact acceptance boundary |
| --- | --- | --- |
| 1 | [Threat model](threat-model.md), [scope corpus](scope-corpus.json), frozen contracts and final ADR dispositions | Bounded Tier 0/1 selected; unsupported registry/schema cases reject. Scope review does not execute production workflows. |
| 2 | [Maintainer decision](maintainer-decision-2026-10-09.md), [governance record](governance.json), real PR #154 chronology | Explicit direct acceptance and RFC-specific early-window exception. Seven days did not elapse; no GitHub approval/comment or second human is invented. |
| 3 | [WP2](wp2-identity.md), [results](wp2-identity-results.json): 18 test methods and 2,000 permission outcomes | Disposable local identity/session, replay/CSRF/audience/scope matrix; application identity and persistent abuse controls remain 16.1/16.2. |
| 4 | [WP3](wp3-sqlite.md), [results](wp3-sqlite-results.json): 11 test methods | Independent connections/processes, fenced claim/crash/restart/stale writes; singleton production workload and power-loss tests remain later. |
| 5 | [WP4](wp4-containment.md), [results](wp4-containment-results.json) | Real pinned OpenTofu/provider in non-root Linux ARM64 Docker; source/catalog/environment/network/resource/process probes. Only the named profile qualifies. |
| 6 | [Real custody](wp5-real-custody.md), [results](wp5-real-custody-results.json) | Actual saved plan; separate UIDs; encrypted local custody, sealed memfd, seven attack cases, receiver-container restart, changed actual plan denial, bounded stores. Anchored tmpfs does not prove host-power-loss durability. |
| 7 | [Synthetic receiver](wp5-receiver.md), [real custody](wp5-real-custody.md) | 12 synthetic test methods plus real-custody adapter, five abrupt crash points, 30 tuple mutations, one harmless counted action at most, unknown locks retained. No infrastructure apply or universal exactly-once claim. |
| 8 | [WP6](wp6-contract-assessment.md), [results](wp6-contract-results.json), [freeze](../../../../schemas/infra-automation/frozen-v1.json) | 15 methods/185 subtests; 25 valid/28 invalid vectors, semantic/hash/permission/error/state checks; actual CLI 6, raw React client 3, pinned external-action summary 3 cases. These are bounded consumer probes, not entire browser/action integration. |
| 9 | This packet, final readiness report, [technical review](technical-review.md), final root validation manifest | All 20 prepared contexts retained, earlier-only dependency graph checked, estimates/owners recorded, open production obligations assigned. Closure requires actual final root checks and evidence reconciliation. |

WP4/WP5 share the same real Linux command and its **3 passed / 6 subtests passed** result; they are not six separate methods. The qualified profile SHA-256 is `1f91ca01dcfce0a06b6ab19cba7f145dae499a551608f0cdc8386c25dd1cbf49`: Linux ARM64, OpenTofu 1.13.1, external provider 2.3.5, collector UID10001 / receiver UID10002. The frozen manifest binds it. Independent contract review additionally exercised 240 workflow orders and 725 negative cases; review evidence is bounded to those cases and recorded by the integration owner.

## Named delivery accountability and review

For **each story and each packet below**, @pramodksahoo is the accountable maintainer and **Codex under @pramodksahoo's supervision** is the assigned assisted execution owner. The discipline column selects the technical review responsibility; implementation is followed by an independent Codex review pass with a distinct reviewer session/agent and maintainer acceptance. Root Codex must record the actual reviewer identity and findings per story before closure. This is a concrete delivery assignment, not a claim that a future reviewer has already worked.

There is one named human maintainer today. A separately named independent human security/architecture reviewer has not been secured; that coverage gap remains explicit. Codex technical independence does not establish multi-maintainer/four-eyes governance. Stable-release security review and pilot coverage are rechecked in 16.19. No fictitious additional engineer or parallel calendar capacity is assumed.

## Revised remaining-story estimates and dependencies

Ranges below are **planning estimates in engineering person-weeks**, including implementation, focused tests, docs, independent technical review and fixes. They are not observed elapsed time, a quote, a release date or AI throughput predictions. WP2's complete matrix, WP3's real contention, real WP4/WP5 resource/custody faults and WP6's consumer/graph discoveries inform uncertainty: production integration, durable abuse state, real networking and browser/recovery work still need delivery. Re-estimate at each accepted dependency and split review packets rather than reducing safety acceptance.

| Story | Earlier dependencies / release condition | Range | Independent review discipline | Spike-informed work still required |
| --- | --- | --- | --- | --- |
| 16.1 | 16.0 | 1.5–2.5 | Identity/security | Move proven parameters into real persistence, HTTPS/session/CSRF/recovery and persistent abuse controls. |
| 16.2 | 16.1 | 1.5–2.5 | Authorization/security | Apply matrix to actual memberships and legacy linked-object/report/policy/settings routes. |
| 16.3 | 16.0 | 1–2 | Schema/graph/security | Production closed parser/typed graph, all-path semantics and 1,000-sample reference workload. |
| 16.4 | 16.2, 16.3 | 1–2 | Persistence/API | Per-slice migration, immutable revisions, feature epochs, audit and configuration contracts. |
| 16.5 | 16.4 | 3–5 | Concurrency/recovery | Six ordered packets integrate lifecycle, bounded workers, SQL fencing, retries, cancellation and capacity. |
| 16.6 | 16.5 | 1.5–2.5 | Evidence/API compatibility | Real intake/shared-core linkage, screened provenance, report consumers and AI-off parity. |
| 16.7 | 16.4, 16.6 | 2–3.5 | UX/accessibility/API | Five packets include named-account entry; actual screens, stale-scope handling and Compose browser proof. |
| 16.8 | 16.2, 16.6 | 1.5–2.5 | Authorization/decision integrity | Persist exact report export bytes and live policy/freshness tuple; runtime gate success and revocation. |
| 16.9 | 16.7, 16.8 | 1.5–2.5 | UX/accessibility/security | Exact packet/confirmation/reason, distinct-principal denial, lost-response receipt and browser races. |
| 16.10 | 16.8 | 2–3 | Network/security/transactions | Registered targets, real SSRF controls, durable outbox/grants and alias-safe locks. |
| 16.11 | 16.9, 16.10 | 2.5–4 | Receiver/security/recovery | Five packets add real versioned GitHub boundary, durable admission, custody and verified reconciliation. |
| 16.12 | 16.2, 16.5 | 1.5–2.5 | Protocol/auth/concurrency | HTTPS enrollment/rotation/attempt streaming, real leases and 20-runner claim measurements. |
| 16.13 | 16.12 | 2–3 | Isolation/security | Package protected launcher/catalog/environment with fail-closed actual host controls and lifecycle proof. |
| 16.14 | 16.6, 16.11, 16.13; 12.5 before distribution | 2–3.5 | Collector/custody/evidence | Integrate real collection/exit codes/screening/upload and exact plan access through production receiver. |
| 16.15 | 16.7, 16.14 | 1–2 | UX/accessibility/runner | Actual health/log/cancel/lease-failure journeys, transient tokens and composed real-runner evidence. |
| 16.16 | 16.3, 16.10, 16.14 | 1.5–2.5 | Graph/domain/UX | Declared exact unit cover, deterministic waves/digests, target binding and accessible tables. |
| 16.17 | 16.4, 16.11, 16.15 | 1.5–2.5 | Signing/API/CLI | Raw-byte signature/replay persistence, source/intake bounds and real CLI authority parity. |
| 16.18 | Incremental after 16.5; final after 16.16, 16.17 | 3–5 | Recovery/operator/security/UX | Six packets cover persistent custody/key policy, quiesced recovery, network/cache operations, capacity and Settings. |
| 16.19 | All 16.0–16.18; 12.5; applicable 12.7/12.8 acceptance | 3–5 | Independent release/security/QA | Full integrated real-profile pilot, 1,000-sample latency gates, saturation, browser/recovery and signed artifacts. |

Total remaining Epic 16 planning effort: **34.5–58 person-weeks**, before contingency. Separately retain **12.5 at 1–2 person-weeks**, giving **35.5–60** combined remaining planning effort. Reserve **20–30%** contingency until production network/recovery and workload qualification reduce uncertainty. This replaces the earlier aggregate 28–49 estimate for remaining work; its coarse packaging understated explicit account-entry/Settings, real custody lifecycle and independent per-packet integration. Story 16.0 effort already spent is excluded. Actual staffing and serial dependencies preclude converting the sum to a calendar promise.

## Broad packet review

| Story / order | Owned boundary and precondition | Required packet proof |
| --- | --- | --- |
| 16.5 A → B → C → D → E → F | A state/entities/migration only after16.4; B repository claims after A; C coordinator/lifespan and worker ports after B; D idempotent outputs/retries after C; E cancellation after D; F test/config/docs/limits after E. Existing story names exact files. | A committed transition/upgrade; B independent owner races/stale writes; C off-loop worker progress; D no blind resend; E descendant/cancel races; F 1,000 transitions and 30-minute capacity. Use scoped worker doubles; receiver/runner support waits for its owners. |
| 16.11 1 → 2 → 3 → 4 → 5 | After16.9/16.10: GitHub versioned adapter/config; receiver operation/consume; protected synthetic exact-byte fixture; reconciliation service/routes; existing run screen/browser tests. External Marketplace runtime remains in `deploywhisper/analyze-action`. | Version-specific real integration; consume/start/completion crash recovery; no-follow/digest/expiry; signed sequenced outcomes retaining unknown locks; browser accepted/unknown/cancel behavior. Seeded custody qualifies this slice without waiting for16.14; integrated actual collection is16.14/16.19. |
| 16.18 18.1 → 18.2 → 18.3 → 18.4 → 18.5 → 18.6 | Prepare against accepted16.5; final integrates16.16/16.17. Respect retention repositories/config, backup/restore scripts/current migration, reconciliation/locks, runner cache/network, operator docs/metrics, Settings/client/e2e scopes. Earlier16.4/16.10 APIs supply Settings. | Pending-evidence deletion/disk quota; coordinated DB/artifact/custody restore with new epochs; no stale authority resurrection; restricted network and rotation; self-service runbooks plus30-minute capacity; composed admin/denied/conflict/disable/keyboard/axe1440/760 proof. Preserve full original12.7/12.8 requirements separately. |

All 20 contexts retain stable IDs, story-specific acceptance, owned paths, tests/docs and per-slice migrations. Earlier slices use explicitly limited ports/fixtures; no table-for-all-future-stories migration or forward production dependency is introduced. Packet order is a review sequence; changing shared implementation paths still requires coordination.

## Carried obligations and next executable stories

| Retained limitation | Owning delivery / acceptance |
| --- | --- |
| Prototype local auth and measurements; no application boundary delivered | 16.1/16.2, full16.19 authority matrix |
| Local Python3.14 tests do not prove complete Python3.11 app compatibility | Each production story's CI;16.19 runtime matrix (isolated Linux image itself uses3.11) |
| Anchored tmpfs covers process/container restart only; host power loss, persistent keys and long-lived janitor absent | 16.11 production custody semantics;16.14 integrated store;16.18 backup/retention/key/recovery exercise;16.19 final profile |
| One ARM64/OpenTofu1.13.1/external2.3.5 profile; no Terraform/AMD64/cloud provider support inferred | 16.13/16.14 explicit supported matrix;16.19 pilot |
| Authenticated collector can lie; host/daemon/receiver identity/DB administrator remain trusted | 16.13/16.14 threat model and operator controls;16.18 trust-limit docs |
| Single synthetic timing and bounded caps do not establish 10-run/2-analysis/20-runner capacity or p95 targets | 16.3/16.5/16.12 measured slices;16.18/16.19 reference workload |
| Harmless local receiver action and consumer functions are not live GitHub delivery or full action compatibility | 16.11/16.14 integration;16.19 pilot; any external action runtime changes use external repo and smoke consumer |
| No actual rendered automation screen, keyboard/axe or visual-parity proof | 16.7/16.9/16.11/16.15/16.16/16.17/16.18;16.19 full composed journey |
| One-human governance coverage; independent technical agents are not another human maintainer | @pramodksahoo records coverage and seeks independent human review/pilot for16.19; do not claim four-eyes governance |
| No stable runner artifact/signing/SBOM release from these experiments | Separate12.5 and16.19; reuse done12.6, preserve done13.8 |

After final root validation and actual Story 16.0 closure, **only 16.1 and16.3** have all earlier dependencies satisfied and may become ready-for-dev. **16.2 and16.4–16.19 remain backlog**. This is a readiness recommendation, not a tracker edit by this reviewer. Next BMad handoff is final code-review/verification for16.0, then dev-story for16.1 or16.3 using the existing prepared context;12.5 remains independently eligible under its own acceptance.

## Validation handoff

This lane verified requirement-ID coverage, all 20context references/dependency ordering and the packet review above. Full root validation was **in progress at assessment time**. Story 16.0 may close only after the root records actual final lint, repo-wide Ruff formatting, smoke, every-directory local CI, affected API/CLI/infra shard, security, real Linux rerun and contract/consumer review results in the manifest. Earlier successful counts are evidence of their recorded runs, never a claim the final combined tree has passed. Root must reconcile final artifact digests and any remaining finding before promotion. No production UI changed, so UI validation is not applicable for16.0.

## Final integration verification — 2026-10-10

The root completed final validation: full local CI exit0; root smoke614tests with2skips; exact API/CLI/infra shard550passed/1skipped/1023subtests; explicit actual Linux suite3passed/6subtests; contract15tests/185subtests and independent240-order/725-negative review; Ruff lint, repo-wide format322files and scoped Bandit passed. The ordinary-CI Docker opt-out was covered by the independent actual run. Final hashes and review corrections are reconciled in the evidence manifest.

The pending integration-verification condition is satisfied. **Story16.0 is done for its bounded governance/qualification scope;16.1 and16.3 are ready-for-dev.** Later stories and stable release retain their own acceptance. This addendum completes the earlier conditional assessment without rewriting its chronology.
