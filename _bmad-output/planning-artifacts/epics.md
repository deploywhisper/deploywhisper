---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/architecture.md
---

# ai-deploy-whisper - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for ai-deploy-whisper, decomposing the requirements from the PRD, UX Design if it exists, and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: Platform engineers can submit deployment artifacts from Terraform, Kubernetes, Ansible, Jenkins, and CloudFormation for a single analysis.  
FR2: Platform engineers can submit multiple files from multiple supported tools in one analysis session.  
FR3: The system can identify the supported tool type of each submitted artifact without requiring manual classification from the user.  
FR4: The system can analyze partial deployment context when only a subset of related artifacts is provided.  
FR5: The system can detect unsupported or sensitive files in a submission and warn the user when those files are excluded from analysis or external model use.  
FR6: Platform engineers can receive a single risk assessment that combines findings across all submitted deployment artifacts.  
FR7: The system can produce a deploy recommendation that indicates whether a change appears safe, needs caution, or requires escalation.  
FR8: The system can identify cross-tool interactions where individually benign changes create elevated combined risk.  
FR9: The system can classify risk findings by severity so that users can distinguish low, medium, high, and critical issues.  
FR10: The system can explain which detected changes contributed to the overall risk assessment.  
FR11: Platform engineers can receive a plain-English narrative that explains what changed, why it matters, and what could break.  
FR12: Junior engineers can receive tool-specific explanations that help them understand why a change is risky.  
FR13: Users can receive actionable guidance describing what to review, change, or verify before deployment.  
FR14: SRE leads can review a decision-ready summary that supports go or no-go deployment decisions.  
FR15: Users can distinguish between the system's recommendation and the final human deployment decision.  
FR16: Users can view which downstream services, systems, or resources may be affected by a deployment change.  
FR17: The system can indicate when blast-radius analysis may be incomplete because required topology context is missing or stale.  
FR18: SRE leads can review impact information in enough detail to assess which teams or systems may need coordination before release.  
FR19: Platform administrators can maintain the service-topology context used for impact analysis.  
FR20: Users can receive a rollback plan for an analyzed deployment.  
FR21: Users can review rollback steps in an ordered sequence that reflects operational recovery flow.  
FR22: SRE leads can review rollback complexity as part of deployment decision making.  
FR23: Platform administrators can ingest past incident records so the system can compare new deployments against historical failures.  
FR24: Users can see when a current deployment resembles a previously recorded incident.  
FR25: The system can retain a history of completed analyses for later review.  
FR26: Engineering managers can review historical deployment analyses to understand risk trends over time.  
FR27: Engineering managers can compare risk patterns across tools, time periods, and deployment outcomes.  
FR28: Teams can use analysis history as an audit trail showing when a deployment was reviewed and what assessment was produced.  
FR29: Users can retrieve past reports for investigation, learning, or approval-thread reference.  
FR30: Platform administrators can configure which language model provider the system uses for narrative generation.  
FR31: Platform administrators can operate the system in a fully local analysis mode when external model usage is not allowed.  
FR32: Platform administrators can add or override team-specific AI Skills so analysis reflects internal modules, conventions, and risk patterns.  
FR33: Platform administrators can manage the operational context required for analysis, including incident records and topology definitions.  
FR34: Teams can use the system without enabling automated deployment blocking.  
FR35: Platform engineers can use a web interface to submit artifacts, review findings, and access historical analyses.  
FR36: Technical users can access analysis capabilities through an API for automation and integration workflows.  
FR37: Technical users can trigger analysis from command-line workflows when a browser interface is not the preferred entry point.  
FR38: CI workflows can submit deployment artifacts for advisory analysis and consume structured results.  
FR39: Teams can share analysis outputs within deployment review workflows without requiring the system itself to make the final release decision.

### NonFunctional Requirements

