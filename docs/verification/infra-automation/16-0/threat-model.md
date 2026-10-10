# WP1 scope and threat-model review inputs

Prepared 2026-10-09 by Codex for Story 16.0. All controls below are requirements
to qualify, not implemented protections. The later maintainer decision and WP2–6 evidence are indexed in the final dispositions below. Canonical authority is the parent PRD §4.4, feature PRD,
72-row active inventory, architecture §25, Epic 16 and RFC 0001; the original
179-row vision remains historical input.

## Scope reconciliation

Tier 0 accepts supported uploads or produces preflight artifacts through a
qualified isolated collector. Tier 1 records a verified human decision and
hands its exact authorized request to a registered external GitHub receiver.
DeployWhisper itself never applies, destroys, provisions or remediates.
An operator-owned external pipeline is responsible for any deployment.
Uploaded advisory evidence cannot authorize an apply, and an `exact_plan`
handoff requires the original immutable bytes in protected local custody.

The parent runner exclusion now explicitly distinguishes privileged isolated
collection from provisioning. Existing uploads remain supported; adding an
automatic collector is a separate scope decision. Canonical findings, severity,
Evidence Law and `should_block=False` stay in the shared analysis core. Workflow
gate eligibility is separate. Declared multi-unit waves order preflight review,
not deployment or proof of materialized upstream infrastructure.

P0's selected topology is one self-hosted app, SQLite, local artifact storage,
an operator-controlled disposable non-root Linux runner and a qualified
self-hosted receiver with protected plan custody. Tool/image/provider pins and
the containment mechanism remain unqualified. No HA, alternate OS/DB/receiver
profile, unattended approval, generalized command/plugin, new AI subsystem,
package ledger, automatic dependency inference or broad adapter catalog is
admitted. Proposed capacity numbers remain unmeasured.

[The scope corpus](scope-corpus.json) contains review scenarios for exclusions
and admission boundaries. They must become executable negative fixtures in the
owning stories. A correctly worded expected denial is not runtime denial proof.

## Assets and actors

| Asset | Required protection | Principal actors |
| --- | --- | --- |
| Password verifiers, bootstrap material, opaque sessions | One-use bootstrap; hashed storage; rotation/revocation; bounded authentication cost; HTTPS cookie/CSRF policy | Operator, verified human, unauthenticated attacker |
| Memberships, capabilities, authorization/restore epochs | Server-owned scope; deny absent/wrong audience; revocation and restore invalidate pending authority | Admin, maintainer, reviewer, contributor, read-only human; service/agent |
| Published revision, source, inputs, reports and policy snapshots | Immutable digests; unavailable provenance explicit; shared-core results retain meaning | Requester, reviewer, uploaded/source content attacker |
| Claims, leases, attempt outputs and audit transitions | Atomic CAS/uniqueness; monotonic fencing; current generation/epoch; output-before-success | Coordinator, restarted/stale coordinator, runner |
| Execution host, catalog, provider cache and task credentials | Qualified containment; immutable pins; least privilege; bounded environment/egress/resources | Runner launcher, admitted source/provider, hostile source |
| Saved binary plan/state, raw and screened digests | Protected local custody; immutable finalization; descriptor verification; expiry; distinct identities | Collector and receiver; malicious local unprivileged process |
| Grant, operation, target lock and external outcome | One-use durable consumption; exact tuple; live authority; authenticated sequenced outcomes; retained uncertainty lock | App dispatcher, registered receiver, external operator pipeline |

Credential classes human/service/agent/runner/receiver are separate audiences;
neither a caller's actor header nor a human-labelled credential demonstrates a
physical person. Shared mode denies requester self-approval. A verified single
operator records acknowledgement without a four-eyes claim.

## Boundaries and abuse cases

Each row names the acceptance packet and downstream implementation owner.
Executable outcomes are recorded in the linked qualification packets; the table maps required boundaries to their owners.

