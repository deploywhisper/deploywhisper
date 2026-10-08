# Epic 16: v1.5.0 Story Preparation Report

Prepared: 2026-10-07. Workflow: `bmad-create-epics-and-stories`, then `bmad-create-story` for the explicitly selected first Story 16.0.

## Outcome and execution boundary

All **20 dedicated story contexts (16.0–16.19)** are created from the adopted user-value epic, canonical 60 FR/12 NFR, architecture, UX and implementation-readiness findings. Existing canonical IDs, release history and non-Epic-16 statuses are preserved. Story 12.5 remains the separate SBOM release enabler.

**Story 16.0 is ready-for-dev for governance and disposable synthetic qualification only.** It does not implement production authentication, automation routes, runner services or deployment. Its seven bounded work packets prepare/obtain the public RFC outcome, qualify identity and SQLite fencing, prove real containment and exact-plan custody/receiver recovery, freeze wire/report/UI contracts, and rerun readiness. No task, public review, experiment or qualification result is marked complete by creating the context.

Stories **16.1–16.19 remain backlog** despite prepared files because RFC/16.0 feasibility, final interfaces and their earlier dependencies remain unmet. Prepared is not a delivery or production-readiness status. Epic 16 is in-progress for preparation/qualification, not completed feature work.

## Ready next task

Use `bmad-dev-story` with [the Story 16.0 context](16-0-adopt-and-qualify-infra-automation-contract.md), restricted to its execution scope. Follow actual session authorization for future publication/credentials/dependencies; do not invent public approvals or repeatedly request authority already explicitly granted. Real public RFC acceptance still requires the documented review window and recorded decision. An unavailable Linux/tool/profile or failed case is a blocker, not a simulated pass.

## Complete context index

