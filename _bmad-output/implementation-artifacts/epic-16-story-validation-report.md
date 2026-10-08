# Epic 16 story context validation

Date: 2026-10-07
Scope: independent documentation review of all 20 dedicated Story 16.0–16.19 specifications for v1.5.0.

## Review boundary

This review applies the installed `bmad-create-story` workflow/checklist against the mandatory project context, canonical feature PRD, 72-row active requirement inventory, Epic 16, architecture §25, feature UX and implementation-readiness report. It assesses preparation, not completed implementation. No RFC approval, feasibility spike, application test, runner/receiver qualification, Compose/browser run or production release was executed by this review.

## Findings and disposition

| Finding | Required disposition | State |
| --- | --- | --- |
| 16.0 primary traceability originally summarized FR-001/041 without their exact canonical text/proof | Preserve exact text/proof in the dedicated file, alongside supporting feasibility coverage | Corrected; machine recheck passes |
| 16.0 pinned-version note described an obsolete project-context Pydantic discrepancy | Align with corrected mandatory context Pydantic 2.13.3 and actual lockfiles | Corrected; context, pyproject.toml and requirements.txt agree |
| 16.8 named a second generic validation module despite 16.3 owning workflow validation | Reuse the owned validator or explicitly name a separate runtime eligibility boundary | Corrected; static workflow_validation.py is reused and approval_eligibility.py owns runtime checks |
| Settings UX table assigned enablement/target/operating settings to stories with no explicit frontend packet | Assign concrete settings integration ownership, negative GWT cases and mandatory composed-app proof; upstream backend slices carry derived UX obligations | Corrected; 16.18 AC7/Packet 18.6 owns browser settings, using earlier APIs without a forward UI dependency |
| Named-account browser access lacked explicit login/session UI ownership | Assign supported browser login/logout/expired-session journey without inventing an identity provider or weakening CSRF | Corrected; 16.7 AC6/Packet 5 owns actual browser sign-in/logout/expiry/recovery-guidance proof |
| Several future-publication notes could cause repeat permission requests despite explicit existing session authority | Honor existing explicit authorization; retain actual public governance evidence and seven-day review requirements | Corrected; future action notes honor existing explicit session authorization |

## Checks completed

- Exactly 20 dedicated files exist, with stable sprint-compatible identifiers.
- Every mapped Epic 16 file contains its active canonical requirement ID, exact text and proof. All 72 active requirements are covered; shared mappings describe owned slices rather than granting early delivery credit.
- Relative references resolve. Claimed brownfield reuse was checked against source paths/symbols and package scripts. New domain/runner/receiver paths are prospective additions.
- Dependencies match the earlier-only canonical DAG, including 16.14 depending on 16.11 and Story 12.5 preceding runner distribution. Scoped doubles prevent implicit forward implementation dependencies.
- Broad stories 16.0, 16.5, 16.11, 16.18 and 16.19 contain bounded packets with ownership, write scope and acceptance evidence. Named implementer assignment and revised estimates remain execution obligations.
- Human identity/session/bootstrap/recovery, server memberships, role-header/legacy-route bypass and nonhuman credential audience denial are explicit.
- Claims and every stale heartbeat/log/upload/completion are fenced; cancel/lease expiry cannot unlock unknown external work.
- Approvals bind immutable evidence/source/target/payload/policy/custody/deadlines/epochs. Upload-only unknown source cannot acquire exact-plan authority or fabricate a commit.
- Raw saved binary plans remain protected locally; actual file bytes, no-follow custody and restart/tamper/expiry/replan checks are required. Synthetic receiver proof is distinct from real-tool integration qualification.
- Consume/start/completion crashes, durable same-operation recovery, uncertain remote outcomes and live disable/revoke/restore authority are covered without universal exactly-once claims.
- Constructor/fixture searches, exact affected pytest shards, explicit new test-directory registration, repo-wide Ruff format checks and per-slice regressions are required.
- Rendered stories require production Compose builds, seeded actual APIs, root SPA routes, Playwright/axe/keyboard and 1440/760 screenshots. Backend-only slices record UI applicability explicitly.
- Story 16.0 requires a real public PR, applicable CODEOWNERS requests, at least seven calendar days and an actual maintainer decision. A draft, user planning approval or elapsed time cannot fabricate acceptance.

## Final recheck evidence

The recovered-session review checked the corrected story files against the saved findings rather than recreating them. All 20 contexts are present; the 72 active rows yield **396 exact ID/text/proof checks across 132 Epic 16 story mappings, with zero mismatches**. All task boxes remain unchecked. Every story retains the required repo-wide Ruff formatting and local-CI verification obligations. Story-relative document links resolve. The proposed workflow-validation and runtime-eligibility files are correctly marked prospective, while the existing Settings screen path resolves.

The corrected login and settings acceptance cases match feature UX and derived Epic 16 UX-13 ownership. Named browser login and admin settings require real composed API-backed journeys, keyboard/axe checks and 1440/760 screenshots; preseeded cookies and Vite runs cannot replace those proofs. Earlier backend slices do not require the future settings UI for their own acceptance. Approval/receiver/custody checks retain the full tuple and current-authority boundaries; protected synthetic receiver admission is distinct from later real collected-plan qualification.

## Final status reconciliation

**Verdict: story preparation passes; Story 16.0 is ready-for-dev only for governance and disposable synthetic qualification.** No unresolved documentation defect remains from this review. Story files, sprint tracker and the preparation/readiness follow-up agree: Epic 16 is in-progress for preparation/qualification; 16.0 is ready-for-dev within its explicit scope; 16.1–16.19 remain backlog despite refined context. The current aggregate is 121 stories: 84 done, 16 ready-for-dev, 2 review and 19 backlog. This review confirms the current reconciliation, not completed runtime feature work.

IR-04 document refinement can close against prepared bounded contexts. Execution sizing/re-estimation remains pending real 16.0 spike evidence. IR-01 public governance, IR-02 feasibility and IR-03 frozen interfaces remain open. The product is not implementation-ready or production-qualified.