NFR1: The system shall complete a standard deployment analysis in under 15 seconds under normal operating conditions.  
NFR2: The web dashboard shall load in under 1.5 seconds on supported desktop browsers under normal internal-network conditions.  
NFR3: The UI shall update analysis results within 500 milliseconds after a completed analysis is available.  
NFR4: The analysis history interface shall remain responsive with at least 1000 stored reports using indexed and paginated retrieval.  
NFR5: The system shall support at least 3 concurrent analyses without major degradation in responsiveness or analysis completion time.  
NFR6: The system shall never send raw infrastructure-as-code content to external LLM providers.  
NFR7: The system shall store API keys only in memory or environment variables and shall never persist them to local databases, logs, or generated reports.  
NFR8: Sensitive-file detection shall always remain enabled and shall automatically exclude dangerous files from external model transmission.  
NFR9: The system shall support a fully offline operating mode using Ollama in which no analysis-related network calls are made outside the local environment.  
NFR10: Application logs shall exclude secrets, prompts, raw infrastructure content, and model responses, and shall contain only operational metadata such as timestamps, filenames, scores, and errors.  
NFR11: The product shall not depend on a formal uptime SLA for v1, but it shall fail gracefully in self-hosted environments.  
NFR12: If the configured LLM provider is unavailable, the system shall still return local analytical outputs including risk score, change breakdown, and blast radius information.  
NFR13: Parser failures shall be isolated to the affected file or artifact and shall not terminate analysis for the remaining valid inputs in the same submission.  
NFR14: Completed analysis reports shall be persisted successfully before they are presented in the dashboard or returned to the user as final output.  
NFR15: Risk severity shall never be communicated by color alone and shall always include explicit textual labels or equivalent non-color indicators.  
NFR16: Core workflows including navigation, file submission, configuration, and report review shall be keyboard navigable on supported desktop browsers.  
NFR17: Narrative content, change tables, and rollback plans shall be rendered using semantic HTML structures compatible with assistive technologies.  
NFR18: Visualizations such as risk gauges and blast-radius graphs shall include textual summaries or `aria` descriptions of their key information.  
NFR19: The product shall target practical accessibility for common engineering workflows without requiring formal WCAG certification in v1.  
NFR20: The system shall expose a stable versioned JSON analysis API for automation and integration workflows.  
NFR21: The system shall accept standard supported artifact formats without requiring users to transform them into proprietary intermediate formats.  
NFR22: The system shall produce advisory outputs that can be consumed easily by CI workflows and scripts.  
NFR23: The system shall not require a single LLM vendor and shall allow provider substitution through configuration rather than code changes.  
NFR24: The v1 product shall be designed for single-team deployment rather than multi-tenant organizational scale.  
NFR25: The persistence layer shall support at least 1000 historical reports without unacceptable degradation in retrieval performance.  
NFR26: The system shall support analyses containing tens of files in one submission, with a tested target of up to 30 files across supported tools.  
NFR27: The default upload limit shall be 50 MB total per analysis session, with configuration support for adjustment if needed.  
NFR28: The system shall support a small number of concurrent active users, with a target operating range of 3 to 5 simultaneous sessions.

### Additional Requirements

- Use a custom NiceGUI + FastAPI foundation as the selected architectural starter.
- Treat project initialization with the NiceGUI + FastAPI foundation as the first implementation story.
- Use SQLite as the v1 persistence store.
- Use SQLAlchemy 2.0.49 as the ORM and data access layer.
- Use Alembic 1.18.4 for schema migrations.
- Use Pydantic 2.12.2 for internal and API contract validation.
- Expose a versioned REST/JSON API under `/api/v1`.
- Keep the product advisory-only; no app-level deployment blocking in v1.
- Keep raw IaC local and restrict external LLM usage to structured summaries only.
- Externalize shared-deployment authentication to network boundary or reverse proxy rather than app-native auth in Phase 1.
- Use a shared service layer so dashboard, API, and CLI all reuse the same business logic.
- Organize source code by responsibility with explicit top-level domains such as `parsers/`, `analysis/`, `llm/`, `models/`, `ui/`, and `api/`.
- Standardize on `snake_case` for Python, persistence, and JSON field naming unless an external contract forces otherwise.
- Use standard success and error API envelopes with `data`/`meta` and `error.code`/`error.message`/`error.details`.
- Use fixed internal analysis stage names: `intake`, `parse`, `score`, `blast_radius`, `incident_match`, `skill_load`, `narrative`, `persist`.
- Persist completed reports before showing success to the user.
- Treat parser failures as isolated per-file failures and LLM failures as graceful degradation to non-narrative output.
- Keep tests in a top-level `tests/` tree grouped by domain with real-world parser fixtures.
- Use one primary app container for dashboard, API, and analysis engine, with optional separate Ollama runtime when offline mode is enabled.