| Story context | Current status | Advancement boundary |
| --- | --- | --- |
| [16.0: Adopt and Qualify the Infra Automation Contract](16-0-adopt-and-qualify-infra-automation-contract.md) | `ready-for-dev` | Governance and disposable synthetic qualification only |
| [16.1: Verified Human Principal And Session Lifecycle](16-1-verified-human-principal-and-session-lifecycle.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.2: Trusted Project Memberships And Automation Permissions](16-2-trusted-project-memberships-and-automation-permissions.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.3: Closed Workflow Schema And Validator](16-3-closed-workflow-schema-and-validator.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.4: Scoped Workflows And Immutable Revisions](16-4-scoped-workflows-and-immutable-revisions.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.5: Durable Engine And Fenced Recovery](16-5-durable-engine-and-fenced-recovery.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.6: Uploaded Artifact Preflight And Report Linkage](16-6-uploaded-artifact-preflight-and-report-linkage.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.7: Workflow Editor and Run History UI](16-7-workflow-editor-and-run-history-ui.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.8: Evidence Bound Decisions and Freshness](16-8-evidence-bound-decisions-and-freshness.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.9: Human Approval Inbox and Decision UX](16-9-human-approval-inbox-and-decision-ux.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.10: Registered Targets, Outbox, Grants and Locks](16-10-registered-targets-outbox-grants-and-locks.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.11: GitHub Receiver and Outcome Reconciliation](16-11-github-receiver-and-outcome-reconciliation.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.12: Runner Enrollment and Attempt Protocol](16-12-runner-enrollment-and-attempt-protocol.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.13: Isolated Runner Execution Profile](16-13-isolated-runner-execution-profile.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.14: OpenTofu/Terraform Collection and Provenance](16-14-opentofu-terraform-collection-and-provenance.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.15: Runner Health and Collection UX](16-15-runner-health-and-collection-ux.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.16: Declared Multi Unit Preflight Planning](16-16-declared-multi-unit-preflight-planning.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.17: Signed Trigger Intake and CLI](16-17-signed-trigger-intake-and-cli.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.18: Operator Recovery, Retention and Network Readiness](16-18-operator-recovery-retention-and-network-readiness.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |
| [16.19: Production Qualification and v1.5.0 Release](16-19-production-qualification-and-v1-5-0-release.md) | `backlog` | Refined context; RFC/16.0/interfaces/earlier dependencies held |

## Readiness findings converted into actionable work

| Finding | Prepared work / evidence obligation | Current disposition |
| --- | --- | --- |
| IR-01 Public RFC acceptance | 16.0 WP1: real PR/open date/CODEOWNERS review/discussion/minimum seven calendar days/maintainer outcome | Open; no publication or outcome fabricated |
| IR-02 Feasibility | 16.0 WP2–WP5: identity/CSRF/revocation/scope, two-connection SQLite fencing/crashes, real hostile-source isolation, actual saved-plan custody and same-operation receiver recovery | Open; all experiments unrun |
| IR-03 Final contracts | 16.0 WP6: typed workflow/runner/receiver/source variants, report/hash compatibility, route/errors/permission matrix and reviewed UX composition | Open; no placeholder treated as frozen executable API |
| IR-04 Story refinement | All 20 dedicated specifications; explicit ownership/negative acceptance/write scope/proof, broad packets in 16.0/16.5/16.11/16.18/16.19 | Document refinement complete; named implementer assignment and spike-based execution sizing remain execution obligations |

## Review corrections applied

- Static workflow validation is reused from 16.3; 16.8 has a separate runtime approval-eligibility boundary instead of a competing generic validator.
- 16.7 explicitly owns local-account browser entry/logout/expired-session and recovery guidance using earlier 16.1/16.2 APIs.
- 16.18 Packet 18.6 explicitly owns admin automation `/settings` controls using earlier 16.4/16.10 APIs; early backend stories have no forward UI acceptance dependency.
- Existing library pins prevail; mandatory context now correctly identifies Pydantic 2.13.3. No dependency upgrade was made.
- Shared requirement tables retain full canonical text/proof while each slice's tests prove only owned contracts; real collector/receiver integration remains in 16.14/16.19.
- Publication instructions honor existing explicit session authorization while preserving real public governance evidence.

## Planning coverage and delivery order

The complete 72 active requirement IDs/text/proofs are retained in every mapped dedicated story; the original 179 vision rows keep their prior explicit dispositions. Complete dependency sequence remains earlier-only, including 16.14→16.11 and 12.5 before runner distribution. User value is one scoped preflight/decision/handoff capability; no new epic or release scope was invented to solve refinement.

New stories create only needed entities and tests/docs per slice. Future UI qualification uses the composed FastAPI root routes, real seeded APIs, Playwright/axe/keyboard and screenshots; backend-only qualification records applicability. No live infrastructure, credentials, raw state or saved binary plan is committed by preparation. All task boxes remain unchecked.

## Validation

Final independent context review and aggregate documentation verification are recorded in [the validation report](epic-16-story-validation-report.md) and the completion entry below. Runtime feature/Compose/cloud/runner/receiver/load qualification remains future work; documentation tests cannot establish it.

## Completion verification

- Independent context review passed after six preparation findings were corrected (exact primary traceability, actual dependency pin, validator reuse, settings ownership, login ownership and existing-authorization caveat).
- All 20dedicated contexts are present with unchecked implementation tasks. The 72 active requirements match all 132 mapped story rows: 396 ID/text/proof checks, zero mismatches. No relative story reference is broken.
- Tracker/epic/status-map agreement: 16.0 ready-for-dev for governance-and-synthetic-qualification-only; 16.1–16.19 backlog; Epic 16 in-progress for preparation/qualification. All 153 other previous status entries preserved. Current 121 stories: 84 done, 16 ready, 2 review, 19 backlog.
- `./.venv/bin/python -m unittest discover -s tests/test_docs -q`: 51 passed. Aggregate schema/link/status/coverage/dependency/source-digest assertions passed. `git diff --check`: passed. Story files were made visible in the review diff without committing them.
- No qualification task, public RFC review, production feature, browser/runner/receiver/cloud/load test or release was performed. Next BMad action is explicit `bmad-dev-story` on 16.0 within its limited execution scope; later feature promotion awaits actual evidence.
