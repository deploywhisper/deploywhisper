---
stepsCompleted:
  - step-01-document-discovery
  - step-02-prd-analysis
  - step-03-epic-coverage-validation
  - step-04-ux-alignment
  - step-05-epic-quality-review
  - step-06-final-assessment
documentsIncluded:
  - type: PRD
    path: _bmad-output/planning-artifacts/prd.md
    format: whole
  - type: Architecture
    path: _bmad-output/planning-artifacts/architecture.md
    format: whole
  - type: Epics
    path: _bmad-output/planning-artifacts/epics.md
    format: whole
  - type: UX Design
    path: _bmad-output/planning-artifacts/ux-design-specification.md
    format: whole
---

# Implementation Readiness Assessment Report

**Date:** 2026-04-27
**Project:** deploywhisper

## Document Discovery

### Files Included

- PRD: `_bmad-output/planning-artifacts/prd.md` (whole document)
- Architecture: `_bmad-output/planning-artifacts/architecture.md` (whole document)
- Epics: `_bmad-output/planning-artifacts/epics.md` (whole document)
- UX Design: `_bmad-output/planning-artifacts/ux-design-specification.md` (whole document)

### Discovery Notes

- No sharded PRD, architecture, epics, or UX folders were found.
- No duplicate whole/sharded document conflicts were found.
- All required document categories are present.

## PRD Analysis

### Functional Requirements

ING-01: Accept one or more artifacts from supported toolchains in a single analysis.

ING-02: Auto-detect artifact type without requiring manual labeling for normal cases.

ING-03: Support partial analysis when not all related artifacts are available.

ING-04: Detect unsupported artifacts and explain why they were excluded.

ING-05: Detect sensitive files and block unsafe downstream handling.

ING-06: Preserve a submission manifest showing which artifacts were accepted, excluded, partially parsed, or failed.

EVD-01: Normalize supported artifacts into a shared internal change model.

EVD-02: Each finding shall reference one or more concrete evidence items.

EVD-03: Evidence items shall identify artifact, location, resource, change operation, or contextual source where applicable.

EVD-04: The report shall distinguish deterministic findings from model-inferred explanations.

EVD-05: The report shall surface confidence and uncertainty for key findings and overall verdict.

EVD-06: The report shall explain the main contributors to overall risk score.

EVD-07: When context is incomplete, the report shall show explicit uncertainty instead of implying certainty.

EVD-08: Evidence items persist with the report for audit and comparison.

RSK-01: Produce a unified deployment risk verdict for the whole submission.

RSK-02: Classify findings and verdicts by severity level.

RSK-03: Detect cross-tool interactions that increase risk.

RSK-04: Generate a reviewer-oriented explanation of why a risk matters operationally.

RSK-05: Generate actionable remediation or verification guidance.

RSK-06: Produce rollback guidance and rollback complexity score.

RSK-07: Distinguish between product recommendation and human decision.

RSK-08: Continue to return deterministic results if narrative generation fails.

CTX-01: Compute blast radius using maintained topology context.

CTX-02: Indicate when topology is stale, missing, or incomplete.

CTX-03: Ingest incident records for similarity matching.

CTX-04: Surface relevant incident similarity results with match confidence.

CTX-05: Support service criticality and environment-aware risk context.

CTX-06: Store deployment history sufficient for comparison and trend analysis.

CTX-07: Support future topology auto-discovery and context connectors without replacing the core report format.

REV-01: The web report shall present verdict first, then evidence, then details.

REV-02: The report shall show top findings, blast radius, rollback, and uncertainty above the fold.

REV-03: Users shall be able to inspect full findings and evidence details on demand.

REV-04: Users shall be able to retrieve prior reports and compare analyses over time.

REV-05: The system shall generate a concise share summary for PRs and approval threads.

REV-06: Shared summaries shall remain explicitly advisory.

REV-07: The report shall support both expert quick scan and detailed investigation.

WRK-01: Expose a stable versioned REST API.

WRK-02: Expose CLI access using the same analysis core.

WRK-03: Support GitHub-first workflow delivery for PR review.

WRK-04: Post a formatted PR summary including verdict, top risks, blast radius, rollback context, and uncertainty.

