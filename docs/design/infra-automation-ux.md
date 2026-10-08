---
project: deploywhisper
release: v1.5.0
epic: 16
date: 2026-10-07
status: planning-adopted-rendering-unverified
implementation_gate: story-16.0-contract-spikes-and-readiness
---

# Infrastructure Automation UX contract

This planning contract adopts the bounded v1.5.0 feature in the [release plan](../../_bmad-output/planning-artifacts/infra-automation-v1.5.0-release-plan.md). It specifies the supported journeys and acceptance obligations; it does not certify implemented screens, production behavior, or visual parity. Story 16.0 must resolve authentication, receiver, collection isolation and saved-plan custody contracts before dependent UI work is ready. No feature screenshots or Compose/browser results exist yet.

## Product and design authority

The experience is a project-scoped preflight followed by an authenticated human decision and a handoff to an existing delivery pipeline. DeployWhisper does not apply or destroy infrastructure. Canonical reports remain advisory; workflow eligibility, human decisions and external delivery outcomes are separate facts.

Use the existing React shell, ProjectSwitcher, global search and permanent `/reports/{id}` links. The Dashboard retains its current information budget, Latest Briefing card and upload flow. Add no automation KPI cards, secondary search bar, assistant launcher or deployment button to the Dashboard. Automation is a dedicated navigation destination. Existing global search may expose authorized automation records only after its scoped API contract is defined; a second global index is not assumed.

The [approved v3 mockup](deploywhisper-redesign-v3.jsx) wins where exact visual values differ. Reuse `frontend/src/theme/tokens.css`, `tokens.ts` and existing `Card`, `Button`, skeleton, badge, `MonoRef` and `SegmentedTabs` primitives. Package fonts locally and use `lucide-react`; the mockup's CDN import and demo data are not production implementation instructions. Do not revive the older coral palette, DM Sans/DM Mono, radius or typography values still present in historical UX sections. Do not introduce a chart/graph library or new dependency for these screens. New screen composition requires review and composed-app evidence; reuse of tokens alone is not proof of pixel parity.

Supported P0: published workflows, uploaded-artifact preflight, isolated OpenTofu/Terraform collection, run history, human decision inbox, GitHub receiver handoff, explicitly declared units, signed intake/CLI, and runner/operator views. AI composition/mapping/planning/diagnosis, package inventory, visual DAG builder, schedules, multiadapter catalogs, environment promotion and deploy/apply buttons are deferred. Existing optional report narrative may render; disabling AI must leave the entire deterministic path usable.

## Navigation and conceptual contracts

These adopted root SPA route names preserve the feature PRD namespace; they are not promises that endpoints already exist. Story 16.0/16.3 must publish the actual schema, permission and state contracts before implementation. All resources are scoped to the selected project on the server; changing ProjectSwitcher must clear stale forms, decisions and cached eligibility before loading another project.

| Root route | Screen and information budget | Conceptual API resources | Story |
| --- | --- | --- | --- |
| `/infra-automation` | Workflows and runs, using local tabs; one primary create/start action per zone | Workflows, revisions, run list, capabilities | 16.7 |
| `/infra-automation/workflows/{id}` | Template/YAML draft, validation errors, immutable revision history and publish/archive actions | Draft validation/save, publish/archive, revisions | 16.7; persistence 16.4 |
| `/infra-automation/runs/{id}` | Summary, ordered steps, linked report, decision and external outcome; logs/details below | Run snapshot, steps, evidence, linked report, cancellation, handoff receipts | 16.7, 16.9, 16.15 |
| `/infra-automation/approvals` | Inbox filtered by project, pending/expired/decided state and environment; exact review opens in run context | Decision requests, eligibility, approve/reject and audit | 16.9 |
| `/infra-automation/runners` | Health/capability table and scoped enrollment/revocation; no credential inventory | Runner health, supported capabilities, enrollment, revoke/rotate | 16.15; protocol 16.12 |
| `/infra-automation/inventory` | Explicit unit/dependency table and deterministic preflight waves, with confirmation | Unit-map validation/revision and run snapshot | 16.16 |
| `/settings` automation section | Feature enablement, registered receiver targets, trust configuration and operator recovery links | Automation settings, targets, quotas, recovery/audit | Browser integration: 16.18 Packet 18.6; earlier APIs: 16.4/16.10 |