### UX Design Requirements

The active UX artifact is `_bmad-output/planning-artifacts/ux-design-specification.md`. Use it alongside the PRD and architecture as the authoritative source for verdict-first information hierarchy, staged progress feedback, responsive breakpoint behavior, accessibility expectations, and admin/review flow details during implementation.

### FR Coverage Map

FR1: Epic 1 - Submit supported deployment artifacts for analysis  
FR2: Epic 1 - Submit multiple files across tools  
FR3: Epic 1 - Auto-detect tool type  
FR4: Epic 1 - Analyze partial deployment context  
FR5: Epic 1 - Detect unsupported or sensitive files  
FR6: Epic 1 - Produce unified risk assessment  
FR7: Epic 1 - Produce deploy recommendation  
FR8: Epic 2 - Detect cross-tool interaction risk  
FR9: Epic 1 - Classify risk severity  
FR10: Epic 1 - Explain risk contributors  
FR11: Epic 1 - Generate plain-English narrative  
FR12: Epic 2 - Provide tool-specific learning explanations  
FR13: Epic 1 - Provide actionable pre-deploy guidance  
FR14: Epic 2 - Support SRE go/no-go review  
FR15: Epic 1 - Distinguish advisory recommendation from human decision  
FR16: Epic 2 - Show blast radius  
FR17: Epic 2 - Warn when blast radius is incomplete  
FR18: Epic 2 - Support impact review for coordination  
FR19: Epic 4 - Maintain topology context  
FR20: Epic 2 - Generate rollback plan  
FR21: Epic 2 - Present ordered rollback steps  
FR22: Epic 2 - Show rollback complexity  
FR23: Epic 2 - Ingest incident records  
FR24: Epic 2 - Show incident similarity matches  
FR25: Epic 3 - Retain analysis history  
FR26: Epic 3 - Review risk trends over time  
FR27: Epic 3 - Compare risk patterns across tools and periods  
FR28: Epic 3 - Use history as audit trail  
FR29: Epic 3 - Retrieve past reports  
FR30: Epic 4 - Configure LLM provider  
FR31: Epic 4 - Operate in fully local mode  
FR32: Epic 4 - Add or override AI Skills  
FR33: Epic 4 - Manage operational context  
FR34: Epic 4 - Operate without deployment blocking  
FR35: Epic 1 - Use web interface  
FR36: Epic 5 - Use API interface  
FR37: Epic 5 - Use CLI interface  
FR38: Epic 5 - Use CI advisory analysis  
FR39: Epic 5 - Share outputs in deployment workflows

## Epic List

### Epic 1: Run a Pre-Deployment Risk Review
Platform engineers can submit infrastructure artifacts, receive a unified risk assessment, and review a plain-English deploy recommendation before release.
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR9, FR10, FR11, FR13, FR15, FR35

### Epic 2: Understand Operational Impact and Recovery
Engineers and SRE leads can understand cross-tool risk interactions, blast radius, rollback complexity, and incident similarity before approving a deployment.
**FRs covered:** FR8, FR12, FR14, FR16, FR17, FR18, FR20, FR21, FR22, FR23, FR24

### Epic 3: Review History, Audit, and Risk Trends
Teams and engineering managers can retrieve past analyses, inspect audit history, and review deployment risk trends over time.
**FRs covered:** FR25, FR26, FR27, FR28, FR29