WRK-05: Support rerun after new commits or changed artifacts.

WRK-06: Support report links and machine-friendly summary payloads.

WRK-07: Support future GitLab / Atlantis / HCP Terraform / Jenkins adapters without redesigning the core analysis object.

HIS-01: Persist completed reports before showing final success.

HIS-02: Retain audit metadata with each report.

HIS-03: Users shall be able to search and filter historical reports.

HIS-04: Managers shall be able to review risk trends over time.

HIS-05: Capture reviewer feedback on report quality and correctness.

HIS-06: Support outcome capture after deployment for later calibration.

HIS-07: Support benchmark and backtest workflows against historical incidents.

ADM-01: Admins shall configure narrative provider settings through a DeployWhisper-owned provider adapter boundary that preserves shared UI/API/CLI behavior and keeps provider secrets out of persistence.

ADM-02: Admins shall enable fully local-only operation.

ADM-03: Admins shall manage topology data and freshness status.

ADM-04: Admins shall manage incident ingestion and indexing.

ADM-05: Admins shall add or override custom skills and organization-specific heuristics.

ADM-06: Admins shall manage thresholds and reporting defaults without changing core code.

ADM-07: Future policy adapters shall consume report outputs without changing advisory-first core behavior.

COM-01: Expose a Skills registry API for listing, fetching, and installing community-contributed skills.

COM-02: Support versioned Skills with a formal manifest schema.

COM-03: Automated test harness runs on every Skill submission.

COM-04: Skills installer CLI: `deploywhisper skill install <name>`.

COM-05: Public Skills browser UI with search, filters, and ratings.

COM-06: Skill analytics: download counts, test pass rates, last-updated timestamps.

COM-07: Contribution workflow: PR template, automated linting, reviewer assignment.

Total FRs: 65.

### Non-Functional Requirements

NFR-SEC-01: Raw infrastructure artifacts shall never be sent to external LLM providers.

NFR-SEC-02: Provider credentials shall not be persisted in the application database.

NFR-SEC-03: Logs shall exclude secrets, raw IaC, prompts, and raw model responses.

NFR-SEC-04: Sensitive-file handling shall always remain enabled.

NFR-SEC-05: Fully local operation shall be possible with local model execution (Ollama).

NFR-SEC-06: The narrative-provider integration path shall minimize unnecessary dependency and supply-chain surface when direct provider SDKs satisfy the required capability more safely than a multi-provider meta-abstraction.

NFR-PERF-01: Standard analysis should complete in under 15 seconds for expected v1 workloads.

NFR-PERF-02: PR summary generation should complete in under 5 seconds.

NFR-PERF-03: History retrieval shall remain responsive for at least 1,000 stored reports in v1.

NFR-PERF-04: The system shall support small-team concurrency without severe degradation.

NFR-REL-01: Parser failures shall be isolated per artifact where possible.

NFR-REL-02: Narrative failure shall degrade gracefully to deterministic output.

NFR-REL-03: Completed reports shall be persisted before being presented as final.

NFR-REL-04: Health checks and startup validation shall make runtime issues visible early.

NFR-XAI-01: Severity must never be communicated by color alone.

NFR-XAI-02: Key visualizations must have textual equivalents.

NFR-XAI-03: Evidence and uncertainty must be readable in both UI and shared summaries.

NFR-XAI-04: The interface shall remain keyboard navigable for common review workflows.

NFR-OPS-01: Web, API, CLI, and integration outputs shall share one analysis core.

NFR-OPS-02: The product shall preserve a stable report schema across access surfaces.

NFR-OPS-03: The architecture shall support migration from SQLite to PostgreSQL without redesigning domain models.

NFR-OPS-04: The architecture shall support adding async workers later without breaking existing interfaces.

NFR-OPS-05: Narrative provider integrations shall be isolated behind an internal adapter interface so providers can be added, removed, upgraded, or capability-scoped without rewriting UI, API, CLI, or report persistence flows.

Total NFRs: 23.

### Additional Requirements

DIF-01: Present evidence-backed findings rather than only natural-language summary.

DIF-02: Explicitly show uncertainty and context completeness.

