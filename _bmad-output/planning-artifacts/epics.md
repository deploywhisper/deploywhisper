---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/planning-artifacts/ux-design-specification.md
  - _bmad-output/project-context.md
sourceOfTruth: finalized-prd-2026-05-01
status: ready-for-implementation-readiness-review
---

# DeployWhisper - Epic Breakdown

## Overview

This document regenerates the DeployWhisper epic and story plan from the finalized PRD and the aligned architecture.

The previous six-epic roadmap is superseded. Existing implementation stories should be treated as historical until they are reconciled against this new plan.

This plan follows the finalized PRD's structure:

- Fully open-source and self-hosted only.
- Evidence Law first.
- Project/workspace/RBAC foundation before broad context hardening.
- Advisory-first core with optional enforcement adapters.
- Day-zero incident memory, benchmark honesty, external scanner ingestion, AI-agent safety, documentation, governance, and CNCF readiness as first-class scope.

## Requirements Inventory

### Functional Requirements

#### Intake and classification

- **ING-01:** Accept one or more artifacts from supported toolchains in a single analysis.
- **ING-02:** Auto-detect artifact type without requiring manual labels for normal cases.
- **ING-03:** Support partial analysis when not all related artifacts are available.
- **ING-04:** Detect unsupported artifacts and explain why they were excluded.
- **ING-05:** Detect sensitive files and block unsafe downstream handling.
- **ING-06:** Preserve a submission manifest showing accepted, excluded, partially parsed, and failed artifacts.
- **ING-07:** Accept Terraform plan JSON as a first-class input.
- **ING-08:** Accept project/workspace key in CLI, API, and integration flows.
- **ING-09:** Preserve artifact provenance and redaction status.

#### Project, workspace, and RBAC

- **PRJ-01:** Define instance, project, workspace/environment, service, resource, analysis run, report, and connector objects.
- **PRJ-02:** Scope reports to a project.
- **PRJ-03:** Scope incidents to a project.
- **PRJ-04:** Scope deployment outcomes to a project and optional workspace.
- **PRJ-05:** Scope external scanner imports to a project.
- **PRJ-06:** Scope connector credentials to instance, project, or workspace.
- **PRJ-07:** Support project-aware RBAC roles.
- **PRJ-08:** Accept or derive project keys in CLI, API, UI, and workflow integrations.
- **PRJ-09:** Include project/workspace scope in context graph nodes and evidence items.
- **PRJ-10:** Document project modeling patterns for monorepos, multi-repos, Terraform workspaces, Kubernetes clusters, and platform teams.

#### Normalization and evidence

- **EVD-01:** Normalize supported artifacts into a shared internal change model.
- **EVD-02:** Each finding references one or more concrete evidence items.
- **EVD-03:** Evidence items identify artifact, location, resource, operation, project, and contextual source where applicable.
- **EVD-04:** Reports distinguish deterministic findings, derived findings, external evidence, model-inferred explanations, and user-provided context.
- **EVD-05:** Reports surface confidence and uncertainty for key findings and overall verdict.
- **EVD-06:** Reports explain main contributors to the overall risk score.
- **EVD-07:** Incomplete context produces explicit uncertainty instead of implied certainty.
- **EVD-08:** Evidence items persist with reports for audit, comparison, and benchmark replay.
- **EVD-09:** High and critical findings require at least one deterministic evidence item.
- **EVD-10:** Narrative generation failure does not remove deterministic evidence or verdict.
- **EVD-11:** Evidence Law status is visible in reports.
- **EVD-12:** CI fails when fixtures generate high/critical findings without deterministic evidence.

#### Risk intelligence

- **RSK-01:** Produce a unified advisory deployment risk verdict.
- **RSK-02:** Classify findings and verdicts by severity.
- **RSK-03:** Detect cross-tool interactions that increase risk.
- **RSK-04:** Generate reviewer-oriented explanations of operational risk.
- **RSK-05:** Generate actionable remediation or verification guidance.
- **RSK-06:** Produce rollback guidance and rollback complexity score.
- **RSK-07:** Distinguish product recommendation from human decision.
- **RSK-08:** Continue deterministic analysis if narrative generation fails.
- **RSK-09:** Provide why-not-lower and why-not-higher explanation for verdicts.
- **RSK-10:** Support an insufficient-context verdict.
- **RSK-11:** Detect AI-generated IaC risk patterns where provenance or content signals are available.
- **RSK-12:** Label public risk pattern matches separately from organization incident matches.

#### Context enrichment

- **CTX-01:** Compute blast radius using project-scoped topology context.
- **CTX-02:** Indicate when topology is stale, missing, incomplete, or conflicting.
- **CTX-03:** Ingest incident records for similarity matching.
- **CTX-04:** Surface relevant incident similarity results with match confidence and match reasons.
- **CTX-05:** Support service criticality and environment-aware risk context.
- **CTX-06:** Store deployment history sufficient for comparison and trend analysis.
- **CTX-07:** Support topology auto-discovery and source connectors without replacing the core report format.
- **CTX-08:** Support read-only Terraform state connector.
- **CTX-09:** Support optional read-only Kubernetes live-state connector.
- **CTX-10:** Support CODEOWNERS and ownership mapping.
- **CTX-11:** Support context freshness and confidence per source.
- **CTX-12:** Generate context TODOs to improve future report quality.
- **CTX-13:** Attach context source metadata to evidence items.

#### Incident memory, risk patterns, and outcomes

- **INC-01:** Support built-in public risk pattern memory on fresh installs.
- **INC-02:** Clearly distinguish public risk pattern matches from organization-specific incidents.
- **INC-03:** Support optional sample incident pack for demos.
- **INC-04:** Support markdown, YAML, and JSON incident import.
- **INC-05:** Support future imports from PagerDuty, Opsgenie, Jira, GitHub Issues, and Slack exports.
- **INC-06:** Store incident metadata, root cause, trigger change, affected services, rollback path, and prevention notes.
- **INC-07:** Compute similarity using deterministic and semantic signals.
- **INC-08:** Explain why an incident matched the current change.
- **INC-09:** Support backtesting against historical incident-causing changes.
- **INC-10:** Capture deployment outcomes for calibration.
- **INC-11:** Track false positives and false reassurance from outcome feedback.
- **INC-12:** Ensure sample incident packs contain no real customer data, no real organization names, and no non-public postmortem content without attribution and permission.

#### Review and reporting experience

- **REV-01:** Web reports present verdict first, then Evidence Law status, confidence, evidence, and details.
- **REV-02:** Reports show top findings, blast radius, rollback, risk patterns, incident memory, external scanner context, and uncertainty above the fold.
- **REV-03:** Users can inspect full findings and evidence details on demand.
- **REV-04:** Users can retrieve prior reports and compare analyses over time.
- **REV-05:** System generates concise summaries for PRs and approval threads.
- **REV-06:** Shared summaries remain explicitly advisory.
- **REV-07:** Reports support expert quick scan and detailed investigation.
- **REV-08:** Report diff shows resolved, new, and persistent risks after reruns.
- **REV-09:** Reports show context TODOs.
- **REV-10:** Report schema version is visible and machine-readable.

#### Workflow-native delivery

- **WRK-01:** Expose a stable versioned REST API.
- **WRK-02:** Expose CLI access using the same analysis core.
- **WRK-03:** Support GitHub-first workflow delivery for PR review.
- **WRK-04:** Post formatted PR summaries including verdict, Evidence Law status, top risks, evidence, blast radius, rollback, incident memory, public risk patterns, external scanner context, and uncertainty.
- **WRK-05:** Support rerun after new commits or changed artifacts.
- **WRK-06:** Support report links and machine-friendly summary payloads.
- **WRK-07:** Support future GitLab, Atlantis, HCP Terraform, Jenkins, Argo CD, Flux, and chat adapters without redesigning the core report object.
- **WRK-08:** CLI and integration flows accept project key or project ID.
- **WRK-09:** GitHub repository flows may derive default project key from repository name.
- **WRK-10:** Support pre-commit or local developer feedback mode.

#### AI-agent interfaces and AI safety

- **AIA-01:** Provide machine-readable analysis output for AI agents.
- **AIA-02:** Provide `--agent-json` CLI mode.
- **AIA-03:** Provide MCP-compatible interface or equivalent agent-callable interface.
- **AIA-04:** Treat AI-generated IaC as untrusted input.
- **AIA-05:** Detect common AI-generated infrastructure risk patterns.
- **AIA-06:** Preserve provenance metadata where available.
- **AIA-07:** Ensure AI models cannot directly create high or critical findings without deterministic evidence.
- **AIA-08:** Include prompt-injection tests for IaC comments, PR comments, incident text, scanner output, and documentation-like artifacts.
- **AIA-09:** Ensure agents cannot use DeployWhisper to autonomously approve, deploy, or remediate production changes.
- **AIA-10:** Document AI-generated IaC review workflows.

#### External scanner and complementary-tool ingestion

- **EXT-01:** Maintain documentation explaining DeployWhisper alongside existing security tools.
- **EXT-02:** Support SARIF ingestion.
- **EXT-03:** Support at least one scanner JSON format in Phase 1.5 or Phase 2.
- **EXT-04:** Label external scanner findings as external evidence.
- **EXT-05:** Prevent external scanner findings from automatically becoming high/critical DeployWhisper findings without DeployWhisper evidence and scoring.
- **EXT-06:** Include external scanner context in reports, PR comments, and API output.
- **EXT-07:** Document how AppSec, SRE, and platform teams should use scanner output with DeployWhisper.
- **EXT-08:** Surface conflicts between external scanner findings and deterministic evidence instead of silently choosing one source.

#### History, analytics, and learning

- **HIS-01:** Persist completed reports before showing final success.
- **HIS-02:** Retain audit metadata with each report.
- **HIS-03:** Users can search and filter historical reports.
- **HIS-04:** Managers can review risk trends over time.
- **HIS-05:** Capture reviewer feedback on report quality and correctness.
- **HIS-06:** Support outcome capture after deployment for calibration.
- **HIS-07:** Support benchmark and backtest workflows against historical incidents.
- **HIS-08:** Scope reports, topology, outcomes, and feedback to a project/workspace.
- **HIS-09:** Support false-positive and false-reassurance tracking.

