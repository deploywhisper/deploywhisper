# DeployWhisper Product Requirements Document

**Product:** DeployWhisper  
**Document type:** Product Requirements Document  
**Version:** 1.0 Final - Self-Hosted, Evidence-Law First, AI-Safety, Documentation-First, Benchmark-Honest, and CNCF-Ready  
**Date:** May 1, 2026  
**Owner:** Pramod Kumar Sahoo   
**License posture:** Fully open-source (MIT). Self-hosted only. No SaaS product. No hosted control plane. No open-core split. No paid enterprise-only features.  
**Strategic posture:** Become the open-source safety standard for human-written and AI-generated infrastructure changes before production.
**v1.0 tightening:** Restores testable performance targets, adds legal/ethical safeguards for sample incident packs, and defines conflict-handling rules for external scanner evidence.
All milestones in this section are part of DeployWhisper V1 scope. The milestone labels describe implementation order and maturity gates, not separate product versions. No item in this section should be interpreted as V2, paid, post-V1, or SaaS-only scope.
---

## 1. Executive Summary

DeployWhisper is a **self-hosted, local-first, evidence-backed, open-source pre-deployment intelligence platform** for infrastructure changes.

It helps platform engineers, SREs, DevOps teams, reviewers, security teams, maintainers, and AI coding agents answer the real pre-release question:

> **Is this infrastructure change safe to ship, what could break, who could be affected, what evidence supports the risk, and what should we verify before rollout?**

DeployWhisper analyzes infrastructure artifacts and related workflow context across Terraform, OpenTofu, Kubernetes, Helm, Kustomize, Ansible, Jenkins, CloudFormation, CI/CD pipelines, and future community-supported toolchains. It produces a **single trusted deployment briefing** built from deterministic evidence, confidence scoring, blast-radius context, rollback readiness, incident memory, deployment outcome learning, external scanner context, and explicit uncertainty indicators.

DeployWhisper is not a generic LLM wrapper. AI narrative is allowed only after deterministic analysis, evidence collection, context enrichment, and risk scoring have produced a stable analysis object.

### 1.1 The Evidence Law

DeployWhisper is governed by the **Evidence Law**:

> **No high or critical finding without deterministic evidence.**

This is the product's headline trust guarantee.

AI may explain, summarize, and suggest next verification steps, but AI narrative must never create a high or critical finding by itself. High and critical findings must be backed by concrete, inspectable evidence from artifacts, plans, manifests, topology, ownership data, incident records, deployment history, policy/scanner output, or other deterministic inputs.

The Evidence Law must appear in:

- README.
- Website hero section.
- CLI output.
- API schema documentation.
- UI report pages.
- PR comments.
- Demo scripts.
- Benchmark reports.
- Documentation examples.
- Contributor guidance.

### 1.2 Two product heroes

DeployWhisper has two co-equal product stories:

1. **Evidence-backed deployment briefing.**  
   Humans need fast, defensible, evidence-backed review before infrastructure changes reach production.

2. **Safety layer for AI-generated infrastructure changes.**  
   AI coding agents and AI-assisted development tools are generating more infrastructure code. Those changes require grounded, deterministic, inspectable review before merge, apply, or deploy.

DeployWhisper should become the tool that both human reviewers and AI agents call before infrastructure changes reach production.

### 1.3 What is in the deployment briefing

Each DeployWhisper report should include:

- Unified advisory risk verdict with contributor breakdown.
- Evidence-backed findings where every material claim links to an artifact, topology source, incident record, deployment history item, external scanner finding, policy context, or benchmarked risk pattern.
- Deterministic-vs-inferred separation for every important finding.
- Cross-tool interaction warnings, such as Terraform networking changes combined with Kubernetes rollout changes or CI/CD approval-path changes.
- Blast-radius analysis with context freshness and completeness indicators.
- Rollback readiness and rollback complexity.
- Day-zero public risk pattern matches.
- Organization-specific incident-memory similarity matches when available.
- Deployment outcome learning signals when available.
- Confidence ledger showing why the system is confident or not confident.
- "Why not lower?" and "Why not higher?" explanation for the overall verdict.
- Context TODOs that tell maintainers what data would improve future reports.
- Plain-English narrative generated downstream of scoring, never upstream of scoring.
- Machine-readable output for API, CLI, CI/CD, PR bots, policy adapters, and AI agents.

### 1.3.1 UI modernization requirements

The React UI migration preserves the Evidence Law, advisory-only posture, and
local-first assumptions after the Phase 7 cutover.
Dashboard screens consume read-only `/api/v1` backend-for-ui endpoints for KPI
summary cards, verdict distribution, project switching, and compact analysis
rows. Backend support for the migration is additive only: no schema migrations,
no destructive report contract changes, and no removal of existing API fields.
The React dashboard is served at `/` within the Part B0
information budget: greeting and Evidence Law status, four KPI cards, five-row
recent analyses table, Latest Briefing summary card, New Analysis upload card,
and verdict-health donut only. The dashboard uses the Phase 2 primitives without
restyling, binds all values to real API responses through TanStack Query, lets
ProjectSwitcher drive the sidebar/greeting/upload scope, and navigates uploads
or recent-row clicks to the React report route instead of restoring the retired
inline report/countdown flow.

### 1.4 Category

DeployWhisper defines and serves the category:

> **Open-source pre-deployment intelligence for infrastructure changes.**

It sits between IaC scanners, CI/CD orchestration, policy engines, CSPM platforms, observability, incident management, and AI code-review assistants.

### 1.5 Seven product pillars

1. **Evidence Law first** - no high or critical finding without deterministic evidence.
2. **Self-hosted-only operation** - users install and operate DeployWhisper in their own infrastructure; there is no DeployWhisper SaaS or hosted control plane.
3. **Local-first security boundary** - raw IaC and sensitive artifacts stay local by default.
4. **AI-infrastructure safety** - DeployWhisper reviews AI-generated and human-written infrastructure changes with the same evidence-backed standard.
5. **Cross-tool context** - infrastructure risk is evaluated across files, tools, workflows, runtime context, ownership, and history.
6. **Decision-ready deployment briefing** - the output helps humans make go/no-go decisions quickly and defensibly.
7. **Open community and CNCF readiness** - governance, documentation, benchmarks, maintainership, security posture, and contribution paths are designed for a large open-source community.

### 1.6 Open-source strategic bet

DeployWhisper wins by becoming the **trusted open standard** for reviewing human-written and AI-generated infrastructure changes before production.

The product must be:

- Fully open-source.
- Self-hosted-only in user-controlled infrastructure.
- Documented clearly enough that users can install, operate, extend, benchmark, and troubleshoot it without a vendor-hosted service.
- Local-first.
- Extensible through public and private Skills.
- Transparent through public benchmarks and honest failure reporting.
- Governed with public maintainer ownership.
- Credible enough for a future CNCF Sandbox application.

The project must not depend on a revenue model, paid features, vendor lock-in, proprietary hosted capabilities, or a DeployWhisper-operated SaaS service to become successful.

---

## 2. Open-Source and Self-Hosted Commitment

### 2.1 Product commitment

DeployWhisper will remain fully open-source.

The project will not use:

- Open-core licensing.
- Paid enterprise-only features.
- Sponsor-only features.
- Features that require users to register with DeployWhisper.
- Features that require users to send raw IaC to a DeployWhisper-operated service.
- A DeployWhisper-hosted SaaS product.
- A DeployWhisper-managed hosted dashboard.
- A DeployWhisper-hosted API.
- A DeployWhisper-hosted model service.
- A vendor-managed control plane.
- Proprietary Skills required for core value.
- Closed benchmark data used for public claims.
- Hidden scoring logic for material deployment-risk decisions.

All core and advanced capabilities should remain available in the public project, including:

- Evidence model.
- Risk scoring.
- Project/workspace/RBAC model.
- Blast-radius analysis.
- Rollback analysis.
- Day-zero risk pattern memory.
- Organization incident memory.
- Deployment outcome memory.
- AI-agent and MCP support.
- Workflow integrations.
- Skills registry and skill test harness.
- Benchmark corpus and scoring tools.
- Honest benchmark failure reports.
- Policy adapters.
- External scanner ingestion.
- Enterprise-grade hardening such as SSO, RBAC, audit logging, PostgreSQL support, signed artifacts, SBOMs, provenance, and air-gapped deployment guides.

### 2.2 Self-hosted-only deployment model

DeployWhisper is **not a SaaS product** and must not be designed around a DeployWhisper-operated cloud service.

Users install and operate DeployWhisper inside infrastructure they control. Supported deployment paths should include:

- Local developer installation for CLI-first evaluation.
- Single-node Docker installation for local testing.
- Docker Compose installation for small teams and trials.
- Kubernetes and Helm installation for platform teams and shared internal deployments.
- Air-gapped or restricted-network installation for regulated environments.
- Self-hosted CI/CD runner integration for GitHub, GitLab, Jenkins, Atlantis, Argo CD, Flux, and similar systems.
- Optional external provider configuration only when explicitly chosen by the user, such as a user-owned LLM provider, VCS API, incident system, external scanner, or observability endpoint.

The project must not require:

- A DeployWhisper-hosted API.
- A DeployWhisper-hosted dashboard.
- A DeployWhisper-hosted model service.
- A vendor-managed control plane.
- Proprietary telemetry.
- Account registration with DeployWhisper.
- Internet access for core offline analysis when local models and local artifacts are used.

All architecture diagrams, onboarding docs, examples, and epics must assume the self-hosted model first. Any optional integration with external systems must be documented as user-owned and user-configured.

### 2.3 Sustainability without revenue

DeployWhisper may accept donations, sponsorships, public grants, foundation support, cloud credits, or community infrastructure help only if they do not create feature control or roadmap capture.

Allowed sustainability paths:

- GitHub Sponsors, OpenCollective, or similar donation channels.
- Public grants.
- Community infrastructure donations.
- Maintainer sponsorships with transparent disclosure.
- Vendor-neutral foundation participation.
- Community-led documentation, benchmarks, examples, talks, and integrations.

Not allowed:

- Sponsor-only features.
- Paid support commitments that define public roadmap priority.
- Proprietary plugins required for major supported platforms.
- Hosted-only analysis capabilities.
- Vendor-managed analysis paths.
- Closed governance controlled by a single commercial entity.

### 2.4 Governance principle

The product should be governed as public infrastructure, not as a sales funnel.

Every major feature should answer:

> **Does this make DeployWhisper more trustworthy, more open, more useful in real workflows, easier to self-host, and easier for the community to extend?**

### 2.5 Documentation-first commitment

Because DeployWhisper will not rely on SaaS onboarding, sales engineering, or vendor-managed support, documentation is a core product surface.

Every feature must ship with enough documentation for users to:

- Understand what the feature does.
- Install or enable it in self-hosted infrastructure.
- Configure it safely.
- Use it in a real workflow.
- Troubleshoot common failures.
- Understand its security and privacy implications.
- Understand how it interacts with existing security tools.
- Contribute improvements back to the project.

A feature is not complete until its user, admin, operator, API, CLI, integration, and troubleshooting documentation impact has been reviewed.

---

## 3. Vision, Mission, and North Star

### 3.1 Vision

Build the most trusted open-source system for understanding infrastructure deployment risk before production.

### 3.2 Mission

Help infrastructure teams and AI coding agents make safer deployment decisions by combining deterministic analysis, historical context, grounded AI explanation, day-zero risk patterns, incident memory, deployment outcome learning, external scanner context, and explicit uncertainty into one deployment briefing.

### 3.3 North star

A team should feel uncomfortable deploying a critical infrastructure change without a DeployWhisper report, the same way engineers today feel uncomfortable merging code without CI.

### 3.4 AI-era mission

As AI coding agents generate more infrastructure code, DeployWhisper becomes the safety layer that validates, explains, and challenges those changes before they reach production.

DeployWhisper does not replace human approvers. It gives human approvers and automation systems a grounded, inspectable, evidence-backed report.

### 3.5 CNCF-era mission

DeployWhisper should be designed for a large neutral open-source community from the beginning. The project should make governance, maintainer ownership, contributor pathways, security posture, public benchmarks, and documentation visible before applying to CNCF.

---

## 4. Product Positioning

### 4.1 Category definition

DeployWhisper belongs to a new but important category:

> **Pre-deployment intelligence for infrastructure changes.**

This category exists because infrastructure risk is not only a syntax problem, not only a security-policy problem, and not only an observability problem.

Infrastructure risk appears when:

- Multiple tools interact.
- A small diff has a large blast radius.
- Runtime context changes the meaning of a configuration change.
- Rollback is more complex than the deploy.
- A change resembles a previous incident.
- A change resembles a public deployment-failure pattern.
- A security scanner finding becomes operationally dangerous because of topology, environment, service criticality, or rollout timing.
- AI-generated infrastructure code looks plausible but contains unsafe assumptions.
- Reviewers do not know what context is missing.

### 4.2 Final positioning statement

> **DeployWhisper is the self-hosted, open-source safety layer for human and AI-generated infrastructure changes, governed by the Evidence Law: no high or critical finding without deterministic evidence.**

### 4.3 Message to the community

DeployWhisper is not trying to become another closed DevOps platform. It is an open, self-hosted, inspectable deployment-risk briefing layer that teams can run in their own infrastructure, extend with their own Skills, benchmark publicly, and govern transparently.

### 4.4 Explicit non-positioning

DeployWhisper is not:

- A SaaS platform.
- A hosted control plane.
- A Terraform runner.
- A CI/CD system.
- A generic chatbot.
- A replacement for Snyk, Checkov, Wiz, OPA, Sentinel, CSPM, SAST, SCA, container scanning, or observability tools.
- A Kubernetes-only diagnostic tool.
- A policy language.
- A production auto-remediation engine.
- An auto-approval engine for AI agents.
- A tool that sends user IaC to a vendor-owned service by default.

DeployWhisper works **alongside** existing tools and adds the missing deployment-risk briefing layer.

---

## 5. Problem Statement

Modern infrastructure teams ship through many tools:

- Terraform and OpenTofu.
- Kubernetes, Helm, and Kustomize.
- CloudFormation.
- Ansible.
- Jenkins and other CI/CD systems.
- GitHub Actions and GitLab CI.
- Atlantis, HCP Terraform, Spacelift, env0, Argo CD, Flux, and other delivery systems.

Each tool exposes only part of the risk. A scanner may detect a security issue. A CI system may show pass/fail. A Terraform plan may show resource replacement. A Kubernetes diff may show rollout changes. An incident system may hold painful context. An observability tool may know which services are critical.

But a reviewer still has to answer:

- Is this safe to deploy?
- What changed?
- What could break?
- What services, users, teams, data stores, or environments are in the blast radius?
- Is rollback simple or dangerous?
- Does this resemble a previous incident?
- Does this resemble a known public risk pattern?
- Did an AI agent generate unsafe infrastructure boilerplate?
- What evidence supports the warning?
- What context is missing?
- Should this be acknowledged, reviewed by a service owner, or blocked by a downstream adapter?

Today, this answer is often assembled manually from diffs, plans, scanner output, Slack context, tribal knowledge, postmortems, dashboards, and intuition.

DeployWhisper exists to make that deployment-review decision faster, safer, inspectable, and repeatable.

---

## 6. Users and Communities

### 6.1 Primary users

| User | Needs |
|---|---|
| Platform engineer | Understand cross-tool deployment risk before merge or apply. |
| SRE | Know blast radius, rollback readiness, service criticality, and incident similarity. |
| DevOps engineer | Review Terraform, Kubernetes, CI/CD, and automation changes quickly. |
| Infrastructure reviewer | See evidence, confidence, uncertainty, and required verification steps. |
| AI coding agent operator | Ensure AI-generated IaC is reviewed by a deterministic safety layer. |
| Open-source contributor | Add parsers, Skills, benchmarks, connectors, documentation, or integrations. |

### 6.2 Secondary users

| User | Needs |
|---|---|
| Security engineer | Understand how security findings affect deployment risk and operations. |
| Engineering manager | Track risk trends, false positives, false reassurance, and adoption. |
| Release manager | Use advisory summaries in release approval workflows. |
| Incident commander | Connect new changes to historical failures and rollback lessons. |
| CNCF reviewer | Evaluate governance, maintainership, community health, project scope, and security posture. |
| Documentation contributor | Help users self-host, troubleshoot, and extend the product. |

### 6.3 Non-users and explicit boundaries

DeployWhisper is not optimized for:

- Non-technical executives looking for dashboards only.
- Teams that do not manage infrastructure as code or deployment automation.
- Users seeking a hosted SaaS risk platform.
- Users seeking fully autonomous deployment approval.
- Users seeking runtime observability without pre-deployment review.

---

## 7. Jobs To Be Done

### 7.1 Core JTBD

When a user is about to merge, apply, or deploy an infrastructure change, they want DeployWhisper to produce a trusted, evidence-backed briefing so they can decide whether to proceed, ask for more review, change the rollout plan, or postpone the deployment.

### 7.2 Supporting JTBDs

- When a reviewer sees a high-risk warning, they want to inspect the evidence behind it.
- When context is missing, an admin wants to know what connector or data would improve future analysis.
- When an incident happened before, an SRE wants to know if the current change resembles it.
- When no incidents exist yet, a new user wants useful public risk pattern matches instead of an empty feature.
- When an AI agent proposes infrastructure changes, a team wants a deterministic safety review before PR creation, merge, or apply.
- When a team already uses Snyk, Checkov, Wiz, OPA, Sentinel, Datadog, or other tools, they want DeployWhisper to complement them instead of competing with them.
- When a contributor adds a Skill or parser, maintainers want tests, examples, and documentation to prove quality.
- When CNCF reviewers evaluate the project, they want to see transparent governance, maintainer coverage, release discipline, security posture, and healthy community participation.

---

## 8. Product Principles

1. **Evidence before narrative.**  
   AI explanation must never outrank deterministic evidence.

2. **The Evidence Law is non-negotiable.**  
   No high or critical finding without deterministic evidence.

3. **Advisory-first by default.**  
   DeployWhisper informs decisions. Humans and explicitly configured downstream systems decide enforcement.

4. **Local-first and self-hosted-only.**  
   Users run DeployWhisper in their own infrastructure. Raw IaC and sensitive artifacts remain local unless users explicitly configure otherwise.

5. **Uncertainty must be visible.**  
   Missing topology, stale state, absent ownership, or unavailable incident history must lower confidence and appear in the report.

6. **Context is the moat.**  
   The product becomes more useful through topology, ownership, criticality, deployment history, incidents, outcomes, scanner outputs, and Skills.

7. **AI is downstream of trust.**  
   AI should summarize, explain, and assist; it must not silently create material risk claims.

8. **Day-zero usefulness matters.**  
   Fresh installs must produce useful public risk pattern matches before any organization-specific incidents are imported.

9. **Workflows beat dashboards.**  
   DeployWhisper should appear where deployment decisions already happen: PRs, CI/CD, CLI, chat, GitOps, and agent workflows.

10. **Documentation is product.**  
    A self-hosted-only project must be installable, operable, extensible, and debuggable through documentation.

11. **Open governance builds trust.**  
    Maintainer ownership, CODEOWNERS, RFCs, roadmap, release process, and contributor ladder must be public.

12. **Honesty beats marketing.**  
    Benchmarks must publish misses, false positives, false reassurance, regressions, and unsupported scenarios.

---

## 9. Competitive Landscape

### 9.1 Adjacent categories

| Category | Examples | DeployWhisper position |
|---|---|---|
| IaC/security scanners | Snyk IaC, Checkov, tfsec, KICS, Trivy | Complement. Consume scanner outputs and add deployment risk context. |
| CSPM/CNAPP | Wiz, Prisma Cloud, Lacework | Complement. These focus on cloud posture and security; DeployWhisper focuses on pre-deployment operational risk briefing. |
| Policy engines | OPA, Gatekeeper, Kyverno, Sentinel | Complement. DeployWhisper can emit policy-ready evidence but is not a policy language. |
| IaC orchestration | HCP Terraform, Atlantis, Spacelift, env0 | Complement. DeployWhisper can run beside or before these workflows. |
| K8s AI diagnosis | K8sGPT | Adjacent. DeployWhisper is pre-deployment and multi-tool, not only runtime Kubernetes diagnosis. |
| Observability | Datadog, Grafana, Prometheus, CloudWatch | Complement. DeployWhisper uses observability metadata as context. |
| Generic LLM review | ChatGPT, Claude, Gemini | Different. DeployWhisper is evidence-first and deterministic before narrative. |
| AI coding agents | Cursor, Copilot-style agents, Devin-style agents, Claude Code-style workflows | Safety layer. DeployWhisper reviews proposed infrastructure changes from agents. |

### 9.2 Strategic differentiation

DeployWhisper differentiates through:

- The Evidence Law.
- Self-hosted-only, fully open-source operation.
- Multi-tool infrastructure review.
- Project-scoped context graph.
- Day-zero public risk pattern memory.
- Organization-specific incident memory.
- Deployment outcome learning.
- External scanner ingestion and contextualization.
- Rollback readiness.
- Honest public benchmarks.
- Agent-native safety interfaces.
- CNCF-ready governance and documentation.

### 9.3 Competitive risk response

DeployWhisper should not claim to replace the best tools in each adjacent category. Instead, it should explain:

> Existing tools tell you important pieces of the truth. DeployWhisper assembles those pieces into a pre-deployment risk briefing that explains what could break, why it matters, what evidence supports it, how hard rollback may be, and what context is missing.

---

## 10. Core Product Thesis

DeployWhisper becomes the first choice in the market by being the most trustworthy open-source pre-deployment intelligence layer.

The winning formula:

```text
Evidence Law
+ self-hosted-only trust boundary
+ project-scoped context graph
+ day-zero public risk patterns
+ organization incident memory
+ deployment outcome learning
+ workflow-native delivery
+ agent-native safety
+ external scanner contextualization
+ tested Skills ecosystem
+ honest public benchmarks
+ documentation-first adoption
+ CNCF-ready governance
= open standard for infrastructure deployment safety
```

---

## 11. Evidence Law

### 11.1 Product headline

The Evidence Law is the product's primary trust promise:

> **No high or critical finding without deterministic evidence.**

This statement should be used consistently across product, documentation, website, demos, benchmark reports, and community talks.

### 11.2 Meaning

The Evidence Law means:

- A high or critical finding must include at least one deterministic evidence item.
- An LLM-generated explanation cannot create a high or critical finding by itself.
- An inferred-only concern must be labeled as a hypothesis, weak signal, or lower-confidence observation.
- If context is missing, DeployWhisper must show uncertainty rather than fake confidence.
- Severity scoring must be reproducible enough to be tested against fixtures.
- Evidence must persist with the report for audit, replay, benchmark, and review.

### 11.3 Surfaces where it must appear

| Surface | Requirement |
|---|---|
| README | First-screen promise. |
| Website | Hero section and demo narrative. |
| CLI | Visible in high/critical report output and `--explain-evidence`. |
| API | Finding schema requires evidence references. |
| UI | Evidence inspector for high/critical findings. |
| PR comments | High/critical findings include evidence references or links. |
| Benchmarks | Evidence coverage and violations tracked. |
| Docs | Dedicated `docs/concepts/evidence-law.md`. |
| Contributor guide | Test requirement for new detectors and Skills. |

### 11.4 Enforcement in code

DeployWhisper must include validation that prevents invalid high/critical findings from being persisted, displayed, or emitted to integrations.

Required validation rules:

- `severity in [high, critical]` requires `evidence.length >= 1`.
- At least one evidence item for high/critical findings must have `evidence_type = deterministic` or equivalent.
- LLM-only evidence cannot satisfy the Evidence Law.
- External scanner evidence can support a finding, but DeployWhisper must still attach deterministic context or clearly label the finding as external.
- Benchmark expected outputs must include expected evidence IDs for high/critical findings.
- CI must fail if fixtures produce high/critical findings without deterministic evidence.

---

## 12. Deployment Briefing Requirements

### 12.1 Report structure

A report must include:

1. Project and workspace scope.
2. Analysis metadata and report schema version.
3. Overall advisory verdict.
4. Confidence ledger.
5. Evidence Law status.
6. Top findings.
7. Blast radius.
8. Rollback readiness.
9. Day-zero public risk pattern matches.
10. Organization incident matches when available.
11. External scanner and policy context when available.
12. AI-generated IaC safety observations when applicable.
13. Context TODOs.
14. Why not lower / why not higher.
15. Detailed evidence inspector.
16. Machine-readable JSON representation.

### 12.2 Risk verdicts

DeployWhisper should support verdicts such as:

- `low`
- `medium`
- `high`
- `critical`
- `insufficient_context`
- `analysis_failed`

`insufficient_context` is not the same as low risk. It means DeployWhisper cannot responsibly produce a confident verdict.

### 12.3 Required explanations

Every report must explain:

- What changed.
- Why the change matters.
- Which tools and artifacts contributed to the verdict.
- Which findings are deterministic.
- Which findings are inferred or contextual.
- Which findings came from external scanner outputs.
- Which evidence supports each material claim.
- What context is missing or stale.
- What a reviewer should verify next.
- What rollback may require.

### 12.4 No unsupported certainty

DeployWhisper must not say:

- "This is safe" when context is insufficient.
- "This will cause an outage" without evidence.
- "This resembles your incident" when only public risk patterns are available.
- "Security tool X found risk, therefore deploy risk is high" without contextual analysis.
- "AI generated this" unless provenance or content signals support the statement.

---

## 13. Project, Workspace, and RBAC Model

### 13.1 Why this model must exist now

Project scope must be designed before v1 persistence, connectors, reports, incidents, credentials, RBAC, policies, and topology become difficult to refactor.

Even though DeployWhisper is self-hosted-only, a single installation may serve multiple teams, repositories, clusters, services, environments, and Terraform workspaces. A clear project model prevents context leakage, permission ambiguity, and future architectural rewrites.

### 13.2 Hierarchy

```text
Instance
  -> Project
      -> Workspace / Environment
          -> Service
              -> Resource
      -> Reports
      -> Incidents
      -> Deployment outcomes
      -> Context connectors
      -> External scanner imports
      -> Policies and adapter settings
      -> Skills configuration
      -> Members and roles
```

### 13.3 Definitions

**Instance**  
A DeployWhisper installation operated by a user or organization in their own infrastructure. DeployWhisper does not provide a hosted control plane.

**Project**  
The primary boundary for context, reports, incidents, connectors, credentials, ownership, policies, Skills configuration, retention, and RBAC. A project usually maps to a product, platform area, service group, repository group, Terraform workspace group, Kubernetes application group, or deployment domain.

**Workspace / Environment**  
A deployable environment within a project, such as `dev`, `staging`, `prod`, a Terraform workspace, a Kubernetes namespace, a cluster, a cloud account, or a GitOps application.