DIF-03: Support PR-native workflow delivery as a first-class use case.

DIF-04: Preserve local-first analysis boundaries as a primary product promise.

DIF-05: Support learning loops from reviewer feedback and deployment outcomes.

DIF-06: Enable community extension through the AI Skills marketplace.

DIF-07: Publish measurable benchmark results against competing approaches.

Phase 1 exit criteria: mixed-artifact analysis works reliably; reports contain evidence and uncertainty; deterministic core works without narrative; history and audit metadata persist correctly; senior reviewers consider high/critical findings credible enough to test in real workflows; evidence inspector is usable in the UI; at least 3 internal or friendly-user teams use the product.

Phase 1.5 exit criteria: GitHub workflow integration is live and documented; PR summaries are reused in real reviews; rerun-on-commit works; report comparison and sharing are usable; deployment approvals start referencing reports regularly; Skills marketplace is live with 20+ seed skills; first external Skill contribution is merged.

Phase 2 exit criteria: context completeness improves materially; incident similarity becomes useful in practice; deployment history and outcome capture exist; published benchmark corpus and quarterly results are available; false positive/false reassurance trends are measurable and improving; CNCF Sandbox application is submitted or accepted; GitHub stars exceed 1,000.

Decisions recorded in open questions: ship GitHub Action first while also supporting a GitHub App; high/critical findings require at least one deterministic evidence item; capture analysis ID, timestamp, deploy outcome, and linked incidents first for deployment history; prioritize Terraform state, GitHub PR history, and Slack postmortem ingestion for context connectors; introduce policy adapters only after 85% high/critical precision is sustained for 3 consecutive quarterly runs; introduce hosted SaaS after Phase 2.

### PRD Completeness Assessment

The PRD is complete enough for traceability validation: it has explicit numbered FRs and NFRs, phase scope, release exit criteria, target users, non-goals, product principles, and key decisions. The main readiness risks to validate in later steps are scope breadth across six epics, whether every NFR has implementation/test coverage, and whether the epics preserve the local-first, advisory-first, evidence-backed product boundaries.

## Epic Coverage Validation

### Epic FR Coverage Extracted

ING-01..06: Covered by existing repository baseline; preserve during Epic 1 migration.

EVD-01: Covered by existing normalized change model plus `E1-S2` and `E1-S3`.

EVD-02..08: Covered by `E1-S1..E1-S8`, `E2-S2..E2-S4`, and `E2-S7`.

RSK-01..08: Covered by existing repository baseline plus `E1-S3`, `E1-S6`, `E1-S7`, `E2-S1`, `E2-S6`, and `E2-S7`.

CTX-01..07: Covered by existing topology/incidents baseline plus `E1-S5`, `E2-S4`, `E2-S5`, and `E5-S1..E5-S8`.

REV-01..07: Covered by existing dashboard/history baseline plus `E2-S1..E2-S8`.

WRK-01..02: Covered by existing API and CLI baseline.

WRK-03..07: Covered by `E3-S1..E3-S8`.

HIS-01..04: Covered by existing persistence/history baseline plus `E5-S4` and `E5-S8`.

HIS-05..07: Covered by `E5-S5..E5-S8` and `E6-S1..E6-S8`.

ADM-01..05: Covered by existing settings/local-mode/topology/custom-skill baseline plus `BH-S1..BH-S5`, `E4-S1..E4-S9`, and `E5-S1..E5-S4`.

ADM-06..07: Claimed as cross-cutting governance in `E1`, `E5`, and future adapter work.

COM-01..07: Covered by `E4-S1..E4-S9`.

Total PRD FRs found in epic coverage claims: 65.

### Coverage Matrix