### Epic 4: Configure and Customize Analysis Context
Platform administrators can configure provider behavior, maintain topology and incident context, operate in local mode, and extend the system with custom AI Skills.
**FRs covered:** FR19, FR30, FR31, FR32, FR33, FR34

### Epic 5: Use DeployWhisper in Automation Workflows
Technical users can access the same analysis capabilities through API, CLI, and CI workflows without changing the advisory-only operating model.
**FRs covered:** FR36, FR37, FR38, FR39

## Epic 1: Run a Pre-Deployment Risk Review

Platform engineers can submit infrastructure artifacts, receive a unified risk assessment, and review a plain-English deploy recommendation before release.

### Story 1.1: Initialize the DeployWhisper Application Foundation

As a platform engineer,  
I want the approved NiceGUI + FastAPI foundation initialized with the core app shell,  
So that all later analysis features are built on a consistent runtime and deployment model.

**FRs implemented:** FR35

**Acceptance Criteria:**

**Given** a fresh repository checkout  
**When** the application is initialized  
**Then** the project contains the approved Python app foundation, configuration files, dependency definitions, and shared runtime entry points  
**And** the initial structure aligns with the architecture document

**Given** the initialized application  
**When** a developer starts it locally  
**Then** the dashboard shell and API health endpoint are both reachable from the shared application runtime  
**And** the runtime uses the selected NiceGUI + FastAPI foundation

### Story 1.2: Upload and Classify Deployment Artifacts

As a platform engineer,  
I want to submit multiple deployment artifacts in one analysis session,  
So that I can review an entire change set instead of one file at a time.

**FRs implemented:** FR1, FR2, FR3, FR5

**Acceptance Criteria:**

**Given** supported Terraform, Kubernetes, Ansible, Jenkins, or CloudFormation files  
**When** I upload one or more files  
**Then** the system accepts the files and displays them as a single pending analysis set  
**And** the upload flow supports multi-file submission

**Given** uploaded files from supported tools  
**When** the upload completes  
**Then** the system identifies each file's supported tool type without requiring manual classification  
**And** detected tool types are visible to the user

**Given** unsupported or sensitive files in the upload set  
**When** intake validation runs  
**Then** the system flags those files clearly  
**And** excludes them from unsafe downstream handling

### Story 1.3: Parse and Normalize Mixed Tool Inputs

As a platform engineer,  
I want uploaded artifacts converted into a common change model,  
So that the system can analyze multi-tool deployments consistently.

**FRs implemented:** FR4, FR6

**Acceptance Criteria:**

**Given** supported deployment artifacts  
**When** parsing runs  
**Then** the system produces normalized change objects in a shared internal schema  
**And** parser output is usable by downstream analysis services

**Given** a submission with only partial deployment context  
**When** parsing completes  
**Then** the system returns a valid partial analysis state rather than rejecting the whole submission  
**And** clearly indicates reduced context where relevant

**Given** one malformed file in a larger submission  
**When** parsing runs  
**Then** that file failure is isolated  
**And** the remaining valid files continue through analysis

### Story 1.4: Generate a Unified Risk Assessment

As a platform engineer,  
I want one combined risk assessment across all uploaded artifacts,  
So that I can judge the deploy as a whole instead of reading isolated results.

**FRs implemented:** FR6, FR7, FR9, FR10, FR15

**Acceptance Criteria:**

**Given** a normalized set of changes  
**When** risk scoring runs  
**Then** the system produces one overall risk assessment for the full submission  
**And** assigns a clear severity classification

**Given** the computed assessment  
**When** results are presented  
**Then** the system shows which changes contributed to the score  
**And** explains the severity classification in user-facing terms

**Given** the assessment is complete  
**When** I review it  
**Then** the system distinguishes its recommendation from the final human deployment decision  
**And** preserves the advisory-only operating model

### Story 1.5: Present a Plain-English Risk Narrative

As a platform engineer,  
I want the system to explain the deployment in plain English,  
So that I can understand what changed, why it matters, and what to check next.

**FRs implemented:** FR11, FR13

