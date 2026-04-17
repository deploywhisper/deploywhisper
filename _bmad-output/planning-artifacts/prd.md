---
stepsCompleted:
  - step-01-init
  - step-02-discovery
  - step-02b-vision
  - step-02c-executive-summary
  - step-03-success
  - step-04-journeys
  - step-05-domain
  - step-06-innovation
  - step-07-project-type
  - step-08-scoping
  - step-09-functional
  - step-10-nonfunctional
  - step-11-polish
  - step-12-complete
inputDocuments:
  - README.md
  - docs_README.md
  - DeployWhisper_PRD.docx
  - DeployWhisper_Architecture.docx
workflowType: 'prd'
documentCounts:
  briefCount: 0
  researchCount: 0
  brainstormingCount: 0
  projectDocsCount: 4
classification:
  projectType: web_app
  domain: general
  subdomain: DevOps / platform engineering / developer tooling
  complexity: medium
  projectContext: brownfield
---

# Product Requirements Document - ai-deploy-whisper

**Author:** psaho01
**Date:** 2026-04-16

## Executive Summary

DeployWhisper is an AI-powered pre-deployment risk intelligence platform for infrastructure and platform teams. It analyzes change sets across Terraform, Kubernetes, Ansible, Jenkins, and CloudFormation, then converts those changes into a single decision-ready risk assessment before deployment. Instead of forcing engineers to manually interpret raw diffs, trace dependencies, and recall prior incidents under time pressure, DeployWhisper produces a plain-English risk narrative, blast radius view, rollback guidance, and deploy recommendation in seconds.

The product is designed for platform engineers, SREs, DevOps leads, engineering managers, and junior engineers participating in deployment review. Its primary value is consistency: every deployment receives the same depth of analysis regardless of who is on shift. Junior engineers get understandable explanations they can learn from, senior engineers get a second layer of operational memory and cross-checking, and managers get clearer visibility into deployment risk trends over time.

### What Makes This Special

DeployWhisper solves deployment risk as a context problem rather than a single-tool problem. A Terraform change, Kubernetes manifest update, or Jenkins pipeline edit may appear safe in isolation while becoming high-risk when combined, targeted at production, or similar to a past outage. DeployWhisper addresses that gap by combining unified multi-tool parsing, tool-specific AI Skills, and incident-memory matching into a single risk narrative.

This makes the product materially different from linters, raw plan viewers, and generic LLM prompts. Linters flag isolated policy violations. Diff viewers show syntax and resource changes without operational context. Generic LLMs lack structured understanding of tool-specific failure modes, service topology, and prior incident patterns. DeployWhisper connects those signals and answers the actual deployment question: what could break, who will be affected, how risky is this change, and is it safe to ship now?

## Release Positioning

DeployWhisper v1 is a concept-complete product, not a stripped-down prototype. The first release intentionally ships the full pre-deployment intelligence loop because the product's value comes from multi-tool parsing, AI Skills, blast radius mapping, incident memory, rollback planning, and analysis history working as one system. The phased roadmap in this document describes build sequencing and expansion priorities, not a feature-stripping exercise within the core v1 thesis.

## Project Classification

DeployWhisper is a brownfield web application in the general software domain, with a specific focus on DevOps, platform engineering, and developer tooling. The project has medium complexity due to its multi-tool parsing scope, cross-system risk analysis, LLM orchestration, incident correlation, and deployment-safety requirements.

## Success Criteria

### User Success

DeployWhisper succeeds for platform engineers and SREs when deployment review quality no longer depends on the most senior reviewer being available. The product must catch meaningful hazards across Terraform, Kubernetes, Ansible, Jenkins, and CloudFormation with consistent quality on every deployment. It must reduce manual review time from approximately 20 minutes to seconds while increasing reviewer confidence that obvious high-risk issues were not missed.

The defining user-success moment is the first time DeployWhisper identifies a real deployment risk the engineer did not connect on their own. The product must surface cross-tool interactions, blast-radius implications, and prior-incident similarity in a way that changes a deployment decision before production impact occurs.

### Business Success

At 3 months, DeployWhisper is used on at least 90% of production deployments for the initial team. Deploy approval threads reference DeployWhisper reports as a standard decision input rather than an optional experiment. The system identifies 2 to 3 high-risk deployments per month that are either fixed before release or escalated for additional review.

At 12 months, DeployWhisper is embedded into the delivery workflow for multiple teams and runs automatically on infrastructure-related changes. Teams maintain custom AI Skills aligned to their service topology and internal modules. The incident-history database becomes a reusable operational knowledge base, and deployment-related P1 incidents show a measurable decline.