| FR Number | PRD Requirement | Epic Coverage | Status |
| --- | --- | --- | --- |
| ING-01 | Accept one or more artifacts from supported toolchains in a single analysis | Existing repo baseline; preserve during Epic 1 migration | Covered |
| ING-02 | Auto-detect artifact type without requiring manual labeling for normal cases | Existing repo baseline; preserve during Epic 1 migration | Covered |
| ING-03 | Support partial analysis when not all related artifacts are available | Existing repo baseline; preserve during Epic 1 migration | Covered |
| ING-04 | Detect unsupported artifacts and explain why they were excluded | Existing repo baseline; preserve during Epic 1 migration | Covered |
| ING-05 | Detect sensitive files and block unsafe downstream handling | Existing repo baseline; preserve during Epic 1 migration | Covered |
| ING-06 | Preserve a submission manifest showing accepted, excluded, partially parsed, or failed artifacts | Existing repo baseline; preserve during Epic 1 migration | Covered |
| EVD-01 | Normalize supported artifacts into a shared internal change model | Existing normalized model plus E1-S2 / E1-S3 | Covered |
| EVD-02 | Each finding shall reference one or more concrete evidence items | E1-S1..E1-S8, E2-S2..E2-S4, E2-S7 | Covered |
| EVD-03 | Evidence items identify artifact, location, resource, operation, or contextual source | E1-S1..E1-S8, E2-S2..E2-S4, E2-S7 | Covered |
| EVD-04 | Distinguish deterministic findings from model-inferred explanations | E1-S1..E1-S8, E2-S2..E2-S4, E2-S7 | Covered |
| EVD-05 | Surface confidence and uncertainty for key findings and overall verdict | E1-S1..E1-S8, E2-S2..E2-S4, E2-S7 | Covered |
| EVD-06 | Explain main contributors to overall risk score | E1-S1..E1-S8, E2-S2..E2-S4, E2-S7 | Covered |
| EVD-07 | Show explicit uncertainty when context is incomplete | E1-S1..E1-S8, E2-S2..E2-S4, E2-S7 | Covered |
| EVD-08 | Evidence items persist with report for audit and comparison | E1-S1..E1-S8, E2-S2..E2-S4, E2-S7 | Covered |
| RSK-01 | Produce a unified deployment risk verdict | Existing baseline plus E1-S3, E1-S6, E1-S7, E2-S1, E2-S6, E2-S7 | Covered |
| RSK-02 | Classify findings and verdicts by severity level | Existing baseline plus E1-S3, E1-S6, E1-S7, E2-S1, E2-S6, E2-S7 | Covered |
| RSK-03 | Detect cross-tool interactions that increase risk | Existing baseline plus E1-S3, E1-S6, E1-S7, E2-S1, E2-S6, E2-S7 | Covered |
| RSK-04 | Generate reviewer-oriented operational explanation | Existing baseline plus E1-S3, E1-S6, E1-S7, E2-S1, E2-S6, E2-S7 | Covered |
| RSK-05 | Generate remediation or verification guidance | Existing baseline plus E1-S3, E1-S6, E1-S7, E2-S1, E2-S6, E2-S7 | Covered |
| RSK-06 | Produce rollback guidance and rollback complexity score | Existing baseline plus E2-S6 | Covered |
| RSK-07 | Distinguish product recommendation from human decision | Existing baseline plus Epic 1/2 advisory presentation | Covered |
| RSK-08 | Continue deterministic results if narrative generation fails | Existing baseline plus E1-S7 | Covered |
| CTX-01 | Compute blast radius using maintained topology context | Existing baseline plus E1-S5, E2-S4, E2-S5, E5-S1..E5-S8 | Covered |
| CTX-02 | Indicate stale, missing, or incomplete topology | Existing baseline plus E1-S5, E2-S4, E5-S3 | Covered |
| CTX-03 | Ingest incident records for similarity matching | Existing baseline plus E5-S6 | Covered |
| CTX-04 | Surface incident similarity with match confidence | Existing baseline plus Epic 1/2/5 context work | Covered |
| CTX-05 | Support service criticality and environment-aware context | Existing baseline plus E5 context work | Covered |
| CTX-06 | Store deployment history for comparison and trend analysis | Existing baseline plus E5-S4, E5-S8 | Covered |
| CTX-07 | Support future topology auto-discovery/connectors without replacing report format | E5-S1..E5-S8 plus stable report architecture | Covered |
| REV-01 | Web report presents verdict first, then evidence, then details | Existing baseline plus E2-S1..E2-S8 | Covered |
| REV-02 | Show top findings, blast radius, rollback, and uncertainty above the fold | Existing baseline plus E2-S1..E2-S8 | Covered |
| REV-03 | Inspect full findings and evidence details on demand | Existing baseline plus E2-S2, E2-S3 | Covered |
| REV-04 | Retrieve prior reports and compare analyses over time | Existing baseline plus E3-S5, E5-S4/E5-S8 | Covered |
| REV-05 | Generate concise share summary for PRs and approval threads | E2-S7 and E3-S2 | Covered |
| REV-06 | Shared summaries remain explicitly advisory | E2-S7 and E3 GitHub-native advisory delivery | Covered |
| REV-07 | Support expert quick scan and detailed investigation | E2-S1..E2-S8 | Covered |
| WRK-01 | Expose stable versioned REST API | Existing API baseline | Covered |
| WRK-02 | Expose CLI access using same analysis core | Existing CLI baseline | Covered |
| WRK-03 | Support GitHub-first workflow delivery for PR review | E3-S1..E3-S8 | Covered |
| WRK-04 | Post formatted PR summary with verdict, top risks, blast radius, rollback, uncertainty | E3-S2 | Covered |
| WRK-05 | Support rerun after new commits or changed artifacts | E3-S3 | Covered |
| WRK-06 | Support report links and machine-friendly summary payloads | E3-S4, E2-S7 | Covered |
| WRK-07 | Support future GitLab / Atlantis / HCP Terraform / Jenkins adapters without redesigning core object | E3-S1..E3-S8 plus future adapter note | Covered |
| HIS-01 | Persist completed reports before final success | Existing baseline plus E5 | Covered |
| HIS-02 | Retain audit metadata with each report | Existing baseline plus E5 | Covered |
| HIS-03 | Search and filter historical reports | Existing baseline plus E5 | Covered |
| HIS-04 | Review risk trends over time | Existing baseline plus E5-S8 | Covered |
| HIS-05 | Capture reviewer feedback on report quality/correctness | E5-S5 | Covered |
| HIS-06 | Support outcome capture after deployment | E5-S4, E5-S6 | Covered |
| HIS-07 | Support benchmark and backtest workflows against historical incidents | E5-S6, E6-S1..E6-S8 | Covered |
| ADM-01 | Configure narrative provider settings through DeployWhisper-owned adapter boundary | Existing baseline plus BH-S1..BH-S5 | Covered |
| ADM-02 | Enable fully local-only operation | Existing baseline plus BH hardening | Covered |
| ADM-03 | Manage topology data and freshness status | Existing baseline plus E5-S1..E5-S4 | Covered |
| ADM-04 | Manage incident ingestion and indexing | Existing baseline plus E5 | Covered |
| ADM-05 | Add or override custom skills and org-specific heuristics | Existing baseline plus E4-S1..E4-S9 | Covered |
| ADM-06 | Manage thresholds and reporting defaults without changing core code | Cross-cutting governance in E1/E5/future adapter work | At Risk |
| ADM-07 | Future policy adapters consume report outputs without changing advisory-first core behavior | Cross-cutting governance in E1/E5/future adapter work | At Risk |
| COM-01 | Expose Skills registry API | E4-S1 | Covered |
| COM-02 | Support versioned Skills with formal manifest schema | E4-S2 | Covered |
| COM-03 | Automated test harness runs on every Skill submission | E4-S3, E4-S6 | Covered |
| COM-04 | Skills installer CLI | E4-S4 | Covered |
| COM-05 | Public Skills browser UI with search, filters, ratings | E4-S5 | Covered |
| COM-06 | Skill analytics | E4-S8 | Covered |
| COM-07 | Contribution workflow | E4-S6 | Covered |