**Acceptance Criteria:**

**Given** a completed analysis  
**When** narrative generation succeeds  
**Then** the system presents a plain-English explanation of what changed, what could break, and what deserves attention  
**And** the narrative is grounded in the structured analysis context

**Given** a completed analysis  
**When** the narrative is displayed  
**Then** the system includes actionable guidance describing what to review, change, or verify before deployment  
**And** the guidance is readable by both junior and senior engineers

**Given** the external LLM provider is unavailable  
**When** narrative generation cannot complete  
**Then** the rest of the analysis results remain available  
**And** the workflow continues without blocking the review

## Epic 2: Understand Operational Impact and Recovery

Engineers and SRE leads can understand cross-tool risk interactions, blast radius, rollback complexity, and incident similarity before approving a deployment.

### Story 2.1: Detect Cross-Tool Interaction Risk

As a platform engineer,  
I want the system to identify risky interactions across multiple tools,  
So that I can catch hazards that would be missed in single-tool review.

**FRs implemented:** FR8

**Acceptance Criteria:**

**Given** a mixed-tool analysis set  
**When** correlation logic runs  
**Then** the system identifies cross-tool interactions where combined changes create elevated risk  
**And** surfaces them in the overall assessment

**Given** a detected interaction  
**When** I review the result  
**Then** the system explains the interaction in user-facing language  
**And** ties the explanation back to the contributing artifacts

### Story 2.2: Show Blast Radius and Impact Warnings

As an SRE lead,  
I want to see which downstream systems may be affected by a deployment,  
So that I can make a defensible go/no-go decision and coordinate with the right teams.

**FRs implemented:** FR16, FR17, FR18

**Acceptance Criteria:**

**Given** an analysis with matching topology context  
**When** blast-radius mapping runs  
**Then** the system shows impacted downstream services, systems, or resources  
**And** presents them in a reviewable impact view

**Given** topology data is missing or stale  
**When** blast-radius analysis is shown  
**Then** the system warns that impact analysis may be incomplete  
**And** does not imply false certainty

### Story 2.3: Generate Rollback Guidance and Complexity

As an SRE lead,  
I want a rollback plan and recovery complexity assessment,  
So that I can weigh not only deployment risk but also recovery cost.

**FRs implemented:** FR20, FR21, FR22

**Acceptance Criteria:**

**Given** a completed analysis  
**When** rollback planning runs  
**Then** the system produces an ordered rollback plan tied to the analyzed deployment  
**And** the plan is reviewable in the report

**Given** the rollback plan  
**When** I review the report  
**Then** the system shows rollback complexity in a form usable for approval decisions  
**And** ties the complexity indicator to the analyzed change set

### Story 2.4: Ingest Incident Records for Similarity Matching

As a platform administrator,  
I want to add incident records to the system,  
So that future deployment reviews can be compared against past failures.

**FRs implemented:** FR23

**Acceptance Criteria:**

**Given** an incident document in an accepted format  
**When** I ingest it  
**Then** the system stores the incident record for future similarity analysis  
**And** preserves enough metadata for later review

**Given** stored incident records  
**When** a new deployment is analyzed  
**Then** those records are available to the incident-matching workflow  
**And** can influence the generated report context

### Story 2.5: Show Incident Similarity in Risk Review

As an SRE lead,  
I want to know when a deployment resembles a previous incident,  
So that historical failures can influence current deploy decisions.

**FRs implemented:** FR12, FR14, FR24

**Acceptance Criteria:**

**Given** stored incident records and a completed deployment analysis  
**When** similarity matching finds a relevant match  
**Then** the report shows that the current deployment resembles a previously recorded incident  
**And** identifies the matched incident context

**Given** an incident similarity result  
**When** it appears in the report  
**Then** it is presented as decision-support context rather than as an automated block  
**And** remains consistent with the advisory-only model

## Epic 3: Review History, Audit, and Risk Trends

Teams and engineering managers can retrieve past analyses, inspect audit history, and review deployment risk trends over time.