**Service**  
A deployable or operational unit owned by a team.

**Resource**  
An infrastructure object such as a Kubernetes Deployment, Service, Ingress, Terraform resource, cloud database, IAM policy, queue, topic, load balancer, DNS record, secret reference, or CI/CD pipeline.

**Analysis Run**  
One execution of DeployWhisper against a set of artifacts, context, and configuration.

**Report**  
The persisted output of an analysis run, scoped to a project and optionally one or more workspaces.

**Connector**  
A user-configured integration that provides context, such as Terraform state, Kubernetes live state, incident records, scanner output, ownership data, or observability metadata.

### 13.4 Required object scoping rule

No report, connector credential, incident record, deployment outcome, ownership mapping, topology object, policy override, or external scanner import may exist without an instance or project scope.

Global objects are limited to:

- Public Skills.
- Built-in risk patterns.
- Benchmark scenarios.
- Documentation.
- Default schemas.
- Global instance settings.

### 13.5 RBAC roles

| Role | Permissions |
|---|---|
| Instance Admin | Manage global settings, auth, users, release settings, global Skills, instance security, and system-level configuration. |
| Project Admin | Manage project config, connectors, members, retention, project policies, project Skills, and project credentials. |
| Maintainer | Run analyses, manage project context, import incidents, review reports, update risk patterns within project scope. |
| Reviewer | View reports, inspect evidence, acknowledge findings, submit feedback, and add review notes. |
| Viewer | Read-only access to permitted reports and documentation. |
| Security Reviewer | Review security-sensitive findings, external scanner evidence, and security-relevant deployment risks. |
| Service Owner | Review and acknowledge findings for owned services. |
| Automation Actor | Limited token-bound role for CI/CD, GitOps, and agent workflows. |

### 13.6 Authentication and authorization requirements

The project must support a simple local mode first, then a stronger self-hosted shared-team mode.

Phase expectations:

- Phase 0/1: Project key accepted by CLI, API, and integration paths; basic local/admin operation; schema supports project scope.
- Phase 2: Project membership and role checks for reports, incidents, and connectors.
- Phase 3/4: SSO/OIDC/SAML-compatible design, service accounts, audit logs, and token scoping.

### 13.7 Project model acceptance criteria

- CLI, API, UI, and integrations accept or derive a project key.
- Reports are scoped to a project.
- Incidents are scoped to a project.
- External scanner imports are scoped to a project.
- Connector credentials are scoped to instance, project, or workspace.
- RBAC decisions are project-aware.
- Context graph nodes include project and workspace scope.
- Report URLs and API endpoints include project identity or an unambiguous project reference.
- Documentation explains how to model projects for monorepos, multi-repos, Kubernetes clusters, Terraform workspaces, and platform teams.

---

## 14. Evidence Model

### 14.1 Evidence item

Each evidence item should include:

```yaml
evidence_id: string
source_type: terraform_plan | terraform_state | kubernetes_manifest | kubernetes_live_state | cloudformation | ansible | jenkins | github_actions | gitlab_ci | incident | deployment_history | ownership | external_scanner | skill | benchmark_pattern | user_context
source_ref: string
project_id: string
workspace_id: string | null
artifact_name: string | null
resource_ref: string | null
operation: create | update | delete | replace | expose | restrict | unknown
location:
  file: string | null
  line_start: number | null
  line_end: number | null
confidence: high | medium | low
evidence_type: deterministic | derived | external | inferred | user_provided
freshness: fresh | stale | unknown | not_applicable
redaction_status: none | redacted | sensitive_blocked
summary: string
```

### 14.2 Finding object

Each finding should include:

```yaml
finding_id: string
project_id: string
workspace_id: string | null
severity: low | medium | high | critical
category: security | availability | data_loss | blast_radius | rollback | compliance | workflow | ai_generated_iac | context_gap | unknown
title: string
summary: string
evidence_ids: [string]
deterministic_evidence_count: number
inferred_notes: [string]
external_signal_refs: [string]
confidence: high | medium | low
uncertainty: string | null
recommended_verification: [string]
rollback_notes: [string]
related_incidents: [string]
related_public_patterns: [string]
evidence_law_status: satisfied | not_required | violation
```

### 14.3 Risk categories

DeployWhisper should support at least:

- Availability risk.
- Security exposure risk.
- Data-loss risk.
- Stateful replacement risk.
- Rollback complexity.
- Blast-radius expansion.
- Cross-tool interaction risk.
- CI/CD approval bypass risk.
- Runtime mismatch risk.
- Ownership and review gap.
- Incident recurrence risk.
- Public risk pattern match.
- AI-generated IaC risk.
- External scanner contextual risk.
- Insufficient context.

### 14.4 Deterministic vs inferred separation

Every report must distinguish:

- **Deterministic evidence** - directly parsed or observed facts.
- **Derived evidence** - computed from deterministic evidence, such as blast radius or impact path.
- **External evidence** - imported from scanners, policy tools, or other systems.
- **User-provided context** - service criticality, ownership, incident notes, or manual annotations.
- **Inferred narrative** - AI-assisted explanation, hypothesis, or reviewer-oriented summary.

Narrative may explain evidence. Narrative must not replace evidence.

---

## 15. Confidence, Uncertainty, and Reviewer Trust

### 15.1 Confidence ledger

Every report should include a confidence ledger:

```text
Confidence: Medium

Strong signals:
- Terraform plan parsed successfully.
- Kubernetes manifests parsed successfully.
- CODEOWNERS mapping found for payments-api.
- Two public risk patterns matched.

Weak signals:
- Terraform state is 19 days old.
- No live Kubernetes state available.
- No organization-specific incidents imported.
- SLO metadata missing.
```

### 15.2 Why not lower / why not higher

Every overall verdict should explain scoring boundaries.

Example:

```text
Why this is not LOW:
- Database ingress is widened.
- A production service is in the blast radius.
- Rollback requires manual data-store verification.

Why this is not CRITICAL:
- No destructive database operation detected.
- Change is limited to one environment.
- Existing rollback procedure was found.
```

### 15.3 Context TODOs

When analysis quality is limited by missing data, DeployWhisper should produce actionable context TODOs:

```text
To improve future reports:
1. Add Terraform state connector for project prod-payments.
2. Add CODEOWNERS mapping for services/payments.
3. Import last 12 months of PagerDuty incidents.
4. Add service criticality for payments-api.
5. Enable read-only Kubernetes live-state connector for prod cluster.
```

### 15.4 Trust constraints

- Do not hide weak context.
- Do not claim certainty from stale data.
- Do not overstate incident similarity.
- Do not call a change safe simply because no risk was detected.
- Do not call a security finding a deployment blocker unless deployment context supports it.
- Do not mark built-in public risk patterns as user incidents.

---

## 16. Context Moat

### 16.1 Context graph

DeployWhisper should build a project-scoped context graph:

```text
Project
  -> Workspace / Environment
      -> Service
          -> Workload
              -> Runtime resource
                  -> Cloud resource
                      -> Data store
                          -> Owner
                              -> SLO / criticality
                                  -> Incident history
                                      -> Deployment history
```

Every node and edge should include:

- Source.
- Project scope.
- Workspace/environment scope.
- Freshness.
- Confidence.
- Last seen timestamp.
- Redaction status.

### 16.2 Minimum context sources

Priority order:

1. Terraform plan JSON.
2. Terraform state, read-only.
3. Kubernetes manifests.
4. Kubernetes live cluster state, read-only and optional.
5. GitHub/GitLab metadata and CODEOWNERS.
6. Markdown/YAML/JSON incident import.
7. PagerDuty/Opsgenie/Jira/GitHub Issues/Slack incident import.
8. CloudFormation stack exports.
9. Prometheus/Grafana/Datadog monitor metadata.
10. Argo CD and Flux application metadata.
11. Atlantis/HCP Terraform/Spacelift/env0 run metadata.
12. External scanner outputs, including SARIF and JSON formats.

### 16.3 Context quality states

- `available_fresh`
- `available_stale`
- `available_partial`
- `conflicting`
- `missing`
- `not_configured`
- `not_supported`

### 16.4 Context must be explainable

When DeployWhisper makes a context-based claim, it must explain:

- Which context source was used.
- When the source was last updated.
- Whether the source is complete.
- Whether the source is project-scoped or global.
- How the context influenced the verdict.

---

## 17. Day-Zero Incident Memory and Incident Learning

### 17.1 Signature feature

Incident Memory should become DeployWhisper's emotional hook:

> **This change resembles something that broke before.**

But a fresh installation has no organization-specific incidents. DeployWhisper must solve this day-zero problem.

### 17.2 Three memory layers

DeployWhisper shall distinguish clearly between:

1. **Risk Pattern Memory**  
   Built-in, public, benchmarked deployment-failure patterns that ship with DeployWhisper.

2. **Organization Incident Memory**  
   User-imported or user-generated incident records scoped to a project.

3. **Deployment Outcome Memory**  
   Feedback captured after DeployWhisper-reviewed deployments, including success, rollback, incident, false positive, and false reassurance.

DeployWhisper must never claim that a built-in public risk pattern is an organization-specific prior incident.

### 17.3 Day-zero user experience

Fresh installs must show useful behavior without imported incidents.

If no organization incidents exist, the report should say:

```text
No organization-specific incidents have been imported for this project yet.
DeployWhisper is using built-in public risk patterns and available project context.
```

If a public pattern matches, the report should say:

```text
Matched public risk pattern:
Kubernetes service selector drift can disconnect traffic from workloads during rollout.

This is not an organization-specific incident match. Import incidents to enable project-specific memory.
```

### 17.4 Built-in risk pattern library

DeployWhisper should include public risk patterns such as:

- Kubernetes service selector drift.
- Kubernetes readiness/liveness probe weakening.
- Kubernetes PDB removal before rollout.
- Kubernetes HPA misconfiguration.
- Kubernetes secret exposure through environment variables.
- Terraform public database ingress.
- Terraform IAM privilege expansion.
- Terraform stateful resource replacement.
- Terraform destructive database operation.
- Terraform route table or subnet exposure.
- CloudFormation replacement of stateful resources.
- CloudFormation security group widening.
- Ansible broad inventory targeting.
- Ansible destructive shell task.
- Jenkins/GitHub Actions/GitLab CI production approval bypass.
- GitOps sync wave or ordering risk.
- Cross-tool database port exposure during app rollout.
- External scanner finding combined with production-critical service context.

Each pattern should include:

```text
Pattern ID
Title
Toolchains
Risk category
Evidence required
False-positive considerations
Example risky diff
Example safe diff
Recommended verification
Rollback guidance
Benchmark scenarios
Related Skills
```

### 17.5 Sample incident pack

DeployWhisper should include optional demo/sample incident data so users can see the incident-memory workflow without importing private data.

Rules:

- Sample incidents must be clearly labeled as sample data.
- Sample incidents must never be loaded by default in production mode.
- Demo reports must clearly distinguish sample data from project incidents.
- Sample incident text must never reference real customer data, real organization names, or be sourced from non-public postmortems without explicit attribution and permission.
- Sample incident packs must be reviewed as public documentation assets, not treated as anonymous test fixtures.

### 17.6 Organization incident record schema

An incident record should include:

```yaml
incident_id: string
project_id: string
title: string
occurred_at: datetime
services: [string]
workspaces: [string]
severity: string
root_cause: string
trigger_change: string
affected_resources: [string]
toolchains: [string]
rollback_path: string
rollback_successful: boolean | null
time_to_detect: string | null
time_to_recover: string | null
prevention_notes: string
source: markdown | yaml | json | pagerduty | opsgenie | jira | github_issue | slack | manual
source_ref: string | null
labels: [string]
redaction_status: string
```

### 17.7 Similarity engine

Similarity should combine:

- Resource overlap.
- Service overlap.
- Environment/workspace overlap.
- Toolchain overlap.
- Risk category overlap.
- Change operation overlap.
- Ownership overlap.
- Deterministic tags.
- Semantic similarity over incident summary and prevention notes.

Every incident match must explain why it matched.

### 17.8 Backtest mode

Users should be able to run DeployWhisper against historical incident-causing changes after importing incidents.

Backtest outputs should include:

- Would DeployWhisper have flagged this?
- What severity would it have assigned?
- Which evidence was available?
- Which context was missing?
- What would need to improve?

### 17.9 Deployment outcome capture

After deployment, users should be able to record:

- Successful.
- Successful with warnings.
- Rolled back.
- Incident created.
- False positive.
- False reassurance.
- Context missing.
- Reviewer feedback.

Outcome capture is required for calibration and public benchmark quality.

---

## 18. AI-Generated Infrastructure Safety and Agent-Native Requirements

### 18.1 Agent safety role

DeployWhisper is the safety layer that AI coding agents call before infrastructure changes reach production.

DeployWhisper does not autonomously deploy, approve, merge, or remediate production changes.

### 18.2 AI-generated IaC risk patterns

DeployWhisper should detect common AI-generated infrastructure risks, including:

- Unsafe defaults.
- Broad IAM permissions.
- Public ingress.
- Missing environment scoping.
- Missing rollback path.
- Hallucinated resource names.
- Inconsistent resource references.
- Missing ownership tags.
- Incomplete dependencies.
- Weak security group descriptions.
- Generated boilerplate copied across environments.
- Drift between generated CI/CD workflow and intended deployment environment.

### 18.3 Agent interfaces

DeployWhisper should provide:

- Stable machine-readable JSON output.
- `--agent-json` CLI mode.
- MCP-compatible interface or equivalent agent-callable interface.
- API endpoint for agent-safe analysis requests.
- Missing-context output suitable for agent planning.
- Recommended verification steps.
- Report links for human review.

### 18.4 Example agent workflow

```text
1. Agent proposes Terraform and Kubernetes changes.
2. Agent runs `deploywhisper analyze --project payments --changed --agent-json`.
3. DeployWhisper returns evidence-backed risk findings and context TODOs.
4. Agent revises the change or adds reviewer notes.
5. Human reviewer sees the DeployWhisper report in the PR.
6. Human reviewer decides whether to approve, request changes, or defer.
```

### 18.5 Prompt-injection and artifact safety

DeployWhisper must treat all user-provided content as untrusted:

- IaC comments.
- YAML annotations.
- PR descriptions.
- Commit messages.
- Incident descriptions.
- Scanner output text.
- Documentation-like files.
- Agent messages.

Required controls:

- Prompt isolation.
- Redaction before model calls.
- Tool-call restrictions.
- Structured inputs to LLMs where possible.
- Prompt-injection tests.
- No model access to credentials.
- No model authority to approve, deploy, or modify project state without explicit user action.

### 18.6 AI safety documentation

Required docs:

- `docs/ai-safety/reviewing-ai-generated-iac.md`
- `docs/ai-safety/agent-json-output.md`
- `docs/ai-safety/mcp-server.md`
- `docs/security/prompt-injection-threat-model.md`

---

## 19. Advisory Core and Optional Enforcement Adapters

### 19.1 Advisory-first default

DeployWhisper's core behavior is advisory.

The default output informs humans and systems. It does not block deployment by default.

### 19.2 Adapter enforcement levels

Optional downstream adapters may support:

| Mode | Behavior |
|---|---|
| Advisory | Comment only. Never blocks. Default. |
| Acknowledgement required | Reviewer must acknowledge risk before workflow proceeds. |
| Soft block | Blocks unless authorized override is provided. |
| Hard block | Blocks only for deterministic, policy-grade findings. |
| Emergency bypass | Requires reason, actor, timestamp, and audit metadata. |

### 19.3 Enforcement guardrails

- Enforcement must be explicitly configured by the user.
- High/critical enforcement must satisfy the Evidence Law.
- LLM-only findings must not trigger hard blocks.
- Emergency bypasses must be audited.
- Policy adapters must not alter the core report object.
- The project must remain useful without enforcement enabled.

---

## 20. Skills Ecosystem

### 20.1 Skills strategy

Skills allow the community to extend DeployWhisper's domain knowledge without hardcoding every pattern into the core.

Skills should be:

- Versioned.
- Tested.
- Documented.
- Installable.
- Trust-labeled.
- Compatible with benchmark fixtures.
- Safe for self-hosted operation.

### 20.2 Skill trust levels

| Level | Meaning |
|---|---|
| Experimental | Community-submitted, not fully reviewed, test coverage limited. |
| Verified | Schema-valid, tests pass, maintainer reviewed. |
| Core | Maintained by DeployWhisper maintainers, included in core testing. |
| Deprecated | Available for compatibility but not recommended. |

### 20.3 Required skill artifacts

Each Skill should include:

- `skill.md`
- `manifest.yaml` or `manifest.json`
- Test scenarios.
- Expected findings.
- False-positive examples.
- Version compatibility.
- Maintainer information.
- License metadata.

### 20.4 Skill manifest example

```yaml
id: terraform.aws.rds
name: Terraform AWS RDS Risk Patterns
version: 1.0.0
toolchains:
  - terraform
providers:
  - aws
risk_categories:
  - data-loss
  - public-exposure
  - rollback-complexity
requires:
  evidence_contract: ">=1.0"
tests:
  scenarios_path: tests/scenarios
maintainers:
  - github: maintainer-handle
license: Apache-2.0
```

### 20.5 Seed Skills target

Seed at least 40 Skills across:

- Terraform AWS.
- Terraform Azure.
- Terraform GCP.
- Terraform IAM.
- Terraform networking.
- Terraform RDS.
- Terraform EKS.
- OpenTofu.
- Terragrunt.
- Kubernetes workload safety.
- Kubernetes networking.
- Kubernetes RBAC.
- Kubernetes storage.
- Helm.
- Kustomize.
- Argo CD.
- Flux.
- CloudFormation IAM.
- CloudFormation networking.
- CloudFormation RDS.
- Ansible inventory.
- Ansible privilege escalation.
- Jenkins deploy pipeline.
- GitHub Actions deploy pipeline.
- GitLab CI deploy pipeline.
- Dockerfile.
- Docker Compose.
- Prometheus rules.
- Grafana alerts.
- Datadog monitors.
- OPA Gatekeeper.
- Kyverno.
- External Secrets.
- Vault.
- cert-manager.
- Istio.
- Linkerd.
- NGINX ingress.
- AWS ALB ingress.
- Rollback readiness.
- AI-generated IaC review.
- External scanner contextualization.

---

## 21. Benchmark Corpus, Calibration, and Honest Failure Reporting

### 21.1 Benchmark as product

Benchmarks are not marketing artifacts. They are part of the product's trust model.

DeployWhisper should maintain a public benchmark corpus with:

- Scenario artifacts.
- Expected verdicts.
- Expected evidence IDs.
- Expected false-positive considerations.
- Expected context limitations.
- Scoring scripts.
- Historical result reports.
- Regression tracking.

### 21.2 Benchmark corpus areas

Include scenarios for:

- Terraform.
- OpenTofu.
- Kubernetes.
- Helm.
- Kustomize.
- CloudFormation.
- Ansible.
- Jenkins.
- GitHub Actions.
- GitLab CI.
- Cross-tool deployment risk.
- AI-generated IaC.
- External scanner contextualization.
- Day-zero public risk patterns.
- Organization incident memory.
- Missing/stale/conflicting context.
- Rollback readiness.

### 21.3 Baselines to compare against

Where reproducible, compare against:

- Generic LLM prompt.
- Checkov or other open IaC scanner for overlapping IaC security cases.
- K8sGPT for Kubernetes diagnostic-adjacent cases.
- Human review baseline where friendly-user studies are available.
- Prior DeployWhisper release.

### 21.4 Benchmark metrics

Track:

- High/critical precision.
- High/critical recall.
- False reassurance rate.
- False-positive rate.
- Evidence coverage.
- Evidence Law violations.
- Severity calibration.
- Context completeness calibration.
- Incident match quality.
- Public risk pattern usefulness.
- Reviewer usefulness score.
- Latency, including p50, p95, p99, timeout rate, deterministic latency, and narrative latency.
- Regression stability.

### 21.5 Honest failure reporting

Every public benchmark report must include:

- Scenarios DeployWhisper detected correctly.
- Scenarios DeployWhisper missed.
- Scenarios where severity was too low.
- Scenarios where severity was too high.
- False positives.
- False reassurance cases.
- Unsupported scenarios.
- Regressions compared with the previous release.
- Root-cause notes for important misses.
- Follow-up GitHub issues linked to missed scenarios.

Suggested template:

```md
# DeployWhisper Benchmark Report - YYYY QX

## Summary
## What improved
## What regressed
## Scenarios detected correctly
## Scenarios missed
## False reassurance cases
## False positives
## Unsupported scenarios
## Evidence coverage
## Context limitations
## Follow-up issues
## Next benchmark goals
```

### 21.6 Benchmark governance

- Benchmark changes require review.
- Benchmark expected outputs must be versioned.
- Benchmark results must be reproducible.
- Material misses must create linked GitHub issues unless explicitly out of scope.
- Benchmark reports must distinguish product limitations from benchmark limitations.
- Benchmark reports must not hide failures to preserve adoption optics.

---

## 22. Workflow-Native Delivery

### 22.1 Workflow principle

Users should not need to open DeployWhisper to benefit from it. DeployWhisper should appear where deployment decisions already happen.

### 22.2 Required surfaces

- Web report UI.
- REST API.
- CLI.
- GitHub PR comments.
- GitHub Action.
- Self-hosted GitHub App path.
- GitLab Merge Requests.
- Jenkins shared library/plugin path.
- Atlantis integration.
- HCP Terraform run task or equivalent adapter.
- Argo CD / Flux GitOps advisory path.
- Slack/Teams deploy briefing.
- MCP/agent interface.
- Pre-commit/local developer mode.

### 22.3 PR comment requirements

PR comments should include:

- Overall verdict.
- Evidence Law status.
- Top findings.
- Evidence links or references.
- Blast radius summary.
- Rollback readiness.
- Incident and risk pattern matches.
- External scanner context.
- Missing context.
- Link to full report.
- Advisory status.

### 22.4 Report diff

On rerun, DeployWhisper should show:

```text
Risk changed: HIGH -> MEDIUM

Resolved:
- Public RDS ingress removed.

New:
- Rollback complexity increased because migration step was added.

Still open:
- Missing production topology.
```

---

## 23. DeployWhisper Alongside Existing Security Tools

### 23.1 Position

DeployWhisper does not replace Snyk, Checkov, Wiz, OPA, Sentinel, CSPM platforms, SAST, SCA, container scanning, secrets scanning, or observability platforms.

DeployWhisper complements them by turning security, policy, topology, incident, ownership, and workflow signals into a deployment-risk briefing.

### 23.2 Required documentation page

Create:

```text
docs/comparisons/deploywhisper-alongside-security-tools.md
```

This page must answer:

- Do I still need Snyk, Checkov, Wiz, OPA, Sentinel, or CSPM?
- What does DeployWhisper do that scanners do not?
- What does DeployWhisper intentionally not do?
- How can DeployWhisper ingest scanner output?
- How should AppSec, SRE, and platform teams divide responsibilities?
- How does DeployWhisper handle scanner findings under the Evidence Law?

### 23.3 Comparison framing

| Question | Existing security/IaC tools | DeployWhisper |
|---|---|---|
| Main job | Find security misconfigurations, vulnerabilities, policy/compliance issues, or cloud posture risks. | Explain deployment risk before production using evidence, context, blast radius, rollback readiness, incidents, and risk patterns. |
| Primary users | AppSec, DevSecOps, cloud security, developers. | Platform engineers, SREs, release engineers, infra reviewers, AI-agent governance teams. |
| Main input | IaC files, code, dependencies, containers, cloud resources, policies. | IaC diffs, plans, manifests, CI/CD changes, topology, incidents, ownership, deployment history, scanner outputs. |
| Main output | Security or compliance findings and fix advice. | Deployment briefing: what changed, what could break, who is affected, how to rollback, and what evidence supports the verdict. |
| Time horizon | Before and after deployment security posture. | Immediately before merge, apply, sync, or deploy. |
| Replace or complement? | Existing security control. | Complementary deployment-risk intelligence layer. |

### 23.4 External scanner ingestion

DeployWhisper should ingest external scanner outputs as supporting evidence.

Priority formats:

- SARIF.
- Checkov JSON.
- Snyk JSON where available.
- Trivy JSON.
- tfsec JSON.
- KICS JSON.
- OPA/conftest output.
- Custom generic finding JSON.

External scanner findings must be labeled as external evidence.

External scanner findings cannot automatically become high/critical DeployWhisper findings without DeployWhisper's own evidence model and scoring rules.

If an external scanner finding contradicts deterministic evidence, DeployWhisper must surface the conflict instead of silently choosing one source. Contradictions should be represented as explicit conflict findings or confidence warnings that show the scanner claim, the deterministic evidence, freshness of each source, and recommended human verification.

Example conflict logic:

```text
External scanner signal:
Snyk/Checkov reported public database exposure.

DeployWhisper deterministic evidence:
Terraform state and the current plan indicate the database security group does not allow public ingress.

DeployWhisper handling:
- Mark this as conflicting evidence.
- Do not silently discard either source.
- Do not escalate to high/critical based only on the external scanner signal.
- Recommend verification of scanner freshness, Terraform state freshness, and cloud runtime state.
```

Example report logic:

```text
External scanner signal:
Snyk/Checkov reported public database exposure.

DeployWhisper context:
- The database is used by payments-api.
- The change targets production.
- Terraform state shows the database is currently private.
- Rollback requires stateful connectivity validation.
- CODEOWNERS requires payments SRE review.

DeployWhisper verdict:
High, supported by deterministic evidence and external scanner context.
```

### 23.5 FAQ requirement

README and docs must include:

```text
Q: We already use Snyk, Checkov, Wiz, OPA, Sentinel, or CSPM. Why use DeployWhisper?

A: Keep those tools. DeployWhisper is not a replacement. It uses their signals where available and adds deployment-specific context: blast radius, rollback readiness, incidents, ownership, workflow risk, confidence, and Evidence Law-backed briefing.
```

---

## 24. Security, Privacy, and Supply Chain

### 24.1 Security posture

DeployWhisper is infrastructure-adjacent software and must be treated like critical tooling.

### 24.2 Core security requirements

- Raw IaC must not be sent to external LLM providers by default.
- External provider usage must be explicit and documented.
- Provider credentials must not be persisted in unsafe form.
- Logs must not contain secrets, raw sensitive IaC, raw prompts, or raw model responses by default.
- Sensitive-file handling must stay enabled.
- Fully local operation through local models must be possible.
- Prompt-injection tests must cover IaC comments, PR text, incident text, scanner output, and documentation-like artifacts.
- RBAC must be project-aware.
- Audit metadata must be retained for reports, acknowledgements, overrides, and enforcement adapter decisions.