### Missing Requirements

No PRD functional requirement is completely absent from the epics document.

### At-Risk Coverage

ADM-06: Admins shall manage thresholds and reporting defaults without changing core code.
- Impact: The epics claim cross-cutting governance but do not assign this to a concrete story with acceptance criteria.
- Recommendation: Add explicit acceptance criteria to an Epic 1 or Epic 5 story, or create a small admin/config story.

ADM-07: Future policy adapters shall consume report outputs without changing advisory-first core behavior.
- Impact: This is directionally covered, but the implementation path is described as future adapter work rather than story-level scope.
- Recommendation: Add an explicit architectural acceptance criterion to the GitHub/workflow adapter stories or a future policy-adapter placeholder story.

### Coverage Statistics

- Total PRD FRs: 65
- FRs covered in epics: 63 fully covered, 2 at-risk but claimed
- Completely missing FRs: 0
- Coverage percentage: 100% claimed coverage; 96.9% strong traceability

## UX Alignment Assessment

### UX Document Status

Found: `_bmad-output/planning-artifacts/ux-design-specification.md`

The UX document is marked complete, with completed workflow steps through responsive/accessibility and finalization. It is a whole document, not sharded.

### UX ↔ PRD Alignment

Aligned:

- The PRD’s platform engineer, SRE approver, junior engineer, manager, admin, CI/automation consumer, and skills contributor users are reflected in UX target users or journey patterns.
- The PRD’s central review question maps directly to the UX “deploy briefing before production” defining experience.
- The PRD’s verdict-first report requirements (`REV-01`, `REV-02`, `REV-07`) align with UX rules for above-the-fold verdict, top risk, and decision hierarchy.
- Evidence and uncertainty requirements (`EVD-02..08`, `NFR-XAI-03`) align with UX rules for evidence on demand, parser coverage, degraded analysis states, and visible uncertainty.
- Rollback, blast radius, incident match, report history, share/re-run, and topology admin flows all have UX coverage.
- Accessibility requirements (`NFR-XAI-01..04`) are explicitly covered by text labels, contrast, keyboard navigation, textual visualization equivalents, and no color-only status communication.