### Story 3.1: Persist Completed Analysis Reports

As a team using DeployWhisper,  
I want completed analyses stored automatically,  
So that reviews are auditable and can be revisited later.

**FRs implemented:** FR25, FR28

**Acceptance Criteria:**

**Given** a completed analysis  
**When** processing reaches the final persistence stage  
**Then** the report is stored successfully before it is shown as complete to the user  
**And** saved report data includes audit-relevant metadata

**Given** a stored analysis  
**When** I inspect history later  
**Then** the report includes enough metadata to support audit and investigation workflows  
**And** can be retrieved by supported interfaces

### Story 3.2: Browse and Retrieve Historical Reports

As a platform engineer,  
I want to browse previous analysis reports,  
So that I can review earlier deploy decisions, learn from past work, and reference them in approval discussions.

**FRs implemented:** FR29

**Acceptance Criteria:**

**Given** stored analysis reports  
**When** I open the history view  
**Then** I can retrieve and inspect prior reports  
**And** review the contents of a selected report

**Given** historical reports  
**When** I search or filter them  
**Then** I can find relevant prior analyses without scanning the full history manually  
**And** the retrieval remains aligned with the documented NFR bounds

### Story 3.3: Review Risk Trends and Audit Signals

As an engineering manager,  
I want trend views over stored analyses,  
So that I can understand whether deployment safety is improving over time.

**FRs implemented:** FR26, FR27

**Acceptance Criteria:**

**Given** a history of completed analyses  
**When** I view trend reporting  
**Then** I can review risk patterns over time and across tools  
**And** identify high-level changes in deployment safety

**Given** historical analysis data  
**When** I inspect audit-oriented views  
**Then** I can see when deployments were reviewed and what assessments were produced  
**And** use that view for management and governance review

### Story 3.4: Capture Audit-Trail Metadata for Analyses

As a platform administrator or compliance reviewer,  
I want each stored analysis to retain audit-trail metadata,  
So that post-incident investigation and deployment accountability are possible without exposing sensitive content.

**FRs implemented:** FR28, FR29

**Acceptance Criteria:**

**Given** a completed analysis  
**When** it is persisted  
**Then** the stored audit trail includes timestamp, triggering user or session context when available, files analyzed, LLM provider used, and resulting risk score  
**And** the record excludes secrets, raw IaC content, prompts, and model responses

**Given** a stored analysis  
**When** I retrieve it through supported history or report surfaces  
**Then** the audit metadata is visible enough for investigation and governance workflows  
**And** remains consistent across supported interfaces

## Epic 4: Configure and Customize Analysis Context

Platform administrators can configure provider behavior, maintain topology and incident context, operate in local mode, and extend the system with custom AI Skills.

### Story 4.1: Configure Narrative Provider Settings

As a platform administrator,  
I want to configure which LLM provider is used for narrative generation,  
So that the system fits our operational and compliance context.

**FRs implemented:** FR30

**Acceptance Criteria:**

**Given** the settings workflow  
**When** I choose a supported provider configuration  
**Then** the system uses that provider for narrative generation without changing core analysis logic  
**And** preserves compatibility with the shared service layer

**Given** a valid provider configuration  
**When** the application starts or settings are applied  
**Then** the system validates the configuration in a way appropriate for the selected runtime mode  
**And** reports invalid configuration safely

### Story 4.2: Operate in Fully Local Mode

As a platform administrator,  
I want the system to run with local-only model execution,  
So that no analysis-related data leaves the environment.

**FRs implemented:** FR31, FR34

**Acceptance Criteria:**

**Given** local mode is enabled  
**When** an analysis runs  
**Then** the system uses the local provider path and avoids external model calls  
**And** preserves the same advisory workflow

**Given** local mode is active  
**When** I inspect system behavior  
**Then** the product supports the core review flow without requiring cloud LLM access  
**And** no analysis-related outbound model traffic occurs

### Story 4.3: Maintain Service Topology Context

As a platform administrator,  
I want to manage the service-topology definition used for blast-radius analysis,  
So that impact results reflect the actual system structure.