### 24.3 Open-source supply-chain requirements

The project should implement:

- OpenSSF Scorecard GitHub Action.
- OpenSSF Best Practices Badge progress.
- CodeQL.
- Dependabot or Renovate.
- SBOM generation.
- Signed container images.
- Release artifact checksums.
- SLSA provenance where practical.
- GitHub artifact attestations where practical.
- Cosign signing for containers where practical.
- Branch protection.
- Required reviews for release workflows.
- Security policy and vulnerability reporting process.

### 24.4 Release artifact requirements

Every release should include:

- Source tag.
- Changelog.
- Container image.
- CLI binaries where applicable.
- Checksums.
- SBOM.
- Provenance/attestation where practical.
- Upgrade notes.
- Known limitations.
- Benchmark result snapshot or link.
- Documentation version link.

---

## 25. Open Governance, Maintainer Ownership, and Community

### 25.1 Required community files

The repository must include:

- `GOVERNANCE.md`
- `MAINTAINERS.md`
- `CODEOWNERS`
- `CONTRIBUTOR_LADDER.md`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`
- `SUPPORT.md`
- `ROADMAP.md`
- `RELEASE_PROCESS.md`
- `ADOPTERS.md`
- `RFC/` directory

### 25.2 Public maintainer ownership model

DeployWhisper must publicly document who maintains what.

`MAINTAINERS.md` should include:

| Area | Scope | Primary maintainer | Backup maintainer | GitHub | Organization | Notes |
|---|---|---|---|---|---|---|
| Evidence Core | Evidence schema, deterministic gates, Evidence Law validation | TBD | TBD | @handle | Org | Release-critical |
| Risk Engine | Scoring, verdict logic, uncertainty model | TBD | TBD | @handle | Org | Release-critical |
| Project/RBAC | Project model, authz, roles, tenancy boundaries | TBD | TBD | @handle | Org | Architecture-critical |
| Parsers & Connectors | Terraform, Kubernetes, CloudFormation, Ansible, Jenkins | TBD | TBD | @handle | Org | Parser ownership |
| Workflow Integrations | GitHub, GitLab, Jenkins, Atlantis, GitOps, PR comments | TBD | TBD | @handle | Org | Workflow-native delivery |
| Incident Memory | Risk patterns, incident import, similarity, outcomes | TBD | TBD | @handle | Org | Signature feature |
| AI Safety | Agent JSON, MCP, prompt-injection tests, AI IaC checks | TBD | TBD | @handle | Org | AI-era positioning |
| External Scanner Ingestion | SARIF, Checkov, Snyk, Trivy, OPA/conftest | TBD | TBD | @handle | Org | Complementary tools |
| Skills Registry | Skill manifests, tests, catalog, trust levels | TBD | TBD | @handle | Org | Community ecosystem |
| Benchmarks | Corpus, scoring, quarterly reports, honest failures | TBD | TBD | @handle | Org | Trust and regression |
| Documentation | User docs, installation docs, examples, docs CI | TBD | TBD | @handle | Org | Self-hosted adoption |
| Security & Release | Security policy, signing, SBOM, provenance, releases | TBD | TBD | @handle | Org | Supply-chain trust |
| Community/CNCF | Governance, RFCs, contributor ladder, adopters | TBD | TBD | @handle | Org | CNCF readiness |

### 25.3 CODEOWNERS requirements

`CODEOWNERS` should cover every major directory.

Example:

```text
/src/evidence/              @deploywhisper/evidence-maintainers
/src/risk/                  @deploywhisper/risk-maintainers
/src/project/               @deploywhisper/project-maintainers
/src/authz/                 @deploywhisper/project-maintainers
/src/parsers/               @deploywhisper/parser-maintainers
/src/connectors/            @deploywhisper/connector-maintainers
/src/incidents/             @deploywhisper/incident-maintainers
/src/ai-safety/             @deploywhisper/ai-safety-maintainers
/integrations/              @deploywhisper/workflow-maintainers
/skills/                    @deploywhisper/skills-maintainers
/benchmarks/                @deploywhisper/benchmark-maintainers
/docs/                      @deploywhisper/docs-maintainers
/.github/workflows/         @deploywhisper/release-maintainers
/GOVERNANCE.md              @deploywhisper/community-maintainers
/SECURITY.md                @deploywhisper/security-maintainers
/RELEASE_PROCESS.md         @deploywhisper/release-maintainers
```

### 25.4 Multi-maintainer target

Before applying to CNCF Sandbox, DeployWhisper should aim to show:

- Multiple active maintainers.
- Maintainers across multiple project areas.
- At least one backup maintainer for release-critical areas where possible.
- Public contribution history beyond the founder.
- Public maintainer promotion process.
- Open issues labeled for new contributors.
- Public community meetings or async decision logs.

An internal readiness target is at least four active maintainers across distinct areas, but the project should avoid presenting that number as a formal CNCF rule.

### 25.5 Maintainer ladder

Contributor progression should be documented:

1. User.
2. Contributor.
3. Regular contributor.
4. Reviewer.
5. Area maintainer.
6. Core maintainer.
7. Maintainer council member, if the project adopts a council model.

Each level should define:

- Expectations.
- Permissions.
- Nomination process.
- Review process.
- Inactivity policy.
- Conflict resolution.

### 25.6 RFC process

Major changes require public RFCs, including:

- Evidence model changes.
- Risk scoring changes.
- Project/RBAC model changes.
- Incident similarity changes.
- Benchmark methodology changes.
- Skills trust model changes.
- Enforcement adapter behavior.
- AI-agent interface changes.
- Security boundary changes.

### 25.7 Community metrics

Track:

- Time to first response.
- Change request closure ratio.
- Contributor absence factor.
- Release frequency.
- Review latency.
- Issue triage latency.
- Documentation contribution rate.
- Benchmark contribution rate.
- Skill contribution rate.
- Maintainer coverage gaps.

### 25.8 Community channels

Recommended public channels:

- GitHub Issues.
- GitHub Discussions.
- Public roadmap board.
- RFC directory.
- Community meeting notes.
- Security reporting channel.
- Release announcements.

---

## 26. Product Documentation and User Enablement

### 26.1 Documentation goal

DeployWhisper must be self-service for installation, operation, extension, and contribution because it is fully open-source and self-hosted-only.

### 26.2 Documentation audiences

Docs must support:

- First-time evaluator.
- Platform engineer.
- SRE reviewer.
- Security engineer.
- AI-agent workflow owner.
- Self-hosted operator.
- Kubernetes admin.
- Air-gapped environment operator.
- Parser contributor.
- Skill contributor.
- Benchmark contributor.
- CNCF/community reviewer.

### 26.3 Documentation information architecture

Required documentation tree:

```text
docs/
  index.md
  getting-started/
    quickstart-local.md
    first-analysis.md
    understand-your-report.md
    sample-artifacts.md
  installation/
    overview.md
    docker.md
    docker-compose.md
    kubernetes.md
    helm.md
    air-gapped.md
    upgrade.md
    backup-restore.md
  concepts/
    evidence-law.md
    evidence-model.md
    project-model.md
    risk-verdicts.md
    confidence-ledger.md
    context-graph.md
    day-zero-incident-memory.md
    incident-memory.md
    public-risk-patterns.md
    deployment-outcomes.md
    advisory-vs-enforcement.md
  user-guides/
    review-a-report.md
    triage-high-risk-finding.md
    compare-report-reruns.md
    import-incidents.md
    record-deployment-outcomes.md
    configure-context-todos.md
  integrations/
    github-action.md
    github-app-self-hosted.md
    gitlab.md
    jenkins.md
    atlantis.md
    hcp-terraform.md
    argocd.md
    flux.md
    slack.md
    teams.md
    pre-commit.md
  connectors/
    terraform-plan.md
    terraform-state.md
    kubernetes-manifests.md
    kubernetes-live-state.md
    codeowners.md
    pagerduty.md
    opsgenie.md
    jira.md
    github-issues.md
    slack-export.md
    prometheus.md
    grafana.md
    datadog.md
    sarif.md
    checkov.md
    snyk.md
    trivy.md
    opa-conftest.md
  ai-safety/
    reviewing-ai-generated-iac.md
    agent-json-output.md
    mcp-server.md
    prompt-injection-threat-model.md
  skills/
    overview.md
    install-skill.md
    author-skill.md
    test-skill.md
    publish-skill.md
    private-skills.md
    skill-trust-levels.md
  api/
    rest-api.md
    report-schema.md
    evidence-schema.md
    webhook-schema.md
    auth.md
  cli/
    overview.md
    commands.md
    examples.md
    agent-json.md
  operations/
    architecture.md
    configuration.md
    database.md
    workers.md
    observability.md
    logs.md
    retention.md
    troubleshooting.md
  security/
    security-model.md
    local-first-provider-boundary.md
    secret-redaction.md
    threat-model.md
    vulnerability-disclosure.md
    supply-chain.md
  comparisons/
    deploywhisper-alongside-security-tools.md
  benchmarks/
    overview.md
    running-benchmarks.md
    adding-scenarios.md
    reading-results.md
    honest-failure-reporting.md
    quarterly-reports.md
  community/
    governance.md
    maintainer-areas.md
    contributor-ladder.md
    rfcs.md
    release-process.md
    adopters.md
  cncf/
    readiness-checklist.md
    sandbox-application-notes.md
```

### 26.4 Documentation workflow for every epic

Every epic must include:

1. Documentation impact assessment.
2. User guide updates.
3. Admin/operator guide updates.
4. API/CLI/schema updates.
5. Security and privacy notes.
6. Troubleshooting entries.
7. Example artifacts.
8. Release notes.
9. Docs review.
10. Link-check and command/schema drift checks where practical.

### 26.5 Documentation acceptance criteria

A feature is not done unless:

- A user can understand what it does.
- A self-hosted operator can install or enable it.
- A reviewer can use it in a real workflow.
- A contributor can test or extend it.
- A security reviewer can understand its trust boundary.
- Failure modes and troubleshooting are documented.
- Examples are copy-pasteable where practical.

### 26.6 Required user documentation deliverables

- Quickstart local.
- Docker Compose install.
- Kubernetes/Helm install.
- Air-gapped install.
- First analysis walkthrough.
- Understanding report verdicts.
- Evidence Law guide.
- Project model guide.
- Day-zero incident memory guide.
- Incident import guide.
- Reviewing AI-generated IaC guide.
- Existing security tools comparison guide.
- GitHub Action guide.
- GitLab guide.
- Terraform plan/state guide.
- Kubernetes context guide.
- Skills authoring guide.
- Benchmark contribution guide.
- Troubleshooting guide.
- CNCF readiness checklist.

### 26.7 Documentation metrics

Track:

- Broken links.
- Docs coverage by feature.
- Quickstart success rate from friendly users.
- Time-to-first-report from docs.
- Search/no-result queries if docs site supports search.
- Docs issues opened/closed.
- Contributor docs feedback.
- Examples passing in CI.

---

## 27. CNCF Readiness Strategy

### 27.1 CNCF goal

DeployWhisper should prepare for CNCF Sandbox consideration after it has credible signs of:

- Open governance.
- Clear project scope.
- Public maintainership model.
- Community participation.
- Active contributions beyond the founder.
- Security policy.
- Release process.
- Adopters or meaningful user evidence.
- Documentation maturity.
- Open-source supply-chain hygiene.

### 27.2 CNCF positioning

DeployWhisper should position itself as:

> **An open-source, self-hosted, pre-deployment infrastructure safety layer for cloud native environments and AI-generated infrastructure changes.**

### 27.3 CNCF preparation checklist

Before application, complete:

- `GOVERNANCE.md`
- `MAINTAINERS.md`
- `CODEOWNERS`
- `CONTRIBUTOR_LADDER.md`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`
- `RELEASE_PROCESS.md`
- `ADOPTERS.md`
- Public roadmap.
- Public RFC process.
- Community meeting notes or async decision records.
- License review.
- DCO/CLA decision.
- OpenSSF Scorecard progress.
- OpenSSF Best Practices Badge progress.
- SBOM/signing/provenance plan.
- Benchmark reports with honest failure sections.
- Documentation site or repository docs.
- Maintainer coverage map.

### 27.4 Long-term maturity path

- Sandbox target: innovative early-stage project with clear governance, scope, community foundations, and adoption signals.
- Incubation target: growing adoption, stable governance, multiple maintainers, production use evidence, robust security/release practices.
- Graduation target: broad adoption, stable APIs, strong governance, production readiness, mature security and support practices.

---

## 28. Success Metrics

### 28.1 Product adoption metrics

- Time to first local report.
- Successful self-hosted installation count, where voluntarily reported.
- GitHub stars and forks.
- Unique contributors.
- Integrations used.
- Skills installed.
- Benchmark contributors.
- Public adopters.

### 28.2 Trust metrics

- High/critical precision.
- High/critical recall.
- False reassurance rate.
- False-positive rate.
- Evidence coverage.
- Evidence Law violation count.
- Reviewer usefulness score.
- Report defensibility score.
- Context completeness score.

### 28.3 Workflow metrics

- PR comment usage.
- Rerun-on-commit usage.
- Report diff usage.
- Average analysis latency.
- Advisory acknowledgement rate.
- Deployment outcome capture rate.

### 28.4 Learning metrics

- Incidents imported.
- Public risk pattern matches.
- Organization incident matches.
- Incident match usefulness score.
- Backtests completed.
- Outcomes captured.
- Calibration changes from outcomes.