### Technical Success

Risk-score quality and parser accuracy are the highest-priority technical success measures. The system must correctly parse and normalize changes across all five supported tools and produce risk assessments that experienced platform engineers consider credible. False positives must remain low enough that operators continue to trust the output and incorporate it into deployment decisions.

Analysis latency must remain fast enough for real deployment workflows, with a target of under 15 seconds for standard analyses, but accuracy takes precedence over raw speed. AI Skills quality must prove the architectural differentiator by identifying tool-specific risks that generic LLM analysis would miss. Incident-similarity matching must become useful early enough to influence real review decisions rather than remain a dormant feature.

### Measurable Outcomes

- 90% or greater coverage of production deployments within 3 months
- 2 to 3 high-risk deployments per month caught before release
- Manual deployment review time reduced from roughly 20 minutes to under 15 seconds for standard analyses
- False-positive rate below 15%
- Analysis latency below 15 seconds for standard multi-file reviews
- Credible parser coverage across Terraform, Kubernetes, Ansible, Jenkins, and CloudFormation at launch
- Measurable reduction in deployment-related P1 incidents within 12 months
- DeployWhisper reports used as a standard approval artifact in production deployment decisions

## Product Scope

### MVP - Minimum Viable Product

The v1 scope includes the full pre-deployment intelligence loop that defines the product category: multi-tool parsing across Terraform, Kubernetes, Ansible, Jenkins, and CloudFormation; AI-generated plain-English risk narrative; weighted risk scoring; blast-radius mapping; automated rollback guidance; incident-history matching; multi-LLM support; analysis history; and tool-specific AI Skills with support for team customization.

### Growth Features (Post-MVP)

Post-v1 scope includes official CI/CD integrations such as GitHub Action and GitLab CI plugins, Slack-based collaboration and approval workflows, polished PDF report export, multi-tenant deployment with team-level access controls, and cost-impact analysis for infrastructure changes. These features improve convenience, distribution, and enterprise readiness, but they are not required to prove the core deployment-intelligence model.

### Vision (Future)

The longer-term vision is for DeployWhisper to evolve from a pre-deployment review tool into a full deployment-intelligence platform. Future scope includes real-time cloud-state introspection, automated deployment blocking and policy enforcement, model specialization on organization-specific incident history, a community marketplace for AI Skills, and post-deploy monitoring feedback that continuously improves risk prediction based on real outcomes.

## User Journeys

### Journey 1: Platform Engineer - Core Pre-Deploy Review

A platform engineer is preparing a deployment late in the day and needs confidence before release. They upload the Terraform plan, Kubernetes manifests, and any related deployment artifacts into DeployWhisper. Instead of manually scanning diffs, tracing dependencies, and recalling similar past incidents from memory, they receive a single risk narrative that explains what changed, what could break, which downstream services are affected, and how to roll back if needed.

The emotional progression moves from uncertainty and time pressure to clarity and confidence. The critical value moment is not the risk score alone, but the narrative that connects multiple changes into a decision-ready explanation. The engineer leaves the review knowing whether the deploy looks safe, what deserves further scrutiny, and what to share with the SRE lead if risk is elevated.

This journey reveals requirements for multi-file upload, parser auto-detection, unified risk narrative generation, blast radius visualization, rollback-plan generation, and risk scoring that is fast enough for daily use.

### Journey 2: Platform Engineer - Cross-Tool Edge Case and Escalation

A platform engineer submits a deployment where no single file looks alarming in isolation. Terraform includes a minor infrastructure adjustment, Kubernetes scales replicas from 3 to 10, and an Ansible change updates service configuration. DeployWhisper detects that these changes together imply a scaling event and warns that the Kubernetes resource limits have not been adjusted to match the increased replica count, creating a realistic risk of OOM kills under load.

This is the edge-case journey that proves the product thesis. The engineer starts with confidence because each individual diff appears routine, then shifts into focused concern when DeployWhisper identifies the cross-tool interaction they did not connect on their own. They use the report to escalate the deployment to their SRE lead with evidence instead of intuition.

This journey reveals requirements for multi-tool correlation, cross-file reasoning, explicit explanation of conflicting or interacting signals, report sharing, and clear escalation paths for HIGH or CRITICAL assessments.

### Journey 3: SRE Lead - Go/No-Go Decision Under Accountability

An SRE lead is asked to approve a risky production deployment. They open the DeployWhisper report shared by the platform engineer and review the risk score, the blast radius, the incident match, and the rollback complexity. They are not looking for raw change detail alone; they are trying to decide whether this deployment is safe enough to ship with their name attached to the outcome.