#### Administration and customization

- **ADM-01:** Admins configure narrative-provider settings through a DeployWhisper-owned provider adapter boundary.
- **ADM-02:** Admins enable fully local-only operation.
- **ADM-03:** Admins manage topology data and freshness status.
- **ADM-04:** Admins manage incident ingestion and indexing.
- **ADM-05:** Admins add or override custom Skills and organization-specific heuristics.
- **ADM-06:** Admins manage thresholds and reporting defaults without changing core code.
- **ADM-07:** Policy adapters consume report outputs without changing advisory-first core behavior.
- **ADM-08:** Admins create and manage lightweight project/workspace records.
- **ADM-09:** Admins configure optional enforcement adapter behavior per integration.
- **ADM-10:** Admins configure external scanner ingestion per project.

#### Skills ecosystem

- **SKL-01:** Expose a Skills registry API for listing, fetching, and installing community-contributed Skills.
- **SKL-02:** Support versioned Skills with a formal manifest schema.
- **SKL-03:** Run automated test harness on every Skill submission.
- **SKL-04:** Provide Skills installer CLI.
- **SKL-05:** Provide public Skills browser UI with search and filters.
- **SKL-06:** Track skill analytics such as install counts, test pass rates, last update, and issue activity.
- **SKL-07:** Provide contribution workflow with PR template, automated linting, and reviewer assignment.
- **SKL-08:** Support trust levels: experimental, verified, core, deprecated.
- **SKL-09:** Require deterministic scenarios for verified/core Skills.

#### Benchmarks

- **BEN-01:** Maintain public benchmark corpus.
- **BEN-02:** Provide benchmark runner.
- **BEN-03:** Compare against reproducible baseline approaches.
- **BEN-04:** Publish quarterly benchmark results.
- **BEN-05:** Track precision, recall, false reassurance, evidence coverage, latency, and regression stability.
- **BEN-06:** Require expected evidence and expected verdict rationale for benchmark scenarios.
- **BEN-07:** Support backtesting against incident records.
- **BEN-08:** Benchmark reports include public scenarios-we-missed sections.
- **BEN-09:** Material misses create linked GitHub issues unless explicitly out of scope.
- **BEN-10:** Benchmark reports distinguish product limitations from benchmark limitations.
- **BEN-11:** Benchmark reports include Evidence Law violation count.

#### Open governance and CNCF readiness

- **GOV-01:** Maintain public governance documentation.
- **GOV-02:** Maintain maintainer ladder.
- **GOV-03:** Maintain public roadmap.
- **GOV-04:** Maintain contributor guide.
- **GOV-05:** Maintain code of conduct.
- **GOV-06:** Maintain security policy.
- **GOV-07:** Maintain release process.
- **GOV-08:** Maintain adopters list.
- **GOV-09:** Use public RFCs for major design decisions.
- **GOV-10:** Maintain CNCF readiness checklist.
- **GOV-11:** Maintain `MAINTAINERS.md` mapping maintainers to major areas.
- **GOV-12:** Maintain `CODEOWNERS` for major directories.
- **GOV-13:** Track maintainer coverage gaps.
- **GOV-14:** Publicly document maintainer promotion and inactivity process.
- **GOV-15:** Track contribution and community health metrics.

#### Documentation and user enablement

- **DOC-01:** Maintain a public, versioned documentation tree or docs site in the repository.
- **DOC-02:** Document every primary user journey.
- **DOC-03:** Provide self-hosted installation guides for local CLI, Docker Compose, Kubernetes/Helm, and air-gapped environments.
- **DOC-04:** Documentation does not assume a DeployWhisper-hosted SaaS service.
- **DOC-05:** Each epic includes documentation tasks and documentation acceptance criteria.
- **DOC-06:** User-facing stories are not done until required docs are updated.
- **DOC-07:** Provide first-analysis and report-interpretation guides using safe sample artifacts.
- **DOC-08:** Maintain integration guides for every supported workflow integration.
- **DOC-09:** Maintain connector guides for every supported context connector.
- **DOC-10:** Maintain API, report schema, evidence schema, webhook, CLI, and MCP references.
- **DOC-11:** Maintain security, privacy, prompt-injection, secrets-handling, and local-first provider-boundary documentation.
- **DOC-12:** Maintain operations docs for backup, restore, upgrade, scaling, observability, logs, database, workers, and troubleshooting.
- **DOC-13:** Maintain Skills authoring, testing, publishing, private Skill, and Skill trust-level documentation.
- **DOC-14:** Maintain benchmark documentation.
- **DOC-15:** Maintain contributor documentation for development setup, architecture, tests, parser authoring, connector authoring, docs authoring, governance, and releases.
- **DOC-16:** Provide docs CI for broken links, markdown formatting, generated references, and command/schema drift where practical.
- **DOC-17:** Provide release notes and upgrade notes for every user-visible release.
- **DOC-18:** Link from UI, CLI errors, API docs, and integration outputs to relevant documentation where practical.
- **DOC-19:** Maintain CNCF readiness documentation.
- **DOC-20:** Track documentation health metrics as part of project health.
- **DOC-21:** Maintain `docs/concepts/evidence-law.md`.
- **DOC-22:** Maintain `docs/concepts/project-model.md`.
- **DOC-23:** Maintain day-zero incident memory documentation.
- **DOC-24:** Maintain AI-generated IaC review documentation.
- **DOC-25:** Maintain existing-security-tools comparison documentation.
- **DOC-26:** Maintain maintainer-areas documentation.
- **DOC-27:** Maintain honest-failure-reporting benchmark documentation.

### NonFunctional Requirements

- **NFR-SEC-01:** Fully local operation must be possible.
- **NFR-SEC-02:** Raw IaC must not be sent externally by default.
- **NFR-SEC-03:** Provider credentials must not be persisted unsafely.
- **NFR-SEC-04:** Secrets must be redacted from logs, prompts, reports, and telemetry by default.
- **NFR-SEC-05:** Prompt-injection controls must be tested.
- **NFR-SEC-06:** High/critical findings must satisfy the Evidence Law.
- **NFR-SEC-07:** Project/RBAC boundaries must prevent cross-project data leakage.
- **NFR-PERF-01:** Standard PR analysis should complete in under 15 seconds at p95 for common small-to-medium changes when using local deterministic analysis and already-available project context, excluding optional remote LLM latency and unavailable external connector timeouts.
- **NFR-PERF-02:** Large artifact submissions should degrade gracefully with partial deterministic results and explicit skipped-scope details.
- **NFR-PERF-03:** Narrative generation failure or timeout must not block deterministic analysis results.
- **NFR-PERF-04:** Benchmark latency should be tracked per release, including p50, p95, p99, timed-out analyses, and deterministic-vs-narrative latency split.
- **NFR-PERF-05:** Connectors that exceed configured timeout must be marked stale/unavailable and must not block core deterministic reports.
- **NFR-REL-01:** Analysis failures must be explicit and actionable.
- **NFR-REL-02:** Partial analysis must show what was included and excluded.
- **NFR-REL-03:** Reports must persist before success is returned.
- **NFR-REL-04:** Re-running the same deterministic inputs should produce stable deterministic findings.
- **NFR-XAI-01:** Reports must be understandable to reviewers without source-code reading.
- **NFR-XAI-02:** Evidence must be inspectable.
- **NFR-XAI-03:** Uncertainty must be visible.
- **NFR-XAI-04:** Severity reasoning must be explainable.
- **NFR-XAI-05:** UI and docs should follow accessibility best practices.
- **NFR-OPS-01:** Support local, Docker Compose, Kubernetes/Helm, and air-gapped deployment paths.
- **NFR-OPS-02:** Configuration must be file/env driven where practical.
- **NFR-OPS-03:** PostgreSQL path should be available for shared/team installs.
- **NFR-OPS-04:** SQLite may be supported for local/single-node installs.
- **NFR-OPS-05:** Backup, restore, upgrade, and retention must be documented.
- **NFR-OPS-06:** Observability metrics and logs must avoid secrets.
- **NFR-DOC-01:** Docs must be sufficient for self-service installation.
- **NFR-DOC-02:** Docs must not assume SaaS onboarding.
- **NFR-DOC-03:** Examples should be copy-pasteable where practical.
- **NFR-DOC-04:** Docs should be versioned with releases.
- **NFR-DOC-05:** Docs CI should catch broken links and obvious drift where practical.
- **NFR-DOC-06:** Docs must include troubleshooting for common self-hosted failures.
- **NFR-OSS-01:** Governance, contribution, release, and security processes must be public.
- **NFR-OSS-02:** Maintainer ownership must be public.
- **NFR-OSS-03:** CODEOWNERS must route reviews for major areas.
- **NFR-OSS-04:** RFC process must be used for major changes.
- **NFR-OSS-05:** Benchmark and Skills contributions must have clear contribution paths.

### Additional Requirements

- Preserve the shared React SPA + FastAPI runtime as the baseline.
- Keep API, CLI, UI, GitHub, policy, and agent surfaces over one shared analysis orchestrator.
- Keep SQLite valid for local/single-node installs and PostgreSQL as the shared/team install path.
- Keep narrative generation downstream of deterministic evidence, context enrichment, and scoring.
- Keep provider-specific behavior behind the DeployWhisper-owned `llm/` adapter boundary.
- Treat external systems as user-owned or community-owned; do not introduce DeployWhisper-hosted dependencies.
- Keep GitHub Marketplace Action runtime in the external `deploywhisper/analyze-action` repository.
- Use Alembic for persistence migrations and explicit report schema versioning for report contract changes.
- Keep Skills markdown-based and non-executable by default.
- Ensure CI can fail on Evidence Law violations.
- Keep story status frozen until this regenerated epic plan passes implementation readiness.

### UX Design Requirements