### 28.5 Community metrics

- Time to first response.
- Issue closure ratio.
- PR review latency.
- Contributor retention.
- Maintainer coverage gaps.
- Documentation PRs.
- Skill contributions.
- Benchmark scenario contributions.
- Organizations represented among contributors.

### 28.6 Security and supply-chain metrics

- OpenSSF Scorecard score trend.
- Best Practices Badge progress.
- CodeQL findings.
- Dependency update latency.
- Signed release coverage.
- SBOM coverage.
- Attestation/provenance coverage.
- Vulnerability response time.

---

## 29. Primary User Journeys

### 29.1 Platform Engineer - Pre-deploy review

A platform engineer opens a PR that changes Terraform and Kubernetes manifests. DeployWhisper posts a PR comment with an advisory verdict, Evidence Law status, top findings, blast radius, rollback notes, and missing context.

### 29.2 SRE Approver - Go/no-go decision

An SRE reviews a high-risk finding, opens evidence details, checks why severity is high, sees rollback readiness, and decides whether to approve, request changes, or ask for a service owner.

### 29.3 Junior Engineer - Learning and remediation

A junior engineer reads the report, sees concrete evidence and recommended verification steps, and learns why the change is risky.

### 29.4 Platform Admin - Context maintenance

A platform admin reviews context TODOs and adds Terraform state, CODEOWNERS, incident imports, and service criticality data to improve future reports.

### 29.5 Fresh Install - Day-zero incident memory

A new user runs DeployWhisper without importing incidents. The report still shows relevant public risk pattern matches and clearly explains that no organization-specific incident memory exists yet.

### 29.6 PR workflow - Automated advisory review

A GitHub or GitLab integration posts a concise advisory summary, reruns after new commits, and updates the report diff.

### 29.7 AI agent - Safe infrastructure proposal

An AI agent generates IaC, runs DeployWhisper in agent JSON mode, receives evidence-backed feedback, revises the change, and links the report for human review.

### 29.8 Existing security tools - Complementary review

A team imports SARIF or scanner JSON. DeployWhisper labels those findings as external evidence and adds deployment context, blast radius, rollback, ownership, and incident memory.

### 29.9 Skills contributor - Ecosystem extension

A contributor adds a Skill with manifest, tests, false-positive examples, docs, and benchmark scenarios. Maintainers review it and assign a trust level.

### 29.10 CNCF reviewer - Project health review

A CNCF reviewer can inspect governance, maintainers, CODEOWNERS, release process, security policy, adoption, benchmarks, and docs without private access.

---

## 30. Functional Requirements

### 30.1 Intake and classification

- **ING-01** Accept one or more artifacts from supported toolchains in a single analysis.
- **ING-02** Auto-detect artifact type without requiring manual labeling for normal cases.
- **ING-03** Support partial analysis when not all related artifacts are available.
- **ING-04** Detect unsupported artifacts and explain why they were excluded.
- **ING-05** Detect sensitive files and block unsafe downstream handling.
- **ING-06** Preserve a submission manifest showing accepted, excluded, partially parsed, and failed artifacts.
- **ING-07** Accept Terraform plan JSON as a first-class input.
- **ING-08** Accept project/workspace key in CLI, API, and integration flows.
- **ING-09** Preserve artifact provenance and redaction status.

### 30.2 Project, workspace, and RBAC

- **PRJ-01** Define instance, project, workspace/environment, service, resource, analysis run, report, and connector objects.
- **PRJ-02** Scope reports to a project.
- **PRJ-03** Scope incidents to a project.
- **PRJ-04** Scope deployment outcomes to a project and optional workspace.
- **PRJ-05** Scope external scanner imports to a project.
- **PRJ-06** Scope connector credentials to instance, project, or workspace.
- **PRJ-07** Support project-aware RBAC roles.
- **PRJ-08** Accept or derive project keys in CLI, API, UI, and workflow integrations.
- **PRJ-09** Include project/workspace scope in context graph nodes and evidence items.
- **PRJ-10** Document project modeling patterns for monorepos, multi-repos, Terraform workspaces, Kubernetes clusters, and platform teams.

### 30.3 Normalization and evidence

- **EVD-01** Normalize supported artifacts into a shared internal change model.
- **EVD-02** Each finding shall reference one or more concrete evidence items.
- **EVD-03** Evidence items shall identify artifact, location, resource, operation, project, and contextual source where applicable.
- **EVD-04** Reports shall distinguish deterministic findings, derived findings, external evidence, model-inferred explanations, and user-provided context.
- **EVD-05** Reports shall surface confidence and uncertainty for key findings and overall verdict.
- **EVD-06** Reports shall explain main contributors to the overall risk score.
- **EVD-07** Incomplete context shall produce explicit uncertainty instead of implied certainty.
- **EVD-08** Evidence items shall persist with reports for audit, comparison, and benchmark replay.
- **EVD-09** High and critical findings shall require at least one deterministic evidence item.
- **EVD-10** Narrative generation failure shall not remove deterministic evidence or verdict.
- **EVD-11** Evidence Law status shall be visible in reports.
- **EVD-12** CI shall fail when fixtures generate high/critical findings without deterministic evidence.

### 30.4 Risk intelligence

- **RSK-01** Produce a unified advisory deployment risk verdict.
- **RSK-02** Classify findings and verdicts by severity.
- **RSK-03** Detect cross-tool interactions that increase risk.
- **RSK-04** Generate reviewer-oriented explanations of operational risk.
- **RSK-05** Generate actionable remediation or verification guidance.
- **RSK-06** Produce rollback guidance and rollback complexity score.
- **RSK-07** Distinguish product recommendation from human decision.
- **RSK-08** Continue deterministic analysis if narrative generation fails.
- **RSK-09** Provide "why not lower" and "why not higher" explanation for verdicts.
- **RSK-10** Support an insufficient-context verdict.
- **RSK-11** Detect AI-generated IaC risk patterns where provenance or content signals are available.
- **RSK-12** Label public risk pattern matches separately from organization incident matches.

### 30.5 Context enrichment

- **CTX-01** Compute blast radius using project-scoped topology context.
- **CTX-02** Indicate when topology is stale, missing, incomplete, or conflicting.
- **CTX-03** Ingest incident records for similarity matching.
- **CTX-04** Surface relevant incident similarity results with match confidence and match reasons.
- **CTX-05** Support service criticality and environment-aware risk context.
- **CTX-06** Store deployment history sufficient for comparison and trend analysis.
- **CTX-07** Support topology auto-discovery and source connectors without replacing the core report format.
- **CTX-08** Support read-only Terraform state connector.
- **CTX-09** Support optional read-only Kubernetes live-state connector.
- **CTX-10** Support CODEOWNERS and ownership mapping.
- **CTX-11** Support context freshness and confidence per source.
- **CTX-12** Generate context TODOs to improve future report quality.
- **CTX-13** Attach context source metadata to evidence items.

### 30.6 Incident memory, risk patterns, and outcomes

- **INC-01** Support built-in public risk pattern memory on fresh installs.
- **INC-02** Clearly distinguish public risk pattern matches from organization-specific incidents.
- **INC-03** Support optional sample incident pack for demos.
- **INC-04** Support markdown, YAML, and JSON incident import.
- **INC-05** Support future imports from PagerDuty, Opsgenie, Jira, GitHub Issues, and Slack exports.
- **INC-06** Store incident metadata, root cause, trigger change, affected services, rollback path, and prevention notes.
- **INC-07** Compute similarity using deterministic and semantic signals.
- **INC-08** Explain why an incident matched the current change.
- **INC-09** Support backtesting against historical incident-causing changes.
- **INC-10** Capture deployment outcomes for calibration.
- **INC-11** Track false positives and false reassurance from outcome feedback.
- **INC-12** Ensure sample incident packs contain no real customer data, no real organization names, and no non-public postmortem content without explicit attribution and permission.

### 30.7 Review and reporting experience

- **REV-01** Web report shall present verdict first, then Evidence Law status, confidence, evidence, and details.
- **REV-02** Report shall show top findings, blast radius, rollback, risk patterns, incident memory, external scanner context, and uncertainty above the fold.
- **REV-03** Users shall be able to inspect full findings and evidence details on demand.
- **REV-04** Users shall be able to retrieve prior reports and compare analyses over time.
- **REV-05** System shall generate concise summaries for PRs and approval threads.
- **REV-06** Shared summaries shall remain explicitly advisory.
- **REV-07** Report shall support expert quick scan and detailed investigation.
- **REV-08** Report diff shall show resolved, new, and persistent risks after reruns.
- **REV-09** Report shall show context TODOs.
- **REV-10** Report schema version shall be visible and machine-readable.

### 30.8 Workflow-native delivery

- **WRK-01** Expose a stable versioned REST API.
- **WRK-02** Expose CLI access using the same analysis core.
- **WRK-03** Support GitHub-first workflow delivery for PR review.
- **WRK-04** Post formatted PR summaries including verdict, Evidence Law status, top risks, evidence, blast radius, rollback, incident memory, public risk patterns, external scanner context, and uncertainty.
- **WRK-05** Support rerun after new commits or changed artifacts.
- **WRK-06** Support report links and machine-friendly summary payloads.
- **WRK-07** Support future GitLab, Atlantis, HCP Terraform, Jenkins, Argo CD, Flux, and chat adapters without redesigning the core report object.
- **WRK-08** CLI and integration flows shall accept project key or project ID.
- **WRK-09** GitHub repository flows may derive default project key from repository name.
- **WRK-10** Support pre-commit or local developer feedback mode.

### 30.9 AI-agent interfaces and AI safety

- **AIA-01** Provide machine-readable analysis output for AI agents.
- **AIA-02** Provide `--agent-json` CLI mode.
- **AIA-03** Provide MCP-compatible interface or equivalent agent-callable interface.
- **AIA-04** Treat AI-generated IaC as untrusted input.
- **AIA-05** Detect common AI-generated infrastructure risk patterns.
- **AIA-06** Preserve provenance metadata where available, including human-authored, AI-assisted, or unknown.
- **AIA-07** Ensure AI models cannot directly create high or critical findings without deterministic evidence.
- **AIA-08** Include prompt-injection tests for IaC comments, PR comments, incident text, scanner output, and documentation-like artifacts.
- **AIA-09** Ensure agents cannot use DeployWhisper to autonomously approve, deploy, or remediate production changes.
- **AIA-10** Document AI-generated IaC review workflows.

### 30.10 External scanner and complementary-tool ingestion

- **EXT-01** Maintain documentation explaining DeployWhisper alongside existing security tools.
- **EXT-02** Support SARIF ingestion.
- **EXT-03** Support at least one scanner JSON format in Phase 1.5 or Phase 2.
- **EXT-04** Label external scanner findings as external evidence.
- **EXT-05** Prevent external scanner findings from automatically becoming high/critical DeployWhisper findings without DeployWhisper evidence and scoring.
- **EXT-06** Include external scanner context in reports, PR comments, and API output.
- **EXT-07** Document how AppSec, SRE, and platform teams should use scanner output with DeployWhisper.
- **EXT-08** Surface conflicts between external scanner findings and deterministic evidence instead of silently choosing one source.

### 30.11 History, analytics, and learning

- **HIS-01** Persist completed reports before showing final success.
- **HIS-02** Retain audit metadata with each report.
- **HIS-03** Users shall be able to search and filter historical reports.
- **HIS-04** Managers shall be able to review risk trends over time.
- **HIS-05** Capture reviewer feedback on report quality and correctness.
- **HIS-06** Support outcome capture after deployment for calibration.
- **HIS-07** Support benchmark and backtest workflows against historical incidents.
- **HIS-08** Scope reports, topology, outcomes, and feedback to a project/workspace.
- **HIS-09** Support false-positive and false-reassurance tracking.

### 30.12 Administration and customization

- **ADM-01** Admins shall configure narrative-provider settings through a DeployWhisper-owned provider adapter boundary.
- **ADM-02** Admins shall enable fully local-only operation.
- **ADM-03** Admins shall manage topology data and freshness status.
- **ADM-04** Admins shall manage incident ingestion and indexing.
- **ADM-05** Admins shall add or override custom Skills and organization-specific heuristics.
- **ADM-06** Admins shall manage thresholds and reporting defaults without changing core code.
- **ADM-07** Policy adapters shall consume report outputs without changing advisory-first core behavior.
- **ADM-08** Admins shall create and manage lightweight project/workspace records.
- **ADM-09** Admins shall configure optional enforcement adapter behavior per integration.
- **ADM-10** Admins shall configure external scanner ingestion per project.

### 30.13 Skills ecosystem

- **SKL-01** Expose a Skills registry API for listing, fetching, and installing community-contributed Skills.
- **SKL-02** Support versioned Skills with a formal manifest schema.
- **SKL-03** Run automated test harness on every Skill submission.
- **SKL-04** Provide Skills installer CLI.
- **SKL-05** Provide public Skills browser UI with search and filters.
- **SKL-06** Track skill analytics such as install counts, test pass rates, last update, and issue activity.
- **SKL-07** Provide contribution workflow with PR template, automated linting, and reviewer assignment.
- **SKL-08** Support trust levels: experimental, verified, core, deprecated.
- **SKL-09** Require deterministic scenarios for verified/core Skills.

### 30.14 Benchmarks