The emotional state starts with skepticism and responsibility. The product earns trust only if the report feels like an operational cockpit rather than a generic summary. The SRE lead needs to see why the deployment is risky, which systems are exposed, whether the pattern resembles a past outage, and how difficult recovery would be if the deploy fails. The journey succeeds when the lead can make a defensible go/no-go call quickly, with evidence.

This journey reveals requirements for high-signal summary views, incident similarity presentation, blast radius depth, rollback complexity scoring, and report formats that support approval-thread decision making.

### Journey 4: Junior Engineer - Learning Through Risk Review

A junior engineer submits an infrastructure change and receives a DeployWhisper report explaining why their modification creates risk. Instead of a cryptic lint rule or senior-reviewer comment, they see a plain-English explanation grounded in the specific tool context, such as why a broad security-group rule is dangerous, how a missing readiness probe affects rollout safety, or why an Ansible task is not idempotent.

The emotional shift is from confusion and dependence on tribal knowledge to understanding and growth. The product succeeds when the junior engineer learns something actionable from the review and can correct the issue without waiting for a senior engineer to decode it for them. Over time, the system becomes a reusable training layer embedded inside normal deployment work.

This journey reveals requirements for plain-English explanations, tool-specific AI Skills, actionable remediation guidance, and report clarity suitable for less experienced engineers.

### Journey 5: Engineering Manager - Deployment Safety Trends and Team Learning

An engineering manager reviews deployment trends at the end of the week or sprint. They are not concerned with one deployment in isolation; they want to understand whether the team is getting safer over time, which tools generate the most high-risk changes, how often the team accepts or fixes flagged risks, and whether deployment incidents are decreasing.

The emotional state begins with ambiguity because safety is often discussed anecdotally. DeployWhisper resolves that ambiguity by turning individual analyses into a history of operational patterns. The journey succeeds when the manager can answer whether the organization is improving, where the risk is concentrated, and whether the product is creating both safer deployments and better team learning.

This journey reveals requirements for analysis history, historical comparisons, trend reporting, tool-level risk breakdowns, and reporting views that summarize outcomes over time rather than per deployment.

### Journey 6: Platform Admin - Maintaining Operational Context

A platform administrator sets up DeployWhisper for the team and keeps its operational context accurate as infrastructure evolves. They configure the LLM provider, maintain the service-topology graph used for blast radius analysis, add custom AI Skills that reflect internal modules and conventions, and ingest past incident documents so the similarity engine can match against real team history.

The most critical part of this journey is service-topology maintenance. If the topology is stale or incorrect, blast radius analysis becomes misleading for every other user. The journey succeeds when the admin can update topology, skills, and incident memory with low friction and clear feedback about whether the system context is current.

This journey reveals requirements for provider configuration, topology import and validation, stale-context indicators, incident-ingestion workflows, custom-skill management, and lightweight operational setup.

### Journey 7: API / CI Consumer - Advisory Analysis in the Delivery Pipeline

A CI workflow detects a pull request that changes Terraform, YAML, or Jenkins pipeline files. The workflow sends the changed artifacts to DeployWhisper's analysis API and receives a structured JSON risk report in response. A PR bot posts a summary comment showing the risk level, plain-English narrative, blast radius summary, and rollback guidance, then requests additional review if the deployment risk is elevated.

The product remains advisory rather than blocking. Engineers and reviewers use the report to make better decisions, but the pipeline does not automatically reject the change. The journey succeeds when DeployWhisper becomes a trusted automated reviewer that runs on every relevant infrastructure change, increasing coverage without removing human judgment.

This journey reveals requirements for FastAPI analysis endpoints, machine-readable JSON output, CI-friendly request flow, PR-comment formatting support, and advisory integration patterns that avoid automated hard blocking in v1.

### Journey Requirements Summary

These journeys define the capability areas the product must support:

- Unified ingestion of Terraform, Kubernetes, Ansible, Jenkins, and CloudFormation artifacts
- Cross-tool correlation that detects risk patterns no single-tool analyzer can see
- Plain-English narratives that explain operational consequences, not just diffs
- Blast radius mapping tied to maintainable service-topology context
- Incident-history matching that adds organizational memory to deployment review
- Rollback guidance and rollback complexity scoring for go/no-go decisions
- Analysis history and trend reporting for management visibility
- Tool-specific AI Skills that teach as well as detect
- Admin workflows for provider setup, topology maintenance, skill customization, and incident ingestion
- API-first analysis for CI/CD and PR-comment automation without mandatory blocking

## Domain-Specific Requirements

### Compliance & Regulatory