- **UX-DR1:** Preserve verdict-first report hierarchy above the fold.
- **UX-DR2:** Show Evidence Law status, confidence, uncertainty, and context completeness near the verdict.
- **UX-DR3:** Provide evidence-on-demand inspection without losing report orientation.
- **UX-DR4:** Present blast radius, rollback, incident/risk-pattern matches, scanner context, and top findings in a scannable review order.
- **UX-DR5:** Expose partial parsing, stale topology, degraded narrative, and missing context as visible trust signals.
- **UX-DR6:** Support expert quick scan and detailed investigation in the same report surface.
- **UX-DR7:** Maintain keyboard navigation and accessible review patterns.
- **UX-DR8:** Keep warnings calm, actionable, and advisory rather than punitive.
- **UX-DR9:** Link UI states and error messages to relevant documentation where practical.
- **UX-DR10:** Preserve one-screen operational review as the primary design intent while supporting deeper drill-downs.

### FR Coverage Map

| Requirement family | Primary epic coverage |
| --- | --- |
| `GOV-*`, `NFR-OSS-*` | Epic 0, Epic 12, Epic 14 |
| `PRJ-*`, `HIS-08`, `NFR-SEC-07` | Epic 1 |
| `ING-*`, `EVD-*`, `RSK-*`, `HIS-01..02`, `NFR-SEC-*`, `NFR-REL-*` | Epic 2 |
| `REV-*`, `HIS-03`, `NFR-XAI-*`, UX-DR1..UX-DR10 | Epic 3 |
| `INC-*`, `CTX-03..04`, `HIS-05..07`, `HIS-09`, `ADM-04` | Epic 4 |
| `WRK-*`, `ADM-07`, `ADM-09` | Epic 5, Epic 11 |
| `BEN-*`, `INC-09`, `HIS-04`, `HIS-06..07`, `NFR-PERF-04` | Epic 6 |
| `CTX-*`, `ADM-03`, `CTX-08..13` | Epic 7 |
| `EXT-*`, `ADM-10` | Epic 8 |
| `SKL-*`, `ADM-05` | Epic 9 |
| `AIA-*`, `RSK-11`, `DOC-24` | Epic 10 |
| `ADM-01..02`, `NFR-OPS-*`, `NFR-SEC-*`, supply-chain requirements | Epic 12 |
| `DOC-*`, `NFR-DOC-*` | Epic 13 |

## Epic List

### Epic 0: Open Governance, Traceability, and Maintainer Ownership

Establish the public project foundation so contributors, maintainers, users, and future foundation reviewers can understand who owns what, how decisions are made, and how roadmap claims trace to requirements.

**Primary coverage:** GOV-01..15, NFR-OSS-01..05, DOC-15, DOC-19, DOC-20.

### Epic 1: Project, Workspace, and RBAC Foundation

Make project and workspace scope explicit across reports, incidents, topology, scanner imports, outcomes, feedback, UI, API, CLI, and integrations before shared usage hardens.

**Primary coverage:** PRJ-01..10, HIS-08, NFR-SEC-07, DOC-22.

### Epic 2: Trusted Evidence Core and Evidence Law

Make DeployWhisper's core report defensible by enforcing evidence-backed findings, deterministic high/critical gates, stable report schema, and graceful degradation.

**Primary coverage:** ING-01..09, EVD-01..12, RSK-01..10, HIS-01..02, NFR-SEC-01..06, NFR-REL-01..04.

### Epic 3: Report and Review Experience

Make reports fast to scan, deep enough to investigate, and honest about confidence, context, evidence, scanner signals, and uncertainty.

**Primary coverage:** REV-01..10, HIS-03, RSK-04..06, RSK-09..10, NFR-XAI-01..05, UX-DR1..10.

### Epic 4: Day-Zero Risk Patterns and Incident Memory

Make fresh installs useful through public risk patterns and build toward organization-specific incident memory, match explanations, outcome learning, and backtesting.

**Primary coverage:** INC-01..12, CTX-03..04, HIS-05..07, HIS-09, ADM-04, RSK-12, DOC-23.

### Epic 5: Workflow-Native Delivery

Put advisory reports where infrastructure review already happens: CLI, API, GitHub PRs, check runs, local developer feedback, reruns, and future workflow adapters.

**Primary coverage:** WRK-01..10, REV-05..08, ADM-07, DOC-08.

### Epic 6: Benchmarks, Calibration, and Honest Failure Reporting

Make trust measurable through a public corpus, benchmark runner, honest failure reports, latency metrics, outcome calibration, and regression tracking.

**Primary coverage:** BEN-01..11, INC-09..11, HIS-04, HIS-06..07, NFR-PERF-01..05, DOC-14, DOC-27.

### Epic 7: Context Moat

Improve deployment-risk quality with project-scoped topology, Terraform state, Kubernetes live-state, ownership, freshness, context graph, and context TODOs.

**Primary coverage:** CTX-01..13, ADM-03, PRJ-09, NFR-PERF-05, DOC-09.

### Epic 8: Existing Security Tool Integration

Work alongside Snyk, Checkov, Wiz, OPA, SARIF-producing scanners, and other security tools by ingesting scanner findings as labeled external evidence.

**Primary coverage:** EXT-01..08, ADM-10, EVD-04, REV-02, WRK-04, DOC-25.

### Epic 9: Skills Ecosystem

Scale DeployWhisper's knowledge through versioned Skills, trust levels, registry APIs, installer, browser, analytics, test harness, and contribution workflow.

**Primary coverage:** SKL-01..09, ADM-05, DOC-13, NFR-OSS-05.

### Epic 10: AI Infrastructure Safety and Agent-Native Review

Make DeployWhisper safe and useful for AI coding agents by providing stable machine-readable output, agent-callable interfaces, provenance handling, prompt-injection tests, and advisory-only guardrails.

**Primary coverage:** AIA-01..10, RSK-11, AIA-related NFR-SEC requirements, DOC-24.

### Epic 11: Optional Enforcement Adapters

Allow users to opt into advisory, warn, soft-block, or hard-block adapter behavior without changing the advisory-first core report.

**Primary coverage:** ADM-07, ADM-09, WRK-07, RSK-07, NFR-SEC-06.

### Epic 12: Security and Supply Chain Hardening

Build trust as infrastructure software through secrets handling, prompt-injection protections, release process, SBOMs, signing, provenance, CodeQL, Scorecard, and air-gapped guidance.

**Primary coverage:** ADM-01..02, NFR-SEC-01..07, NFR-OPS-01..06, GOV-06..07, DOC-11, DOC-12.

### Epic 13: Documentation and User Enablement

Make DeployWhisper self-service by documenting installation, configuration, first analysis, report interpretation, integrations, APIs, connectors, operations, contribution, and release behavior.

**Primary coverage:** DOC-01..27, NFR-DOC-01..06, DOC-related requirements across all epics.

### Epic 14: CNCF Readiness

Prepare the project for foundation-scale community maturity with public adopters, maintainer coverage, community health metrics, governance maturity, release maturity, and a CNCF readiness package.

**Primary coverage:** GOV-08..15, DOC-19..20, NFR-OSS-01..05.

### Epic 15: UI modernization & migration

Migrate the web UI from retired UI to a static React SPA served by FastAPI, following `docs/ui-migration-plan.md` and `docs/design/deploywhisper-redesign-v3.jsx` as the governing scope, design, and verification contract.

**Primary coverage:** REV-01..10, HIS-03..05, ADM-01..05, SKL-05, UX-DR1..09, DOC-05..06, DOC-18, NFR-XAI-05.

## Epic 0: Open Governance, Traceability, and Maintainer Ownership

Establish the public project foundation needed for open-source trust, contribution, and roadmap accountability.

### Story 0.1: Publish Core Governance Files

As a project maintainer,  
I want public governance, support, security, conduct, contributing, and roadmap files,  
So that users and contributors understand how the project operates.

**Acceptance Criteria:**

**Given** a new contributor or user visits the repository  
**When** they inspect governance and community files  
**Then** they can find `GOVERNANCE.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`, and `ROADMAP.md`  
**And** the documents do not imply SaaS, open-core, or paid feature gating.

### Story 0.2: Define Maintainer Ownership and CODEOWNERS

As a maintainer,  
I want maintainer areas and CODEOWNERS documented,  
So that reviews route to accountable project owners.

**Acceptance Criteria:**

**Given** a PR changes a major repository area  
**When** CODEOWNERS evaluates the change  
**Then** the appropriate maintainership area is requested for review  
**And** `MAINTAINERS.md` explains owner responsibilities and known coverage gaps.

### Story 0.3: Create Requirements Traceability Matrix

As a product owner,  
I want PRD requirements mapped to epics and implementation artifacts,  
So that future planning changes do not silently drift from the finalized PRD.

**Acceptance Criteria:**

**Given** the finalized PRD requirements  
**When** the traceability matrix is generated  
**Then** every requirement family maps to one or more epics  
**And** gaps, deferred requirements, and cross-cutting requirements are explicitly marked.

### Story 0.4: Establish RFC and Decision Process

As a maintainer,  
I want major design decisions to use a public RFC process,  
So that architecture, roadmap, and governance changes remain auditable.

**Acceptance Criteria:**

**Given** a change affects architecture, governance, security, or roadmap scope  
**When** maintainers propose it  
**Then** the RFC process defines required sections, review expectations, and decision recording  
**And** accepted decisions link back to relevant PRD or architecture sections.

## Epic 1: Project, Workspace, and RBAC Foundation

Make DeployWhisper project-aware before reports, incidents, topology, scanner imports, and feedback become harder to migrate.

### Story 1.1: Project and Workspace Records

As a platform admin,  
I want first-class project and workspace records,  
So that analysis, reports, and future context can be scoped before shared usage expands.

**Acceptance Criteria:**

**Given** a self-hosted DeployWhisper instance  
**When** an admin creates projects and workspaces  
**Then** project and workspace/environment records are represented with stable keys, display names, descriptions, and timestamps  
**And** migrations only add the entities needed for project/workspace selection and lookup.

**Given** a duplicate, missing, or invalid project key is submitted  
**When** project or workspace validation runs  
**Then** the user receives an explicit error and no partial project/workspace record is created.

### Story 1.2: Project-Aware Analysis Submission

As a platform engineer,  
I want to provide or derive a project key during analysis,  
So that reports are saved under the correct project.

**Acceptance Criteria:**