API concepts may live under `/api/v1/infra-automation`; linked reports use existing report APIs with the new verified authority checks. Story 16.7 Packet 5 owns the named-account browser entry/logout/expired-session and recovery-guidance screens using earlier 16.1/16.2 local-account APIs. Entry route and wire contract freeze in 16.0; bootstrap remains operator-held and this UI introduces no email/SSO provider. Signed triggers and CLI share server authority and run links; they do not create alternative browser approval semantics.

Feature off: hide the normal Automation navigation entry, and show a concise unavailable state on direct entry. Administrators can find enablement in Settings. Authorized operators must retain read-only history and reconciliation access for existing accepted/unknown external work; disabling the feature revokes unconsumed grants and new starts, not historical evidence. Unauthorized users see a generic denial without record names, logs or receiver details. Existing uploaded analysis outside automation remains available under its sanctioned contract.

## Workflow and run journeys

1. Choose a project and supported template or upload-first workflow. The editor shows the closed supported step types and inline errors with step/field location. Save draft and Validate are separate from Publish. A successful validation is not a published executable revision.
2. An authorized human publishes an immutable revision. Starting a run shows its revision, selected environment/target, declared units, source/input snapshot and collection mode. Unsupported modes fail explicitly; a draft cannot start.
3. Upload supported artifacts or select an enrolled qualified collector. Show file validation and limits before submission; do not invite binary plans, state or credentials. Collection selection includes the approved source commit and trust profile. A new source/evidence set creates a new run/decision context.
4. Run detail shows actual stages and timestamps, not invented percentages: queued, collecting/uploading, analyzing, awaiting decision, handoff and reconciliation. The ordered step table exposes skipped/failed/timed-out steps and retry eligibility. A failed or partial analysis offers correction/re-run and cannot silently become approval-ready.
5. Open the immutable linked report using its normal tabs, verdict and evidence hierarchy. The run shows advisory verdict and workflow gate separately. The existing report presentation label `PROCEED` must not change canonical `go`/`caution`/`no-go` values or be interpreted as an approval.
6. Review the exact decision packet, approve/reject if eligible, then track handoff and external outcome separately. Show a durable decision receipt with authenticated actor, timestamp, reason, profile and the bound evidence/action identity.

No primary button is labeled Deploy or Apply. An eligible action may be labeled “Approve handoff”; upload-only advisory handoffs say that exact saved-plan execution is not authorized and display unavailable repository provenance as a limitation. The decision packet names advisory-request versus exact-plan authorization explicitly; an advisory receipt cannot authorize apply. Publication is a workflow configuration action, not a deployment approval. The API enforces every permission independently of whether a button is visible.

## Human decision packet

The review summary must make project, environment, registered target, requested action, advisory verdict, gate result, evidence freshness and decision deadline visible before the decision controls. Supporting sections provide the complete immutable packet without hiding a material mismatch behind an expansion:

| Packet item | Required presentation |
| --- | --- |
| Workflow and requester | Published revision/digest, inputs snapshot, verified requester and project/workspace |
| Source | Repository identity and exact immutable IaC commit for collected/exact-plan paths; explicitly unavailable source for upload-only advisory review, never invented provenance. Pipeline workflow identity/ref is separate. |
| Evidence | Permanent report link, report schema/digest, collection time, source/trust flags, sanitized artifact digests and redaction version |
| Saved plan | Availability/expiry of the operator-controlled retained plan, opaque custody handle and raw-local identity; no plan contents, state or secret-bearing path download |
| Scope | Confirmed unit-map revision/digest, affected/prerequisite units, exact environment and registered target |
| Policy and action | Policy version, eligibility and non-overridable blocks, exact screened payload/target or equivalent typed field summary |
| Time | Evidence freshness deadline, approval expiry and the effective earliest deadline, with absolute timestamp/time zone and readable remaining time |
| Decision model | Shared approval with requester/reviewer separation, or authenticated single-operator acknowledgement explicitly labeled as such |

Show full hashes on demand with accessible selectable text; shortened display must not conceal a mismatch. Never show a receiver approval grant or credential as evidence. Permission/reason requirements come from the server, and hard blocks cannot be bypassed through a reason field.

Shared approval rejects requester self-approval. Single-operator mode labels the action “Acknowledge handoff” and does not claim independent review/four eyes. The account's human classification is an authorization rule, not proof of a physical click. Agent/service/runner principals cannot publish or approve. Old caller-supplied role/actor headers never establish identity, including on linked report, policy and settings paths reused here.