Potential gaps:

- PRD `COM-05` requires a public Skills browser UI with search, filters, and ratings. UX references AI Skills and admin/custom-skill validation, but does not deeply specify the public marketplace browse/detail/rating experience.
- PRD/Epic 6 requires public benchmark results and calibration dashboards. UX covers risk trends and history scanability, but does not specify benchmark dashboard UX or comparative-results browsing.
- PRD `HIS-05..07` and Epic 5 include reviewer feedback, outcome capture, calibration, and trend analysis. UX mentions feedback loops and manager trends, but feedback capture and calibration dashboard interactions are lighter than the PRD scope.

### UX ↔ Architecture Alignment

Aligned:

- UX chooses NiceGUI / Quasar as the component foundation, matching architecture ADR-01 and the shared NiceGUI + FastAPI runtime.
- UX emphasizes one shared report object rendered across review surfaces, matching the architecture’s one-analysis-core and Report Service decisions.
- UX component strategy maps cleanly to architecture: VerdictCard, ParserCoverageRow, Evidence/ChangeRiskTable, BlastRadiusPanel, RollbackTimeline, IncidentMatchCard, and AnalysisHistoryRow are supported by the evidence, context, rollback, incident, report, and history services.
- UX parser coverage and staged progress align with the canonical pipeline: intake, parse, skills, evidence, context, blast radius, similarity, rollback, score, narrate, assemble, persist, deliver.
- UX share/re-run/escalation flows align with the GitHub adapter, share summary, report URL, and comparison architecture.
- UX topology/admin validation aligns with context service, topology versions, and future topology import/drift stories.

Potential architecture/UX gaps:

- Architecture includes Skills Registry Service, Skill Validator, installer, registry API, and public registry repository; UX does not yet fully define the public registry browser and skill detail interaction model.
- Architecture includes Benchmark Runner, benchmark corpus, comparator execution, and public results dashboard; UX does not yet define benchmark-result pages, filters, methodology display, or comparison tables.
- Architecture includes feedback event persistence and calibration dashboards; UX does not yet define the per-finding feedback controls or calibration dashboard information architecture in detail.

### Warnings

- UX is strong for the core deploy-review workflow and sufficient for Epics 1-3.
- UX should be extended before full Epic 4-6 implementation to cover public Skills marketplace browsing, benchmark result dashboards, reviewer feedback capture, calibration dashboards, and manager trend views.

## Epic Quality Review

### Summary

The epic plan is strong as a product roadmap and has good requirement-family traceability. It is not yet uniformly strong as a strict implementation-ready story pack. The biggest issues are:

- Several stories are technical milestones framed around developer/maintainer work rather than direct user value.
- Several stories are too large to be independently completed as a small implementation story.
- Acceptance criteria are generally testable but are not written in Given/When/Then format.
- Two PRD admin/governance requirements have at-risk, cross-cutting ownership instead of concrete story-level ownership.

### Critical Violations

None found that fully block the roadmap from being used. No epic requires a future epic to function in a circular or impossible way, and no PRD FR is completely absent from coverage.

### Major Issues

1. Technical stories in Epic 1 and the Brownfield Hardening Track.

Examples:

- `E1-S1: Domain model foundations` is framed as developer-facing model/table setup.
- `E1-S2: Evidence Extractor service` is service construction.
- `E1-S3: Refactor risk scorer to consume evidence` is implementation refactoring.
- `BH-S2: Introduce provider adapter contract and registry` is technical boundary work.
- `BH-S4: Migrate OpenRouter, Groq, and xAI...` is dependency/runtime migration.

Impact: These stories may be necessary in a brownfield system, but under strict create-epics-and-stories standards they are not ideal user-value stories. They should be tied more explicitly to reviewer/admin outcomes or kept as a labeled technical hardening track outside the product story sequence.

Recommendation: Keep the Brownfield Hardening Track separate, but revise Epic 1 story titles and acceptance criteria to foreground reviewer trust outcomes. Example: “Reviewer can inspect evidence-backed findings” rather than “Domain model foundations.”

2. Oversized stories.

Examples:

- `E3-S6: GitHub App` includes runtime, operator guide, checks API, PR events, OAuth, installation, and docs. This should be split.
- `E4-S7: Seed 20 community skills` requires 20 skills, manifests, scenarios, installation, and risk patterns. This is an epic-sized batch.
- `E5-S1: Terraform state import` covers AWS, GCP, and Azure provider support in one story. This should likely split by provider or capability.
- `E6-S1: Benchmark corpus v1` requires 100 scenarios across five tools. This is too large for one implementation story.
- `E6-S4: Comparative runner` covers multiple comparator integrations in one story.

Impact: These stories are difficult to estimate, review, test, and complete independently.

Recommendation: Split these into smaller vertical increments. For example, `E5-S1a AWS Terraform state import`, `E5-S1b GCP coverage`, `E5-S1c Azure coverage`; `E6-S1a corpus schema`, `E6-S1b 20 Terraform/Kubernetes seed scenarios`, then follow-on batches.

3. Acceptance criteria format is not BDD-style.

Most acceptance criteria are bullet lists rather than Given/When/Then. They are often testable, but not consistently structured as independent acceptance scenarios.

Impact: Implementation agents and reviewers may interpret criteria differently, especially for UI and integration stories.

Recommendation: Before story execution, convert active story acceptance criteria into explicit scenario-style checks. This is most important for GitHub integration, skills marketplace, feedback/calibration, and benchmark stories.

4. ADM-06 and ADM-07 lack concrete story ownership.

- `ADM-06` threshold/default management is only mapped to cross-cutting governance.
- `ADM-07` policy adapter consumption is only mapped to future adapter work.

Impact: These requirements can fall through during implementation because no single story is accountable.

Recommendation: Add explicit story ownership or acceptance criteria before implementation reaches the relevant admin/integration scope.

### Minor Concerns

- Epic 6 serves trust/marketing/proof outcomes more than immediate in-product user workflow. It is strategically valid but should be treated as proof-engine work, not core deploy-review readiness.
- Epic 4 includes public marketplace and contribution flow but the UX spec is thinner for marketplace detail pages, ratings, curation, and contribution review surfaces.
- Some story actors are internal roles (`developer`, `maintainer`, `system`, `marketer`). That is acceptable for technical enablement, but these should be clearly marked as platform enablement stories rather than user-facing workflow stories.
- Some dependency language is high-level rather than operationally enforced. Example: “Epic 4 can start as soon as Epic 2 is rendering the new schema” is reasonable, but should be reflected in sprint sequencing.

### Dependency Review