**Given** a user submits artifacts through UI, API, CLI, or GitHub flow  
**When** a project key is provided or derivable  
**Then** the analysis run and report are associated with that project  
**And** missing or ambiguous project scope produces an explicit, actionable message.

**Given** a project key references a project the caller cannot access  
**When** analysis submission is attempted  
**Then** the request is rejected before parsing artifacts  
**And** no report, incident, outcome, feedback, topology, or scanner data is associated with that unauthorized project.

### Story 1.3: Project-Scoped Report Persistence

As a platform admin,  
I want saved reports and analysis runs scoped to their project and optional workspace,  
So that teams do not see unrelated deployment reviews by accident.

**Acceptance Criteria:**

**Given** analysis runs and reports are created or queried  
**When** persistence and retrieval run  
**Then** records are scoped to project and optional workspace where applicable  
**And** report repository queries and API responses prevent accidental cross-project leakage.

**Given** a report lookup uses an ID from another project  
**When** the caller's active project does not match the report scope  
**Then** the response does not reveal report contents or metadata beyond an authorized error envelope.

### Story 1.4: Project-Scoped Learning and Context Records

As a platform admin,  
I want incidents, outcomes, feedback, topology, and scanner imports scoped consistently,  
So that future learning and context never cross project boundaries.

**Acceptance Criteria:**

**Given** incidents, deployment outcomes, feedback, topology, or scanner imports are created or queried  
**When** they are created or queried  
**Then** they are scoped to project and optional workspace where applicable  
**And** repository queries and API responses prevent accidental cross-project leakage.

**Given** a context or learning record has no project scope  
**When** validation runs before persistence  
**Then** persistence fails with an actionable error unless the object type is explicitly global by architecture.

### Story 1.5: Lightweight RBAC Role Model

As a platform admin,  
I want project-aware roles defined even before full enterprise auth exists,  
So that future shared installs can enforce permissions without redesigning data contracts.

**Acceptance Criteria:**

**Given** DeployWhisper runs in self-hosted mode  
**When** project roles are configured or documented  
**Then** admin, maintainer, reviewer, contributor, and read-only roles have defined capabilities  
**And** API and UI contracts avoid assumptions that all users can access all projects.

**Given** a caller lacks permission for a project-level action  
**When** the UI, API, CLI, or automation actor attempts that action  
**Then** the surface returns a clear authorization result without leaking unrelated project data.

### Story 1.6: Project Model Documentation

As a user deploying DeployWhisper,  
I want project modeling guidance,  
So that I can map monorepos, multi-repos, Terraform workspaces, Kubernetes clusters, and platform teams correctly.

**Acceptance Criteria:**

**Given** users read project model docs  
**When** they compare deployment patterns  
**Then** the docs explain recommended project/workspace mappings for common infrastructure setups  
**And** examples remain self-hosted and do not assume a SaaS control plane.

## Epic 2: Trusted Evidence Core and Evidence Law

Make the core analysis defensible, stable, and evidence-backed.

### Story 2.1: Submission Manifest and Provenance

As a reviewer,  
I want every analysis to show accepted, excluded, partial, failed, and sensitive artifacts,  
So that I know exactly what was and was not analyzed.

**Acceptance Criteria:**

**Given** one or more artifacts are submitted  
**When** DeployWhisper classifies and validates them  
**Then** the submission manifest records accepted, excluded, failed, partial, sensitive, provenance, and redaction status  
**And** the report surfaces partial analysis instead of implying complete coverage.

### Story 2.2: Terraform Plan JSON Intake

As a platform engineer,  
I want Terraform plan JSON accepted as a first-class input,  
So that deployment review can use concrete planned changes instead of only source files.

**Acceptance Criteria:**

**Given** a Terraform plan JSON file is submitted  
**When** intake and parsing run  
**Then** plan actions, resources, modules, and relevant metadata are normalized into the shared change model  
**And** unsupported or redacted plan fields are reported explicitly.

### Story 2.3: Evidence Item Model and Extraction

As a reviewer,  
I want findings to reference inspectable evidence items,  
So that every claim can be traced to concrete source or context.

**Acceptance Criteria:**

**Given** parsed changes and context are available  
**When** evidence extraction runs  
**Then** evidence items identify artifact, location, resource, operation, project/workspace, source kind, determinism level, and redaction status  
**And** evidence items are persisted with the report.

### Story 2.4: Finding Model and Evidence Links

As a reviewer,  
I want findings to distinguish deterministic, derived, external, model-inferred, and user-provided context,  
So that I understand what kind of support each finding has.

**Acceptance Criteria:**

**Given** evidence items are available  
**When** findings are generated  
**Then** each finding references one or more evidence items where applicable  
**And** finding fields include severity, category, confidence, explanation, guidance, and evidence classification.

### Story 2.5: Evidence Law Runtime Gate

As a maintainer,  
I want high and critical findings blocked unless deterministic evidence exists,  
So that DeployWhisper cannot overclaim severe risk.

**Acceptance Criteria:**

**Given** a high or critical finding is generated  
**When** report validation runs  
**Then** validation fails or downgrades the finding unless at least one deterministic evidence item is linked  
**And** CI fixtures fail if high/critical findings violate this rule.

### Story 2.6: Confidence, Uncertainty, and Insufficient Context

As a reviewer,  
I want confidence, uncertainty, and insufficient-context signals,  
So that missing data does not look like certainty.

**Acceptance Criteria:**

**Given** topology, evidence, parser, or incident context is incomplete  
**When** risk scoring completes  
**Then** the report includes confidence, uncertainty, context completeness, context TODOs, and insufficient-context verdict support  
**And** low context does not silently produce stronger certainty.

### Story 2.7: Narrative After Scoring and Degraded Fallback

As a reviewer,  
I want deterministic evidence and verdicts to survive narrative failure,  
So that LLM outages do not break deployment review.

**Acceptance Criteria:**

**Given** narrative generation fails, times out, or returns invalid output  
**When** analysis completes  
**Then** deterministic findings, evidence, verdict, rollback, and context output remain available  
**And** the report records degraded narrative status and provider metadata.

### Story 2.8: Report Schema Versioning

As an integration developer,  
I want machine-readable report schema versions,  
So that API, CLI, PR, benchmark, and agent consumers can evolve safely.

**Acceptance Criteria:**

**Given** a report is persisted or returned  
**When** consumers inspect it  
**Then** `report_schema_version` is present and documented  
**And** schema docs and tests cover evidence, findings, context, narrative status, and advisory fields.

### Story 2.9: Durable Report Persistence and Audit Metadata

As a reviewer or auditor,  
I want reports persisted with audit metadata before success is returned,  
So that every completed analysis is retrievable, defensible, and comparable later.

**Primary coverage:** HIS-01, HIS-02, NFR-REL-03.

**Acceptance Criteria:**

**Given** deterministic analysis produces a report object  
**When** UI, API, CLI, GitHub, or future integration delivery returns final success  
**Then** the report has already been persisted with project/workspace scope, schema version, evidence references, finding metadata, narrative status, delivery metadata, actor, source surface, timestamps, and redaction status  
**And** the success response includes a report identifier or explicit persisted-report reference where the surface supports it.

**Given** report persistence fails or audit metadata cannot be recorded  
**When** final delivery would otherwise return success  
**Then** the surface returns an explicit actionable failure or degraded persistence state  
**And** it does not imply the analysis was durably saved.

## Epic 3: Report and Review Experience

Make the report experience fast, inspectable, and honest.

### Story 3.1: Verdict-First Report Header

As a reviewer,  
I want the verdict, Evidence Law status, confidence, and top risk visible immediately,  
So that I can orient quickly before drilling into detail.

**Acceptance Criteria:**

**Given** an analysis report is displayed  
**When** the result page loads  
**Then** verdict, advisory posture, Evidence Law status, confidence, top risk, and next action are visible above the fold  
**And** the copy avoids implying automatic approval or blocking.

### Story 3.2: Findings Table With Evidence Badges

As a reviewer,  
I want a findings table with severity, determinism, confidence, and evidence counts,  
So that I can scan risk quickly and choose what to inspect.

**Acceptance Criteria:**

**Given** findings exist  
**When** the findings table renders  
**Then** each row shows severity, category, confidence, deterministic/derived/external labels, and evidence count  
**And** high/critical rows visibly satisfy or fail Evidence Law status.

### Story 3.3: Evidence Inspector Panel

As a reviewer,  
I want to inspect the proof behind each finding,  
So that I can decide whether the recommendation is credible.

**Acceptance Criteria:**

**Given** a finding has evidence links  
**When** the reviewer opens evidence details  
**Then** artifact reference, resource, operation, context source, determinism, project/workspace, and redaction status are visible  
**And** evidence inspection preserves report orientation and keyboard accessibility.

**Given** evidence is redacted, missing, or unavailable due to sensitive-file handling  
**When** the reviewer opens evidence details  
**Then** the inspector explains the redaction or missing-state reason without exposing sensitive content  
**And** the finding remains clearly tied to available safe metadata.

### Story 3.4: Confidence Ledger and Why-Not-Lower/Higher

As a reviewer,  
I want to know why the verdict is not lower or higher,  
So that severity reasoning is explainable.

**Acceptance Criteria:**

**Given** a verdict is produced  
**When** the reviewer opens reasoning details  
**Then** the report shows contributors, confidence factors, why-not-lower, why-not-higher, and uncertainty drivers  
**And** explanations remain grounded in evidence and context.

### Story 3.5: Context Completeness and TODO Panel

As a platform admin,  
I want report-level context completeness and TODOs,  
So that I know what data would improve future analysis.

**Acceptance Criteria:**

**Given** context sources are missing, stale, incomplete, or conflicting  
**When** the report renders  
**Then** context completeness state and TODOs are visible near the relevant findings and summary  
**And** TODOs link to connector or documentation guidance where practical.

### Story 3.6: Report Diff After Rerun

As a reviewer,  
I want report diffs after reruns,  
So that I can see which risks are new, resolved, or persistent.

**Acceptance Criteria:**

**Given** two related reports exist for the same project/workspace and workflow context  
**When** the reviewer opens comparison  
**Then** the diff shows new, resolved, persistent, changed-severity, and changed-context findings  
**And** comparison respects redaction and project scope.