DeployWhisper v1 is a self-hosted, single-team product and is not required to achieve formal certifications such as SOC 2 at launch. However, the product must be designed so that regulated-environment review is straightforward from its architecture and data flow. The system shall maintain an audit trail for every analysis, including timestamp, triggering user or session, files analyzed, LLM provider used, and resulting risk score. This audit trail supports both post-incident investigation and internal deployment accountability.

The product shall document its data flow clearly enough that a security or compliance reviewer can determine what is processed locally, what is sent to external APIs, what is stored on disk, and what is written to logs. For regulated or sensitive environments, the product shall support a fully local deployment mode using Ollama so that no analysis data leaves the network boundary. Application logs shall exclude API keys, raw file contents, prompts, and model responses.

### Technical Constraints

DeployWhisper shall process raw IaC artifacts locally and shall never send raw infrastructure files to external LLM providers. Parsing, risk scoring, blast radius analysis, environment detection, and incident matching shall run locally. External LLM usage is limited to generating narrative output from structured summaries derived from parsed change objects. If external LLM access is unavailable, the product shall still produce local analytical outputs including risk score, change breakdown, and blast radius data.

API keys shall be stored only in environment variables or in-memory session state and shall never be persisted to SQLite, logs, or generated reports. Sensitive file detection shall be always-on and shall automatically exclude dangerous files such as `.env`, `*.pem`, `*.key`, `id_rsa`, `kubeconfig`, `credentials`, and `*.tfstate` from any LLM-bound payload. When sensitive files are detected, the product shall warn the user that the content was excluded from external model transmission.

The product shall remain advisory only. There shall be no mode in v1 where DeployWhisper can block a deployment. Human reviewers retain final authority regardless of risk score or recommendation.

### Integration Requirements

The product shall accept standard engineering artifacts without requiring teams to adopt new intermediate formats. Terraform support shall prioritize `terraform plan -json` and parse provider-agnostic resource changes across AWS, GCP, Azure, and other Terraform ecosystems. Kubernetes support shall handle multi-document YAML and common manifest packaging patterns, including raw manifests and rendered outputs from Helm or Kustomize workflows.

Ansible analysis shall work with partial context, providing task-level review when only playbooks are uploaded and richer targeting analysis when inventory or variable files are included. Jenkins support shall fully analyze declarative pipelines and provide best-effort analysis for scripted pipelines where full static parsing is not feasible. Blast-radius analysis shall use a manually maintained service-topology JSON file in v1, with topology auto-discovery treated as a future enhancement. Incident-history ingestion shall accept flexible postmortem inputs such as markdown, plain text, or exported documentation rather than requiring a single canonical format.

### Risk Mitigations

The highest-risk failure mode is false reassurance on a dangerous deployment. The system shall therefore be conservative by default and treat false negatives as more severe than false positives. Risk scoring thresholds and heuristics shall err toward escalation when uncertainty exists, with team tuning allowed only after trust is established through real usage.

Parser correctness is a foundational trust boundary. Parsers shall be tested against real-world artifact samples and validated carefully because incorrect parsing corrupts all downstream analysis. Sensitive-data leakage is the second critical failure mode; architecture and file-detection rules shall prevent accidental transmission of secrets or raw infrastructure state to external providers.

Risk scoring shall be explainable rather than opaque. Users shall be able to see which changes, environments, and incident signals contributed to the final score. Blast-radius results shall include uncertainty indicators when service-topology data is stale or incomplete. If referenced resources are missing from the topology graph, the system shall warn that blast-radius analysis may be incomplete instead of silently presenting false confidence.

## Innovation & Novel Patterns

### Detected Innovation Areas

DeployWhisper introduces a novel combination of capabilities rather than a single isolated feature. The strongest innovation signal is the AI Skills layer, which grounds a general-purpose LLM with tool-specific operational expertise across Terraform, Kubernetes, Ansible, Jenkins, and CloudFormation. This changes the model from a generic narrator into a context-aware reviewer that can reason about provider-specific pitfalls, rollout safety issues, idempotency failures, approval-gate removal, and similar domain-specific hazards.

The broader innovation is the combination of four elements into one review system: multi-tool parsing, tool-specific AI Skills, incident-memory matching, and a decision-ready risk narrative. Existing deployment-review tools operate on one artifact type at a time or rely on static rule evaluation. DeployWhisper treats deployment risk as a context problem across multiple tools and uses that combined context to produce a single operational assessment.

The product also challenges two common assumptions in current tooling. First, it rejects the assumption that deployment-risk tools can only reason about one artifact at a time. Second, it rejects the assumption that LLMs are too generic to be useful for infrastructure review by grounding them with AI Skills and limiting their role to informed reasoning over structured summaries.