The server revalidates the complete packet, membership, feature state, policy and deadlines at decision, dispatch and receiver admission. The browser does not authorize from a countdown or cached eligibility. Any changed/expired evidence, source, payload, target, policy or unit snapshot displays a specific “Review required again” state with the correct next action. An expiry during an open confirmation fails safely and preserves the entered reason for local correction without resubmitting the old decision. A lost decision response requires reloading the durable receipt before another submission.

## External delivery and cancellation

Run execution status and external delivery status have separate labels/columns. Analysis completed, human approved and GitHub dispatch accepted each mean only that recorded fact. External queued/running/succeeded/failed/unknown needs an authenticated correlated receipt or reconciliation. A GitHub run URL must be screened, authorized and bound to the recorded operation/source; receiving a run ID is not deployment success.

Canonical pre-handoff outcomes distinguish `stopped_by_gate` (policy/safety gate), `rejected` (human decision), `expired` (decision/evidence deadline), `timed_out` (run deadline), `cancelled` and `failed`. Display these reasons explicitly rather than collapsing them into a success/failure chip. The final enum/API contract is qualified in Story 16.0.

`delivery_unknown` displays “Delivery outcome unknown” with last confirmed timestamp, operation reference and operator reconciliation action. No automatic or user one-click blind resend is offered. Explain: “The pipeline may have accepted this request. Check its recorded outcome before sending another request.” Keep target-lock status visible; elapsed time or local cancellation cannot establish that the target is free.

Before dispatch, Cancel requests cancellation and waits for the server's confirmed state. After dispatch/acceptance/uncertainty, label the action “Request cancellation” where supported and explain that the external pipeline may still be running. Show cancellation requested separately from confirmed external stop. Reconciliation or an authorized audited intervention resolves uncertainty; a UI action cannot silently release the target lock. Feature disable, role revocation and restore can invalidate outstanding approval while preserving accepted/unknown operations for reconciliation.

## Runner and collection UX

Runner rows show configured identity, authorized project/target scope, declared supported tools/versions/profile, last heartbeat, active attempt and online/stale/offline state. Health does not certify isolation or truthfulness. Show configured/qualified trust profile separately from connectivity and show when a runner cannot satisfy the requested collection contract. Unsupported tool/profile/version, unavailable runner, lease loss, retention expiry and collection truncation each provide a specific correction action.

Enrollment is an administrator-scoped one-time reveal with expiration and explicit close/reissue behavior. Keep enrollment/rotation secrets only in a protected transient response/view: no URL/query string, browser persistence, logs, audit payload or automatic clipboard copy. Closing, switching project or losing authorization clears the view. If a user deliberately copies a token, explain that clipboard history can retain it; do not rely on clipboard clearing as a security boundary. Show revoked/rotated credential state without redisplaying secret material. Runner configuration belongs to the operator, not an arbitrary command field in the browser.

Collection choices carry a short useful explanation: “Planning can execute repository and provider code. Use an approved source and an isolated runner with limited credentials.” Do not bury this behind a generic safe/check-only claim. Untrusted PR sources are denied for production credential profiles by default, with guidance to use supported uploads or an approved restricted profile. Never request pasted provider secrets through workflow YAML or a settings free-text field.

Collection timeline includes actual source pinning, collection, screening, upload and analysis outcomes; expose redacted logs as an optional bounded view with timestamps, sequence gaps and truncation indicators. Polling cannot steal focus or continuously announce every log chunk. Raw plan bytes/state are never downloadable from DeployWhisper, and logs do not claim perfect redaction. Run detail distinguishes received content determinism from collector trust.

## Declared units and operator flows

Use an accessible table/form for unit ID, source/path identity, environment/target, explicit prerequisites and affected scope. Validate unknown IDs/cycles inline and show the deterministic wave order as an ordered table/list. The operator explicitly confirms the unit-map snapshot before a run. This is collection/review order, not proof that upstream provisioning is complete; new downstream plans after infrastructure changes require new analysis/approval. No inferred edges, drag-and-drop graph or visual DAG editor is part of P0.

Operator Settings and recovery views provide scoped feature/target configuration, published limits, health warnings, outstanding target locks and links to retention, credential rotation, upgrade/restore and reconciliation procedures. Read-only history remains available where needed for incident review. Privileged interventions identify the consequence and require a reason and durable audit. Signed-trigger origin, source identity and manual/CLI initiation appear in the same run history; no service credential may convert itself into a human reviewer.