### Story 3.7: Keyboard and Accessibility Review Pass

As a reviewer using keyboard or assistive technology,  
I want the report to be navigable and understandable,  
So that deployment review is not blocked by inaccessible UI.

**Acceptance Criteria:**

**Given** a report page is loaded  
**When** keyboard and accessibility checks run  
**Then** focus order, headings, labels, landmarks, contrast, and status announcements support the primary review flow  
**And** automated or manual accessibility verification is documented.

### Story 3.8: Historical Report Search and Filtering

As a reviewer,  
I want to search and filter historical reports by project, workspace, risk, toolchain, time, and status,  
So that I can retrieve prior deployment reviews without browsing unrelated project history.

**Primary coverage:** HIS-03, REV-04.

**Acceptance Criteria:**

**Given** historical reports exist for one or more projects  
**When** a user opens report history  
**Then** they can filter by project, workspace, time range, risk verdict, toolchain, and analysis status  
**And** result rows show timestamp, project/workspace, verdict, tool mix, top risk, and report schema version.

**Given** filters match no reports or include reports outside the caller's project access  
**When** the history view or API responds  
**Then** it shows an empty or authorized-only result set without leaking inaccessible report metadata.

## Epic 4: Day-Zero Risk Patterns and Incident Memory

Give new installs useful memory immediately and grow organization-specific learning over time.

### Story 4.1: Public Risk Pattern Library v1

As a fresh-install user,  
I want built-in public risk patterns,  
So that DeployWhisper can catch known deployment failure modes before I have my own incidents.

**Acceptance Criteria:**

**Given** no organization incidents exist  
**When** analysis matches a built-in risk pattern  
**Then** the report labels it as a public risk pattern match  
**And** the match includes reason, evidence, confidence, and verification guidance.

### Story 4.2: Safe Sample Incident Pack

As a demo user,  
I want sample incidents that are legally and ethically safe,  
So that I can understand incident memory without using real customer data.

**Acceptance Criteria:**

**Given** sample incident data is loaded  
**When** the sample pack is inspected  
**Then** it contains no real customer data, real organization names, or non-public postmortem content without explicit attribution and permission  
**And** documentation explains sample pack provenance and limitations.

### Story 4.3: Incident Import for Markdown, YAML, and JSON

As a platform admin,  
I want to import incident records from simple files,  
So that organization memory can be added without integrating a ticketing system first.

**Acceptance Criteria:**

**Given** markdown, YAML, or JSON incident files are provided  
**When** import runs  
**Then** incident metadata, root cause, trigger change, affected services, rollback path, and prevention notes are stored under the correct project  
**And** invalid records produce actionable errors.

**Given** an imported incident is missing required scope, source, or redaction metadata  
**When** validation runs  
**Then** the record is rejected with field-level errors  
**And** no partial incident index entry is created.

### Story 4.4: Incident Similarity With Match Explanation

As a reviewer,  
I want similar incidents explained,  
So that I know why a past failure is relevant.

**Acceptance Criteria:**

**Given** project-scoped incidents exist  
**When** an analysis resembles past incidents  
**Then** the report shows match confidence, matched signals, affected services, and prevention notes  
**And** public risk patterns and organization incidents are clearly distinguished.

**Given** no incidents match or only weak signals are present  
**When** incident similarity runs  
**Then** the report states that no organization-specific incident match was found or labels the match as low-confidence  
**And** it does not imply a prior incident occurred when only public risk patterns are available.

### Story 4.5: Reviewer Feedback Capture

As a reviewer,  
I want to mark findings as useful, noisy, false positive, or missed,  
So that future calibration can improve.

**Acceptance Criteria:**

**Given** a report finding is displayed  
**When** the reviewer submits feedback  
**Then** the feedback is scoped to project/workspace and linked to the report/finding  
**And** feedback does not silently alter historical report verdicts.

### Story 4.6: Deployment Outcome Capture

As a platform engineer,  
I want to record deployment outcomes after review,  
So that DeployWhisper can learn from success, failure, rollback, and incident outcomes.

**Acceptance Criteria:**

**Given** a deployment follows a DeployWhisper report  
**When** outcome data is captured  
**Then** success, failure, rollback, linked incident, notes, project, and workspace are stored  
**And** the outcome is available for calibration and backtesting.

### Story 4.7: Incident Ingestion Management and Indexing

As a platform admin,  
I want to manage incident ingestion status, indexing, reindexing, and failures,  
So that organization incident memory stays understandable and maintainable.

**Primary coverage:** ADM-04, INC-04, INC-06.

**Acceptance Criteria:**

**Given** incident import jobs or indexed incident records exist  
**When** an admin opens incident ingestion management  
**Then** they can see import source, project/workspace scope, indexed count, rejected count, last indexed timestamp, redaction status, and failure summaries  
**And** each failure includes an actionable correction path.

**Given** incidents are updated, deleted, or reimported  
**When** reindexing runs  
**Then** stale index entries are replaced or removed under the same project scope  
**And** reports never mix old and new incident index state without exposing freshness.

## Epic 5: Workflow-Native Delivery

Deliver the report in real review workflows without duplicating analysis logic.

### Story 5.1: Versioned API Report Contract

As an integration developer,  
I want stable `/api/v1` report and analysis endpoints,  
So that integrations can rely on machine-readable advisory output.

**Acceptance Criteria:**

**Given** an API client submits or retrieves analysis  
**When** the API responds  
**Then** it returns versioned report schema, project/workspace scope, evidence, findings, context, narrative status, and advisory recommendation  
**And** errors use the existing API error envelope.

### Story 5.2: CLI Project-Aware Advisory Output

As a CLI user,  
I want project-aware analysis output,  
So that local and CI workflows can consume the same core report.

**Acceptance Criteria:**

**Given** a user runs the CLI with artifacts and optional project/workspace key  
**When** analysis completes  
**Then** output includes verdict, Evidence Law status, top findings, uncertainty, report schema version, and advisory posture  
**And** deterministic output remains available without narrative.

### Story 5.3: GitHub Action Integration Contract

As a platform team,  
I want the app repo to document and integrate with the external GitHub Action,  
So that Marketplace action runtime stays in `deploywhisper/analyze-action`.

**Acceptance Criteria:**

**Given** GitHub Action docs and integration examples exist  
**When** users configure PR review  
**Then** docs reference `deploywhisper/analyze-action@v1` and do not place action runtime in this repo  
**And** report outputs map to the canonical schema.

### Story 5.4: PR Comment Formatter

As a PR reviewer,  
I want concise advisory comments,  
So that I can understand risk without opening the full UI.

**Acceptance Criteria:**

**Given** a report is generated for a PR  
**When** the comment formatter runs  
**Then** the comment includes verdict, Evidence Law status, top risks, evidence, blast radius, rollback, incident/public pattern matches, scanner context, uncertainty, and report link  
**And** it remains explicitly advisory.

### Story 5.5: Rerun-on-Commit and Report Comparison

As a PR reviewer,  
I want analysis to rerun and compare after new commits,  
So that I can see whether changes resolved or introduced risk.

**Acceptance Criteria:**

**Given** a PR receives new commits or changed artifacts  
**When** rerun is triggered  
**Then** a new report is generated and compared with the previous relevant report  
**And** PR output highlights new, resolved, and persistent findings.

### Story 5.6: Future Adapter Output Contract

As an integration maintainer,  
I want GitLab, Jenkins, Atlantis, GitOps, chat, and other adapters to consume one report contract,  
So that new workflow integrations do not redesign the core.

**Acceptance Criteria:**

**Given** future adapters are implemented  
**When** they consume DeployWhisper output  
**Then** they use canonical report summaries and adapter metadata  
**And** adapter-specific formatting cannot mutate canonical severity or Evidence Law status.

## Epic 6: Benchmarks, Calibration, and Honest Failure Reporting

Prove trust claims with measurable, repeatable evidence.

### Story 6.1: Benchmark Corpus v1

As a maintainer,  
I want a public benchmark corpus,  
So that risk detection quality is measurable and inspectable.

**Acceptance Criteria:**

**Given** benchmark scenarios are added  
**When** corpus validation runs  
**Then** each scenario includes artifacts, expected findings, expected evidence, expected verdict rationale, labels, and licensing metadata  
**And** unsafe or non-public samples are rejected.

### Story 6.2: Benchmark Runner

As a maintainer,  
I want a benchmark runner that uses the same analysis core,  
So that benchmark results reflect actual product behavior.

**Acceptance Criteria:**

**Given** a benchmark corpus exists  
**When** the runner executes scenarios  
**Then** it records pass/fail, findings, evidence coverage, Evidence Law violations, latency, and unsupported scenarios  
**And** it does not use a separate scoring path.

### Story 6.3: Honest Failure Report Generator

As a user evaluating DeployWhisper,  
I want benchmark reports that include misses and regressions,  
So that trust claims are credible.

**Acceptance Criteria:**

**Given** a benchmark run completes  
**When** a report is generated  
**Then** it includes improvements, regressions, detected scenarios, missed scenarios, false reassurance, false positives, unsupported scenarios, evidence coverage, and context limitations  
**And** material misses create linked issues unless explicitly out of scope.

### Story 6.4: Outcome Calibration Metrics

As a maintainer,  
I want deployment outcomes and feedback to inform calibration metrics,  
So that false positives and false reassurance can be tracked.

**Acceptance Criteria:**

**Given** feedback and deployment outcomes exist  
**When** calibration views or exports are generated  
**Then** precision, recall proxy signals, false-positive rate, false-reassurance cases, and confidence trends are computed per project/workspace where possible  
**And** historical report verdicts remain immutable.

**Given** feedback or outcome data is sparse or biased  
**When** calibration metrics are shown  
**Then** the dashboard labels confidence limitations and avoids implying statistical certainty.

### Story 6.5: Incident Backtesting

As a platform admin,  
I want historical incident-causing changes replayed through the analysis core,  
So that I can see whether DeployWhisper would have caught them.

**Acceptance Criteria:**

**Given** incident records and replay artifacts exist  
**When** backtesting runs  
**Then** results show detected, missed, unsupported, and insufficient-context scenarios  
**And** findings link back to expected evidence and incident metadata.