### Market Context & Competitive Landscape

The closest alternatives each cover only part of the problem space. Linters such as `tflint`, `kube-score`, and `ansible-lint` catch syntax errors and best-practice violations within a single tool, but they do not correlate changes across tools, explain blast radius, or connect current changes to past incidents. Terraform-focused platforms such as plan viewers and policy-checking systems improve Terraform review, but they stop at Terraform and do not account for the Kubernetes, Ansible, or Jenkins changes that often ship alongside infrastructure updates.

Policy engines such as OPA, Rego, and Sentinel provide strong enforcement for known rules, but they only catch risks that have already been codified. They do not reason about novel interaction patterns that emerge across multiple artifacts. Generic LLM prompting can produce plausible review text, but it lacks consistent grounding, tool-specific expertise, blast-radius context, incident memory, and auditability. DeployWhisper differentiates itself by combining multi-tool context, grounded AI reasoning, incident-memory awareness, rollback planning, and structured deploy-review outputs in a single workflow.

### Validation Approach

The AI Skills thesis should be validated directly against baseline alternatives. The first validation path is a skill-enhanced versus vanilla-LLM comparison using known risky deployment scenarios. The team should run the same scenarios through DeployWhisper with AI Skills enabled and through an ungrounded LLM prompt, then compare both outputs against senior SRE review. This validates whether the Skills layer materially improves tool-specific hazard detection.

The second validation path is cross-tool detection. The team should create scenarios where risk only becomes visible when multiple tools are analyzed together, then compare DeployWhisper against individual single-tool linters and reviewers. If DeployWhisper consistently identifies cross-tool interaction risk that the single-tool alternatives miss, the multi-tool thesis is validated.

The third validation path is incident-memory usefulness. The team should ingest real or representative incident postmortems, generate new deployment scenarios with meaningful similarity to those incidents, and evaluate whether incident matches appear in the analysis and change reviewer behavior. Success is measured not just by similarity scoring, but by whether engineers report that the historical warning would have affected the deployment decision.

### Risk Mitigation

If the innovation thesis underperforms, the product still retains substantial value as a deployment-review system. Even without strong cross-tool reasoning or high-value incident matching, DeployWhisper still provides a useful plain-English infrastructure narrator, rollback-plan generator, blast-radius visualizer, and audit trail for deployment review. This gives the product a meaningful floor even if the more ambitious intelligence layer needs refinement.

To protect trust while pursuing innovation, the system must remain conservative, explainable, and advisory. Risk assessments should err toward escalation rather than false reassurance. The contribution of each detected risk should be visible to the user rather than hidden behind opaque scoring. The system should never block deployment automatically in v1, which limits the blast radius of incorrect model behavior while allowing the team to build evidence and confidence over time.

## Web App Specific Requirements

### Project-Type Overview

DeployWhisper is a desktop-first internal web application for infrastructure and platform teams. The primary usage environment is an engineer's work laptop on Chrome, Edge, or Firefox using the latest stable browser versions. The application runs locally during development and behind an internal network boundary or company VPN in production. Mobile is not a target platform for v1, and tablet support is limited to readable, non-broken layouts rather than full operational optimization.

The product is not a public-facing website and has no SEO requirements. It is an authenticated or internal operational tool designed for engineers performing deployment review, risk analysis, and operational decision support.

### Technical Architecture Considerations

The frontend architecture shall remain pure Python with zero JavaScript build tooling. The product shall not require `npm`, `webpack`, `vite`, `node_modules`, or a separate frontend build pipeline. The preferred implementation direction is a pure-Python web UI framework that supports component-level updates, asynchronous workflows, and production-grade dashboard components while remaining operable from a single Python application process.

The application shall support a single-container deployment model in which the dashboard and REST API run together on one server, one process boundary, and one exposed port. The system shall support large multi-file uploads, asynchronous long-running analysis workflows, and real-time progress feedback without requiring the user to refresh the page or manually poll for results.

### Browser Matrix

DeployWhisper v1 shall support the latest stable releases of Chrome, Edge, and Firefox on Linux, macOS, and Windows. Safari compatibility is desirable when it works through standards-based rendering, but Safari-specific behavior is not a v1 testing target. Internet Explorer and legacy browsers are explicitly out of scope.

The application is intended for desktop browser use on internal engineering workstations. No native mobile app, Electron wrapper, or dedicated mobile browser optimization is required.

### Responsive Design