- **BEN-01** Maintain public benchmark corpus.
- **BEN-02** Provide benchmark runner.
- **BEN-03** Compare against baseline approaches where reproducible.
- **BEN-04** Publish quarterly benchmark results.
- **BEN-05** Track precision, recall, false reassurance, evidence coverage, latency, and regression stability.
- **BEN-06** Require expected evidence and expected verdict rationale for benchmark scenarios.
- **BEN-07** Support backtesting against incident records.
- **BEN-08** Benchmark reports shall include a public "scenarios we missed" section.
- **BEN-09** Material misses shall create linked GitHub issues unless the scenario is explicitly out of scope.
- **BEN-10** Benchmark reports shall distinguish product limitations from benchmark limitations.
- **BEN-11** Benchmark reports shall include Evidence Law violation count.

### 30.15 Open governance and CNCF readiness

- **GOV-01** Maintain public governance documentation.
- **GOV-02** Maintain maintainer ladder.
- **GOV-03** Maintain public roadmap.
- **GOV-04** Maintain contributor guide.
- **GOV-05** Maintain code of conduct.
- **GOV-06** Maintain security policy.
- **GOV-07** Maintain release process.
- **GOV-08** Maintain adopters list.
- **GOV-09** Use public RFCs for major design decisions.
- **GOV-10** Maintain CNCF readiness checklist.
- **GOV-11** Maintain `MAINTAINERS.md` mapping maintainers to major project areas.
- **GOV-12** Maintain `CODEOWNERS` for major directories.
- **GOV-13** Track maintainer coverage gaps.
- **GOV-14** Publicly document maintainer promotion and inactivity process.
- **GOV-15** Track contribution and community health metrics.

### 30.16 Documentation and user enablement

- **DOC-01** Maintain a public, versioned documentation tree or docs site in the repository.
- **DOC-02** Document every primary user journey: install, configure, analyze, review, integrate, troubleshoot, extend, and contribute.
- **DOC-03** Provide self-hosted installation guides for local CLI, Docker Compose, Kubernetes/Helm, and air-gapped environments.
- **DOC-04** Documentation shall not assume a DeployWhisper-hosted SaaS service, hosted API, hosted dashboard, hosted model, or hosted control plane.
- **DOC-05** Each epic shall include documentation tasks and documentation acceptance criteria.
- **DOC-06** User-facing stories shall not be considered done until required docs are updated.
- **DOC-07** Provide first-analysis and report-interpretation guides using safe sample artifacts.
- **DOC-08** Maintain integration guides for every supported workflow integration.
- **DOC-09** Maintain connector guides for every supported context connector.
- **DOC-10** Maintain API, report schema, evidence schema, webhook, CLI, and MCP references.
- **DOC-11** Maintain security, privacy, prompt-injection, secrets-handling, and local-first provider-boundary documentation.
- **DOC-12** Maintain operations docs for backup, restore, upgrade, scaling, observability, logs, database, workers, and troubleshooting.
- **DOC-13** Maintain Skills authoring, testing, publishing, private Skill, and Skill trust-level documentation.
- **DOC-14** Maintain benchmark documentation, including methodology, running benchmarks, adding scenarios, and reading results.
- **DOC-15** Maintain contributor documentation for development setup, architecture, tests, parser authoring, connector authoring, docs authoring, governance, and releases.
- **DOC-16** Provide docs CI for broken links, markdown formatting, generated references, and command/schema drift where practical.
- **DOC-17** Provide release notes and upgrade notes for every user-visible release.
- **DOC-18** Link from UI, CLI errors, API docs, and integration outputs to relevant documentation where practical.
- **DOC-19** Maintain CNCF readiness documentation covering governance, security, releases, adoption, community, and project scope.
- **DOC-20** Track documentation health metrics as part of project health.
- **DOC-21** Maintain `docs/concepts/evidence-law.md`.
- **DOC-22** Maintain `docs/concepts/project-model.md`.
- **DOC-23** Maintain `docs/incidents/day-zero-incident-memory.md` or equivalent.
- **DOC-24** Maintain `docs/ai-safety/reviewing-ai-generated-iac.md`.
- **DOC-25** Maintain `docs/comparisons/deploywhisper-alongside-security-tools.md`.
- **DOC-26** Maintain `docs/community/maintainer-areas.md`.
- **DOC-27** Maintain `docs/benchmarks/honest-failure-reporting.md`.

---

## 31. Non-Functional Requirements

### 31.1 Trust and security

- **NFR-SEC-01** Fully local operation must be possible.
- **NFR-SEC-02** Raw IaC must not be sent externally by default.
- **NFR-SEC-03** Provider credentials must not be persisted unsafely.
- **NFR-SEC-04** Secrets must be redacted from logs, prompts, reports, and telemetry by default.
- **NFR-SEC-05** Prompt-injection controls must be tested.
- **NFR-SEC-06** High/critical findings must satisfy the Evidence Law.
- **NFR-SEC-07** Project/RBAC boundaries must prevent cross-project data leakage.

### 31.2 Performance

- **NFR-PERF-01** Standard PR analysis should complete in under 15 seconds at p95 for common small-to-medium changes when using local deterministic analysis and already-available project context, excluding optional remote LLM latency and unavailable external connector timeouts. The benchmark corpus must define the reference dataset, runner profile, timeout policy, and measurement method.
- **NFR-PERF-02** Large artifact submissions should degrade gracefully by returning partial deterministic results, explicit skipped-scope details, and actionable timeout/context messages rather than failing silently.
- **NFR-PERF-03** Narrative generation failure or timeout must not block deterministic analysis results.
- **NFR-PERF-04** Benchmark latency should be tracked per release, including p50, p95, p99, timed-out analyses, and deterministic-vs-narrative latency split.
- **NFR-PERF-05** Connectors that cannot respond within their configured timeout must be marked stale/unavailable and must not block the core deterministic report.

### 31.3 Reliability

- **NFR-REL-01** Analysis failures must be explicit and actionable.
- **NFR-REL-02** Partial analysis must show what was included and excluded.
- **NFR-REL-03** Reports must persist before success is returned.
- **NFR-REL-04** Re-running the same deterministic inputs should produce stable deterministic findings.

### 31.4 Explainability and accessibility

- **NFR-XAI-01** Reports must be understandable to reviewers without requiring source-code reading.
- **NFR-XAI-02** Evidence must be inspectable.
- **NFR-XAI-03** Uncertainty must be visible.
- **NFR-XAI-04** Severity reasoning must be explainable.
- **NFR-XAI-05** UI and docs should follow accessibility best practices.

### 31.5 Operability and architecture

- **NFR-OPS-01** Support local, Docker Compose, Kubernetes/Helm, and air-gapped deployment paths.
- **NFR-OPS-02** Configuration must be file/env driven where practical.
- **NFR-OPS-03** PostgreSQL path should be available for shared/team installs.
- **NFR-OPS-04** SQLite may be supported for local/single-node installs.
- **NFR-OPS-05** Backup, restore, upgrade, and retention must be documented.
- **NFR-OPS-06** Observability metrics and logs must avoid secrets.

### 31.6 Documentation quality and self-service

- **NFR-DOC-01** Docs must be sufficient for self-service installation.
- **NFR-DOC-02** Docs must not assume SaaS onboarding.
- **NFR-DOC-03** Examples should be copy-pasteable where practical.
- **NFR-DOC-04** Docs should be versioned with releases.
- **NFR-DOC-05** Docs CI should catch broken links and obvious drift where practical.
- **NFR-DOC-06** Docs must include troubleshooting for common self-hosted failures.

### 31.7 Open-source maintainability

- **NFR-OSS-01** Governance, contribution, release, and security processes must be public.
- **NFR-OSS-02** Maintainer ownership must be public.
- **NFR-OSS-03** CODEOWNERS must route reviews for major areas.
- **NFR-OSS-04** RFC process must be used for major changes.
- **NFR-OSS-05** Benchmark and Skills contributions must have clear contribution paths.

---

## 32. V1 Delivery Milestones

All milestones in this section are part of DeployWhisper V1 scope. The milestone labels describe implementation order and maturity gates, not separate product versions. No item in this section should be interpreted as V2, paid, post-V1, or SaaS-only scope.

### 32.1 V1 Foundation - Open-source and execution foundation

Focus:

- Remove SaaS/open-core language.
- Publish governance files.
- Add `MAINTAINERS.md` and `CODEOWNERS`.
- Define project/workspace/RBAC model.
- Add requirements traceability matrix.
- Add baseline-vs-roadmap document.
- Add documentation information architecture.
- Add OpenSSF Scorecard.
- Add security policy.
- Add first demo and examples.

### 32.2 V1 Core - Trusted Advisory Core

Focus:

- Evidence Law enforcement.
- Deterministic analysis core.
- Mixed-artifact intake.
- Project-scoped reports.
- Evidence inspector.
- Confidence ledger.
- Why not lower / why not higher.
- Basic rollback guidance.
- Day-zero public risk patterns v1.
- CLI/API/web report baseline.
- Documentation for first analysis and report interpretation.

### 32.3 V1 Workflow proof - Workflow, docs, and benchmark proof

Focus:

- GitHub Action / GitHub PR comments.
- Rerun-on-commit.
- Report diff.
- Benchmark corpus v1.
- First honest failure benchmark report.
- 20+ seed Skills.
- First external scanner ingestion format.
- Existing-security-tools comparison documentation.
- Sample incident pack.
- Outcome capture v1.

### 32.4 V1 Context Expansion - Context moat

Focus:

- Terraform state connector.
- Kubernetes live-state connector.
- CODEOWNERS/service ownership mapping.
- Incident markdown/YAML/JSON importer.
- Service criticality mapping.
- Project-scoped context graph.
- Context TODOs.
- Backtest mode.
- Deployment outcome learning.
- External scanner contextualization expansion.

### 32.5 V1 Agent and Adapter Expansion - Agent-native and integration expansion

Focus:

- MCP server alpha or equivalent agent interface.
- Stable agent JSON output.
- AI-generated IaC benchmark scenarios.
- Prompt-injection test suite.
- GitLab/Jenkins/Atlantis/GitOps integrations.
- Optional enforcement adapters.
- 40+ verified Skills.
- AI safety documentation.

### 32.6 V1 GA and CNCF Readiness - CNCF and scale readiness

Focus:

- PostgreSQL production path.
- Async worker path.
- RBAC/SSO implementation or detailed design.
- Audit logs.
- Signed containers.
- SBOMs.
- Provenance/attestations.
- OpenSSF Best Practices Badge progress.
- Public adopter list.
- Community health metrics.
- CNCF Sandbox package.
- Complete documentation set.

---

## 33. Epics

| Epic | V1 milestone | Purpose | Requirement families |
|---|---|---|---|
| Epic 0: Open Governance, Traceability, and Maintainer Ownership | Phase 0 | Remove ambiguity, map owners, prepare community growth | GOV, OSS, traceability, NFR-OSS |
| Epic 1: Project, Workspace, and RBAC Foundation | Phase 0/1 | Define core boundaries before persistence and connectors harden | PRJ, ADM, NFR-SEC |
| Epic 2: Trusted Evidence Core and Evidence Law | Phase 1 | Make evidence model enforceable and deterministic | ING, EVD, RSK, NFR-SEC |
| Epic 3: Report and Review Experience | Phase 1 | Make reports defensible and fast to review | REV, RSK, XAI |
| Epic 4: Day-Zero Risk Patterns and Incident Memory | Phase 1/2 | Make signature incident memory useful from day one and smarter over time | INC, CTX, HIS |
| Epic 5: Workflow-Native Delivery | Phase 1.5 | Put reports in PRs, CI/CD, GitOps, and chat | WRK, REV |
| Epic 6: Benchmarks, Calibration, and Honest Failure Reporting | Phase 1.5/2 | Prove trust publicly and honestly | BEN, HIS, RSK |
| Epic 7: Context Moat | Phase 2 | Add topology, state, ownership, scanner outputs, and history | CTX, EXT, HIS |
| Epic 8: Existing Security Tool Integration | Phase 1.5/2 | Work alongside Snyk, Checkov, Wiz, OPA, Sentinel, and scanners | EXT, EVD, DOC |
| Epic 9: Skills Ecosystem | Phase 1.5/3 | Scale knowledge through community | SKL, COM, BEN |
| Epic 10: AI Infrastructure Safety and Agent-Native Review | Phase 3 | Make DeployWhisper callable by AI agents and safe for AI-generated IaC | AIA, WRK, NFR-SEC |
| Epic 11: Optional Enforcement Adapters | Phase 3 | Support explicit downstream enforcement | WRK, ADM, RSK |
| Epic 12: Security and Supply Chain Hardening | Phase 0-4 | Build trust as infrastructure software | NFR-SEC, NFR-OPS, GOV |
| Epic 13: Documentation and User Enablement | Phase 0-4 | Make the product self-service, installable, operable, extensible, and contributor-friendly | DOC, NFR-DOC, OSS, GOV |
| Epic 14: CNCF Readiness | Phase 4 | Prepare for foundation-scale community | GOV, OSS, adoption, DOC, NFR-DOC |

---

## 34. Release Exit Criteria

### 34.1 V1 Foundation exit

- PRD updated with full open-source and self-hosted-only commitment.
- Open-core, SaaS, hosted-control-plane, and paid-feature references removed.
- Project/workspace/RBAC model documented.
- `MAINTAINERS.md` exists.
- `CODEOWNERS` exists for major directories.
- Governance, contributing, security, roadmap, maintainer, support, release process, and adopters files exist.
- Requirements traceability matrix exists.
- Baseline-vs-roadmap document exists.
- OpenSSF Scorecard action enabled.
- Demo media and sample artifacts available.
- Documentation IA, quickstart, first-analysis guide, self-hosted install guide, Evidence Law guide, and docs contribution guide exist.