### Story 6.6: Risk Trend Review

As an engineering manager,  
I want to review risk trends over time by project, workspace, toolchain, severity, and outcome,  
So that I can understand whether deployment risk is improving or recurring.

**Primary coverage:** HIS-04, HIS-06, HIS-09, BEN-05.

**Acceptance Criteria:**

**Given** persisted reports, reviewer feedback, and deployment outcomes exist  
**When** a manager opens risk trend review or exports trend data  
**Then** they can compare verdict distribution, high/critical frequency, false-positive signals, false-reassurance signals, outcome links, and context-completeness trends by time window, project, workspace, toolchain, and severity  
**And** trend calculations preserve historical report immutability.

**Given** data is missing, sparse, or outside the selected project scope  
**When** trends are rendered  
**Then** the view explains the limitation and excludes inaccessible data without leaking metadata.

## Epic 7: Context Moat

Improve deployment-risk judgment with richer project-scoped context.

### Story 7.1: Project-Scoped Topology Context

As a reviewer,  
I want blast radius computed from project-scoped topology,  
So that affected services and dependencies are meaningful.

**Acceptance Criteria:**

**Given** topology exists for a project/workspace  
**When** analysis computes blast radius  
**Then** affected services, dependencies, ownership, freshness, and context source are included in the report  
**And** stale, missing, incomplete, or conflicting topology is explicit.

### Story 7.2: Terraform State Connector

As a platform admin,  
I want read-only Terraform state context,  
So that planned changes can be evaluated against existing infrastructure.

**Acceptance Criteria:**

**Given** Terraform state is configured as a read-only context source  
**When** analysis runs  
**Then** relevant resources and relationships enrich evidence/context snapshots  
**And** connector timeout, staleness, and unavailable states do not block deterministic analysis.

### Story 7.3: Kubernetes Live-State Connector

As a platform admin,  
I want optional read-only Kubernetes live-state context,  
So that manifests can be compared against current cluster reality.

**Acceptance Criteria:**

**Given** a Kubernetes context source is configured  
**When** analysis runs  
**Then** service, workload, namespace, selector, and freshness signals enrich the report  
**And** unavailable cluster access produces context TODOs, not silent certainty.

### Story 7.4: CODEOWNERS and Ownership Mapping

As a reviewer,  
I want service and file ownership visible in reports,  
So that review and escalation paths are clear.

**Acceptance Criteria:**

**Given** CODEOWNERS or ownership data exists  
**When** relevant files/resources are analyzed  
**Then** report context includes owner signals and escalation hints  
**And** missing owner data produces a context TODO.

### Story 7.5: Context Graph and Freshness Ledger

As a platform admin,  
I want context freshness and confidence per source,  
So that I can prioritize connector improvements.

**Acceptance Criteria:**

**Given** multiple context sources exist  
**When** the context graph is built  
**Then** source freshness, confidence, scope, and conflicts are visible in UI/API/CLI output  
**And** evidence items can reference context source metadata.

## Epic 8: Existing Security Tool Integration

Make DeployWhisper complementary to scanners rather than a replacement or severity passthrough.

### Story 8.1: SARIF Ingestion

As an AppSec reviewer,  
I want SARIF findings imported into DeployWhisper,  
So that scanner output can be reviewed in deployment context.

**Acceptance Criteria:**

**Given** a SARIF file is submitted for a project  
**When** scanner import runs  
**Then** scanner findings are stored as external evidence with tool, rule, severity, location, and project scope  
**And** unsupported SARIF structures produce actionable errors.

### Story 8.2: Scanner JSON Adapter v1

As a platform team,  
I want at least one scanner-specific JSON format supported,  
So that real scanner output can be integrated before broader adapter expansion.

**Acceptance Criteria:**

**Given** a supported scanner JSON file is submitted  
**When** ingestion runs  
**Then** findings normalize into the external evidence model  
**And** scanner-specific fields needed for report context are preserved.

### Story 8.3: External Evidence Report Context

As a reviewer,  
I want scanner context visible but clearly labeled,  
So that I know what came from DeployWhisper versus another tool.

**Acceptance Criteria:**

**Given** external scanner findings are linked to a report  
**When** the report, PR comment, or API output renders  
**Then** scanner findings are labeled as external evidence  
**And** they do not automatically become high/critical DeployWhisper findings.

### Story 8.4: Scanner Conflict Handling

As a reviewer,  
I want conflicts between scanner output and deterministic evidence surfaced,  
So that DeployWhisper does not silently choose one source.

**Acceptance Criteria:**

**Given** scanner findings conflict with deterministic evidence or context  
**When** report synthesis runs  
**Then** the conflict is shown with source details and uncertainty impact  
**And** severity remains governed by DeployWhisper scoring and Evidence Law.

**Given** a conflict appears in UI, API, CLI, or PR output  
**When** a reviewer inspects the report  
**Then** the output includes scanner source, deterministic evidence source, freshness of each source, recommended verification, and confidence impact  
**And** no surface silently drops either side of the conflict.

### Story 8.5: Existing Security Tools Comparison Guide

As an AppSec or platform team,  
I want guidance for using DeployWhisper alongside scanners,  
So that responsibilities are clear.

**Acceptance Criteria:**

**Given** users read the comparison guide  
**When** they evaluate scanners and DeployWhisper together  
**Then** docs explain complementary roles, ingestion setup, conflict handling, and examples  
**And** docs avoid claiming DeployWhisper replaces scanners.

## Epic 9: Skills Ecosystem

Grow community knowledge safely through non-executable, tested, versioned Skills.

### Story 9.1: Skill Manifest Spec v1

As a Skill author,  
I want a formal manifest schema,  
So that Skills can be validated consistently.

**Acceptance Criteria:**

**Given** a Skill package is authored  
**When** manifest validation runs  
**Then** required fields, version, supported toolchains, trust level, scenario references, and documentation links are checked  
**And** invalid Skills provide actionable validation messages.

### Story 9.2: Skills Registry API

As a user,  
I want to list and fetch published Skills,  
So that I can discover community guidance.

**Acceptance Criteria:**

**Given** registry metadata exists  
**When** the API is called  
**Then** users can list, search, filter, and fetch Skill metadata and versions  
**And** trust level, test status, last update, and source are visible.

### Story 9.3: Skill Test Harness

As a maintainer,  
I want every verified/core Skill tested against deterministic scenarios,  
So that Skills do not add ungrounded guidance.

**Acceptance Criteria:**

**Given** a Skill declares test scenarios  
**When** the harness runs  
**Then** expected triggers, outputs, evidence assumptions, and safety constraints are verified  
**And** verified/core trust levels require passing tests.

### Story 9.4: Skills Installer CLI

As a platform admin,  
I want to install, update, and remove Skills from the CLI,  
So that self-hosted teams can manage extensions without manual file copying.

**Acceptance Criteria:**

**Given** a Skill registry or local Skill source is configured  
**When** the CLI install/update/remove commands run  
**Then** Skills are validated, stored, listed, and removable  
**And** errors never execute untrusted Skill content.

### Story 9.5: Skills Browser UI

As a user,  
I want a searchable Skills browser,  
So that I can inspect available guidance and trust levels.

**Acceptance Criteria:**

**Given** Skills registry metadata exists  
**When** the browser renders  
**Then** users can search, filter, inspect trust level, see test status, and view install instructions  
**And** private/local Skills are distinguished from public registry Skills.

### Story 9.6: Skill Contribution Workflow

As a community maintainer,  
I want a clear contribution workflow for Skills,  
So that Skill submissions are reviewable, testable, and routed to the right maintainers.

**Acceptance Criteria:**

**Given** a contributor submits a Skill  
**When** repository automation and maintainer review run  
**Then** the submission uses a PR template, manifest/schema linting, test harness checks, ownership routing, and reviewer assignment  
**And** failures produce actionable feedback without publishing the Skill.

### Story 9.7: Skill Analytics and Deprecation Signals

As a community maintainer,  
I want Skill quality and activity signals visible,  
So that users can judge whether a Skill is maintained and trustworthy.

**Acceptance Criteria:**

**Given** Skill registry, test, issue, and usage metadata exists  
**When** users or maintainers inspect Skill listings or details  
**Then** install counts, test pass rates, issue activity, last update, trust level, and source are visible  
**And** deprecated Skills are clearly marked.

## Epic 10: AI Infrastructure Safety and Agent-Native Review

Serve AI coding agents safely without letting them bypass human judgment.

### Story 10.1: Agent JSON CLI Mode

As an AI coding agent,  
I want stable JSON output from the CLI,  
So that I can consume deployment-risk analysis without scraping human text.

**Acceptance Criteria:**

**Given** the CLI runs with `--agent-json`  
**When** analysis completes  
**Then** output includes schema version, verdict, advisory-only status, evidence, findings, confidence, uncertainty, context TODOs, and verification guidance  
**And** output explicitly states it is not deployment approval.

### Story 10.2: MCP-Compatible or Equivalent Agent Interface

As an agent-tool integrator,  
I want an agent-callable interface,  
So that AI workflows can request DeployWhisper review safely.

**Acceptance Criteria:**

**Given** an agent calls the interface  
**When** it submits artifacts or report requests  
**Then** the interface returns bounded, schema-versioned, advisory output  
**And** it enforces project scope and does not expose raw secrets or unrelated project data.

**Given** an agent requests a project, report, or context object outside its allowed scope  
**When** authorization is evaluated  
**Then** the request is denied with a bounded error  
**And** the response does not reveal whether inaccessible project data exists.

### Story 10.3: AI-Generated IaC Provenance and Risk Patterns

As a reviewer,  
I want AI-generated infrastructure risk patterns detected where possible,  
So that plausible but unsafe generated code receives appropriate scrutiny.

**Acceptance Criteria:**

**Given** provenance or content signals suggest AI-assisted IaC  
**When** analysis runs  
**Then** relevant risk patterns are detected and labeled without overclaiming authorship certainty  
**And** findings still require deterministic evidence for high/critical severity.

### Story 10.4: Prompt-Injection Test Suite

As a maintainer,  
I want prompt-injection tests across untrusted inputs,  
So that narrative and agent outputs cannot be manipulated by artifact text.