The interface shall be optimized for desktop screens at approximately 1200 pixels and above, where multi-column layouts, risk tables, blast-radius graphs, and rollback panels can be displayed together without loss of usability. On tablet-sized screens, the application shall remain readable and structurally intact, with tables scrollable and layout blocks stacking gracefully when needed.

Mobile-phone optimization is out of scope for v1. Small-screen rendering may degrade gracefully, but the product is not required to support full deployment-review workflows on narrow mobile displays.

### Performance Targets

Initial dashboard load time shall be under 1.5 seconds under normal internal-network conditions. Once analysis completes, time to interactive update for risk score, narrative, tables, and supporting panels shall be under 500 milliseconds so that results feel immediate.

File uploads shall provide immediate visual feedback, including file names, detected tool types, and file sizes before analysis begins. Long-running analysis workflows shall provide staged progress updates for parsing, risk scoring, blast-radius computation, AI Skill loading, and narrative generation rather than relying on an undifferentiated spinner. The history interface shall remain responsive with at least 1000 reports stored, using pagination, filtering, and server-side query execution.

### SEO Strategy

DeployWhisper has no SEO requirements. The product is an internal operational system rather than a public marketing property. No sitemap, search-engine indexing strategy, structured metadata strategy, or crawler-specific rendering is required for v1.

### Accessibility Level

DeployWhisper shall meet a practical accessibility bar suitable for internal engineering tools. Risk indicators shall never rely on color alone; each severity state shall include explicit text labels or equivalent non-color cues. Core workflows including navigation, upload, configuration, and report review shall remain keyboard navigable through standard browser interaction patterns.

Narrative text, change tables, and rollback plans shall be rendered using semantic HTML structures that work with screen readers. Visualizations such as gauges and network graphs shall include textual summaries or `aria` descriptions of key information, but full screen-reader operability of complex interactive graphs is not required in v1. Formal WCAG certification is out of scope, but common accessibility needs such as color-blind-safe indicators, zoom/text scaling tolerance, and keyboard preference support are required.

### Implementation Considerations

The application shall support multi-file drag-and-drop uploads with a configurable total payload limit of at least 50 MB. Tool detection shall occur immediately on upload, while parsing and analysis proceed asynchronously in the background. If analysis takes multiple seconds, the UI shall surface stage-based progress and status updates so that the user understands what the system is doing.

Session state may be connection-scoped and transient for in-progress analysis, but completed reports shall persist in SQLite and remain available after browser refresh or reconnect. Browser-side storage shall not be used for critical operational state. API keys shall remain memory-only at the session or environment level and shall not be persisted to the browser or local database.

The UI framework choice shall reinforce the product's broader architectural priorities: pure Python developer experience, real-time incremental updates, and shared runtime with the API backend. The preferred direction is a framework that can serve both dashboard and API from the same application process while avoiding separate frontend infrastructure.

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** DeployWhisper v1 is a concept-complete product rather than a stripped-down prototype. The team deliberately chose to ship all 12 functional requirements in the first release because the product's value emerges from the interaction between multi-tool parsing, AI Skills, blast radius mapping, incident memory, rollback planning, and analysis history working as one system. Removing any one of these capabilities reduces the product to a narrower feature category that already exists elsewhere.

The phased roadmap reflects a build and scaling sequence, not a feature-stripping exercise. What was excluded from v1 was already cut intentionally: official CI/CD plugins, cost impact analysis, multi-tenant support, automated blocking, and custom LLM fine-tuning.

**Resource Requirements:** The minimum credible delivery team is two strong Python engineers, with three preferred. One engineer owns parsers, UnifiedChange normalization, risk scoring, and blast radius logic. A second engineer owns LLM integration, AI Skills, prompt design, and the dashboard experience. A third engineer, if available, owns Docker, API, persistence, CLI mode, test infrastructure, and CI support. With two engineers, v1 is feasible in approximately six weeks. With three, delivery compresses to roughly four weeks with better test coverage and lower context-switching overhead.

### MVP Feature Set (Phase 1)

**Core User Journeys Supported:**
- Platform engineer running daily pre-deploy review
- Platform engineer escalating cross-tool high-risk findings
- SRE lead making go/no-go decisions
- Junior engineer learning from plain-English review output
- Engineering manager reviewing deployment-risk trends
- Platform admin maintaining topology, AI Skills, and incident history
- API/CI consumer running advisory analysis in pipeline workflows