## Common states and accessibility

| State | Required behavior |
| --- | --- |
| Loading | Existing skeletons and concise actual-stage status; no placeholder metrics/eligible buttons |
| Empty | One contextual explanation and authorized next action: create workflow, start uploaded preflight or enroll runner |
| Disabled/unsupported | Reason adjacent to control, permitted recovery link; never a silent fallback collector/target |
| Unauthenticated | Supported identity-profile entry with safe return route; clear transient secrets and never preserve approval submission |
| Denied/missing | Generic scoped denial/unavailable view without leaking object existence or prior project's contents |
| Validation/conflict | Field/step errors plus summary; stale revision or concurrent decision reloads exact server state |
| Network loss | Retain nonsecret draft edits, mark last-known state/time and disable consequential actions until fresh eligibility |
| Expired/revoked | Explicit fresh-review requirement; historical receipt preserved and new submission blocked |
| Failed/degraded | Explain the known failure, limits and permitted retry; no GO/success treatment based on partial results |

Use semantic headings/landmarks, real form labels, table captions/column headers and named row links rather than click-only rows. Sorting controls expose direction; errors link/focus their fields. Long source/digest values wrap or have accessible overflow without losing meaningful content. Decision confirmation identifies the target/action and traps focus correctly, supports Escape, and restores focus to its trigger. After a failed submit focus the error summary; after success focus the durable receipt heading. Tabs need keyboard navigation, associated panels and correct focus semantics; the current `SegmentedTabs` primitive alone does not prove that behavior.

Status always includes text and must not depend on color. Use existing focus/reduced-motion tokens. Live updates announce meaningful stage changes politely, not every log line; critical invalidation is explicit without submitting a pending decision. Keep content readable at zoom and tablet widths; tables may scroll in labeled containers with textual summaries, but approval scope/time/action remain discoverable. No new screen inherits a formal accessibility-compliance claim without qualification.

## Acceptance and remaining readiness evidence

| Story | Required UX acceptance evidence |
| --- | --- |
| 16.0 | Selected identity profile; final routes/API/state/error matrix; decision packet, receiver topology/custody and collection-trust choices agreed; reviewed screen composition |
| 16.7 | Actual browser named-account sign-in/logout/expiry/recovery guidance plus composed template/draft/validate/publish/upload/run/report journey; real API/seed data; feature-off/denied/loading/empty/errors; unchanged Dashboard budget |
| 16.9 | Keyboard-only authenticated decision; shared self-approval denied and honest acknowledgement; complete packet; expiry/mutation/revocation races; durable receipt |
| 16.11 | Accepted versus terminal versus unknown external outcome; no blind resend; correlated receipt; post-dispatch cancellation/reconciliation contract shown |
| 16.15 | Real qualified isolated runner to report; heartbeat/stale/offline/caps; redacted bounded logs; cancellation/lease/truncation/unsupported states; transient enrollment secret handling |
| 16.16 | Explicit unit/dependency edit/confirm; cycle/unknown rejection; deterministic accessible wave table; collection order clearly separate from deployment outcome |
| 16.17 | Manual, signed-trigger and CLI origins/source snapshots in run history; shared permissions; service/agent approval denied |
| 16.18–16.19 | Admin `/settings` enablement/targets/quotas/retention/TTL browser controls with nonadmin/conflict/disable tests; operator recovery/retention/help aligned to tested contracts; upgrade/restore UX; full composed E2E/a11y/screenshots and independent review |

Implementation must run `npm run ui:typecheck`, `npm run ui:test` and `npm run ui:build`, then `docker compose up -d --build`, wait for `http://localhost:8080/api/v1/health`, seed synthetic authorized data and run Playwright against `BASE_URL=http://localhost:8080` using root SPA routes. Capture required 1440/760-width screenshots and keyboard/a11y/error/unknown-state evidence from the composed FastAPI app, then `docker compose down`. The relevant expanded browser suite must cover these new journeys; passing existing report tests alone is insufficient. Record commands/results in each story's Dev Agent Record. Backend-for-UI changes require their own labeled PR under repository rules.

This document resolves planning-level scope and flows only. Identity mechanism, exact wire enums/routes, receiver admission and retained-plan custody, isolation profile and reviewed final screen compositions remain Story 16.0 gates. Rendering, keyboard, contrast, Compose/runtime and production acceptance are unverified until implemented. No story is moved to ready-for-dev or done by this UX artifact alone.