| Boundary | Abuse case and required denial/recovery | Proof owner |
| --- | --- | --- |
| Browser/CLI → human session | Bootstrap replay/expiry, fixation, forged actor/role headers, default password, wrong audience, cost exhaustion; rotate at login/privilege change; deny expired/logout/reset/revoked sessions | WP2; 16.1 |
| Cookie → mutation | Missing/wrong CSRF, foreign/null Origin, unsafe cookie scope, unsupported HTTP production use; deny before any consequential mutation | WP2; 16.1 |
| Principal → scoped object/capability | Missing membership, cross-project/workspace IDs, legacy sharing or missing-role admin bypass; reused reports/artifacts/policy/settings protected; shared requester cannot decide | WP2; 16.2 |
| Draft/source → published run | Unknown versions/kinds/fields, YAML bombs/duplicate keys/cycles, >50 steps, executable substitutions, unpinned/untrusted collected source, failed/partial gate or unrelated approval ancestor; no execution before validation | WP6; 16.3–16.6 |
| Coordinator → SQLite/attempt | Simultaneous claims, expired lease, overlapping generations, restart/crash; stale heartbeat/log/upload/completion denies at current fence/epoch; committed transitions survive | WP3; 16.5/16.12 |
| Admitted source → task sandbox/host | Traversal/symlink escape, option/catalog replacement, inherited Git hooks/config/env, hostile provider/external process; non-root/no socket/no host secrets; real denied egress/metadata; bounded CPU/memory/disk/time/output and descendant termination | WP4; 16.13–16.14 |
| Collector → transport/app | Sensitive plan/state or chunk-spanning secret leakage; screened JSON has its own digest/redaction version; raw binary/state never enters app/public artifacts; authenticated sender is not truthful-output proof | WP4–6; 16.14 |
| Collector → local custody → receiver | Overwrite, symlink swap/TOCTOU, tamper, expiry, restart or unauthorized identity; finalize original bytes immutably and verify a no-follow descriptor's digest and owner; changed plan needs new evidence/decision | WP5; 16.11/16.14 |
| Evidence/decision → grant/action | Independently mutate revision/source/input/scope/report/policy/unit/target/payload/custody/digest/deadline/epoch; reject substitution and advisory-request apply; unavailable authority fails closed | WP5–6; 16.8/16.10–16.11 |
| Receiver consume → external effect/outcome | Crash before/after consume/start/completion, lost response, duplicate delivery; durable operation/consumption precedes counted action; recover same operation, never blind retry uncertain effect; accepted dispatch is not terminal success | WP5; 16.11 |
| Target aliases/cancel/lease → locks | Cross-project aliases bypass collision keys; cancel/timeout silently unlocks uncertain action; retain delivery_unknown lock until verified terminal outcome or reasoned audited lock break that grants no new authority | WP5; 16.10–16.11/16.18 |
| Disable/revoke/restore → outstanding action | Old grants/sessions/leases resurrect; membership/target/feature unavailable or epoch changed before new/resumed action; block new action and retain read/reconciliation; do not claim already-started action stopped | WP3/5; 16.4/16.18 |
| Registered target → remote endpoint | User-selected arbitrary destinations, DNS rebinding, redirects/metadata access, payload/replay/source mismatch; registration, bounded requests and correlated authenticated sequenced outcomes required | WP5–6; 16.10–16.11/16.17 |
| Evidence/narrative → AI | Raw uploaded secrets/injected instructions or model-issued publish/approval/dispatch; AI receives only allowed structured summaries after scoring, cannot grant authority; AI-off operation required | WP6; 16.6/16.19 |

## Trust limits and unresolved questions

- Host/root/DB administrators can read or modify local state; API append-only
  audit is not tamper-proof against them. Backup/restore epoch discipline and
  operator procedures mitigate mistakes, not a malicious host administrator.
- A compromised runner/collector can fabricate output. Signed metadata and
  a transport digest prove sender/content identity, not source truth. Separate
  collector/receiver identities and trusted-source admission are prerequisites.
- Provider/external-data execution is privileged even for `plan`. Fixed argv
  cannot substitute for real non-root Linux containment and controlled caches.
  Select actual image/tool/provider pins only against operator availability.
- Regex screening is bounded corpus evidence, never a universal secrecy claim.
  Saved binary plans/state stay local under an explicit encryption/storage,
  ownership and cleanup policy that WP5 must select and prove.
- Live authority checks cannot reverse an external action already begun.
  Unknown remote effects require reconciliation and target-lock retention;
  no exactly-once deployment or automatic cancellation guarantee is offered.
- Crypto adequacy/costs, exact isolation controls, receiver recovery semantics,
  canonical tuple/hash, schema/error/permission fixtures, report consumers and
  final UX composition remain unresolved WP2–6 evidence, not draft defaults.

## Final IA-ADR dispositions — 2026-10-10

All eight bounded design choices are **Accepted** under the [maintainer decision](maintainer-decision-2026-10-09.md). The qualification below establishes their feasibility for the declared profile; production delivery remains in the owning stories.

| Record | Disposition | Rationale and acceptance evidence |
| --- | --- | --- |
| IA-ADR-01 | Accepted | Tier0/1 and shared-core posture retained; scope corpus plus closed-registry negative vectors reject excluded modes |
| IA-ADR-02 | Accepted | WP2 proves verified session/audience/scope denials and bounded existing PBKDF2 primitives; application auth remains16.1/16.2 |
| IA-ADR-03 | Accepted | WP3 proves independent SQLite ownership, fencing, epochs, committed output and abrupt restart; no HA/capacity claim |
| IA-ADR-04 | Accepted | WP4 real pinned OpenTofu/provider proves the named non-root Linux ARM64 profile; other tools/platforms need their own qualification |
| IA-ADR-05 | Accepted | Synthetic and actual saved-plan receiver tests prove bound grants, original bytes, crash/replay and conservative unknown locks |
| IA-ADR-06 | Accepted with concrete selection | Relational run/report linkage preserves reportv2; separate provenancev1 and exact-byte report snapshot digest; WP6 API/agent/CLI/raw-client/action consumer probes passed |
| IA-ADR-07 | Accepted within recorded limits | Epoch invalidation/unknown locks and bounded resources tested; disposable anchored custody covers process/container restart, with production persistent storage/recovery/load owned later |
| IA-ADR-08 | Accepted | Narrative remains downstream and optional; no new AI subsystem or model-issued authority is admitted |

Evidence: [WP2](wp2-identity.md), [WP3](wp3-sqlite.md), [WP4](wp4-containment.md), [real WP5](wp5-real-custody.md), [WP6](wp6-contract-assessment.md), [WP7](wp7-readiness.md). Independent technical reviews resolved recorded defects. The maintainer's direct approval is distinct from that agent review; a second human reviewer is not claimed.