**Must-Have Capabilities:**
- Parsing and normalization for Terraform, Kubernetes, Ansible, Jenkins, and CloudFormation
- Unified change schema and local-first analysis pipeline
- AI-generated plain-English risk narrative grounded by AI Skills
- Tool-specific AI Skills for all supported tool types
- Risk scoring with explainable score breakdown
- Blast radius mapping using service topology
- Incident-history ingestion and similarity matching
- Rollback-plan generation with complexity scoring
- Analysis history, audit trail, and trend visibility
- Dashboard, REST API, and CLI access modes
- Custom AI Skill override support
- Advisory-only workflow with no automated deployment blocking

**Explicit Scope Note:** PDF export is the first non-core feature to defer if schedule pressure requires a cut. Intelligence-layer capabilities are not candidates for removal because they define the product thesis.

### Post-MVP Features

**Phase 2 (Post-MVP):**
- Official CI/CD plugins for GitHub Actions, GitLab CI, and Jenkins integration
- Slack bot with interactive collaboration workflows
- Topology auto-discovery from Terraform state
- Side-by-side report diffing across analyses
- Risk-threshold customization UI
- Lightweight multi-user and team-sharing features

**Phase 3 (Expansion):**
- Automated deployment blocking and policy-gating integrations
- Real-time cloud API introspection and live-state discovery
- Custom LLM fine-tuning on team-specific incident and review data
- Community AI Skills marketplace and distribution model
- Post-deploy monitoring integration with feedback-loop learning
- Cost impact analysis across cloud providers

### Risk Mitigation Strategy

**Technical Risks:** The highest technical risk is parser correctness across five tools, especially real-world edge cases such as nested Terraform modules, multi-document Kubernetes YAML, dynamic Ansible execution paths, scripted Jenkins pipelines, and conditional CloudFormation templates. Mitigation requires extensive fixture-based testing with real-world samples and treating parser crashes or silent misreads as top-priority defects. The second major technical risk is whether AI Skills materially improve LLM narrative quality, which must be validated through structured A/B comparison against ungrounded prompts.

**Market Risks:** The biggest adoption risk is trust failure through poor score calibration. If the system over-flags, engineers will ignore it. If it under-flags and falsely reassures on a dangerous deploy, adoption may collapse permanently. Mitigation requires conservative defaults, transparent score explainability, and calibration against real historical deployment scenarios before teams rely on the output operationally.

**Resource Risks:** If staffing or time is reduced, the contingency is not to remove core intelligence features but to defer peripheral convenience features. The integrated nature of the product means the core feature set must remain intact for the product to make sense. Resource pressure should be absorbed by trimming polish and secondary outputs first, with PDF export the clearest early deferral candidate.

## Functional Requirements

### Multi-Tool Change Intake

- FR1: Platform engineers can submit deployment artifacts from Terraform, Kubernetes, Ansible, Jenkins, and CloudFormation for a single analysis.
- FR2: Platform engineers can submit multiple files from multiple supported tools in one analysis session.
- FR3: The system can identify the supported tool type of each submitted artifact without requiring manual classification from the user.
- FR4: The system can analyze partial deployment context when only a subset of related artifacts is provided.
- FR5: The system can detect unsupported or sensitive files in a submission and warn the user when those files are excluded from analysis or external model use.

### Unified Risk Analysis

- FR6: Platform engineers can receive a single risk assessment that combines findings across all submitted deployment artifacts.
- FR7: The system can produce a deploy recommendation that indicates whether a change appears safe, needs caution, or requires escalation.
- FR8: The system can identify cross-tool interactions where individually benign changes create elevated combined risk.
- FR9: The system can classify risk findings by severity so that users can distinguish low, medium, high, and critical issues.
- FR10: The system can explain which detected changes contributed to the overall risk assessment.

### Narrative Guidance & Learning

- FR11: Platform engineers can receive a plain-English narrative that explains what changed, why it matters, and what could break.
- FR12: Junior engineers can receive tool-specific explanations that help them understand why a change is risky.
- FR13: Users can receive actionable guidance describing what to review, change, or verify before deployment.
- FR14: SRE leads can review a decision-ready summary that supports go or no-go deployment decisions.
- FR15: Users can distinguish between the system's recommendation and the final human deployment decision.

### Blast Radius & Operational Impact

- FR16: Users can view which downstream services, systems, or resources may be affected by a deployment change.
- FR17: The system can indicate when blast-radius analysis may be incomplete because required topology context is missing or stale.
- FR18: SRE leads can review impact information in enough detail to assess which teams or systems may need coordination before release.
- FR19: Platform administrators can maintain the service-topology context used for impact analysis.

### Rollback & Incident Intelligence