**FRs implemented:** FR19, FR33

**Acceptance Criteria:**

**Given** topology data management capabilities  
**When** I update topology context  
**Then** the system uses the updated structure for future blast-radius analysis  
**And** stores the maintained context for later analyses

**Given** topology context becomes missing or stale  
**When** the application evaluates impact  
**Then** the system can surface uncertainty rather than silently assuming complete coverage  
**And** the warning is visible in the review workflow

### Story 4.4: Add and Override Custom AI Skills

As a platform administrator,  
I want to add or override team-specific AI Skills,  
So that analysis reflects our internal modules, conventions, and risk patterns.

**FRs implemented:** FR32

**Acceptance Criteria:**

**Given** a valid custom skill file  
**When** it is placed in the supported custom skill location  
**Then** the system loads it in preference to the default skill when applicable  
**And** preserves the default fallback when no custom skill exists

**Given** custom skills are present  
**When** relevant artifacts are analyzed  
**Then** those custom skill definitions affect the structured narrative context used by the system  
**And** the override behavior is consistent across supported interfaces

## Epic 5: Use DeployWhisper in Automation Workflows

Technical users can access the same analysis capabilities through API, CLI, and CI workflows without changing the advisory-only operating model.

### Story 5.1: Expose a Stable Analysis API

As a technical user,  
I want a versioned analysis API,  
So that I can automate DeployWhisper from scripts and external systems.

**FRs implemented:** FR36, FR38, FR39

**Acceptance Criteria:**

**Given** the application is running  
**When** a client calls the supported analysis endpoint  
**Then** the system accepts standard artifact inputs and returns a stable structured JSON result  
**And** the result follows the documented response envelope

**Given** API consumers  
**When** they inspect the contract  
**Then** the versioned API surface is documented consistently with the system's response schema  
**And** remains aligned with `/api/v1`

### Story 5.2: Provide a CLI for Headless Analysis

As a technical user,  
I want to trigger analysis from the command line,  
So that I can use DeployWhisper without opening the dashboard.

**FRs implemented:** FR37

**Acceptance Criteria:**

**Given** the CLI entry point  
**When** I invoke analysis with supported inputs  
**Then** the CLI runs the same shared analysis workflow used by the web and API interfaces  
**And** returns consistent output for the same underlying analysis

**Given** a completed CLI analysis  
**When** results are returned  
**Then** the output remains consistent with the advisory-only product model  
**And** can be consumed in a headless workflow

### Story 5.3: Support CI-Friendly Advisory Consumption

As a team integrating DeployWhisper into CI,  
I want automation-friendly advisory outputs,  
So that pull requests and pipelines can consume analysis results without turning the tool into an enforcement gate.

**FRs implemented:** FR38, FR39

**Acceptance Criteria:**

**Given** a CI workflow submits deployment artifacts  
**When** analysis completes  
**Then** the result can be consumed programmatically by the workflow  
**And** includes enough structured context for advisory automation

**Given** a CI-integrated analysis result  
**When** it is shared into deployment review workflows  
**Then** the output remains advisory  
**And** does not require the system itself to make the final release decision

### Story 5.4: Format Advisory Outputs for PR and Approval Threads

As a team integrating DeployWhisper into CI,  
I want a reusable approval-thread and PR-comment summary format,  
So that bots and scripts can share the most important advisory signals without reverse-engineering raw analysis payloads.

**FRs implemented:** FR38, FR39

**Acceptance Criteria:**

**Given** a completed advisory analysis  
**When** a CI workflow or bot prepares a shared summary  
**Then** the system exposes a script-friendly summary shape or formatter for pull-request and approval-thread use  
**And** the summary includes risk level, recommendation, top narrative signal, blast-radius context, rollback context, and uncertainty indicators

**Given** a shared PR or approval-thread summary  
**When** reviewers read it  
**Then** the message remains explicitly advisory  
**And** it never implies that DeployWhisper itself has made the final release decision or blocked deployment