**Acceptance Criteria:**

**Given** malicious content appears in IaC comments, PR comments, incident text, scanner output, or docs-like artifacts  
**When** tests run  
**Then** model prompts and agent outputs preserve boundaries and do not follow injected instructions  
**And** failures block release until remediated.

### Story 10.5: AI Safety Documentation

As a user of AI coding agents,  
I want documented safe review workflows,  
So that agents use DeployWhisper as an advisory reviewer, not an approver.

**Acceptance Criteria:**

**Given** AI-agent documentation is read  
**When** users configure agent workflows  
**Then** docs show safe invocation, output interpretation, human review expectations, prompt-injection risks, and forbidden auto-approval patterns  
**And** examples remain self-hosted/local-first.

## Epic 11: Optional Enforcement Adapters

Expose optional enforcement interpretation without changing the advisory core.

### Story 11.1: Policy Adapter Output Contract

As a platform admin,  
I want a policy adapter contract,  
So that report outputs can be translated into local workflow decisions.

**Acceptance Criteria:**

**Given** a canonical report exists  
**When** a policy adapter consumes it  
**Then** the adapter can output advisory, warn, soft-block, or hard-block status with reasons  
**And** the canonical report remains unchanged and advisory.

### Story 11.2: Threshold and Reporting Defaults Management

As a platform admin,  
I want configurable thresholds and reporting defaults,  
So that teams can tune adapter behavior without changing core code.

**Acceptance Criteria:**

**Given** thresholds are configured per project or integration  
**When** adapter output is generated  
**Then** thresholds are applied only to adapter interpretation  
**And** the original evidence, findings, and severity remain auditable.

### Story 11.3: Integration-Level Enforcement Settings

As a platform admin,  
I want enforcement mode configured per integration,  
So that teams can adopt warnings before blocking.

**Acceptance Criteria:**

**Given** GitHub, CI, or future integrations are configured  
**When** enforcement settings are changed  
**Then** each integration can use advisory, warn, soft-block, or hard-block mode  
**And** defaults preserve advisory-first behavior.

### Story 11.4: Enforcement Guardrail Documentation

As a reviewer,  
I want docs explaining optional enforcement guardrails,  
So that teams understand when not to block automatically.

**Acceptance Criteria:**

**Given** users read policy adapter docs  
**When** they configure enforcement  
**Then** docs explain Evidence Law, benchmark thresholds, false reassurance, human review, and rollback responsibilities  
**And** docs discourage autonomous approval or remediation.

## Epic 12: Security and Supply Chain Hardening

Make the project trustworthy to install, operate, and contribute to.

### Story 12.1: Secrets and Raw Artifact Boundary Audit

As a security-conscious operator,  
I want raw artifacts, prompts, logs, reports, and telemetry protected,  
So that self-hosted analysis does not leak sensitive deployment data.

**Acceptance Criteria:**

**Given** uploaded artifacts, generated prompts, logs, reports, and telemetry exist  
**When** security tests and review run  
**Then** secrets are redacted and raw artifacts are not sent externally by default  
**And** local-only operation remains possible.

**Given** sensitive content is detected in input or generated output  
**When** persistence or narrative generation runs  
**Then** unsafe content is blocked or redacted with an explicit status visible to reviewers and operators.

### Story 12.2: Provider Settings Administration

As a platform admin,  
I want to configure narrative-provider settings through DeployWhisper's provider adapter boundary,  
So that external or local model usage is explicit, local-first, and safe.

**Primary coverage:** ADM-01, ADM-02, NFR-SEC-01, NFR-SEC-02, NFR-SEC-03.

**Acceptance Criteria:**

**Given** an admin opens provider settings  
**When** they configure local-only mode or an external provider  
**Then** settings are validated through the DeployWhisper-owned provider adapter boundary  
**And** provider credentials are read from environment-backed configuration or equivalent secure references, not stored unsafely.

**Given** provider configuration is missing, invalid, or disabled by local-only mode  
**When** narrative generation is requested  
**Then** deterministic analysis still completes and the report records degraded or disabled narrative status.

### Story 12.3: Connector Credential Handling and Redaction Audit

As a self-hosted operator,  
I want connector credentials and sensitive context protected,  
So that topology, incident, scanner, and workflow integrations do not leak secrets.

**Acceptance Criteria:**

**Given** connector settings or imported context include credentials or sensitive references  
**When** validation, logging, report rendering, API output, or docs examples are generated  
**Then** credentials are redacted or referenced securely  
**And** unsafe persistence, prompt inclusion, and telemetry exposure are covered by tests or documented controls.

### Story 12.4: OpenSSF Scorecard and CodeQL

As a maintainer,  
I want baseline open-source security checks,  
So that supply-chain posture is visible.

**Acceptance Criteria:**

**Given** repository workflows run  
**When** Scorecard and CodeQL complete  
**Then** results are visible to maintainers and documented  
**And** high-priority findings have follow-up issues or accepted rationale.

### Story 12.5: SBOM and Release Checksums

As an operator,  
I want release artifacts to include SBOMs and checksums,  
So that I can evaluate self-hosted deployment trust.

**Acceptance Criteria:**

**Given** a release is produced  
**When** artifacts are published  
**Then** SBOMs, checksums, and verification instructions are available  
**And** release docs explain limitations and verification steps.

### Story 12.6: Signing and Provenance

As an operator,  
I want release artifacts signed with provenance or attestations where practical,  
So that I can verify artifact origin before self-hosted deployment.

**Acceptance Criteria:**

**Given** release signing or provenance is enabled  
**When** artifacts are published  
**Then** signatures, provenance or attestations, verification commands, and known limitations are documented  
**And** unsigned or unverifiable artifacts are explicitly labeled.

### Story 12.7: Backup, Restore, Upgrade, and Retention Docs

As an operator,  
I want operational docs for data lifecycle,  
So that I can run DeployWhisper safely.

**Acceptance Criteria:**

**Given** a self-hosted operator reads operations docs  
**When** they plan backup, restore, upgrade, retention, logs, or database maintenance  
**Then** supported SQLite and PostgreSQL paths are documented  
**And** examples avoid exposing secrets.

### Story 12.8: Air-Gapped and Restricted-Network Guide

As a regulated operator,  
I want air-gapped installation guidance,  
So that I can use DeployWhisper without internet access for core analysis.

**Acceptance Criteria:**

**Given** an operator follows restricted-network docs  
**When** they install and run core analysis  
**Then** local deterministic analysis works without external services  
**And** optional provider, registry, connector, and update limitations are clearly documented.

## Epic 13: Documentation and User Enablement

Make the product self-service for users, operators, integrators, and contributors.

### Story 13.1: Documentation Information Architecture

As a user,  
I want a coherent docs structure,  
So that I can find install, use, configure, operate, integrate, extend, and contribute guidance.

**Acceptance Criteria:**

**Given** users open the docs  
**When** they navigate the information architecture  
**Then** top-level sections match primary user journeys  
**And** the docs do not assume hosted SaaS onboarding.

### Story 13.2: First Analysis and Report Interpretation Guides

As a new user,  
I want a safe first-analysis walkthrough and report guide,  
So that I understand DeployWhisper's advisory output.

**Acceptance Criteria:**

**Given** safe sample artifacts are available  
**When** a user follows the first-analysis guide  
**Then** they can run analysis and interpret verdict, evidence, confidence, uncertainty, rollback, and context TODOs  
**And** docs explain Evidence Law in plain terms.

### Story 13.3: API and Report Schema References

As an integrator,  
I want reference docs for REST API and report schema contracts,  
So that I can build integrations safely.

**Acceptance Criteria:**

**Given** API endpoints, report schema, webhook schema, and error envelopes exist  
**When** docs are generated or updated  
**Then** contract fields, versions, examples, errors, project/workspace scope, and advisory semantics are documented  
**And** docs match current implementation behavior.

### Story 13.4: CLI, Evidence, and Agent Output References

As a CLI or agent integrator,  
I want CLI, evidence schema, and agent/MCP output references,  
So that local, CI, and agent workflows consume DeployWhisper safely.

**Acceptance Criteria:**

**Given** CLI commands, evidence schema, and agent/MCP outputs exist  
**When** docs are generated or updated  
**Then** command options, output fields, schema versions, examples, errors, local-first behavior, and advisory-only semantics are documented  
**And** docs match current implementation behavior.

### Story 13.5: Connector Guides

As a platform admin,  
I want setup guides for context connectors,  
So that I can configure topology, incident, ownership, scanner, and provider context safely in self-hosted environments.

**Acceptance Criteria:**

**Given** a supported context connector exists  
**When** users read its guide  
**Then** setup, permissions, secrets, troubleshooting, limitations, and self-hosted assumptions are documented  
**And** UI/CLI/API surfaces link to docs where practical.

### Story 13.6: Workflow Integration Guides

As a platform admin,  
I want setup guides for workflow integrations,  
So that I can configure GitHub, future GitLab/Jenkins/Atlantis/GitOps/chat, and local workflow delivery safely.

**Acceptance Criteria:**

**Given** a supported workflow integration exists  
**When** users read its guide  
**Then** setup, permissions, secrets, troubleshooting, limitations, report schema behavior, and advisory/enforcement boundaries are documented  
**And** UI/CLI/API surfaces link to docs where practical.

### Story 13.7: Docs CI and Drift Checks

As a maintainer,  
I want documentation drift checks,  
So that docs do not silently fall behind behavior.

**Acceptance Criteria:**

**Given** docs CI runs  
**When** links, generated references, command examples, schema examples, or markdown formatting are invalid  
**Then** the check reports actionable failures  
**And** accepted gaps are documented.

### Story 13.8: Release Notes and Upgrade Notes

As a self-hosted operator,  
I want release and upgrade notes,  
So that I know what changed and what action is required.

**Acceptance Criteria:**

**Given** a user-visible release is prepared  
**When** release notes are written  
**Then** they include changes, migration notes, compatibility notes, schema changes, operational impacts, and known issues  
**And** upgrade instructions are available where needed.

## Epic 14: CNCF Readiness

Prepare the project for foundation-scale open-source maturity.