- FR20: Users can receive a rollback plan for an analyzed deployment.
- FR21: Users can review rollback steps in an ordered sequence that reflects operational recovery flow.
- FR22: SRE leads can review rollback complexity as part of deployment decision making.
- FR23: Platform administrators can ingest past incident records so the system can compare new deployments against historical failures.
- FR24: Users can see when a current deployment resembles a previously recorded incident.

### History, Audit, and Trend Review

- FR25: The system can retain a history of completed analyses for later review.
- FR26: Engineering managers can review historical deployment analyses to understand risk trends over time.
- FR27: Engineering managers can compare risk patterns across tools, time periods, and deployment outcomes.
- FR28: Teams can use analysis history as an audit trail showing when a deployment was reviewed and what assessment was produced.
- FR29: Users can retrieve past reports for investigation, learning, or approval-thread reference.

### Configuration & Customization

- FR30: Platform administrators can configure which language model provider the system uses for narrative generation.
- FR31: Platform administrators can operate the system in a fully local analysis mode when external model usage is not allowed.
- FR32: Platform administrators can add or override team-specific AI Skills so analysis reflects internal modules, conventions, and risk patterns.
- FR33: Platform administrators can manage the operational context required for analysis, including incident records and topology definitions.
- FR34: Teams can use the system without enabling automated deployment blocking.

### Interfaces & Workflow Access

- FR35: Platform engineers can use a web interface to submit artifacts, review findings, and access historical analyses.
- FR36: Technical users can access analysis capabilities through an API for automation and integration workflows.
- FR37: Technical users can trigger analysis from command-line workflows when a browser interface is not the preferred entry point.
- FR38: CI workflows can submit deployment artifacts for advisory analysis and consume structured results.
- FR39: Teams can share analysis outputs within deployment review workflows without requiring the system itself to make the final release decision.

## Non-Functional Requirements

### Performance

- The system shall complete a standard deployment analysis in under 15 seconds under normal operating conditions.
- The web dashboard shall load in under 1.5 seconds on supported desktop browsers under normal internal-network conditions.
- The UI shall update analysis results within 500 milliseconds after a completed analysis is available.
- The analysis history interface shall remain responsive with at least 1000 stored reports using indexed and paginated retrieval.
- The system shall support at least 3 concurrent analyses without major degradation in responsiveness or analysis completion time.

### Security

- The system shall never send raw infrastructure-as-code content to external LLM providers.
- The system shall store API keys only in memory or environment variables and shall never persist them to local databases, logs, or generated reports.
- Sensitive-file detection shall always remain enabled and shall automatically exclude dangerous files from external model transmission.
- The system shall support a fully offline operating mode using Ollama in which no analysis-related network calls are made outside the local environment.
- Application logs shall exclude secrets, prompts, raw infrastructure content, and model responses, and shall contain only operational metadata such as timestamps, filenames, scores, and errors.

### Reliability

- The product shall not depend on a formal uptime SLA for v1, but it shall fail gracefully in self-hosted environments.
- If the configured LLM provider is unavailable, the system shall still return local analytical outputs including risk score, change breakdown, and blast radius information.
- Parser failures shall be isolated to the affected file or artifact and shall not terminate analysis for the remaining valid inputs in the same submission.
- Completed analysis reports shall be persisted successfully before they are presented in the dashboard or returned to the user as final output.

### Accessibility

- Risk severity shall never be communicated by color alone and shall always include explicit textual labels or equivalent non-color indicators.
- Core workflows including navigation, file submission, configuration, and report review shall be keyboard navigable on supported desktop browsers.
- Narrative content, change tables, and rollback plans shall be rendered using semantic HTML structures compatible with assistive technologies.
- Visualizations such as risk gauges and blast-radius graphs shall include textual summaries or `aria` descriptions of their key information.
- The product shall target practical accessibility for common engineering workflows without requiring formal WCAG certification in v1.

### Integration

- The system shall expose a stable versioned JSON analysis API for automation and integration workflows.
- The system shall accept standard supported artifact formats without requiring users to transform them into proprietary intermediate formats.
- The system shall produce advisory outputs that can be consumed easily by CI workflows and scripts.
- The system shall not require a single LLM vendor and shall allow provider substitution through configuration rather than code changes.

### Scalability

- The v1 product shall be designed for single-team deployment rather than multi-tenant organizational scale.
- The persistence layer shall support at least 1000 historical reports without unacceptable degradation in retrieval performance.
- The system shall support analyses containing tens of files in one submission, with a tested target of up to 30 files across supported tools.
- The default upload limit shall be 50 MB total per analysis session, with configuration support for adjustment if needed.
- The system shall support a small number of concurrent active users, with a target operating range of 3 to 5 simultaneous sessions.