### 34.2 V1 Core exit

- Mixed-artifact analysis works reliably.
- Reports contain project scope, evidence, confidence, and uncertainty.
- Evidence Law enforced in code and tests.
- High/critical findings require deterministic evidence.
- Deterministic core works without narrative.
- Day-zero public risk pattern memory v1 exists.
- History and audit metadata persist correctly.
- Evidence inspector is usable.
- Report interpretation, Evidence Law, evidence model, project model, configuration, and troubleshooting docs are published.
- Senior reviewers consider high/critical findings credible in friendly-user workflows.

### 34.3 V1 Workflow proof exit

- GitHub workflow integration live and documented.
- PR summaries used in real reviews.
- Rerun-on-commit works.
- Report comparison works.
- Benchmark corpus v1 published.
- First benchmark results published with honest failure section.
- Skills marketplace live with 20+ seed Skills.
- First external Skill contribution merged.
- First external scanner ingestion path available or prototyped.
- Existing-security-tools comparison guide published.
- Sample incident pack available.
- GitHub integration, benchmark, Skills authoring, and day-zero incident docs are published and linked from relevant workflows.

### 34.4 V1 Context Expansion exit

- Terraform plan and state context improve blast-radius quality.
- Kubernetes live-state connector available as optional read-only context.
- Incident similarity is useful in practice.
- Deployment outcome capture exists.
- Context TODOs guide admins.
- Backtest mode exists.
- False reassurance and false-positive trends are measurable.
- External scanner contextualization produces useful deployment-risk context.
- Connector, incident memory, context graph, outcome-capture, and scanner-ingestion docs are published.

### 34.5 V1 Agent and Adapter Expansion exit

- MCP server alpha or equivalent agent interface available.
- Agent JSON output stable.
- AI-generated IaC benchmark scenarios available.
- Prompt-injection test suite running.
- GitLab/Jenkins/Atlantis or equivalent non-GitHub integration available.
- Policy adapter alpha available.
- 40+ verified Skills.
- Agent, MCP, GitLab/Jenkins/Atlantis/GitOps, integration, and policy-adapter documentation published.

### 34.6 V1 GA and CNCF Readiness exit

- PostgreSQL path available.
- Async worker path available.
- RBAC/SSO open-source implementation available or clearly designed.
- Release SBOM/signing/attestation process documented.
- Public adopter list has meaningful entries.
- OpenSSF Best Practices Badge progress visible.
- Maintainer coverage map shows multiple active maintainers or clear gaps.
- CNCF readiness checklist substantially complete.
- CNCF Sandbox application submitted when maintainers believe the project is ready.
- CNCF docs package is complete: governance, maintainership, security, releases, adoption, benchmarks, self-hosted architecture, and community health.

---

## 35. Risks and Mitigations

### Risk 1: Score credibility

**Risk:** Users do not trust risk verdicts.  
**Mitigation:** Evidence Law, benchmarks, honest failures, evidence inspector, confidence ledger, reviewer feedback, and deterministic scoring.

### Risk 2: Parser coverage edge cases

**Risk:** Unsupported syntax creates incorrect analysis.  
**Mitigation:** Partial analysis, unsupported artifact explanation, fixtures, parser-specific tests, community parser contributions.

### Risk 3: Weak evidence model

**Risk:** Reports sound convincing but are not defensible.  
**Mitigation:** Evidence Law validation, evidence schema, high/critical gates, benchmark evidence coverage.

### Risk 4: Context freshness

**Risk:** Stale or missing context causes false reassurance.  
**Mitigation:** Context freshness labels, `insufficient_context` verdict, context TODOs, confidence ledger.

### Risk 5: No incidents on day one

**Risk:** Incident Memory feels empty for new users.  
**Mitigation:** Built-in public risk pattern memory, sample incident pack, clear empty states, outcome capture.

### Risk 6: Workflow delay

**Risk:** Reports slow down PRs.  
**Mitigation:** Fast deterministic core, async narrative, PR summary, incremental reruns, latency benchmarks.

### Risk 7: Community bootstrap

**Risk:** One founder does too much.  
**Mitigation:** Public maintainership areas, CODEOWNERS, good-first-issues, contributor ladder, documentation, public roadmap.

### Risk 8: CNCF readiness gap

**Risk:** Project applies before governance/security/community are ready.  
**Mitigation:** CNCF readiness checklist, maintainer map, adopters list, security policy, release process, benchmark reports.

### Risk 9: AI-agent misuse

**Risk:** Users let agents treat DeployWhisper as auto-approval.  
**Mitigation:** Agent outputs advisory by default, no autonomous approval, prompt-injection tests, human-review documentation.

### Risk 10: Supply-chain trust

**Risk:** Users distrust release artifacts.  
**Mitigation:** OpenSSF Scorecard, Best Practices Badge, SBOM, signing, provenance, attestations, release process.

### Risk 11: Scope creep

**Risk:** Product becomes an observability platform, scanner, or CI/CD tool.  
**Mitigation:** Clear non-goals, complementary positioning, PRD scope checks, RFC process.

### Risk 12: Documentation debt

**Risk:** Self-hosted users cannot install or operate the product.  
**Mitigation:** Documentation epic, docs acceptance criteria, docs CI, troubleshooting guides, example-driven docs.

### Risk 13: Existing security tool confusion

**Risk:** Users think DeployWhisper is a cheaper Snyk/Checkov/Wiz.  
**Mitigation:** Comparison guide, scanner ingestion, complementary positioning, examples showing added deployment context.

### Risk 14: Project model refactor

**Risk:** Reports, incidents, connectors, and permissions are built before project scope is defined.  
**Mitigation:** Project/RBAC epic in Phase 0/1 and object scoping rule.

---

## 36. Open Questions and Decisions

### 36.1 Open-source model

**Decision:** Fully open-source, self-hosted-only, no SaaS, no hosted control plane, no open-core split, no paid enterprise-only features.

### 36.2 GitHub integration

**Decision:** GitHub-first workflow delivery is allowed, but core architecture must support GitLab, Jenkins, Atlantis, GitOps, and CLI/API workflows.

### 36.3 Minimum evidence standard

**Decision:** Evidence Law is mandatory. High/critical findings require deterministic evidence.

### 36.4 Enforcement

**Decision:** Core is advisory-first. Enforcement is optional through explicitly configured adapters.

### 36.5 Project model

**Decision:** Project/workspace/RBAC model must be designed before production persistence hardens.

### 36.6 Day-zero incident memory

**Decision:** Built-in public risk patterns must ship before or alongside organization incident memory so fresh installs are useful.

### 36.7 External scanner positioning

**Decision:** DeployWhisper complements existing security tools and may ingest their outputs as external evidence.

### 36.8 Benchmark honesty

**Decision:** Public benchmark reports must include misses, false positives, false reassurance, unsupported scenarios, and regressions.

### 36.9 Deployment history inputs

**Open:** Which deployment-history source should be prioritized first after GitHub metadata and report history?

### 36.10 Context connector priority

**Decision:** Terraform plan JSON, Terraform state, Kubernetes manifests/live-state, CODEOWNERS, incident import, and scanner ingestion are early priorities.

### 36.11 Benchmark threshold before enforcement recommendation

**Open:** What precision/false-reassurance threshold must be met before recommending soft-block or hard-block adapter examples?

### 36.12 CNCF timing

**Open:** Apply after governance, maintainers, security, docs, benchmarks, and adoption signals are credible.

### 36.13 License review

**Open:** Final license should be reviewed for CNCF compatibility and community expectations.

### 36.14 Documentation as part of Done

**Decision:** Documentation is required for feature completion.

### 36.15 Self-hosted-first documentation

**Decision:** All docs assume self-hosted operation first.

---

## 37. Roadmap Summary

### Now - Build open-source trust

- Rewrite PRD.
- Remove SaaS/open-core language.
- Add Evidence Law to README and website.
- Add project model.
- Add governance files.
- Add `MAINTAINERS.md` and `CODEOWNERS`.
- Add documentation IA.
- Add traceability matrix.

### Next - Build product trust

- Enforce Evidence Law in code.
- Publish report schema.
- Add evidence inspector.
- Add day-zero public risk patterns.
- Add confidence ledger.
- Add first sample incident pack.
- Publish first demo.

### Then - Build workflow adoption

- GitHub PR comments.
- Rerun-on-commit.
- Report diff.
- First external scanner ingestion.
- Existing-security-tools comparison docs.
- First benchmark corpus.
- First honest benchmark report.

### Then - Build context moat

- Terraform state connector.
- Kubernetes live-state connector.
- CODEOWNERS mapping.
- Incident import.
- Context graph.
- Deployment outcome capture.
- Backtest mode.

### Then - Build AI-agent safety

- Agent JSON.
- MCP server alpha.
- Prompt-injection tests.
- AI-generated IaC risk patterns.
- AI safety documentation.

### Later - Build CNCF-scale maturity

- Multiple maintainers.
- Public adopters.
- Release signing/SBOM/provenance.
- Best Practices Badge progress.
- Community health metrics.
- CNCF Sandbox application package.

---

## 38. What Not To Build Yet

Do not build yet:

- SaaS product.
- Hosted DeployWhisper control plane.
- Paid enterprise-only feature set.
- Auto-remediation.
- Auto-rollback.
- Auto-approval for AI agents.
- Broad observability platform.
- General cloud cost optimization product.
- Generic chat interface without evidence model.
- Hard enforcement by default.
- Raw IaC telemetry collection.
- Proprietary Skills required for core workflows.
- Closed benchmark corpus.

---

## 39. Companion Artifacts Required

Planning and traceability:

- `_bmad-output/planning-artifacts/prd.md`
- `_bmad-output/planning-artifacts/requirements-traceability.md`
- `_bmad-output/planning-artifacts/baseline-vs-roadmap.md`
- `_bmad-output/planning-artifacts/cncf-readiness-checklist.md`

Governance/community:

- `GOVERNANCE.md`
- `MAINTAINERS.md`
- `CODEOWNERS`
- `CONTRIBUTOR_LADDER.md`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`
- `SUPPORT.md`
- `ROADMAP.md`
- `RELEASE_PROCESS.md`
- `ADOPTERS.md`
- `RFC/`

Documentation:

- `docs/concepts/evidence-law.md`
- `docs/concepts/project-model.md`
- `docs/incidents/day-zero-incident-memory.md`
- `docs/ai-safety/reviewing-ai-generated-iac.md`
- `docs/comparisons/deploywhisper-alongside-security-tools.md`
- `docs/community/maintainer-areas.md`
- `docs/benchmarks/honest-failure-reporting.md`
- Full docs tree defined in Section 26.

Product examples:

- `examples/day-zero-incident-memory/`
- `examples/sample-incidents/`
- `examples/external-scanner-ingestion/`
- `examples/ai-generated-iac/`
- `examples/github-pr-comment/`
- `examples/self-hosted-install/`

Benchmarks:

- `benchmarks/`
- `benchmark-reports/YYYY-QX.md`
- `patterns/`
- `patterns/terraform/aws/public-rds-ingress.md`
- `patterns/kubernetes/service-selector-drift.md`
- `patterns/cicd/prod-approval-bypass.md`
- `patterns/ai-generated-iac/unsafe-defaults.md`

Security/supply chain:

- OpenSSF Scorecard workflow.
- CodeQL workflow.
- Dependency update workflow.
- SBOM workflow.
- Signing/provenance workflow.
- Security threat model.

---

## 40. Reference Links

These links are included to guide implementation and community readiness. They should be periodically reviewed because external requirements and best practices may evolve.

- CNCF Project Lifecycle and Process: https://contribute.cncf.io/projects/lifecycle/
- CNCF Governance guidance: https://contribute.cncf.io/community/governance/
- CNCF Maintainer Council Template: https://contribute.cncf.io/projects/best-practices/governance/templates/governance-maintainer/
- OpenSSF Scorecard: https://github.com/ossf/scorecard
- OpenSSF Best Practices Badge: https://openssf.org/projects/best-practices-badge/
- OpenSSF Best Practices Badge Program: https://www.bestpractices.dev/
- SLSA: https://slsa.dev/
- GitHub Artifact Attestations: https://docs.github.com/en/actions/concepts/security/artifact-attestations
- CHAOSS Starter Project Health Metrics: https://chaoss.community/kb/metrics-model-starter-project-health/
- Snyk IaC documentation: https://docs.snyk.io/scan-with-snyk/snyk-iac

---

## 41. Final Product Thesis

DeployWhisper should become the first choice in the market by out-trusting, not outspending, commercial platforms.

The product is:

> **The self-hosted, fully open-source safety layer for human and AI-generated infrastructure changes, governed by the Evidence Law: no high or critical finding without deterministic evidence.**

The path to leadership is:

1. Make the Evidence Law the headline.
2. Define project, workspace, and RBAC boundaries early.
3. Make day-zero incident memory useful through public risk patterns.
4. Keep organization incident memory as the long-term moat.
5. Work alongside existing security tools instead of replacing them.
6. Publish honest benchmarks, including misses and regressions.
7. Make AI-generated infrastructure review a co-equal product story.
8. Keep everything self-hosted and open-source.
9. Treat documentation as product.
10. Build public maintainer ownership and CNCF-ready governance.

DeployWhisper is not an AI DevOps app.

It is the open-source pre-deployment safety standard for infrastructure changes.