- Epic sequencing is coherent: Epic 1 evidence model precedes Epic 2 report UI; Epic 2 share/report structure supports Epic 3 PR delivery; Epic 4 can begin after schema/rendering foundations; Epics 5 and 6 depend on report/schema stability.
- No circular dependency found.
- No forward dependency found where an earlier epic requires a later epic to function.
- Within-epic sequencing is generally logical, especially Epic 1, Epic 2, Epic 3, and Epic 5.

### Database / Entity Timing Review

- The plan does not create every future table up front in one setup story.
- `E1-S1` creates evidence-model tables when the evidence model is introduced, which is acceptable.
- Architecture lists future tables for skills and benchmarks, but the epics place those capabilities in Epic 4 and Epic 6 rather than forcing them into Epic 1.

### Best Practices Compliance Checklist

| Epic | User Value | Independent | Story Size | No Forward Dependencies | AC Quality | Traceability |
| --- | --- | --- | --- | --- | --- | --- |
| Brownfield Hardening | Partial | Yes | Mostly OK | Yes | Needs BDD conversion | Good |
| Epic 1 | Partial | Yes | Mostly OK | Yes | Needs BDD conversion | Strong |
| Epic 2 | Strong | Depends appropriately on Epic 1 | Mostly OK | Yes | Needs BDD conversion | Strong |
| Epic 3 | Strong | Depends appropriately on Epics 1-2 | Mixed; E3-S6 large | Yes | Needs BDD conversion | Strong |
| Epic 4 | Strong | Depends on schema/UI foundation | Mixed; E4-S7 large | Yes | Needs BDD conversion | Strong |
| Epic 5 | Strong | Depends on stable report/context baseline | Mixed; E5-S1 large | Yes | Needs BDD conversion | Good |
| Epic 6 | Moderate | Depends on stable analysis/report baseline | Mixed; E6-S1/E6-S4 large | Yes | Needs BDD conversion | Good |

### Quality Review Recommendation

The roadmap is usable for implementation planning, but individual stories should be refined before execution. The next implementation-ready pass should focus on:

1. Split oversized stories.
2. Add concrete ownership for ADM-06 and ADM-07.
3. Convert acceptance criteria into Given/When/Then or equivalent testable scenarios.
4. Extend UX coverage for Epic 4-6 surfaces before starting those epics.

## Summary and Recommendations

### Overall Status

**NEEDS WORK**

The planning package is strong enough to continue implementation for individually refined near-term stories, especially the existing evidence-first analysis and review flows. It is not yet fully implementation-ready for the whole remaining roadmap because several later-epic stories are too large, acceptance criteria need test-ready structure, and a few PRD requirements need clearer story ownership.

### Critical Issues Requiring Immediate Action

No blocker-level document gaps were found. The PRD, architecture, epics, and UX specification are all present as whole documents, and no functional requirement is completely missing from epic coverage.

Before starting new roadmap implementation, address these readiness issues:

1. Assign concrete story ownership for `ADM-06` threshold/default management and `ADM-07` policy adapter consumption.
2. Split oversized stories before implementation: `E3-S6`, `E4-S7`, `E5-S1`, `E6-S1`, and `E6-S4`.
3. Convert active story acceptance criteria into testable Given/When/Then form.
4. Extend UX coverage before Epic 4 through Epic 6 implementation, especially marketplace browsing/detail/rating, reviewer feedback and calibration, and benchmark dashboards.

### Recommended Next Steps

1. Patch the epics document with explicit `ADM-06` and `ADM-07` ownership and smaller implementation slices for the oversized stories.
2. For the next implementation slice, run `bmad-create-story` only after selecting the next sprint item and refining that story's acceptance criteria into BDD-style checks.
3. Before Epic 4 through Epic 6 enter delivery, update the UX specification for marketplace, feedback/calibration, and benchmark reporting workflows.
4. Refresh sprint tracking after planning refinements so implementation status matches the corrected story structure.

### Final Note

Assessment completed on 2026-04-27 by Codex using the BMad implementation readiness workflow. Findings: 0 duplicate or missing planning documents, 0 missing functional requirements, 2 at-risk requirements, 4 major epic-quality issues, and 4 minor roadmap readiness concerns. Proceed with refined stories, but do not treat the complete roadmap as implementation-ready until the issues above are resolved.