### Story 14.1: CNCF Readiness Checklist

As a maintainer,  
I want a visible CNCF readiness checklist,  
So that the project can track maturity honestly.

**Acceptance Criteria:**

**Given** the checklist exists  
**When** maintainers review readiness  
**Then** governance, security, releases, adopters, documentation, maintainers, benchmarks, and community health are tracked  
**And** incomplete areas are visible.

### Story 14.2: Public Adopters and Usage Signals

As a project maintainer,  
I want public adopter and usage signal documentation,  
So that community maturity can be assessed without private claims.

**Acceptance Criteria:**

**Given** adopters or usage examples are submitted  
**When** they are reviewed  
**Then** public adopter entries include permitted organization/project names, usage context, and contact or validation metadata where appropriate  
**And** no private customer claims are invented.

### Story 14.3: Maintainer Coverage and Promotion Process

As a community contributor,  
I want a clear path to maintainership,  
So that the project can grow beyond a single maintainer.

**Acceptance Criteria:**

**Given** contributors review maintainer docs  
**When** they look for promotion, inactivity, or area ownership rules  
**Then** expectations, responsibilities, process, and coverage gaps are clear  
**And** maintainer coverage is periodically reviewed.

### Story 14.4: Community Health Metrics

As a maintainer or CNCF reviewer,  
I want public project health metrics,  
So that project sustainability can be evaluated.

**Acceptance Criteria:**

**Given** repository activity exists  
**When** health metrics are updated  
**Then** contribution activity, issue response, PR review, maintainer coverage, release cadence, docs health, benchmark cadence, and security response indicators are visible  
**And** metrics avoid vanity-only claims.

### Story 14.5: CNCF Application Package

As a maintainer,  
I want a CNCF application package prepared only when ready,  
So that submission is grounded in evidence rather than aspiration.

**Acceptance Criteria:**

**Given** readiness checklist items are substantially complete  
**When** maintainers prepare the package  
**Then** governance, scope, adopters, maintainers, security, releases, docs, benchmarks, architecture, and community health artifacts are linked  
**And** open gaps are disclosed.

## Epic 15: UI modernization & migration

Migrate DeployWhisper's web experience from retired UI to the approved React SPA without changing the advisory-first analysis core. This epic is governed by `docs/ui-migration-plan.md`; when exact visual values disagree, `docs/design/deploywhisper-redesign-v3.jsx` wins. Backend work is limited to the sanctioned Part A3 cases and must ship separately as `backend-for-ui`.

### Story 15.0: Phase 0 - Scaffold Frontend and Migration Documentation

As a maintainer,
I want the React frontend scaffold and migration documentation hooks established,
So that later UI migration stories execute against the approved stack and operating rules.

**Acceptance Criteria:**

**Given** the migration plan is approved
**When** Phase 0 work is performed
**Then** `frontend/` is scaffolded with Vite, React 18, TypeScript, Tailwind CSS, local font packages, `lucide-react`, TanStack Query, React Router, Vitest, Testing Library, Playwright, axe, and OpenAPI type generation
**And** root scripts expose `ui:typecheck`, `ui:build`, and `ui:test`
**And** UI verification is performed against the compose-built app at `http://localhost:8080/`, not against the Vite dev server
**And** the Part E Phase 0 documentation rows are complete.

### Story 15.1: Phase 1 - SPA Serving

As a maintainer,
I want the built SPA served at `/`,
So that the current UI runs from the same FastAPI container users deploy.

**Acceptance Criteria:**

**Given** the frontend build exists
**When** the FastAPI app and Docker image are updated
**Then** `frontend/dist` is mounted at `/` with SPA fallback routing
**And** the Dockerfile adds a Node 22 Alpine frontend build stage but keeps Node out of the runtime image
**And** `docker compose up -d --build` serves the React SPA at `http://localhost:8080/`, and `/api/v1/health` stays green
**And** the image size delta is recorded in the PR.

### Story 15.2: Phase 2 - Design System Foundation and Parity Audit

As a reviewer,
I want the approved design system implemented as reusable primitives before screens migrate,
So that dashboard, report, history, settings, incidents, and skills share one tested visual language.

**Acceptance Criteria:**

**Given** the Part B tokens and mockup source
**When** the foundation is built
**Then** Tailwind theme variables and `src/components/ui/` primitives match the approved mockup
**And** `/dev/components` renders every primitive and state as the permanent visual-regression gallery from the composed app at `http://localhost:8080/dev/components`
**And** each primitive has Vitest render and snapshot coverage
**And** `docs/design/ui-parity-audit.md` inventories every retired UI page, element, control, message, and behavior as `replaced-by-design`, `sanctioned-change`, or `not-in-demo -> stop-and-ask`.

### Story 15.3: Phase 3 - Dashboard

As a reviewer,
I want a concise dashboard that shows current deployment risk without embedding the full report,
So that the first screen answers what needs attention now.

**Acceptance Criteria:**

**Given** dashboard data is available through existing or Part A3-sanctioned endpoints
**When** the React dashboard is implemented
**Then** it contains only the Part B0 dashboard information budget: greeting and Evidence Law chip, four KPI cards, recent analyses table, Latest Briefing card, new-analysis upload card, and verdict-health donut
**And** upload success navigates to the Report screen instead of rendering an expiring inline result
**And** loading, empty, error, and narrative-degraded states follow Part B4
**And** seeded e2e proves upload-to-report navigation against the composed container.

### Story 15.4: Phase 4 - Report Detail and Shared Report

As a deployment reviewer,
I want the report screen organized by verdict header and six tabs,
So that I can scan the decision quickly and inspect evidence deeply.

**Acceptance Criteria:**

**Given** `GET /api/v1/analyses/{id}` returns the report contract
**When** the React report screen is implemented
**Then** the sticky header, Overview, Findings, Confidence, Context, Rollback, and Audit tabs match Part B3
**And** the same screen backs shared `/reports/{id}` views with actions hidden and password protection preserved
**And** "Copy briefing" uses the existing share-summary markdown
**And** any schema gaps are documented as additive serializer needs before implementation.

### Story 15.5: Phase 5 - History

As a reviewer,
I want searchable, filterable, paginated analysis history in the new SPA,
So that I can find prior reports without scanning repeated verdict text.

**Acceptance Criteria:**

**Given** historical reports exist
**When** the history screen is implemented
**Then** rows show timestamp, severity badge, verdict chip, score bar, tools, and rescan delta
**And** server-side severity, recommendation, search, page, and page-size filters are supported
**And** expandable detail contains summary text once
**And** bulk select, delete, and pagination preserve the current authorized behavior.

### Story 15.6: Phase 6 - Settings, Incidents, and Skills

As an administrator,
I want the remaining retired UI operational screens rebuilt in the React design system,
So that configuration, incidents, topology, reviewer feedback, and Skills management are migrated before cutover.

**Acceptance Criteria:**

**Given** the Part D parity audit is complete
**When** Phase 6 screens are implemented
**Then** settings, incidents, and skills list/detail flows match the design system
**And** provider settings, topology upload and drift cadence, reviewer-feedback stats, and custom-skills management preserve current behavior unless Part A2 sanctions a change
**And** any retired UI callback-only behavior is extracted into `/api/v1` as Part A3-sanctioned backend work
**And** the retired Dashboard Result Display Duration setting is recorded as `sanctioned-change (A2)`.

### Story 15.7: Phase 7 - Cutover and retired UI Removal

As a maintainer,
I want the React SPA to become the only web UI,
So that retired UI code, dependencies, assets, and tests no longer remain in the runtime.

**Acceptance Criteria:**

**Given** every screen has a React replacement or approved disposition
**When** cutover is performed
**Then** the SPA moves to `/` and legacy routes redirect appropriately
**And** the retired Python UI package, its dependency, old UI tests, old assets, dead CSS, and orphaned static files are removed
**And** Part D2 grep gates pass for retired framework and old test-lane references
**And** README screenshots, runtime badges, CI lanes, a11y routes, CHANGELOG, and final image-size delta are updated.

### retired UI Story Supersession

The following existing stories were written for the retired UI-era UI. Their UI implementation scope is superseded by Epic 15 and the Part D parity audit. Non-UI backend, API, data, or documentation obligations remain in force unless a later planning update explicitly replaces them.

| Existing story | Superseded UI scope | Replacement in Epic 15 |
|---|---|---|
| Story 3.1: Verdict-First Report Header | retired UI report header rendering | Story 15.4 |
| Story 3.2: Findings Table With Evidence Badges | retired UI findings table and evidence badge rendering | Story 15.4 |
| Story 3.3: Evidence Inspector Panel | retired UI evidence inspector UI | Story 15.4 |
| Story 3.4: Confidence Ledger and Why-Not-Lower/Higher | retired UI confidence ledger UI | Story 15.4 |
| Story 3.5: Context Completeness and TODO Panel | retired UI context and TODO panel UI | Story 15.4 and Story 15.6 |
| Story 3.6: Report Diff After Rerun | retired UI report comparison/diff UI | Story 15.4 and Story 15.5 |
| Story 3.7: Keyboard and Accessibility Review Pass | retired UI keyboard and accessibility review surface | Stories 15.2 through 15.7 |
| Story 3.8: Historical Report Search and Filtering | retired UI history UI | Story 15.5 |
| Story 4.5: Reviewer Feedback Capture | Separate retired UI reviewer-feedback UI placement | Story 15.4 inline finding feedback and Story 15.6 feedback stats |
| Story 6.4: Outcome Calibration Metrics | retired UI dashboard trend/limitation labels | Story 15.3 |
| Story 9.5: Skills Browser UI | retired UI skills browser UI | Story 15.6 |
| Story 12.2: Provider Settings Administration | retired UI provider settings UI | Story 15.6 |

## Final Validation Notes

- All finalized PRD requirement families are represented in the Requirements Inventory.
- Every functional requirement family maps to at least one epic.
- Cross-cutting NFRs are assigned to the epics where they are enforced.
- Stories are sequenced so each story depends only on prior baseline capabilities or earlier stories in the same epic.
- Existing story files should be reconciled against this plan before sprint planning resumes.
- Next recommended workflow: `bmad-check-implementation-readiness`.
