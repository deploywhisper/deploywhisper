# DeployWhisper Infra Automation - Product Requirements Document

**Product:** DeployWhisper
**Feature name:** Infra Automation (key: `infra-automation`; left-navigation label: **Infra Automation**)
**Document type:** Feature PRD - addendum to the DeployWhisper PRD v1.0
**Version:** 0.2 Draft (supersedes `deploywhisper-automation-prd.md` v0.1)
**Date:** October 5, 2026
**PRD owner of record:** Pramod Kumar Sahoo (per `prd.md` v1.0) - confirm
**Proposed epic:** Epic 16 - Infra Automation (Epic 15 is the React UI migration)
**Baseline:** Application implemented through Story 12.2 (Provider Settings Administration) plus the Epic 15 React SPA cutover, as shown in the current UI (Dashboard, Skills, Incidents, History, Settings).
**Parent documents:** `_bmad-output/planning-artifacts/prd.md`, `architecture.md`, `epics.md`, `ux-design-specification.md`, `_bmad-output/project-context.md`, `docs/ui-migration-plan.md`, `AGENTS.md`
**License posture (unchanged):** Fully open-source (MIT). Self-hosted only. No SaaS, no open-core split, no paid or enterprise-only features. Every capability in this document ships in the public project.

**What changed from v0.1:**

1. Renamed to **Infra Automation** (`infra-automation`) everywhere: route, API, package, docs, flags, requirement IDs (`IAU-*`).
2. Added a **market and best-practice analysis** and derived requirements from it (Sections 2-3).
3. Added **IaC and package orchestration** as a first-class model: units, packages, an infra map, a dependency graph, stage plans, target locks, and drift (Section 7).
4. Added an **AI orchestration layer** with strict roles, a structured-IR approach, guardrail floors, and evaluation (Section 8).
5. Added an **implementation guide after Story 12.2** with the exact order of work, backend and frontend tasks per story, and **adjusted wording for the remaining stories** 12.3-12.8, Epic 13, and Epic 14 (Section 17).

---

## 0. How to Use This Document

Read Section 0.1 first; those decisions shape everything else. Section 17 is the working plan: it tells you what to do next after Story 12.2, in what order, and what to build on the backend and the frontend for each story.

### 0.1 Decisions Required Before Build

| # | Decision | Recommendation | Why | Blocks |
|---|----------|----------------|-----|--------|
| D1 | **Execution posture.** Your PRD says DeployWhisper is *not* a Terraform runner, CI/CD system, or auto-remediation engine (PRD 4.4), the core is advisory-first (PRD 19, ADR-06), and agents may never autonomously approve, deploy, or remediate (AIA-09). | Ship **Tier 0 (observe/collect)** and **Tier 1 (handoff to the user's own pipeline)** first. Defer **Tier 2 (execute)** behind a separate RFC and a PRD 4.4 amendment (Section 4). | Preserves product identity while delivering most of the user value. | Story 16.0 |
| D2 | **Runner model.** Where do `terraform plan`, `ansible-playbook --check`, `kubectl diff` run? | An **outbound-only runner agent** (`deploywhisper runner start`) in the same repo that users deploy where tools and credentials already live. Do not bundle IaC tools in the main image; do not mount `docker.sock`. **Do not publish a runner image that bundles Terraform** (it is distributed under a source-available license; verify current terms). Ship reference Dockerfiles that let the operator install their own tools, and prefer documenting OpenTofu. | Image size, blast radius, local-first boundary, and licensing safety for an MIT project. | Stories 16.12, 16.13 |
| D3 | **Workflow format and AI output format.** | Declarative **YAML + JSON Schema**, closed step registry, substitution-only templating. AI never writes YAML directly: it emits a **schema-validated intermediate representation (IR)** that a deterministic renderer turns into YAML. | Safer, testable, and consistent with ADR-10 (non-executable extensions). The market is converging on structured IR rather than raw generated code. | Stories 16.1, 16.16 |
| D4 | **Identity for approvals.** README lists production-grade authn/authz for shared deployments as still evolving. | If multi-user identity is not available at Phase A, run approvals in **single-operator mode**: labeled "acknowledgement", separation-of-duties disabled and visibly so. Prefer pulling a minimal local-user/OIDC story forward. | An approval UI must not imply controls it cannot enforce. | Story 16.7 |
| D5 | **Prerequisite story.** Story 12.3 (Connector Credential Handling and Redaction Audit) is open. | Complete 12.3 **with the expanded acceptance criteria in Section 17.3**, before Stories 16.9-16.13. | Infra Automation adds runner tokens, webhook secrets, handoff tokens, and AI prompt data flows. | Stories 16.9-16.13 |
| D6 | **New dependencies.** Architecture guardrail: none without justification. | None in Phase A. ADR candidates: CodeMirror 6 (YAML editor, optional; fallback `<textarea>`), a cron parser (Phase B), a graph rendering library (Phase B; fallback is a small hand-rolled layered SVG). | Respects the guardrail. | 16.4, 16.21, 16.26 |
| D7 | **Naming and placement.** | Nav label **Infra Automation**, route `/infra-automation`, API `/api/v1/infra-automation/*`, Python package `infra_automation/`, docs `docs/infra-automation/`, flag `DEPLOYWHISPER_INFRA_AUTOMATION_ENABLED`. Placed after **Incidents** and before **History**, with a pending-approvals badge. | Matches the existing badge pattern in the screenshot. | Story 16.4 |
| D8 | **Default state.** | Disabled until an admin enables it. Nav item always visible; when disabled it shows an enablement page. | Safe default; discoverable. | Story 16.2 |
| D9 | **AI posture.** | AI may **draft, plan, map, explain, and diagnose**. AI may never approve, publish, execute, create findings, weaken a guardrail, add a package, or see secrets. The feature must be fully usable with AI turned off, and must work with local-only providers. | Matches AGENTS.md: prefer deterministic, evidence-backed logic over "AI magic" in risk-sensitive paths. | Story 16.16 |
| D10 | **Package registry lookups.** | Default **off**. Package governance runs on local evidence (lockfiles, charts, requirements, image refs) and an admin-managed allow-list. Optional registry lookups are a user-owned connector, labeled external evidence. | Local-first and air-gapped support. | Story 16.20 |

### 0.2 Baseline Assumptions (verify against code before sprint planning)

| # | Assumption | How to verify |
|---|-----------|---------------|
| A1 | Epics 0-11, Stories 12.1-12.2, and Epic 15 are complete (per owner statement). | `sprint-status.yaml`, `CHANGELOG.md` |
| A2 | Policy adapter contract (Epic 11), GitHub integration (Epic 5), agent interface (Epic 10), scanner import (Epic 8), RBAC role model (Story 1.5), Skills loading (Epic 9) are reusable. | Inspect `integrations/`, `api/routes/`, `services/`, `llm/`. |
| A3 | Authentication is lightweight; bearer-token protection exists for some APIs. | Inspect `api/` dependencies, `config.py`. |
| A4 | No async worker process exists; ADR-14 treats workers as a scale path. The engine runs in the FastAPI process. | `docker-compose.yml`, `app.py`. |
| A5 | An HTTP client library is already in `requirements.txt`. | `requirements.txt` |
| A6 | Analysis list rows expose `trigger_ref` and `pr_ref` aliases (README). | `GET /api/v1/analyses` schema |
| A7 | The provider boundary in `llm/` supports JSON/structured output and exposes capability metadata (README mentions structured-output and local-only flags). | `llm/` adapters, provider settings (Story 12.2) |
| A8 | `AGENTS.md` and `_bmad-output/project-context.md` are current. The publicly indexed `AGENTS.md` snapshot still lists a NiceGUI `ui/` directory from before the React cutover, so re-read the current file. | Open both files before Story 16.0. |

---

## 1. Executive Summary

DeployWhisper answers one question before release: **is this infrastructure change safe to ship, and what is the evidence?** Today a user must produce artifacts (plan JSON, manifests, diffs), upload them, read the briefing, then carry the decision into some other system by hand. Real estates are also not one artifact: they are many Terraform stacks, Helm releases, Ansible playbooks, Kubernetes overlays, and the **packages** they depend on (providers, modules, charts, roles, images), with ordering constraints between them.

**Infra Automation** is the evidence-gated orchestration layer for that estate. It **discovers** IaC units and packages, **plans** a safe order of work, **collects** read-only plan/diff artifacts on user-controlled runners, **analyzes** everything through the existing shared core, **gates** on the verdict, asks a **human** to approve against pinned evidence, and **hands off** to the user's own delivery system. AI assists at the edges (drafting workflows, mapping the estate, proposing stage plans, explaining failures) but is never the decision-maker.

```
Discover units & packages -> Plan stages -> Collect (runner, read-only) -> Analyze (shared core) -> Gate -> Approve (pinned evidence) -> Handoff
        (deterministic first,      (graph + waves,   (plan, check, diff,       (Evidence Law)       (route only)  (human)              (user's pipeline)
         AI refines)                AI proposes)      helm template)
```

What makes this different from generic orchestrators and from "agentic IaC" products:

1. **Evidence-gated approval.** Approvers see the DeployWhisper briefing inside the approval card, pinned to the exact artifact digests analyzed.
2. **One analysis core.** Orchestration can route on a verdict but cannot change a finding or severity.
3. **Package-aware.** Lockfiles, chart dependencies, role/collection requirements, and image references become deterministic evidence; AI cannot introduce packages.
4. **AI as drafter, not actor.** AI emits validated structured plans; guardrails are enforced in code, not prompts; the feature works without AI and with local models.
5. **Advisory-first and open source.** Collection is read-only, handoff always needs an approval ancestor, execution is a separate RFC-gated tier, and nothing is paywalled.
6. **Local-first.** Runners execute where infrastructure and credentials live; only redacted structured results return.

### 1.1 Problem

- Pre-deployment checks are manual and inconsistent across tools and teams.
- Multi-stack changes (network -> cluster -> platform -> apps) have ordering and dependency risk that no single scanner sees.
- Dependency/package changes (a module bump, an unpinned `latest` image, a new Ansible collection) slip through because they look small.
- Approvals happen in chat, disconnected from evidence.
- AI-assisted workflows add speed and new failure modes: hallucinated steps, hallucinated packages, prompt injection through repo contents, and over-trust.

### 1.2 Outcome

A platform team can stand up a governed, AI-assisted pre-flight for a multi-unit estate in under 30 minutes (under 15 for a single stack), trigger it from the UI, webhook, schedule, or PR event, and obtain an auditable record of what was discovered, planned, collected, concluded, approved, and handed off.

---

## 2. Market and Best-Practice Analysis

### 2.1 What the market shows

| Source | What it shows | Implication for DeployWhisper |
|--------|---------------|-------------------------------|
| **Terraform Stacks (HashiCorp)** | Splitting infrastructure across many configurations leaves dependency stitching to the user; Stacks coordinates interdependent configurations, supports deferred changes, and offers plan-condition orchestration rules, including auto-approve when a plan meets criteria (for example no removals). | Cross-unit ordering is a recognized pain. Adopt dependency-aware stage plans. **Reject auto-approve for handoff** (advisory-first). |
| **Pulumi Neo** | An AI agent built on an IaC substrate, integrated through an MCP server, with adjustable autonomy from human-approved steps to fully automated; dev may allow autonomous operation while prod requires approval. | Adopt an **autonomy dial per environment**, but cap it below unattended execution (Section 4.3). |
| **Spacelift (Intent, MCP, guardrail guidance)** | Intent authors IaC through a structured intermediate representation instead of raw LLM output; guidance says agents should not install new packages or modules on their own (allow-list or human approval), should not push or merge to main without humans, and production needs approval gates. | Adopt **structured IR for AI output** and **package allow-listing**. |
| **Governance comparisons (Qovery)** | Four controls matter when agents touch infrastructure: complete audit trail, policy evaluated before apply, budget guardrails, human approval on irreversible changes. Prompt instructions are mitigations, not guardrails. Require approval above a blast-radius threshold (resource count, cost delta, environment tier); use short-lived credentials per run and replayable audit. | Enforce rules in **validators and code**; add **blast-radius-threshold approvals**; require **short-lived runner credentials**; record AI interactions in audit. |
| **HashiCorp Terraform MCP server** | Gives AI clients live Terraform Registry access for provider docs, modules, and policies, plus optional HCP Terraform tools. | Optional, **opt-in, read-only registry context** via a user-owned connector; results are external evidence. Not a default (local-first). |
| **Kestra 2.0** | Copilot with Edit / Plan / Ask modes behind a confirmation gate, log-reading diagnosis, agent guardrails, metrics on agent/tool calls, and flows exposed as MCP tools with origin-tagged executions. | Adopt the **Draft / Explain / Review** panel pattern and **agent-origin tagging**, with stricter publish and approval rules. |
| **Slopsquatting research** | AI tools invent package names; most fabricated names are wholly invented rather than typos; mitigations are lockfiles, pinning, and human review of first-seen packages. | Treat packages as a first-class risk surface; **AI cannot add packages**; first-seen packages require human review. |
| **Spacelift 2026 Infrastructure Automation Report (vendor survey)** | Reports that most surveyed organizations have had at least one AI-caused infrastructure incident and most plan to adopt agentic AI. | Directional only (vendor-reported). Supports the need for guardrails. |

### 2.2 Insights

| # | Insight |
|---|---------|
| I1 | The hard problem is **orchestration across many units**, not running one plan. State isolation pushes dependency management onto users. |
| I2 | The industry is converging on an **autonomy dial**. DeployWhisper's differentiator is to stay **evidence-gated and advisory** at the top of the dial. |
| I3 | Guardrails must live in **code paths** (validators, policy floors, authorization), not in prompts. |
| I4 | **Structured IR beats free-form generation** for AI output: it is validatable, diffable, and renderable deterministically. |
| I5 | **Packages are a first-class risk surface**, amplified by AI. |
| I6 | Most competitors focus on **executing** changes. The open gap is **self-hosted, open-source, evidence-gated decisioning across tools**. |
| I7 | Plan/apply separation, drift detection, environment promotion, target locking, change windows, and ephemeral credentials are table stakes for serious IaC operations. |

### 2.3 Positioning

> **Infra Automation is the open-source, self-hosted, evidence-gated orchestration layer for IaC and packages. It discovers, plans, verifies, gates, and hands off. It does not apply.**

### 2.4 Kestra comparison (what to adopt and reject)

| Mechanism | Decision | Rationale |
|-----------|----------|-----------|
| Declarative YAML flows | **Adopt** with closed step registry and substitution-only templating | Reviewable, Git-friendly, ADR-10 compliant. |
| Wrap existing tools unchanged | **Adopt** via runner-side command catalog | Users keep Terraform/OpenTofu/Ansible/kubectl. |
| Remote workers, outbound connection, tag routing, fail-fast fallback | **Adopt** | Fits local-first and air-gapped installs. |
| Pause with typed resume inputs; user/group approvals | **Adopt and extend** with evidence pinning and embedded briefing | Core differentiator; available to everyone. |
| Draft vs published revisions | **Adopt** | Drafts never execute. |
| Copilot panel with confirmation gate and log diagnosis | **Adopt the pattern**, constrain to IR + validator, no auto-apply | AGENTS.md prefers deterministic logic. |
| 2,100-plugin catalog, general data orchestration | **Reject** | Out of scope. |
| Free-form shell and unisolated process runner | **Reject** | Command injection and credential exposure. |
| Edition-gated features | **Reject** | PRD 2.1. |

### 2.5 Alternatives considered

| Option | Description | Verdict |
|--------|-------------|---------|
| **A. Native lightweight engine (this PRD)** | DB-backed state machine in the FastAPI process, outbound runners, evidence-gated approvals, AI at the edges. | **Recommended.** |
| **B. Integration-only** | No engine; publish recipes so Kestra, Argo, Jenkins, GitHub Actions call DeployWhisper and use the verdict. | **Ship as documentation as well** (Story 16.17). Cheap and complementary. |
| **C. Embed a third-party engine** | Run Kestra or Temporal alongside DeployWhisper. | **Rejected.** Breaks single-container baseline, adds heavy operations, imports edition questions into an MIT-only project. |

---

## 3. Best-Practice Requirements (derived)

These are the "best requirements" drawn from the analysis. Each maps to detailed requirements in Section 9.

| ID | Best practice | Realized by |
|----|---------------|-------------|
| BR-01 | Separate **plan from apply**: collection is plan/check/diff only; apply happens in the user's pipeline. | IAU-STP-01..05, Tier rules |
| BR-02 | Orchestrate **across IaC units** with an explicit dependency graph; deterministic edges first, AI suggestions second and labeled. | IAU-ORC-* |
| BR-03 | **Evidence pinning**: approvals bound to report and artifact digests; stale evidence invalidates. | IAU-APR-05..07 |
| BR-04 | **Autonomy dial per environment**, capped: suggest -> assist -> supervise; never unattended in v1. | Section 4.3, IAU-GRD-* |
| BR-05 | **Policy floors enforced in code** at publish and run time, not in prompts; AI cannot edit them. | IAU-GRD-* |
| BR-06 | **Blast-radius-threshold approvals**: approval required above thresholds (severity, resource count, environment tier). | IAU-APR-08, IAU-GRD-04 |
| BR-07 | **Package governance**: pin, lock, digest, allow-list, flag first-seen, AI cannot add packages. | IAU-PKG-* |
| BR-08 | **Short-lived credentials per run** on the runner (workload identity / OIDC where available); no static cloud keys on the server. | IAU-RNR-06, IAU-RNR-13 |
| BR-09 | **Replayable audit** including AI interactions. | IAU-AUD-*, IAU-AI-12 |
| BR-10 | **Target locks and change windows** to prevent conflicting concurrent handoffs and out-of-window changes. | IAU-ORC-10..12 |
| BR-11 | **Drift detection** as a first-class scheduled workflow, read-only. | IAU-TRG-06, templates |
| BR-12 | **Environment promotion** (dev -> stage -> prod) with a diff and a separate approval per environment. | IAU-ORC-08 |
| BR-13 | **Structured IR for AI** with validator-and-repair loop and deterministic rendering. | IAU-AI-02..05 |
| BR-14 | **Deterministic fallback** for every AI feature; AI optional; local-only supported. | IAU-AI-09, IAU-AI-10 |
| BR-15 | **Untrusted inputs everywhere**: repo contents, logs, registry text, and plan output are data, not instructions. | IAU-AI-08, IAU-AEV-08 |
| BR-16 | **Honest uncertainty**: plan age, check-mode gaps, plan-vs-apply drift, AI-inferred edges are visible, not hidden. | IAU-AEV-05, IAU-ORC-05 |
| BR-17 | **Measure AI**: acceptance, validity, unsafe-suggestion rate (must be zero), latency; publish misses. | IAU-AI-13, Story 16.30 |

---

## 4. Strategic Fit and Posture

### 4.1 Constraints this feature must respect

| Source | Constraint |
|--------|-----------|
| PRD 4.4 | DeployWhisper is not a Terraform runner, CI/CD system, auto-remediation engine, or auto-approval engine. |
| PRD 19, ADR-06 | Core is advisory. Enforcement only through explicitly configured adapters. |
| PRD 19.3 | Hard blocks require Evidence Law-satisfying deterministic findings; LLM-only findings never block. |
| AIA-09 | Agents may not autonomously approve, deploy, or remediate production changes. |
| ADR-03 | One shared analysis core. |
| ADR-10 | Extensions are non-executable guidance. |
| ADR-14 | Workers and PostgreSQL are scale paths, not baseline dependencies. |
| PRD 2.1 | No open-core, no paid-only features, no hosted control plane. |
| Architecture 23 | No new dependencies without justification; raw artifacts not sent externally by default. |
| AGENTS.md | Prefer deterministic logic and evidence-backed reasoning over "AI magic" in risk-sensitive code paths; never persist secrets; use synthetic fixtures. |

### 4.2 Capability tiers

| Tier | Name | What it may do | Mutates infrastructure? | Default | Phase |
|------|------|----------------|-------------------------|---------|-------|
| **0** | **Observe** | Discover units and packages, run read-only collection (`terraform plan` + `show -json`, `ansible-playbook --check --diff`, `kubectl diff`, `helm template`, `git diff`), import scanner results, run the analysis core, notify. | No | On when Infra Automation is enabled | A, B |
| **1** | **Handoff** | After a mandatory approval, trigger the user's own system: GitHub Actions `workflow_dispatch`, a webhook, a CI job, an ITSM callback. | Not by DeployWhisper | Off per workflow until configured | A (webhook, GitHub), B (others) |
| **2** | **Execute** | Run mutating commands through a runner. | **Yes** | **Disabled; no UI to enable until an RFC is accepted** | C - gated |

**Tier 2 conditions (recorded now so the design leaves room):** instance flag default off; per-project allow; runner tag `exec` plus a runner-side allow-list; a published revision approved by a *different* Project Admin; Evidence Law satisfied at run time; fresh (non-stale) plan; approval at run time; no unattended trigger; break-glass only with reason and audit; rollback guidance linked. Requires a PRD 4.4 amendment and a new ADR before any code.

### 4.3 Autonomy levels (the "dial")

| Level | Name | AI role | Human role | Allowed triggers | Max in v1 |
|-------|------|---------|-----------|------------------|-----------|
| **L0** | Suggest | Proposes only (drafts, explanations) | Does everything | Manual | Yes |
| **L1** | Assisted | Drafts workflows/plans; human reviews and publishes | Reviews diffs, publishes, runs, approves | Manual, webhook | Yes |
| **L2** | Supervised | Same as L1; runs auto-start read-only collection and analysis on schedule/events | Approves every handoff | Manual, webhook, schedule, event | Yes (Phase B) |
| **L3** | Unattended handoff | Not applicable | Pre-authorized low-risk non-prod handoff | - | **No.** Requires RFC (Phase C) |

Defaults: production workspaces are capped at L2; the project can lower, never raise, a workspace's cap above the instance cap.

### 4.4 Hard rules (apply to every tier and every AI feature)

1. **A workflow can route on a verdict; it can never change a finding or severity.**
2. **Any `handoff.*` or `execute.*` step must have an `approval` step among its ancestors.** Enforced by the validator at save, publish, and run time.
3. **Agents and automation tokens may request runs of `agent_callable` workflows; they may not approve or publish.**
4. **Approval never auto-approves on expiry.** Expiry fails the run.
5. **No inline secrets** in workflow definitions. Secrets are references resolved on the runner.
6. **AI output is a proposal.** Nothing AI-generated is published, run, approved, or applied without an explicit human action, and AI-assisted revisions are labeled.
7. **AI cannot weaken a guardrail floor** (Section 8.6) and cannot add a package that is not already allow-listed.
8. **Everything works with AI off.**

---

## 5. Goals and Non-Goals

### 5.1 Goals

| ID | Goal |
|----|------|
| G1 | A user can define, validate, publish, and run a governed pre-flight workflow from UI, API, or CLI. |
| G2 | The approval step presents the DeployWhisper briefing and is pinned to analyzed evidence. |
| G3 | Read-only collection runs on user-controlled runners; credentials never reach the server. |
| G4 | Every run is auditable: trigger, redacted inputs, artifacts with digests, report, decision, handoff, and any AI involvement. |
| G5 | **(Phase B)** The system discovers IaC units and packages, builds a dependency graph, and produces a stage plan that is validated against deterministic edges. |
| G6 | **(Phase B)** Package changes become deterministic evidence; AI cannot introduce packages. |
| G7 | AI assists authoring, mapping, planning, and diagnosis with structured, validated, auditable outputs. |
| G8 | Fully open source, self-hosted, documented for self-service, and compatible with the current stack. |

### 5.2 Non-Goals (explicit)

- A general-purpose data/ETL orchestrator or a plugin marketplace of executable integrations.
- **AI authoring of IaC code.** DeployWhisper reviews AI-generated IaC (Epic 10); it does not generate Terraform/Ansible/Kubernetes code in this feature.
- Executing mutating commands in Phase A or B (Tier 2 deferred).
- Auto-approval, auto-merge, auto-deploy, auto-remediation, by humans' proxy or agents.
- Replacing GitHub Actions, Jenkins, Atlantis, Argo CD, Flux, Rundeck, or Kestra.
- A hosted control plane, telemetry, or any DeployWhisper-operated service.
- Adding Infra Automation widgets to the Dashboard. The Dashboard information budget (Part B0) is unchanged.
- Cost estimation as a native feature. Cost deltas may arrive only as imported external evidence (Phase B, optional).

---

## 6. Users and Jobs To Be Done

### 6.1 Personas (mapped to existing roles in PRD 13.5)

| Persona | Existing role | Primary needs |
|---------|---------------|---------------|
| Platform engineer | Maintainer | Define workflows, map the estate, run pre-flights, review stage plans. |
| SRE approver / Service Owner | Reviewer, Service Owner | Review the briefing, approve or reject a handoff with a recorded reason. |
| Security reviewer | Security Reviewer | Require scanner import and package checks; review audit and AI involvement. |
| Platform admin | Project Admin / Instance Admin | Enable the feature, enroll runners, set allow-lists, quotas, retention, guardrail floors. |
| ITSM / CI system | Automation Actor | Trigger a workflow by webhook; receive callbacks. |
| AI coding agent | Automation Actor (request/read only) | Propose or request pre-flights; never approve or publish. |
| Viewer | Viewer | Read-only visibility. |

### 6.2 Jobs To Be Done

- When a production change spans several stacks and packages, I want the right order and checks computed for me so that nothing is applied before its dependencies are verified.
- When I describe a process in plain language, I want a valid draft workflow that I can review, so that I do not hand-write YAML for every case.
- When I am asked to approve, I want to see the evidence and exactly what happens next so that my approval is informed.
- When a run fails, I want a plain-language explanation and safe next steps so that I recover quickly without guessing.
- When a module or chart version changes, I want it surfaced as evidence so that dependency risk is not hidden in a "small" diff.
- When my team uses AI agents, I want them to request reviews but never approve or ship.
- When I run in a restricted network, I want collection and AI to work locally so that credentials and artifacts never leave it.

---

## 7. IaC and Package Orchestration Model

This section defines **what is orchestrated** and **how ordering is decided** for all supported infrastructure code and packages.

### 7.1 Orchestrated unit types

| Unit type | Typical identity (`unit_id`) | Collected by | Parsed by (existing) | Notes |
|-----------|------------------------------|--------------|----------------------|-------|
| Terraform / OpenTofu stack | `terraform:<path>[:<workspace>]` | `collect.terraform_plan` | Terraform parser (plan JSON) | OpenTofu documented as the preferred open-source binary. |
| Terragrunt unit | `terragrunt:<path>` | Phase B (`collect.terragrunt_plan`) | Terraform parser | Dependency blocks give deterministic edges. |
| CloudFormation stack | `cloudformation:<stack>` | Phase B (change set describe, read-only) | CloudFormation parser | |
| Ansible playbook | `ansible:<playbook>[:<inventory>]` | `collect.ansible_check` | Ansible parser | Check-mode coverage gaps become confidence factors. |
| Kubernetes manifests | `k8s:<path>` | `collect.kubectl_diff` | Kubernetes parser | |
| Helm release | `helm:<release>[:<namespace>]` | `collect.helm_template` | Kubernetes/Helm parsing | Chart dependencies tracked as packages. |
| Kustomize overlay | `kustomize:<path>` | `collect.kustomize_build` (Phase B) | Kubernetes parser | |
| CI/CD pipeline definition | `pipeline:<path>` | `collect.git_diff` | Jenkins/Actions parsers | Analyzed as change input; not orchestrated as a stage. |

### 7.2 Package model

"Packages" are versioned dependency units consumed by infrastructure code.

| Ecosystem | Package kinds | Local evidence sources (deterministic) |
|-----------|---------------|----------------------------------------|
| Terraform / OpenTofu | Providers, modules | `.terraform.lock.hcl` (versions and hashes); module `source` and `version` from plan JSON `configuration.module_calls` or HCL scan |
| Helm | Charts, subcharts | `Chart.yaml` dependencies, `Chart.lock` digests, `values.yaml` image references |
| Ansible | Roles, collections | `requirements.yml`, `galaxy.yml`, collection versions |
| Kubernetes / Kustomize | Container images, remote bases | `image:` references (tag vs digest, `latest`), remote base refs |

**Package reference (conceptual schema):**

```
ecosystem: terraform | helm | ansible | oci | kustomize
kind: provider | module | chart | role | collection | image | base
name: string
source: registry URL / repo / namespace
constraint: string | null          # declared constraint
resolved_version: string | null    # from lockfile or render
digest_or_hash: string | null
pinned: boolean                    # exact version or digest
first_seen_in_project: boolean     # not in the project's package ledger
allowlist_status: allowed | not_allowed | not_configured
origin: deterministic | external | ai_suggested
unit_refs: [unit_id]
```

**Package ledger:** a per-project, per-workspace record of packages seen in previously analyzed bundles. It is what lets the system say "first seen", "version changed", or "hash changed without a version change" deterministically.

**Deterministic package signals (candidate public risk patterns, scored by the existing risk engine and Evidence Law):**

| Signal | Example |
|--------|---------|
| Unpinned or floating | Module with no `version`; image tag `latest`; Git source on a branch |
| Major version bump | Provider or chart major change |
| Hash/digest drift | Lockfile hash changed with unchanged version |
| First seen | Package absent from the project ledger |
| Non-allow-listed source | Module or chart from an unlisted registry or namespace |
| Pin removed | Digest pin replaced with a tag |

Severity is decided by the existing risk engine; high/critical requires deterministic evidence (these signals qualify).

### 7.3 Infra map

A human-reviewed file that tells the system what units exist and how they relate. Proposed location in the user's repository: `.deploywhisper/infra-map.yaml` (also storable in the project record).

```yaml
schema: deploywhisper.infra-map/v1
project: payments
layers: [network, data, platform, apps]        # ordering convention, earliest first
units:
  - id: terraform:infra/network
    layer: network
    workspaces: [dev, stage, prod]
    runner_tags: [terraform, vpc]
    owner: "@payments-platform"                # may be derived from CODEOWNERS
  - id: terraform:infra/eks
    layer: platform
    depends_on: [terraform:infra/network]
  - id: helm:platform/ingress
    layer: platform
    depends_on: [terraform:infra/eks]
  - id: kustomize:apps/payments
    layer: apps
    depends_on: [helm:platform/ingress]
packages:
  allowlist:
    terraform: ["registry.terraform.io/hashicorp/*", "registry.terraform.io/terraform-aws-modules/*"]
    helm: ["oci://registry.example.internal/charts/*"]
    oci: ["registry.example.internal/*"]
```

Unit discovery is **deterministic first** (file patterns: `*.tf` with a lockfile, `Chart.yaml`, `kustomization.yaml`, playbooks with `hosts:`, `Jenkinsfile`, CloudFormation templates). AI may propose names, layers, and groupings; a human accepts or edits (Section 8).

### 7.4 Dependency graph and edge provenance

The orchestration graph has units and packages as nodes. Every edge carries a **basis** that determines whether it can enforce ordering.

| Basis | Source | Enforces order? |
|-------|--------|-----------------|
| `declared` | `depends_on` in the infra map | Yes |
| `layer_rule` | Layer ordering convention (`network` before `platform`) | Yes |
| `remote_state` | `terraform_remote_state` or equivalent reference parsed from plan JSON / HCL | Yes (deterministic) |
| `terragrunt_dependency` | Terragrunt `dependency` blocks | Yes |
| `package_use` | Unit consumes a package | Informational (blast radius and ledger) |
| `topology` | Existing project service topology (Epic 7) | Informational (blast radius) |
| `ai_inferred` | AI Planner suggestion | **No**, until a human accepts it (becomes `declared`) |

Edge confidence and basis are displayed in the UI and persisted in the plan snapshot.

### 7.5 Change set and stage plan

- **Change set:** the units and packages affected by a trigger, derived from the Git diff (changed paths mapped to units via the infra map), a PR event, or explicit selection.
- **Stage plan:** a topologically ordered list of **stages (waves)**. Units with no mutual dependency share a wave. A plan is valid only if it respects every enforcing edge and covers exactly the change set (no omitted unit, no unlisted unit).
- **Plan snapshot:** the resolved plan (units, edges with basis, waves, rationale, digest) is stored with the run and pinned by approvals.
- **Per-stage pipeline:** each stage runs *collect -> analyze -> gate -> approval -> handoff* (the approval may be waived only for stages with no handoff, such as read-only audits).
- **Bundle analysis plus stage analysis:** the cross-tool interaction analysis already supports multi-artifact bundles. Phase B runs one bundle analysis for cross-unit interactions and per-stage analyses for stage approvals.

### 7.6 Target locks, change windows, and promotion

| Concept | Behavior | Phase |
|---------|----------|-------|
| **Target lock** | `lock_key = <unit_id>:<workspace>`. Held from run start until handoff completion, cancellation, or expiry. Prevents two concurrent pre-flights from handing off against the same target. Admin can break a lock (audited). | B |
| **Change window** | Per workspace allowed windows and freeze periods. Approvals outside a window require an explicit, audited exception reason. Window checks are deterministic. | B |
| **Promotion** | A workflow can promote the same change across `dev -> stage -> prod`. Each environment has its own collect, analyze, gate, and approval. A promotion diff compares reports and package versions between environments. | B |
| **Drift detection** | Scheduled read-only plan/check (`terraform plan -detailed-exitcode`, `ansible --check`) producing a drift report and optional notification. No handoff. | B |

### 7.7 Honest uncertainty in orchestration

- A plan is a prediction; it can differ at apply time. Plan age and drift risk are shown (TTL default 60 minutes).
- Ansible check mode does not cover every module; coverage gaps are confidence factors.
- Edges from `ai_inferred` are labeled and cannot enforce ordering.
- If the infra map is missing or stale, the plan states what it could not determine and produces context TODOs instead of guessing.

---

## 8. AI Orchestration Layer

### 8.1 Principles

1. **Deterministic first, AI on top.** Every AI capability has a deterministic baseline (detectors, templates, rules). AI improves usability; it does not replace logic (AGENTS.md).
2. **AI proposes, code enforces, humans decide.** Validators and policy floors are code. Prompts are never relied on as guardrails.
3. **Structured IR in, structured IR out.** The model receives structured context and returns schema-constrained JSON. A deterministic renderer produces YAML. The model never writes YAML, shell, or commands that are executed.
4. **Validate, repair, then present.** Output is validated; up to two repair attempts feed validator errors back; failures degrade to the deterministic path.
5. **Untrusted inputs.** Repository contents, file names, comments, logs, registry text, plan output, and ticket text are data, never instructions.
6. **Data minimization and local-first.** Models receive structured summaries, never raw artifacts or secrets; local-only providers (Ollama) are first-class.
7. **Everything is labeled and audited.** AI-originated items carry an origin label, and each AI interaction is recorded (digest, model, outcome).
8. **No silent change.** AI output is shown as a diff or proposal; applying it is an explicit human action; publishing is a separate explicit action.

### 8.2 AI capability catalog

| ID | Capability | Structured input | Structured output (IR) | Deterministic fallback | Explicitly forbidden | Phase |
|----|-----------|------------------|------------------------|------------------------|----------------------|-------|
| AI-1 | **Workflow Composer** (modes: Draft, Explain, Review) | Natural-language request; step registry; project guardrail floors; selected Skills; existing draft (for edit/explain/review) | `WorkflowIR` plus rationale, assumptions, warnings | Template picker (Story 16.17) and the validator's error messages | Publishing, running, adding steps outside the registry, inline secrets, lowering floors | A |
| AI-2 | **Infra Mapper** | Deterministic detector output: unit candidates with file-pattern evidence and metadata (paths, types, sizes) - not file contents | `InfraMapIR` (units, layers, runner tags, suggested owners from CODEOWNERS) | Detector output rendered as an editable draft map | Reading file contents by default; inventing units not present in detector output | B |
| AI-3 | **Orchestration Planner** | Change set; infra map; graph edges with basis; package diffs; topology summary; Skills | `StagePlanIR` (waves, rationale per wave, suggested extra edges marked `ai_inferred`, open questions) | Deterministic topological waves from enforcing edges | Dropping or adding units; reordering against an enforcing edge; adding packages; approving | B |
| AI-4 | **Run Diagnostician** | Redacted, bounded log excerpt; exit code; step type; `command_id`; deterministic **failure signature** match | `DiagnosisIR` (summary, likely causes ranked, next verification steps, docs links) | Signature library output (rule-based) | Executing or proposing executable commands; touching secrets; hiding the raw error | B |
| AI-5 | **Approval briefing narrative** | Existing structured report summary | Existing narrative (downstream of scoring) | Existing degraded-narrative path (Story 2.7) | Changing verdict, severity, or Evidence Law status | A (reuse) |
| AI-6 | **Package Advisor** | Package diffs from lockfiles/charts/requirements; optional **locally supplied** changelog text | `PackageImpactIR` (summary of version-change implications, verification steps) | Deterministic package signals only | Network lookups by default; adding or approving packages; marking a package safe | B |
| AI-7 | **Agent / MCP surface** | Authenticated agent request to a workflow marked `agent_callable` | Run request and status reads | Same API without agent tag | Approve, publish, edit guardrails, access secrets | B |

### 8.3 Generation pipeline (all structured AI capabilities)

```
1. Build context     structured, redacted, size-capped; project scope enforced; Skills selected by trust level
2. Call provider     through llm/ boundary; JSON/structured-output mode where supported; local-only honored
3. Parse             strict JSON parse; reject extra fields
4. Validate          schema + validator rules + guardrail floors + registry membership + package allow-list
5. Repair (<= 2)     feed validator errors back; stop on repeated failure
6. Render            deterministic IR -> YAML / map / plan (no model-written YAML)
7. Present           diff against current draft, with rationale, assumptions, warnings, and origin labels
8. Human action      Apply to draft  ->  Review  ->  Publish (separate permissions and audit)
9. Record            ai_run row: digests, model, outcome (accepted / edited / rejected), validator result
```

If steps 3-5 fail, the UI shows the validator errors and offers the deterministic fallback; it never shows a half-valid result as usable.

### 8.4 IR examples

**WorkflowIR (excerpt):**

```json
{
  "ir_version": "workflow-ir/v1",
  "key": "prod-terraform-preflight",
  "scope": { "project": "payments", "workspace": "prod" },
  "inputs": [{ "id": "stack_path", "type": "string", "pattern": "^infra/[a-z0-9/_-]+$", "required": true }],
  "steps": [
    { "id": "plan", "type": "collect.terraform_plan", "runner_tags": ["terraform", "prod-vpc"], "with": { "path": "${{ inputs.stack_path }}" } },
    { "id": "analyze", "type": "analyze", "needs": ["plan"] },
    { "id": "gate", "type": "gate.verdict", "needs": ["analyze"] },
    { "id": "approve", "type": "approval", "needs": ["gate"], "with": { "roles": ["service_owner"], "min_approvals": 1 } },
    { "id": "handoff", "type": "handoff.github_dispatch", "needs": ["approve"], "with": { "repo": "acme/infra", "workflow": "apply.yml" } }
  ],
  "rationale": ["Plan is collected on a runner tagged for the prod VPC.", "Handoff is preceded by approval as required by guardrails."],
  "assumptions": ["Repository acme/infra exposes workflow apply.yml."],
  "warnings": []
}
```

**StagePlanIR (excerpt):**

```json
{
  "ir_version": "stage-plan-ir/v1",
  "change_set": ["terraform:infra/network", "terraform:infra/eks", "helm:platform/ingress"],
  "waves": [
    { "id": "w1", "units": ["terraform:infra/network"], "basis": ["declared", "layer_rule"], "rationale": "Network precedes cluster." },
    { "id": "w2", "units": ["terraform:infra/eks"], "needs": ["w1"], "basis": ["remote_state"], "rationale": "EKS reads network outputs via remote state." },
    { "id": "w3", "units": ["helm:platform/ingress"], "needs": ["w2"], "basis": ["declared"], "rationale": "Ingress chart targets the cluster." }
  ],
  "suggested_edges": [
    { "from": "helm:platform/ingress", "to": "terraform:infra/dns", "basis": "ai_inferred", "reason": "Chart values reference a DNS zone name.", "requires_acceptance": true }
  ],
  "open_questions": ["No owner found for helm:platform/ingress; add CODEOWNERS or infra-map owner."]
}
```

### 8.5 Data minimization and local-first

| Capability | Data sent to the model | Never sent |
|------------|------------------------|-----------|
| AI-1 Composer | User text, step registry, floors, Skills excerpts, current draft YAML (already redacted of secret refs' values) | Secrets, runner tokens, artifact contents |
| AI-2 Mapper | Unit candidates, file-type counts, relative path names | File contents, `*.tfstate`, `.env`, keys |
| AI-3 Planner | Unit ids, layers, edges with basis, package names/versions, severity/score summaries | Plan JSON bodies, raw logs |
| AI-4 Diagnostician | Redacted bounded log excerpt, signature id, exit code | Unredacted logs, environment variable values |
| AI-6 Advisor | Package names/versions, local changelog text supplied by the user | Network-fetched content (unless an opt-in connector exists) |

- External providers receive only the above structured summaries (NFR-SEC-02). Raw prompts and responses are **not stored by default**; the audit stores digests and a redacted summary. An admin setting can enable full-prompt retention for debugging.
- With **local-only mode** on (Story 12.2), AI features use the configured local provider or are disabled with a clear message.
- **Small local models:** because structured output is constrained and validated, a small local model (for example the 3B model recommended in your README for development) can still be useful for Composer drafts and Diagnostician summaries; quality is measured by the benchmark in Section 8.9, and the UI states when only the deterministic path is available.

### 8.6 Guardrail floors (policy floors)

Floors are minimum controls enforced by the validator at save, publish, and run time. **AI cannot create, edit, or lower them.** Phase A ships built-in floors; Phase B makes some project-configurable (by Project Admin only).

| ID | Floor | Default | Configurable |
|----|-------|---------|--------------|
| GRD-1 | Every `handoff.*` has an `approval` ancestor | On | No |
| GRD-2 | `approval.on_expire` is `fail` | On | No |
| GRD-3 | Prod workspaces: `analyze` and `gate.verdict` are required before approval | On | No |
| GRD-4 | Prod workspaces: `min_approvals >= 1` and `separation_of_duties: true` (in multi-user mode) | On | Yes (stricter only) |
| GRD-5 | Packages must come from the allow-list when an allow-list is configured | On | Yes |
| GRD-6 | AI-assisted revisions for prod require a second reviewer before publish ("four-eyes") | On for prod | Yes |
| GRD-7 | Outbound hosts must be on the admin allow-list | On | Yes |
| GRD-8 | Approval required above thresholds: `severity >= high`, `recommendation = no_go`, `insufficient_context`, or blast radius above N services | On | Yes (lower thresholds only) |
| GRD-9 | Maximum steps per workflow and per run quotas | On | Yes |
| GRD-10 | Agent/automation tokens cannot approve or publish | On | No |

### 8.7 AI provenance and audit

- Every workflow revision records `authored_by`: `human` or `ai_assisted`, plus the `ai_run_id` list that contributed, and a diff of AI-originated changes.
- Plan and map items record `origin`: `deterministic`, `declared`, `ai_suggested`, or `ai_accepted`.
- The `infra_automation_ai_runs` table stores: id, capability, actor, project/workspace, provider, model, prompt digest, redacted input summary, output digest, validator result, repair count, outcome (`accepted`, `edited`, `rejected`, `abandoned`), latency, timestamp.
- AI events are part of the audit export (BR-09).

### 8.8 AI-specific threats (see Section 12 for the full table)

Prompt injection through repository files and logs; hallucinated steps, units, or packages; guardrail erosion through repeated suggestions; automation bias (approving because "AI said so"); data leakage to external providers; cost and latency blowups. Each has a control and a test (Stories 16.16, 16.30).

### 8.9 AI evaluation

A benchmark corpus under `benchmarks/corpus/v1/infra-automation/` (synthetic, licensed, no real infrastructure):

| Corpus part | Contents | Metric |
|-------------|----------|--------|
| Composer prompts | Natural-language requests with expected validator outcomes | First-pass validity rate; validity after repair; step-registry violations (target 0) |
| Unsafe-request set | Requests that try to skip approval, add inline secrets, lower floors, or add packages | Unsafe-acceptance rate (**must be 0**) |
| Injection set | Repo files, logs, and tickets with embedded instructions | Injection-success rate (**must be 0**) |
| Mapper repos | Synthetic repo trees with known units | Unit precision/recall vs ground truth |
| Planner cases | Change sets with known enforcing edges | Order violations (**must be 0**); coverage errors (**must be 0**) |
| Diagnostician cases | Redacted logs with known signatures | Signature-match accuracy; unsafe-suggestion rate (**must be 0**) |

Published like other benchmarks, including misses (BEN-08). Targets for rates other than "must be 0" are set after the first baseline run and reported honestly.

### 8.10 AI user experience pattern

A persistent **Assistant** panel in the workflow editor and plan views, with three modes:

- **Draft** - proposes a workflow or plan from your request; shows a diff; nothing changes until you choose **Apply to draft**.
- **Explain** - plain-language explanation of the selected workflow, step, run, or failure.
- **Review** - checks a draft against floors and best practices and lists issues with suggested fixes.

Every AI result shows an **AI-generated** chip, the validator status, and a link to the audit record. Copy is calm and advisory; AI never says a plan is "safe".

---

## 9. Functional Requirements

Priority: **P0** required for the phase to ship, **P1** should ship, **P2** nice to have. Phase: **A** core (target v1.4.0), **B** IaC/package orchestration with AI (target v1.5.0), **C** gated by RFC.

### 9.1 Workflow definition and lifecycle (`IAU-WF`)

| ID | Requirement | Phase | Pri |
|----|-------------|-------|-----|
| IAU-WF-01 | Workflows are declarative YAML with `schema: deploywhisper.workflow/v1` and a published JSON Schema in `schemas/`. | A | P0 |
| IAU-WF-02 | Validation (API, CLI, UI) checks syntax, schema, references, DAG acyclicity, tier rules, approval-ancestor rule, and guardrail floors with no side effects. | A | P0 |
| IAU-WF-03 | Only step types in the closed registry are accepted; unknown types are rejected with field-level errors. | A | P0 |
| IAU-WF-04 | Templating is substitution-only (`${{ inputs.x }}`, `${{ steps.id.outputs.y }}`, `${{ run.id }}`, `${{ project.key }}`); no function calls, loops, or code evaluation. | A | P0 |
| IAU-WF-05 | Typed inputs (`string`, `integer`, `boolean`, `select`, `artifact`) with pattern/enum/min/max validation; webhook inputs validated identically. `artifact` lets a user upload a file for a run, enabling runner-less workflows. | A | P0 |
| IAU-WF-06 | Secrets are referenced by name (`*_ref`); inline secret-looking values are rejected. | A | P0 |
| IAU-WF-07 | Revisions: draft, publish, history, restore as new draft. Drafts are never executed. Published revisions are immutable. | A | P0 |
| IAU-WF-08 | Every workflow is scoped to a project and optional workspace. | A | P0 |
| IAU-WF-09 | Steps declare `needs` forming a DAG; independent branches may run in parallel; default maximum of 50 steps. | A | P0 |
| IAU-WF-10 | Per-step `retries` and `timeout`; workflow-level `on_failure` and `finally`. | A | P1 |
| IAU-WF-11 | Per-workflow concurrency limit and per-project run quota. | A | P1 |
| IAU-WF-12 | Starter templates in `examples/infra-automation/` (non-executable YAML), each validated in CI. | A | P1 |
| IAU-WF-13 | Git-based read-only import of workflow YAML and promotion between workspaces with a diff. | B | P2 |
| IAU-WF-14 | Visual (no-code) builder synchronized with YAML. | B | P2 |
| IAU-WF-15 | `orchestrate` block that expands a stage plan into explicit per-stage steps at run start (Section 10.3). | B | P0 |

### 9.2 Triggers (`IAU-TRG`)

| ID | Requirement | Phase | Pri |
|----|-------------|-------|-----|
| IAU-TRG-01 | Manual start from UI, API, CLI with typed input validation. | A | P0 |
| IAU-TRG-02 | Inbound webhook with per-trigger token (hashed at rest), constant-time compare, optional HMAC-SHA256, timestamp tolerance, replay protection. | A | P0 |
| IAU-TRG-03 | Webhook idempotency key prevents duplicate runs. | A | P1 |
| IAU-TRG-04 | Every run records trigger type, actor, surface, and reference. | A | P0 |
| IAU-TRG-05 | Runs started by agent or automation tokens cannot skip approvals or start workflows containing `execute.*` steps. | A | P0 |
| IAU-TRG-06 | Schedule trigger (cron, timezone, optional calendar skip) including drift-detection templates. | B | P1 |
| IAU-TRG-07 | Event triggers: `analysis.completed` (internal) and GitHub pull-request events through the existing integration. | B | P1 |

### 9.3 Execution engine (`IAU-RUN`)

| ID | Requirement | Phase | Pri |
|----|-------------|-------|-----|
| IAU-RUN-01 | Run and step state is persisted as a state machine; in-flight runs resume after restart. | A | P0 |
| IAU-RUN-02 | The engine runs inside the existing FastAPI process with no new infrastructure dependency (ADR-14); a DB lease prevents two engine leaders. | A | P0 |
| IAU-RUN-03 | Transitions are persisted before side effects; at-least-once delivery with idempotency keys. | A | P0 |
| IAU-RUN-04 | Cancel a run; runner tasks cancelled best-effort; final state recorded. | A | P0 |
| IAU-RUN-05 | Explicit terminal states: `succeeded`, `failed`, `cancelled`, `stopped_by_gate`, `expired`, `timed_out`. | A | P0 |
| IAU-RUN-06 | Inputs, outputs, and logs persisted only after redaction (extends 12.1/12.3). | A | P0 |
| IAU-RUN-07 | Runs link to the report(s) from their `analyze` steps; reruns compare using the existing report diff. | A | P1 |
| IAU-RUN-08 | Configurable retention (defaults: runs 90 days, artifacts 30 days). | A | P1 |
| IAU-RUN-09 | Multi-instance-safe claiming for PostgreSQL (`SKIP LOCKED` or equivalent). | B | P1 |

### 9.4 Runners (`IAU-RNR`)

| ID | Requirement | Phase | Pri |
|----|-------------|-------|-----|
| IAU-RNR-01 | Runner is a subcommand of the existing package and connects **outbound** over HTTPS only. | A | P0 |
| IAU-RNR-02 | Enrollment via one-time token; runner token is project-scoped, hashed server-side, revocable, expiring, shown once. | A | P0 |
| IAU-RNR-03 | Tag routing (`runner.tags`, all-of by default). No eligible runner -> fail fast; `fallback: wait` needs `max_wait`. | A | P0 |
| IAU-RNR-04 | Heartbeats and leases; lost tasks re-queued only for steps declared `idempotent`. | A | P0 |
| IAU-RNR-05 | Runner-side **command catalog**: fixed argv templates plus parameter schemas; the server sends only `command_id` and validated parameters. | A | P0 |
| IAU-RNR-06 | Secrets and cloud credentials are resolved on the runner; the server never stores or receives them. | A | P0 |
| IAU-RNR-07 | Per-task working directory, environment allow-list, output caps, timeouts; optional container profile documented. | A | P0 |
| IAU-RNR-08 | Protocol version negotiation; incompatible runners refused with an actionable message. | A | P1 |
| IAU-RNR-09 | Runner health (last seen, version, tags, current task) in UI and API. | A | P1 |
| IAU-RNR-10 | Server-side steps run in-process and need no runner. | A | P0 |
| IAU-RNR-11 | Runner-side custom commands only via a local allow-list file owned by the runner operator. | B | P2 |
| IAU-RNR-12 | Mutual TLS and signed task envelopes. | C | P1 |
| IAU-RNR-13 | Optional runner setting `require_ephemeral_credentials`: refuse tasks when only long-lived static cloud keys are detected; documentation for workload identity/OIDC. | B | P1 |

### 9.5 Step catalog (`IAU-STP`)

| ID | Step type | Where | Tier | Phase |
|----|-----------|-------|------|-------|
| IAU-STP-01 | `collect.terraform_plan` (OpenTofu or Terraform binary chosen by the runner catalog) | Runner | 0 | A |
| IAU-STP-02 | `collect.ansible_check` | Runner | 0 | A |
| IAU-STP-03 | `collect.kubectl_diff` | Runner | 0 | A |
| IAU-STP-04 | `collect.helm_template` | Runner | 0 | A |
| IAU-STP-05 | `collect.git_diff` | Runner | 0 | A |
| IAU-STP-06 | `analyze` (shared orchestrator) | Server | 0 | A |
| IAU-STP-07 | `scanner.import` (Epic 8) | Server | 0 | A |
| IAU-STP-08 | `gate.verdict` | Server | 0 | A |
| IAU-STP-09 | `approval` | Server | 0 | A |
| IAU-STP-10 | `notify.slack_webhook`, `notify.github_pr_comment` | Server | 0 | A |
| IAU-STP-11 | `handoff.webhook`, `handoff.github_dispatch` | Server | 1 | A |
| IAU-STP-12 | `collect.kustomize_build`, `collect.terragrunt_plan`, `collect.cloudformation_changeset` | Runner | 0 | B |
| IAU-STP-13 | `handoff.jenkins`, `handoff.gitlab_pipeline`, `itsm.callback` | Server | 1 | B |
| IAU-STP-14 | `packages.inspect` (build/refresh the package inventory for selected units) | Server/Runner | 0 | B |
| IAU-STP-15 | `wait` (delay or until callback) | Server | 0 | B |
| IAU-STP-16 | `execute.*` | Runner | 2 | C - gated |

### 9.6 Approvals (`IAU-APR`)

| ID | Requirement | Phase | Pri |
|----|-------------|-------|-----|
| IAU-APR-01 | `approval` pauses the run durably; the pause survives restarts and never auto-approves. | A | P0 |
| IAU-APR-02 | Assignment by users and/or project roles with `min_approvals`. | A | P0 |
| IAU-APR-03 | Optional `separation_of_duties` (requester cannot approve); unavailable and labeled in single-operator mode. | A | P0 |
| IAU-APR-04 | Typed decision payload (`approved`, `reason`, declared fields) becomes step output. | A | P0 |
| IAU-APR-05 | **Evidence pinning**: records `report_id`, artifact sha256 digests, and (Phase B) plan-snapshot digest; any change or supersession invalidates the approval. | A | P0 |
| IAU-APR-06 | Approval card shows verdict, score, Evidence Law status, confidence, top findings, blast radius, rollback summary, context TODOs, plan age, AI-involvement indicator, and the exact handoff target. | A | P0 |
| IAU-APR-07 | Stale-evidence warning when pinned collection exceeds the TTL (default 60 min). | A | P1 |
| IAU-APR-08 | Reason required for `no_go`, `severity >= high`, `insufficient_context`; high/critical additionally requires typed confirmation. Thresholds follow GRD-8. | A | P0 |
| IAU-APR-09 | Expiry ends in `expired` (run fails), never approval. | A | P0 |
| IAU-APR-10 | Agent and automation tokens cannot approve or reject; attempts are denied and audited. | A | P0 |
| IAU-APR-11 | Approvals inbox with filters, sidebar badge, and deep links from notifications. | A | P0 |
| IAU-APR-12 | Emergency bypass per PRD 19.2 (reason, actor, timestamp, audit); disabled by default. | B | P1 |
| IAU-APR-13 | Reassign or delegate an approval. | B | P2 |
| IAU-APR-14 | Per-stage approvals with the stage plan digest pinned. | B | P0 |

### 9.7 Evidence, report, and AI-safety integration (`IAU-AEV`)

| ID | Requirement | Phase | Pri |
|----|-------------|-------|-----|
| IAU-AEV-01 | Collected artifacts enter normal intake: classification, sensitive-file handling (`*.tfstate`, keys, credentials never ingested), project/workspace scoping. | A | P0 |
| IAU-AEV-02 | Provenance per artifact: run, step, runner id, `command_id`, argv digest, exit code, `collected_at`, sha256. | A | P0 |
| IAU-AEV-03 | New evidence `source_type` `automation_collection` is `deterministic` only with complete provenance; otherwise downgraded to `user_provided`. | A | P0 |
| IAU-AEV-04 | Infra Automation never creates or changes findings, severity, or Evidence Law status. | A | P0 |
| IAU-AEV-05 | Collection limitations become confidence factors and context TODOs (check-mode gaps, plan age, plan-apply drift, partial collection). | A | P0 |
| IAU-AEV-06 | Terraform plan `sensitive` values are redacted before storage or analysis. | A | P0 |
| IAU-AEV-07 | Report schema gains an additive optional `automation` block; `report_schema_version` increments; docs updated. | A | P0 |
| IAU-AEV-08 | Step logs/outputs are untrusted text for narrative generation; prompt-injection tests cover them. | A | P0 |
| IAU-AEV-09 | CI fixtures verify automation-originated reports satisfy the Evidence Law (EVD-12 extended). | A | P0 |

### 9.8 IaC orchestration (`IAU-ORC`)

| ID | Requirement | Phase | Pri |
|----|-------------|-------|-----|
| IAU-ORC-01 | Infra map schema `deploywhisper.infra-map/v1` (units, layers, runner tags, owners, depends_on, package allow-lists) with JSON Schema and validator. | B | P0 |
| IAU-ORC-02 | Deterministic unit detection from repository content and changed paths (file patterns) with evidence for each detected unit. | B | P0 |
| IAU-ORC-03 | Dependency graph with per-edge `basis` (Section 7.4) and confidence; only enforcing bases constrain order. | B | P0 |
| IAU-ORC-04 | A stage plan is valid only if it respects all enforcing edges and covers exactly the change set; invalid plans are rejected with reasons. | B | P0 |
| IAU-ORC-05 | Limitations are surfaced: missing map, stale map, undeterminable edges, AI-inferred edges - as context TODOs, never silent. | B | P0 |
| IAU-ORC-06 | Plan snapshot (units, edges, waves, rationale, digest) persisted with the run and pinned by approvals. | B | P0 |
| IAU-ORC-07 | `orchestrate` expansion generates explicit per-stage *collect, analyze, gate, approval, handoff* steps at run start; the expanded definition is stored and validated by the same validator. | B | P0 |
| IAU-ORC-08 | Environment promotion `dev -> stage -> prod` with per-environment approvals and a promotion diff (report and package versions). | B | P1 |
| IAU-ORC-09 | Cross-unit bundle analysis plus per-stage analyses; cross-unit interaction findings reference all contributing units. | B | P1 |
| IAU-ORC-10 | Target locks keyed `<unit_id>:<workspace>`, held until handoff completion/cancel/expiry; audited admin break. | B | P1 |
| IAU-ORC-11 | Change windows and freeze periods per workspace; out-of-window approvals need an audited exception reason. | B | P1 |
| IAU-ORC-12 | Lock and window state visible in UI and API; conflicts produce explicit messages. | B | P1 |

### 9.9 Package governance (`IAU-PKG`)

| ID | Requirement | Phase | Pri |
|----|-------------|-------|-----|
| IAU-PKG-01 | Parsers for `.terraform.lock.hcl` and module calls (plan JSON `module_calls` / HCL), `Chart.yaml`/`Chart.lock`, Ansible `requirements.yml`, Kubernetes image references, Kustomize remote bases, registered through the parser registry. | B | P0 |
| IAU-PKG-02 | Package inventory per unit and per run using the package reference schema (Section 7.2). | B | P0 |
| IAU-PKG-03 | Per-project, per-workspace **package ledger** supporting first-seen, version-changed, and hash-changed-without-version-change detection. | B | P0 |
| IAU-PKG-04 | Deterministic package signals (Section 7.2) feed the existing risk engine as evidence and public risk patterns; severity remains governed by Evidence Law. | B | P0 |
| IAU-PKG-05 | Admin-managed package allow-list (registries, namespaces, images); non-allow-listed sources are flagged; GRD-5 enforces for workflows. | B | P0 |
| IAU-PKG-06 | First-seen packages require explicit human acknowledgement in the approval card. | B | P1 |
| IAU-PKG-07 | Registry lookups are off by default; an opt-in, user-owned connector (including MCP-based registry access) may add `external` evidence with freshness and source labels. | C | P2 |
| IAU-PKG-08 | AI cannot add, upgrade, or approve packages (IAU-AI-11). | B | P0 |
| IAU-PKG-09 | New public risk patterns for package signals ship with benchmark scenarios and false-positive notes. | B | P1 |

### 9.10 AI orchestration (`IAU-AI`)

| ID | Requirement | Phase | Pri |
|----|-------------|-------|-----|
| IAU-AI-01 | AI is optional; each capability has a deterministic fallback; the feature is fully usable with AI off. | A | P0 |
| IAU-AI-02 | AI output is schema-constrained IR; strict parse; unknown fields rejected. | A | P0 |
| IAU-AI-03 | All AI output passes the validator, guardrail floors, registry checks, and package allow-list; failures are never shown as usable results. | A | P0 |
| IAU-AI-04 | Repair loop of at most two attempts using validator errors only. | A | P0 |
| IAU-AI-05 | Deterministic renderer converts IR to YAML/map/plan; the model never emits YAML, shell, or executable commands. | A | P0 |
| IAU-AI-06 | Results are proposals shown as diffs; **Apply to draft**, **Publish**, **Run**, **Approve** are separate explicit human actions. | A | P0 |
| IAU-AI-07 | Origin labels on items; revisions record `authored_by` and `ai_run_id`s. | A | P0 |
| IAU-AI-08 | Untrusted-input handling: prompt isolation, structured inputs, size caps; injection test suite extended with infra-automation fixtures. | A | P0 |
| IAU-AI-09 | Provider unavailable/invalid/timeout falls back to the deterministic path with a clear message. | A | P0 |
| IAU-AI-10 | Local-only mode honored; data-minimization rules (Section 8.5) enforced; external providers receive structured summaries only. | A | P0 |
| IAU-AI-11 | AI cannot add steps outside the registry, units outside the change set, packages outside the allow-list, or lower/disable floors. | A | P0 |
| IAU-AI-12 | AI interaction audit records (Section 8.7), included in audit export. | A | P0 |
| IAU-AI-13 | AI evaluation corpus, metrics, and release gate; zero-tolerance metrics as listed in Section 8.9. | B | P0 |
| IAU-AI-14 | Rate limits, size caps, timeouts, per-user budgets; no background AI calls without a user action unless an admin enables optional auto-diagnosis (off by default). | A | P1 |
| IAU-AI-15 | AI requests originating from agent/automation tokens are treated as untrusted and cannot trigger publish or approval paths. | B | P0 |
| IAU-AI-16 | Workflow Composer (Draft, Explain, Review). | A | P0 |
| IAU-AI-17 | Infra Mapper. | B | P0 |
| IAU-AI-18 | Orchestration Planner (suggestions marked `ai_inferred` until accepted). | B | P0 |
| IAU-AI-19 | Run Diagnostician with rule-based failure signatures as the baseline. | B | P1 |
| IAU-AI-20 | Package Advisor using only local inputs by default. | B | P2 |

### 9.11 Guardrails (`IAU-GRD`)

| ID | Requirement | Phase | Pri |
|----|-------------|-------|-----|
| IAU-GRD-01 | Floors GRD-1..GRD-10 (Section 8.6) enforced at save, publish, and run time. | A | P0 |
| IAU-GRD-02 | Floors cannot be created, edited, or lowered by AI, by agent tokens, or by workflow content. | A | P0 |
| IAU-GRD-03 | Project Admins may raise floors where marked configurable; every change is audited. | B | P1 |
| IAU-GRD-04 | Blast-radius thresholds (severity, `no_go`, `insufficient_context`, services affected, environment tier) drive mandatory approval and reason requirements. | A | P0 |
| IAU-GRD-05 | Floors reuse the Epic 11 policy-adapter field names and semantics where they exist. | A | P1 |

### 9.12 Audit (`IAU-AUD`)

| ID | Requirement | Phase | Pri |
|----|-------------|-------|-----|
| IAU-AUD-01 | Append-only events for workflow create/edit/publish/archive, run start/cancel, approval requested/decided/expired, runner enroll/revoke, token create/rotate, setting and floor changes, AI interactions, lock breaks, and denied actions. | A | P0 |
| IAU-AUD-02 | Each event records actor, role, surface, project, workspace, target, timestamp, reason, and before/after digest. | A | P0 |
| IAU-AUD-03 | Viewable in UI, exportable as JSON, retention configurable. | A | P1 |
| IAU-AUD-04 | No secrets or raw artifact content in audit (tested). | A | P0 |

### 9.13 API and CLI (`IAU-API`)

| ID | Requirement | Phase | Pri |
|----|-------------|-------|-----|
| IAU-API-01 | REST endpoints under `/api/v1/infra-automation/` for workflows, revisions, validation, runs, approvals, runners, audit, stats, AI, and (Phase B) inventory, packages, plans, locks. Use the existing `{data, meta}` and error envelopes and Pydantic models. | A | P0 |
| IAU-API-02 | Endpoints enforce project scope and role checks; unauthorized access returns bounded errors that do not reveal existence. | A | P0 |
| IAU-API-03 | `GET /api/v1/infra-automation/stats/summary` for page KPIs and sparklines with the same optional scope filters as `/stats/summary`. | A | P1 |
| IAU-API-04 | CLI under `deploywhisper infra-automation`: `validate`, `run`, `status`, `approve`, `list`, `compose` (AI draft to stdout); and `deploywhisper runner`: `enroll`, `start`, `status`. | A | P0 |
| IAU-API-05 | `--agent-json` read/request-only equivalents; no approve or publish. | B | P1 |
| IAU-API-06 | OpenAPI types for the SPA regenerated through the existing generation step. | A | P0 |

### 9.14 Administration (`IAU-ADM`)

| ID | Requirement | Phase | Pri |
|----|-------------|-------|-----|
| IAU-ADM-01 | Enable/disable per instance and per project. | A | P0 |
| IAU-ADM-02 | Configure allowed outbound hosts, quotas, retention, approval TTL defaults, runner token lifetime, AI enablement and budgets. | A | P0 |
| IAU-ADM-03 | Manage runners and webhook trigger tokens (enroll, rotate, revoke). | A | P0 |
| IAU-ADM-04 | Manage the infra map, layers, package allow-lists, change windows, and guardrail raises. | B | P0 |

### 9.15 UI (`UX-DR`) - continues UX-DR numbering

| ID | Requirement | Phase | Pri |
|----|-------------|-------|-----|
| UX-DR11 | **Infra Automation** nav item after Incidents and before History, reusing the existing nav component, a `lucide-react` icon, and a pending-approvals badge. | A | P0 |
| UX-DR12 | Landing page follows its own information budget (Section 13.3); Dashboard budget unchanged. | A | P0 |
| UX-DR13 | Run detail with step timeline, redacted logs, artifacts with digests, linked briefing. | A | P0 |
| UX-DR14 | Approval card embeds the briefing; fully keyboard operable. | A | P0 |
| UX-DR15 | Loading, empty, error, disabled, and degraded states follow Part B4 patterns. | A | P0 |
| UX-DR16 | Calm, advisory copy; no "deploy" verbs for Tier 0/1; AI never claims safety. | A | P0 |
| UX-DR17 | New primitives live in `src/components/ui/`, appear in `/dev/components`, and have Vitest snapshots. | A | P0 |
| UX-DR18 | Accessibility smoke (axe and keyboard) for all new routes. | A | P0 |
| UX-DR19 | Assistant panel (Draft/Explain/Review) with AI chip, validator status, diff, and audit link. | A | P0 |
| UX-DR20 | Provenance chip and "Collected by run" link on the report screen's Audit tab. | A | P1 |
| UX-DR21 | Inventory view (units, packages, edges with basis) and Plan view (waves, rationale, open questions). | B | P0 |
| UX-DR22 | Graph view with an equivalent accessible table alternative. | B | P1 |

### 9.16 Documentation (`DOC`) - continues DOC numbering

| ID | Requirement |
|----|-------------|
| DOC-28 | Maintain `docs/infra-automation/` (Section 15.2). |
| DOC-29 | Capability-tiers, autonomy-levels, and guardrail-floors concept pages. |
| DOC-30 | Runner installation guides (Docker, Kubernetes, systemd) and restricted-network guide, with the Terraform/OpenTofu licensing note. |
| DOC-31 | Workflow schema, infra-map schema, step catalog, API, CLI references generated from source where practical, with docs-CI drift checks. |
| DOC-32 | Comparison page: Infra Automation alongside Kestra, Rundeck, Atlantis, Argo CD, GitHub Actions, Terraform Stacks, and AI-agent platforms. |
| DOC-33 | AI guide: capabilities, data sent to providers, local-only setup, limitations, and evaluation results. |
| DOC-34 | Package governance guide and failure-signature contribution guide. |

---

## 10. Workflow Specification (v1)

### 10.1 Example A - single-stack production pre-flight (Phase A)

```yaml
schema: deploywhisper.workflow/v1
key: prod-terraform-preflight
name: Production Terraform pre-flight
description: Plan, analyze, gate, approve, then hand off to the apply pipeline.
project: payments
workspace: prod
authoring:
  origin: ai_assisted            # human | ai_assisted ; set by the platform, not by the author
  ai_runs: ["air_01HV..."]       # references to infra_automation_ai_runs

inputs:
  - id: stack_path
    type: string
    required: true
    pattern: "^infra/[a-z0-9/_-]+$"
  - id: ref
    type: string
    default: main

triggers:
  - id: manual
    type: manual
  - id: change-request
    type: webhook
    key: prod-change-request          # server stores only a hashed token
    auth: token+hmac

steps:
  - id: plan
    type: collect.terraform_plan
    runner:
      tags: [terraform, prod-vpc]
      fallback: fail                  # default; "wait" requires max_wait
    with:
      path: "${{ inputs.stack_path }}"
      ref: "${{ inputs.ref }}"
    timeout: 15m
    idempotent: true

  - id: analyze
    type: analyze
    needs: [plan]
    with:
      artifacts: ["${{ steps.plan.outputs.plan_json }}"]

  - id: gate
    type: gate.verdict
    needs: [analyze]
    with:
      stop_when:
        evidence_law_status: violation
      needs_approval_when:
        recommendation_in: [caution, no_go, insufficient_context]
        severity_at_least: medium

  - id: approve
    type: approval
    needs: [gate]
    with:
      assign: { roles: [service_owner, reviewer] }
      min_approvals: 1
      separation_of_duties: true
      expires_in: 4h
      on_expire: fail
      pin:
        report: "${{ steps.analyze.outputs.report_id }}"
        artifacts: ["${{ steps.plan.outputs.plan_json }}"]
      decision_fields:
        - { id: reason, type: string, required: true }

  - id: handoff
    type: handoff.github_dispatch
    needs: [approve]
    with:
      repo: acme/infra
      workflow: apply.yml
      ref: main
      token_ref: GITHUB_DISPATCH_TOKEN
      inputs:
        report_id: "${{ steps.analyze.outputs.report_id }}"
        plan_sha256: "${{ steps.plan.outputs.plan_json.sha256 }}"

on_failure:
  - id: notify_failure
    type: notify.slack_webhook
    with:
      secret_ref: SLACK_WEBHOOK_PLATFORM
      message: "Pre-flight ${{ run.id }} for ${{ project.key }} ended in ${{ run.state }}"
```

### 10.2 Example B - runner-less workflow (first end-to-end slice, Phase A)

This workflow needs no runner. A user uploads a plan JSON as a run input; the engine analyzes, gates, requests approval, and notifies. It is the fastest way to deliver and demonstrate value, and the first end-to-end test of the engine.

```yaml
schema: deploywhisper.workflow/v1
key: review-uploaded-plan
name: Review an uploaded Terraform plan
project: payments
workspace: qa
inputs:
  - id: plan_json
    type: artifact
    accept: [".json"]
    required: true
steps:
  - id: analyze
    type: analyze
    with: { artifacts: ["${{ inputs.plan_json }}"] }
  - id: gate
    type: gate.verdict
    needs: [analyze]
  - id: approve
    type: approval
    needs: [gate]
    with:
      assign: { roles: [reviewer] }
      min_approvals: 1
      expires_in: 24h
      on_expire: fail
      pin: { report: "${{ steps.analyze.outputs.report_id }}" }
  - id: tell_team
    type: notify.slack_webhook
    needs: [approve]
    with:
      secret_ref: SLACK_WEBHOOK_PLATFORM
      message: "Plan review approved: report ${{ steps.analyze.outputs.report_id }}"
```

### 10.3 Example C - multi-unit orchestration with promotion (Phase B)

```yaml
schema: deploywhisper.workflow/v1
key: estate-preflight
name: Estate pre-flight (changed units, staged)
project: payments
workspace: prod
inputs:
  - { id: base,  type: string, default: main }
  - { id: head,  type: string, required: true }
orchestrate:
  source: infra-map                 # units resolved from the project's infra map
  select: changed                   # changed | all | explicit
  between: { base: "${{ inputs.base }}", head: "${{ inputs.head }}" }
  stages: auto                      # deterministic waves from enforcing edges
  suggestions: allow                # AI Planner may add ai_inferred edges as proposals only
  per_stage: [collect, analyze, gate, approval, handoff]
  promote: [dev, stage, prod]       # separate collect/analyze/approval per environment
  packages:
    inspect: true                   # packages.inspect for each selected unit
    require_ack_for_first_seen: true
  locks: true                       # target locks per unit and workspace
  windows: enforce                  # change windows per workspace
handoff:
  type: handoff.github_dispatch
  with: { repo: acme/infra, workflow: apply.yml, ref: main, token_ref: GITHUB_DISPATCH_TOKEN }
```

At run start the engine expands `orchestrate` into explicit steps, stores the expanded definition and the plan snapshot digest, validates the result with the same validator, and pins approvals to that digest. Nothing in an `orchestrate` block can express an unapproved handoff.

### 10.4 Step reference (Phase A unless noted)

| Step | Key `with` fields | Outputs | Notes |
|------|-------------------|---------|-------|
| `collect.terraform_plan` | `path`, `ref`, `var_files[]`, `workspace` | `plan_json`, `plan_text`, `collected_at` | `plan -out` then `show -json`; `sensitive` redacted; state files never returned. |
| `collect.ansible_check` | `playbook`, `inventory`, `limit`, `tags[]` | `check_output`, `changed_hosts` | `--check --diff` only. |
| `collect.kubectl_diff` | `context_ref`, `namespace`, `path` | `diff_output` | Runner resolves the kube context locally. |
| `collect.helm_template` | `chart`, `values[]`, `release`, `namespace` | `rendered_manifests` | Offline render. |
| `collect.git_diff` | `repo_ref`, `base`, `head`, `paths[]` | `diff_output`, `changed_files[]` | Feeds change-set detection in Phase B. |
| `analyze` | `artifacts[]` | `report_id`, `recommendation`, `severity`, `score`, `evidence_law_status` | Calls the shared orchestrator; `trigger_ref = infra-automation:<run_id>`. |
| `scanner.import` | `format`, `artifact` | `import_id`, `finding_count` | Reuses Epic 8; stays external evidence. |
| `gate.verdict` | `stop_when`, `needs_approval_when` | `decision` | Reads report fields only. |
| `approval` | `assign`, `min_approvals`, `separation_of_duties`, `expires_in`, `pin`, `decision_fields` | `approved`, `approvers[]`, `decision` | Durable pause. |
| `notify.slack_webhook` | `secret_ref`, `message` | `status` | Host on admin allow-list. |
| `notify.github_pr_comment` | `repo`, `pr`, `template` | `comment_url` | Existing GitHub integration; advisory wording enforced. |
| `handoff.webhook` | `url_ref`, `method`, `body`, `hmac_secret_ref` | `status_code`, `response_excerpt` | SSRF controls; approval ancestor required. |
| `handoff.github_dispatch` | `repo`, `workflow`, `ref`, `token_ref`, `inputs` | `dispatch_status` | Approval ancestor required. |
| `packages.inspect` (B) | `units[]` | `package_inventory`, `signals[]` | Local evidence only by default. |

### 10.5 Gate semantics

`gate.verdict` reads report fields that already exist (`recommendation`, `severity`, `score`, `evidence_law_status`, `confidence`, `context_completeness`) and yields one decision.

| Decision | Meaning |
|----------|---------|
| `stop` | Workflow ends `stopped_by_gate`. The report is unchanged and advisory. |
| `needs_approval` | Continue to the next `approval` step. |
| `proceed` | Continue; still cannot bypass the mandatory approval ancestor for `handoff.*`. |

Order: `stop_when`, then `needs_approval_when`, then default `needs_approval`. `insufficient_context` and `analysis_failed` are never treated as safe. Field names reuse the Epic 11 adapter contract where they exist.

### 10.6 Validator rules (API, CLI, UI, and at run time)

1. Schema valid; `key` unique within project; `project` and `workspace` resolve and are accessible.
2. Step ids unique; `needs` resolve; acyclic; maximum steps respected.
3. Every `${{ ... }}` reference resolves to a declared input, upstream output, `run.*`, or `project.*`.
4. No inline secret-looking values; only `*_ref` fields hold secrets.
5. Every `handoff.*` and `execute.*` step has an `approval` ancestor.
6. `approval.on_expire` is `fail`.
7. `collect.*` steps declare `runner.tags`; `fallback: wait` declares `max_wait`.
8. Tier 2 steps are rejected unless the Tier 2 capability exists (never in Phase A or B).
9. Outbound hosts checked against the admin allow-list at publish **and** at run time.
10. Guardrail floors GRD-1..GRD-10 evaluated; any floor violation blocks publish.
11. Packages referenced in the workflow or inventory conform to the allow-list when configured (GRD-5).
12. For `authoring.origin = ai_assisted` in prod, a second reviewer is required before publish (GRD-6).
13. (Phase B) `orchestrate` expansion must respect enforcing edges and cover exactly the change set (IAU-ORC-04).

---

## 11. Technical Architecture

### 11.1 Fit with the existing architecture

Infra Automation is an additive subsystem. It calls the existing shared orchestrator for analysis and reuses project scope, RBAC roles, redaction, evidence, report persistence, GitHub integration, scanner import, Skills, the `llm/` provider boundary, and the API envelope.

```
               React SPA (/infra-automation, /infra-automation/runs/:id, /infra-automation/approvals, ...)
                                              |
                              FastAPI /api/v1/infra-automation/*
                                              |
          +-----------------------------------+-----------------------------------+
          |                                   |                                   |
  Infra Automation service          AI service (llm/ boundary)         Shared analysis orchestrator (unchanged)
  validate, publish, start run      IR build -> call -> validate        intake -> parse -> evidence -> score -> persist
          |                                   |                                   ^
  Workflow engine (in-process)                |                                   |
  DB state machine, ticks, approvals,         +-- Skills (markdown, non-executable)|
  server steps  ------------- analyze step ---------------------------------------+
          |
  Task queue table  <---- HTTPS, outbound claim/heartbeat/result ----  Runner agent (user infra)
                                                                       command catalog, tags,
  Orchestration (Phase B): detectors, infra map, graph, plan,          local secret/credential resolution
  package parsers + ledger, locks, windows
```

### 11.2 Repository changes (aligned with architecture directory rules)

```
infra_automation/                   domain package (engine and rules; no scoring logic)
  schema/                           Pydantic models: workflow, infra-map, IRs; JSON Schema export
  validator/                        rules (Section 10.6) and guardrail floors
  templating.py                     substitution-only resolver
  registry.py                       closed step registry
  engine/                           state machine, ticks, leases, idempotency, leader lease
  steps/                            analyze, gate, approval, notify, handoff_*, packages_inspect
  runner/                           agent: client, catalog, executor, redaction
  orchestration/                    detectors, infra map, graph, stage planner (deterministic), locks, windows   [Phase B]
  packages/                         package model, ledger, signals                                              [Phase B]
  diagnostics/                      failure signatures (YAML data) + classifier                                  [Phase B]
  ai/                               IR models, context builders, validators, renderers (call llm/ boundary)
services/infra_automation_service.py        facade for API/CLI
services/infra_automation_ai_service.py     AI facade (rate limits, audit, fallback)
models/infra_automation.py                  SQLAlchemy tables; models/repositories/infra_automation_*.py
api/routes/infra_automation.py              routes; api/schemas/infra_automation.py
cli/infra_automation.py                     CLI, including `runner`
llm/infra_automation/                       prompt templates and IR schemas used with the provider boundary
parsers/ (Phase B)                          lockfile, Chart, requirements, image-ref parsers via the parser registry
patterns/ (Phase B)                         package public risk patterns
schemas/infra-automation/                   workflow.v1, infra-map.v1, workflow-ir.v1, stage-plan-ir.v1 JSON Schemas
examples/infra-automation/                  starter workflows and sample infra maps (non-executable, synthetic)
benchmarks/corpus/v1/infra-automation/      AI and orchestration corpus
docs/infra-automation/                      documentation tree (Section 15.2)
frontend/src/features/infra-automation/     pages, components, hooks (TanStack Query)
tests/infra_automation/                     unittest coverage; frontend/e2e for Playwright
migrations/versions/                        Alembic migrations, additive only
```

Rules carried over: UI/API/CLI adapt I/O only; engine logic stays in `infra_automation/` and `services/`; scoring and severity stay in the analysis core; provider specifics stay behind `llm/`.

### 11.3 State machines and engine loop

**Run:** `queued -> running -> (waiting_approval <-> running) -> succeeded | failed | cancelled | stopped_by_gate | expired | timed_out`

**Step:** `pending -> queued -> claimed -> running -> succeeded | failed | skipped | cancelled | timed_out`; `waiting` for approval steps.

Engine loop (single process baseline):

1. A **leader lease** row ensures one engine instance acts at a time; others stay passive.
2. On each tick (and on events), select runs with ready steps (all `needs` satisfied).
3. Persist the transition to `queued`, then dispatch: server-side steps execute in process; `collect.*` steps become task-queue rows.
4. Persist results before advancing. On startup, recover `running`/`claimed` steps by lease rules.
5. Approval steps move to `waiting` and consume no resources until a decision or expiry.

SQLite: single instance, short write transactions, modest tick. PostgreSQL: claim with `FOR UPDATE SKIP LOCKED` (IAU-RUN-09, Phase B).

### 11.4 Runner protocol (HTTPS + JSON, outbound only)

| Call | Purpose |
|------|---------|
| `POST /api/v1/infra-automation/runners/enroll` | Exchange one-time token for a runner token (shown once; stored hashed). |
| `POST /api/v1/infra-automation/runners/claim` | Long-poll (default 25s) for a task matching tags and projects. |
| `POST /api/v1/infra-automation/runners/heartbeat` | Renew lease; report version and current task. |
| `POST /api/v1/infra-automation/runners/tasks/{id}/log` | Stream redacted, size-capped log chunks. |
| `POST /api/v1/infra-automation/runners/tasks/{id}/artifacts` | Upload artifacts with declared sha256. |
| `POST /api/v1/infra-automation/runners/tasks/{id}/complete` | Report exit code, outputs, timing. |

Task envelope: `task_id`, `run_id`, `step_id`, `command_id`, `params`, `timeout`, `idempotency_key`, `secret_refs` (names only), `project`, `workspace`, `protocol_version`. The runner rejects any `command_id` not in its local catalog and any parameter failing its local schema.

Catalog entry (ships with the runner, versioned):

```yaml
- id: iac.plan_json
  # binary selected by the runner operator: "tofu" or "terraform"
  argv:
    - ["{iac_bin}", "-chdir={path}", "init", "-input=false"]
    - ["{iac_bin}", "-chdir={path}", "plan", "-input=false", "-out=tfplan.bin"]
    - ["{iac_bin}", "-chdir={path}", "show", "-json", "tfplan.bin"]
  params:
    path: { type: string, pattern: "^[A-Za-z0-9_./-]+$", max_length: 200 }
  env_allow: [AWS_*, ARM_*, GOOGLE_*, TF_VAR_*, TF_IN_AUTOMATION]
  outputs:
    plan_json: { from: stdout_of_step_3, redact: terraform_sensitive }
  timeout_max: 30m
  mutates_infrastructure: false
```

### 11.5 Data model (additive Alembic migrations; SQLite and PostgreSQL compatible)

| Table | Key columns | Phase |
|-------|-------------|-------|
| `infra_automation_workflows` | `id`, `project_id`, `workspace_id?`, `key`, `name`, `description`, `status`, `current_published_revision_id?`, timestamps. Unique (`project_id`, `key`). | A |
| `infra_automation_workflow_revisions` | `id`, `workflow_id`, `revision_no`, `state` (draft/published/superseded), `definition_yaml`, `definition_json`, `definition_sha256`, `schema_version`, `authored_by`, `ai_run_ids_json`, `created_by`, `created_at`. Published rows immutable. | A |
| `infra_automation_triggers` | `id`, `workflow_id`, `type`, `config_json`, `token_hash?`, `hmac_secret_ref?`, `enabled`. | A |
| `infra_automation_runs` | `id`, `workflow_id`, `revision_id`, `project_id`, `workspace_id?`, `state`, `trigger_type`, `trigger_ref`, `actor_id`, `actor_surface`, `inputs_redacted_json`, `idempotency_key?`, `plan_snapshot_id?`, `started_at`, `finished_at?`, `final_report_id?`. | A |
| `infra_automation_run_steps` | `id`, `run_id`, `step_id`, `type`, `state`, `attempt`, `runner_id?`, `lease_expires_at?`, `exit_code?`, `outputs_redacted_json`, `log_ref?`, `idempotency_key`, `started_at`, `finished_at?`. | A |
| `infra_automation_artifacts` | `id`, `run_id`, `step_id`, `name`, `sha256`, `size_bytes`, `storage_path`, `redaction_status`, `provenance_json`, `expires_at`. Stored under `data/infra-automation/`. | A |
| `infra_automation_approvals` | `id`, `run_id`, `step_id`, `state`, `assignment_json`, `min_approvals`, `pinned_report_id`, `pinned_digests_json`, `pinned_plan_digest?`, `expires_at`, `requested_by`, `decisions_json`. | A |
| `infra_automation_runners` | `id`, `name`, `project_scope_json`, `tags_json`, `token_hash`, `token_expires_at`, `version`, `last_seen_at`, `status`. | A |
| `infra_automation_audit_events` | `id`, `ts`, `actor_id`, `role`, `surface`, `project_id`, `workspace_id?`, `event_type`, `target_type`, `target_id`, `reason?`, `digest_before?`, `digest_after?`. Append-only. | A |
| `infra_automation_ai_runs` | `id`, `capability`, `actor_id`, `project_id`, `workspace_id?`, `provider`, `model`, `prompt_digest`, `input_summary_redacted`, `output_digest`, `validator_result_json`, `repair_count`, `outcome`, `latency_ms`, `created_at`. | A |
| `infra_automation_engine_lease` | `id`, `holder`, `expires_at`. | A |
| `infra_automation_units` | `id`, `project_id`, `unit_id`, `type`, `path`, `layer?`, `workspaces_json`, `runner_tags_json`, `owner?`, `origin` (deterministic/declared/ai_accepted), `detected_evidence_json`. | B |
| `infra_automation_edges` | `id`, `project_id`, `from_unit`, `to_unit`, `basis`, `confidence`, `origin`, `accepted_by?`. | B |
| `infra_automation_plan_snapshots` | `id`, `run_id`, `change_set_json`, `waves_json`, `edges_json`, `rationale_json`, `digest`, `origin`. | B |
| `infra_automation_package_ledger` | `id`, `project_id`, `workspace_id?`, `ecosystem`, `kind`, `name`, `source`, `resolved_version?`, `digest_or_hash?`, `first_seen_at`, `last_seen_at`, `pinned`. | B |
| `infra_automation_locks` | `id`, `project_id`, `lock_key`, `run_id`, `acquired_at`, `expires_at`, `released_at?`, `broken_by?`. | B |
| `infra_automation_windows` | `id`, `project_id`, `workspace_id`, `type` (allow/freeze), `schedule_json`, `timezone`. | B |

Every table carries `project_id` (and `workspace_id` where applicable); repository methods require scope arguments (Epic 1 pattern). Reports gain an additive nullable `automation_run_id` (or JSON block) and a minor `report_schema_version` bump.

### 11.6 API surface (illustrative; final names settled in Stories 16.3, 16.6, 16.7)

| Method and path | Purpose |
|-----------------|---------|
| `GET/POST /api/v1/infra-automation/workflows` | List; create draft. |
| `GET/PUT /api/v1/infra-automation/workflows/{id}` | Read; save draft. |
| `POST /api/v1/infra-automation/workflows/validate` | Validate without side effects. |
| `POST /api/v1/infra-automation/workflows/{id}/publish` | Publish a draft. |
| `GET /api/v1/infra-automation/workflows/{id}/revisions` | History. |
| `POST /api/v1/infra-automation/workflows/{id}/runs` | Start a run (supports multipart for `artifact` inputs). |
| `GET /api/v1/infra-automation/runs`, `/runs/{id}` | Filtered list; detail with steps. |
| `POST /api/v1/infra-automation/runs/{id}/cancel` | Cancel. |
| `GET /api/v1/infra-automation/approvals` | Inbox for the caller. |
| `POST /api/v1/infra-automation/approvals/{id}/decision` | Approve or reject. Human principals only. |
| `GET/POST /api/v1/infra-automation/runners` | List; enrollment token; rotate/revoke. |
| `POST /api/v1/infra-automation/webhooks/{trigger_key}` | Inbound trigger. |
| `GET /api/v1/infra-automation/audit` | Filtered events; JSON export. |
| `GET /api/v1/infra-automation/stats/summary` | KPIs and sparklines. |
| `POST /api/v1/infra-automation/ai/compose` | Draft/Explain/Review (returns IR, rendered YAML, validation, rationale; never persists as published). |
| `GET /api/v1/infra-automation/inventory`, `/packages`, `/graph` (B) | Units, packages, edges. |
| `POST /api/v1/infra-automation/ai/map`, `/ai/plan`, `/ai/diagnose` (B) | Mapper, Planner, Diagnostician proposals. |
| `GET/POST /api/v1/infra-automation/plans` (B) | Create/read plan snapshots; accept AI-suggested edges. |
| `GET/POST /api/v1/infra-automation/locks`, `/windows` (B) | Lock state and break; change windows. |

### 11.7 CLI

```
deploywhisper infra-automation validate path/to/workflow.yml
deploywhisper infra-automation compose "pre-flight for prod terraform, approval by service owner" --project payments --workspace prod
deploywhisper infra-automation run prod-terraform-preflight --project payments --workspace prod --input stack_path=infra/network
deploywhisper infra-automation status <run_id>
deploywhisper infra-automation approve <approval_id> --reason "Reviewed blast radius with payments SRE"
deploywhisper runner enroll --server https://dw.example.internal --token <one-time>
deploywhisper runner start --tags terraform,prod-vpc --catalog ./runner-commands.yaml
```

`approve` requires an authenticated human principal and is denied for agent and automation tokens. `compose` prints a proposal to stdout; it never saves or publishes.

---

## 12. Security, Privacy, and Threat Model

Infra Automation introduces the first components that touch user infrastructure (runners), call out to other systems (handoff), and feed repository content to a model (AI). It needs a stricter design than the read-only analysis path.

### 12.1 Trust boundaries

```
[User / UI / API / agent] -> [DeployWhisper server] <-HTTPS, outbound from runner- [Runner in user infra] -> [OpenTofu/Terraform, Ansible, kubectl, helm + local credentials]
                                   |
                                   +-> [llm/ provider boundary] -> [Local model or user-configured external provider] (structured summaries only)
                                   +-> [Allow-listed outbound hosts: Slack, GitHub API, webhooks]
```

- Raw IaC, state, and credentials stay on the runner side. The server receives redacted logs, declared artifacts with digests, and structured outputs.
- Repository content, logs, plan output, registry text, and tickets are untrusted data everywhere, including inside prompts.

### 12.2 Threats and controls

| Threat | Control | Verified by |
|--------|---------|-------------|
| Command injection through parameters | Closed step registry; `command_id` plus schema-validated params; fixed argv; no `shell=True`; runner re-validates locally. | Fuzz tests; runner unit tests. |
| Compromised server sends arbitrary commands to a runner | Runner-side command catalog and allow-list; unknown `command_id` rejected; signed envelopes in Phase C. | Runner rejection tests. |
| Stolen runner token | Short lifetime, project-scoped, hashed, revocable, shown once, rotation; mTLS in Phase C. | Token lifecycle tests. |
| Long-lived cloud keys on runners | Documentation for workload identity/OIDC; optional `require_ephemeral_credentials` (B). | Runner tests; docs review. |
| Credential leakage in logs, outputs, artifacts, audit, prompts | Reference-only secrets; runner-side resolution; redaction at runner and server; Terraform `sensitive` stripped; `*.tfstate` blocked; prompts built from structured summaries. | Redaction corpus; prompt-content tests. |
| SSRF via `notify.*` / `handoff.*` | Admin host allow-list at publish and run time; block loopback, link-local, metadata ranges; no redirects off-list; timeouts and size caps. | SSRF corpus. |
| Approval spoofing or replay | Authenticated human principal; bound to `approval_id`, `report_id`, digests; single-use; audited. | Contract and replay tests. |
| Approving stale or swapped evidence | Evidence pinning; plan-age warning; digest mismatch invalidates. | Pinning tests. |
| Cross-project privilege escalation | Project-scoped repositories and tokens; bounded errors. | Cross-project matrix. |
| Agent self-approval or unattended handoff | Agent/automation tokens cannot approve or publish; validator requires approval ancestor. | Authorization tests. |
| **Prompt injection via repo files, logs, plan text, tickets, registry text** | Untrusted-data handling; structured inputs; schema-constrained outputs; deterministic validation and rendering; no tool use by the model; injection corpus with zero tolerance. | Injection suite (Story 10.4 extended). |
| **Hallucinated steps, units, or packages** | Registry membership checks; unit set equality with detector output/change set; package allow-list; first-seen acknowledgement. | AI validator tests; corpus. |
| **Guardrail erosion** (AI or user prompts weaken controls) | Floors enforced in code; AI cannot edit floors; unsafe-request corpus with zero tolerance. | Unsafe-request set. |
| **Automation bias** (approving because "AI said so") | AI-involvement indicator on the approval card; AI never states safety; evidence-first card layout; four-eyes for AI-assisted prod revisions. | UX review; copy tests. |
| **Data leakage to an external provider** | Data minimization table; local-only mode; no raw artifacts; prompts not stored by default. | Prompt-content tests; settings tests. |
| **AI cost/latency abuse** | Rate limits, size caps, timeouts, budgets; no background calls by default. | Limit tests. |
| Webhook forgery/replay | Hashed token, HMAC, timestamp window, idempotency, rate limiting. | Webhook tests. |
| Resource exhaustion | Concurrency limits, quotas, timeouts, output/artifact caps, retention. | Load and limit tests. |
| Tampered audit | Append-only repository; export includes event digests; optional hash chain (B). | Repository tests. |
| Runner supply chain | Same release controls as the app (SBOM, checksums, signing, provenance: Stories 12.5, 12.6); no bundled third-party IaC binaries. | Release checks. |

### 12.3 Privacy and local-first

- No telemetry and no hosted dependency are added.
- Artifacts live under `data/infra-automation/` with retention controls; plan JSON is treated as sensitive.
- External providers receive structured summaries only (NFR-SEC-02). Logs are never forwarded to a provider except bounded, redacted excerpts for the Diagnostician when AI is enabled.

### 12.4 Security documentation

`docs/infra-automation/security/threat-model.md`, `runner-hardening.md`, `secret-handling.md`, `ai-safety.md`, and an Infra Automation section in `SECURITY.md` describing how to report runner, workflow, and AI-pipeline vulnerabilities.

---

## 13. UX and UI Specification

Grounded in the current UI shown in the screenshot: left navigation (Dashboard, Skills, Incidents with count badge, History, Settings), top bar with search, the project switcher (`Test-Demo`, `main`), the orange primary **Run analysis** action, KPI cards, the recent-analyses table (change, severity, verdict, score, env), and the dark "Latest briefing" card with score ring, blast radius, incident match, and rollback estimate.

### 13.1 Navigation

```
Dashboard
Skills
Incidents          0
Infra Automation   2     <- new; badge = approvals waiting for the current user
History
Settings
```

- Icon: `Workflow` from `lucide-react` (fallback `GitBranch`).
- Routes (SPA root routes, consistent with `/history`, `/settings`): `/infra-automation`, `/infra-automation/workflows/:key`, `/infra-automation/runs/:id`, `/infra-automation/approvals`, `/infra-automation/runners`; Phase B adds `/infra-automation/inventory` and `/infra-automation/plans/:id`.
- Scope follows the existing **ProjectSwitcher**. Workspace labels (`main`, `qa`) use the same ENV pattern as the analyses table.
- When disabled, the page shows an enablement panel (what it does, tiers, how to enable, docs link).

### 13.2 Design-system reuse

Reuse KPI card, table with severity/verdict chips, score bar, dark briefing card, status chips (including the green "Evidence Law enforced" chip), orange primary button, and project switcher. Per Story 15.2, any new primitive (step timeline, digest chip, YAML editor wrapper, assistant panel, stage graph) is built in `src/components/ui/`, added to `/dev/components`, and covered by Vitest snapshots. Exact visual values follow `docs/design/deploywhisper-redesign-v3.jsx`. UI verification runs only against the composed app at `http://localhost:8080/`.

### 13.3 Landing page (information budget)

Only these elements:

1. Header: title, scope line, **Evidence Law enforced** chip, primary action **Run workflow**, secondary **New workflow**.
2. Four KPI cards: **Workflows**, **Runs (7-day)**, **Awaiting approval**, **Median run time**.
3. Tabs: **Runs** (default), **Workflows**, **Approvals**, **Runners**; Phase B adds **Inventory** and **Plans**.
4. Runs table (five rows, "View all"): workflow, trigger, state chip, verdict chip and score from the linked report, env, duration.
5. Right-hand dark **Approval briefing** card for the oldest pending approval assigned to the user, or an empty state.

```
Infra Automation                                         [ New workflow ]  [ > Run workflow ]
Evidence-gated workflows . Test-Demo                                      ( Evidence Law enforced )

[ Workflows 4 ] [ Runs . 7d 23 ] [ Awaiting approval 2 ] [ Median run time 1m 12s ]

Runs | Workflows | Approvals (2) | Runners (1) | Inventory | Plans
+----------------------------------------------------+   +--------------------------------+
| WORKFLOW            TRIGGER   STATE   VERDICT  ENV |   | APPROVAL BRIEFING     WAITING  |
| prod-tf-preflight   webhook   waiting CAUTION  prod|   |  (42/100 ring)  CAUTION        |
| review-uploaded     manual    ok      PROCEED  qa  |   |  Blast radius 3 . Rollback 2   |
| ansible-audit       manual    failed  --       main|   |  Handoff: acme/infra apply.yml |
| ...                                                |   |  [ Review & decide > ]         |
+----------------------------------------------------+   +--------------------------------+
```

### 13.4 Workflow editor and Assistant

- Two-pane layout: YAML editor (CodeMirror 6 if approved in D6, else a monospaced `<textarea>`) and a **Validation** panel listing errors by line with documentation links, plus a read-only step-graph preview.
- Actions: **Save draft**, **Validate**, **Publish**, **Run**. Drafts are labeled "Never executed". AI-assisted drafts carry an **AI-assisted** chip.
- **Assistant** side panel (UX-DR19) with modes **Draft / Explain / Review**:

```
+ Assistant ------------------------------------------+
| ( Draft ) ( Explain ) ( Review )          AI-generated|
| "Pre-flight for prod Terraform with service-owner     |
|  approval, then dispatch to the apply workflow"       |
|                                         [ Generate ]  |
|------------------------------------------------------|
| Validator: passes (0 errors, 1 warning)               |
| Floors: GRD-1 ok . GRD-3 ok . GRD-6 requires 2nd reviewer
| Diff vs current draft  (+24 / -0)                     |
| Rationale . Assumptions (1) . Warnings (1)            |
| [ Apply to draft ]   [ Discard ]     Audit record >   |
+------------------------------------------------------+
```

- **Run workflow** dialog renders typed inputs (including file upload for `artifact` inputs) from the definition and validates before starting.
- Revision drawer: history, author (human / AI-assisted), digest, **Restore as draft**.

### 13.5 Run detail

- Sticky header: workflow, run id, state chip, trigger, actor, started/duration, environment.
- Left: vertical **step timeline** (state, attempts, runner name, duration, redacted log drawer with a "redacted" indicator).
- Right: **Linked briefing** (score ring, recommendation, Evidence Law status, top finding, **Open full briefing**); **Artifacts** (name, size, sha256 copyable, redaction status, collected-at, plan-age warning); **Compare with previous run**; on failure, **Diagnose** (Phase B) showing the rule-based signature first, then the AI explanation labeled AI-generated.
- Tabs: Overview, Steps, Artifacts, Audit.

### 13.6 Approval experience (signature screen)

```
Approval requested . prod-terraform-preflight . run 7f3a
+------------------------------------------------------------------+
| (42/100)  CAUTION . Severity Medium . Evidence Law: satisfied    |
| Why not lower / higher  (expandable)                             |
| Top findings (3)   [evidence]   Blast radius 3   Rollback est. 2 |
| Packages: 1 first-seen (acknowledge) . 0 non-allow-listed        |   <- Phase B
| Context TODOs: add Terraform state connector for prod            |
|------------------------------------------------------------------|
| Pinned evidence:  report #482   plan.json sha256 9c1e...a7f2     |
| Plan collected 12 min ago (fresh)   Draft origin: AI-assisted    |
| If approved: dispatch acme/infra apply.yml@main with report id   |
|------------------------------------------------------------------|
| Reason (required)  [____________________________________]      |
| ( Reject )                                  ( Approve handoff )  |
+------------------------------------------------------------------+
```

- High/critical or `no_go` requires typed confirmation in addition to a reason.
- If pinned evidence changed: "Evidence changed - approval no longer valid"; approval disabled.
- Single-operator mode banner: "Single-operator mode: approvals are recorded as acknowledgements; separation of duties is unavailable."
- Copy never implies DeployWhisper deploys anything.

### 13.7 Runners tab

Table: name, tags, projects, version, status (online/stale/offline), last seen, current task. Actions: **Add runner** (one-time enrollment command and token), **Rotate token**, **Revoke**. A helper links to Docker, Kubernetes, and systemd guides.

### 13.8 Inventory and Plan views (Phase B)

- **Inventory:** tabs **Units** and **Packages**. Units show type, layer, owner, runner tags, workspaces, and origin (deterministic / declared / AI-accepted). Packages show ecosystem, name, constraint, resolved version, pinned, first-seen, allow-list status, and the units that use them. A **Discover** wizard runs deterministic detection, then offers the AI Mapper's proposal as a diff.
- **Plan view:** waves as ordered rows with the units in each wave, rationale, and edge basis chips. **AI-suggested edges** appear in a separate list with **Accept** and **Dismiss**. A **Graph** toggle renders a layered SVG, always paired with an equivalent table (UX-DR22). Open questions and context TODOs sit above the fold. Plan digest is shown and is what approvals pin.

```
Plan . 3 waves . digest 4be1...90cd . built from 3 changed units + 2 packages
Wave 1  terraform:infra/network       basis: declared, layer_rule
Wave 2  terraform:infra/eks           basis: remote_state          needs: Wave 1
Wave 3  helm:platform/ingress         basis: declared              needs: Wave 2
AI-suggested edges (1)   helm:platform/ingress -> terraform:infra/dns   [ Accept ] [ Dismiss ]
Open questions (1)       No owner found for helm:platform/ingress
```

### 13.9 States and accessibility

| State | Behavior |
|-------|----------|
| Loading | Skeletons consistent with existing screens. |
| Empty (no workflows) | Template picker: pre-flight (Terraform), review an uploaded plan, Ansible check-mode audit, Kubernetes diff check, ITSM request to handoff, drift detection (B). |
| Disabled | Enablement panel. |
| Error | Actionable message with docs link (UX-DR9). |
| AI unavailable | Assistant shows the reason (local-only mode, no provider, timeout) and offers the template picker. |
| Narrative degraded | Same treatment as report screens; deterministic content remains. |
| No eligible runner | Run fails with message naming required tags and a link to Runners. |

Accessibility: full keyboard operation of editor actions, Assistant, timeline, drawers, decision form, and graph alternative; focus trap/restore in dialogs; `aria-live` announcements for run state changes and AI results; state never conveyed by color alone; axe and keyboard smoke tests for all Infra Automation routes (UX-DR18).

---

## 14. Non-Functional Requirements

Targets marked (T) are initial and validated in Stories 16.18 and 16.30; results are published honestly.

| ID | Requirement |
|----|-------------|
| NFR-IAU-01 | **Durability:** no loss of run or approval state across restart or crash; fault injection covers crash after every transition. |
| NFR-IAU-02 | **Delivery semantics:** at-least-once with idempotency keys; duplicate completions are harmless. |
| NFR-IAU-03 | **Orchestration overhead (T):** p95 under 1 s between a step finishing and the next server-side step starting, excluding runner time. |
| NFR-IAU-04 | **Claim latency (T):** p95 under 2 s from enqueue to claim with 20 online runners. |
| NFR-IAU-05 | **Capacity (T):** SQLite single node: at least 10 concurrent runs. PostgreSQL: at least 100. |
| NFR-IAU-06 | **Validation latency (T):** p95 under 500 ms for a 50-step workflow. |
| NFR-IAU-07 | **Isolation:** no cross-project access to any object (tested matrix). |
| NFR-IAU-08 | **Redaction:** zero known secret patterns in persisted logs, outputs, artifacts, audit, or stored AI summaries. |
| NFR-IAU-09 | **Graceful degradation:** runner outage, AI failure, narrative failure, or notification failure never corrupts run state or blocks deterministic analysis. |
| NFR-IAU-10 | **Evidence Law:** zero violations from automation-originated reports in CI fixtures. |
| NFR-IAU-11 | **Operability:** structured logs without secrets; metrics for runs, step durations, queue depth, runner health, approval wait, AI calls and outcomes (extends NFR-OPS-06). |
| NFR-IAU-12 | **Portability:** SQLite and PostgreSQL; additive reversible migrations where practical. |
| NFR-IAU-13 | **Accessibility:** per Section 13.9. |
| NFR-IAU-14 | **Documentation:** not done without Section 15.2 docs. |
| NFR-IAU-15 | **AI latency (T):** Composer draft p95 under 20 s with a hosted provider; local model results reported, no hard target in v1. |
| NFR-IAU-16 | **AI safety invariants:** unsafe-acceptance, injection-success, order-violation, coverage-error, and unsafe-suggestion rates are **zero** on the corpus; any regression blocks release. |
| NFR-IAU-17 | **Planner scale (T):** deterministic plan for up to 200 units and 500 edges in under 2 s; larger inputs degrade with explicit skipped-scope output (NFR-PERF-02). |

---

## 15. Open-Source Commitments, Governance, and Documentation

### 15.1 Commitments specific to this feature

- All capabilities - runners, approvals, RBAC integration, audit, self-service, AI assistance, package governance - are MIT-licensed in the public repository; none is reserved for a paid tier; no hosted service is introduced.
- Tier 2 cannot be added without a public RFC (Story 0.4 process), a PRD 4.4 amendment, and a new ADR.
- New maintainer area **Infra Automation** in `MAINTAINERS.md`; CODEOWNERS entries for `/infra_automation/`, `/models/infra_automation.py`, `/api/routes/infra_automation.py`, `/docs/infra-automation/`, `/frontend/src/features/infra-automation/`, and `/benchmarks/corpus/v1/infra-automation/`.
- A security contact path for runner, workflow, and AI-pipeline vulnerabilities.
- Failure signatures, workflow templates, runner command-catalog entries, and package risk patterns are designed for community contribution with tests.

### 15.2 Documentation deliverables

```
docs/infra-automation/
  index.md
  concepts/
    workflows.md
    capability-tiers.md
    autonomy-levels.md
    guardrail-floors.md
    approvals-and-evidence-pinning.md
    runners.md
    gates.md
    iac-units-and-packages.md
    orchestration-graph-and-stage-plans.md
    ai-assistance.md
  getting-started/
    enable-infra-automation.md
    first-workflow-uploaded-plan.md
    first-workflow-with-a-runner.md
    install-a-runner-docker.md
    install-a-runner-kubernetes.md
    install-a-runner-systemd.md
    restricted-network.md
  guides/
    terraform-preflight.md
    ansible-check-mode-audit.md
    kubernetes-diff-check.md
    helm-and-kustomize.md
    package-governance.md
    drift-detection.md
    promotion-dev-stage-prod.md
    github-actions-handoff.md
    itsm-webhook-intake-and-callback.md
    slack-notifications.md
    local-ai-with-ollama.md
    integrating-with-kestra-argo-jenkins.md
  reference/
    workflow-schema.md
    infra-map-schema.md
    ir-schemas.md
    step-catalog.md
    template-syntax.md
    runner-command-catalog.md
    failure-signatures.md
    api.md
    cli.md
    audit-events.md
  security/
    threat-model.md
    runner-hardening.md
    secret-handling.md
    ai-safety.md
  operations/
    sizing-and-limits.md
    retention.md
    backup-restore.md
    troubleshooting.md
  ai/
    capabilities-and-data-sent.md
    evaluation-results.md
  comparisons/
    deploywhisper-infra-automation-alongside-orchestrators.md
```

Docs CI must catch broken links and drift between JSON Schemas, step catalog, API reference, and CLI help (DOC-31). README, ROADMAP, CHANGELOG, release notes, and upgrade notes are updated; docs state clearly that Tier 2 does not exist.

---

## 16. Success Metrics

| Metric | Target | Source |
|--------|--------|--------|
| Time to first workflow run (uploaded-plan workflow, no runner) | Under 10 minutes following docs | Friendly-user trials |
| Time to first runner-collected pre-flight | Under 30 minutes following docs | Friendly-user trials |
| Share of published workflows containing `analyze` | At least 90% | Local DB analytics (no external telemetry) |
| Evidence Law violations from automation-originated reports | 0 | CI fixtures; benchmark runner |
| Cross-project leakage test failures | 0 | Authorization matrix |
| Secrets found in persisted data | 0 | Redaction corpus |
| AI safety invariants (Section 8.9 zero-tolerance set) | 0 failures | AI corpus |
| Composer first-pass validity / validity after repair | Baseline in v1.4.0, improve each release | AI corpus |
| Composer drafts accepted (applied to draft) | Tracked; no target | `infra_automation_ai_runs` |
| Median approval wait time | Tracked | Approvals table |
| Approvals invalidated by evidence change | Tracked (pinning working) | Approvals table |
| Runs recovered after forced restart | 100% in fault-injection tests | Story 16.18 |
| Package signals surfaced that reviewers marked useful | Tracked from feedback (Story 4.5 pattern) | Feedback events |
| Order violations / coverage errors in stage plans | 0 | Planner corpus |
| External contributions (templates, signatures, catalog entries, docs) | At least 3 within 90 days of v1.4.0 | GitHub |

---

## 17. Implementation Guide After Story 12.2

This section is the working plan. It tells you what to do next, in what order, what to build on the **backend** and the **frontend** for each story, and how the remaining stories (12.3-12.8, Epic 13, Epic 14) change. File names are proposals aligned with your repository shape; verify exact locations against `_bmad-output/project-context.md` and `docs/ui-migration-plan.md` before each story.

### 17.1 Operating loop (BMAD, per your `AGENTS.md`)

**Once, now (planning changed materially, so do not skip):**

1. Run `bmad-help`; read `_bmad-output/project-context.md` (mandatory) and confirm assumptions A1-A8.
2. Run `bmad-correct-course` to record the scope change (new Epic 16).
3. Update planning artifacts in the same workstream: append this PRD (or add it as `prd-infra-automation.md`), add Epic 16 to `epics.md` with the FR coverage map (Section 17.9), add ADRs to `architecture.md` (Section 17.10).
4. Run `bmad-check-implementation-readiness`, then `bmad-sprint-planning` to add `16-*` entries to `sprint-status.yaml`.

**For every story:** `bmad-create-story` -> `bmad-dev-story` -> `bmad-code-review` -> fix -> update `sprint-status.yaml` and verification notes. For the high-risk stories (16.7 approvals, 16.9 outbound, 16.12-16.13 runner, 16.16 AI, 16.24 planner) also run `bmad-review-adversarial-general` and `bmad-review-edge-case-hunter`. After each wave, run `bmad-retrospective`.

**Delivery style:** vertical slices behind the feature flag. Every story ends with something runnable, tested, documented, and demoable on the composed app. Use small increments (AGENTS.md).

**Validation commands (from your repo):**

```
./.venv/bin/python -m unittest discover -q
./.venv/bin/ruff check . && ./.venv/bin/ruff format --check .
bash scripts/ci-local.sh
npm run ui:typecheck && npm run ui:test && npm run ui:build
docker compose up -d --build
curl -fsSL http://localhost:8080/api/v1/health
BASE_URL=http://localhost:8080 npm run test:ui-review
```

Frontend verification happens only against the composed app at `http://localhost:8080/`, never the Vite dev server.

### 17.2 Recommended execution order after Story 12.2

Sizes are relative (S/M/L/XL); calendar estimates depend on your team and are intentionally omitted.

| Order | Wave | Story | Area | Size | Why now / dependency |
|-------|------|-------|------|------|----------------------|
| 1 | 0 | **12.2 close-out** | BE | S | Finish review. Confirm provider capability metadata (structured output, local-only) is reachable from the service layer; Composer depends on it. |
| 2 | 0 | **16.0** Course correction and planning artifacts | Planning | S | Makes the plan official before code (AGENTS.md). |
| 3 | 1 | **12.3 (expanded)** Connector credential handling and redaction audit | BE | M | Must precede anything that handles runner/webhook/handoff secrets. Expanded ACs in 17.3. |
| 4 | 1 | **16.1** Workflow schema, validator, guardrail floors | BE | L | Foundation for everything; also the AI safety backbone. |
| 5 | 1 | **16.2** Persistence, feature flag, settings, audit table | BE + small FE | M | Tables, flag, engine lease, Settings toggle. |
| 6 | 1 | **12.4 (minor change)** Scorecard and CodeQL | CI | S | Parallel, any time; scope paths updated. |
| 7 | 2 | **16.3** Workflow service and API | BE | M | CRUD, revisions, validate, publish. |
| 8 | 2 | **16.4** Nav entry, routes, workflow editor | FE | L | "Infra Automation" appears in the sidebar. |
| 9 | 3 | **16.5** Engine, state machine, server steps (analyze, gate) | BE | XL | Core. Runner-less end-to-end starts here. |
| 10 | 3 | **16.6** Runs API, runs list and run detail | BE + FE | L | First visible runs and linked briefing. |
| 11 | 4 | **16.7** Approvals and identity modes | BE | L | Durable pause, pinning, principals. |
| 12 | 4 | **16.8** Approvals inbox and approval briefing | FE | L | Signature screen. |
| 13 | 4 | **16.9** Handoff and outbound controls | BE + FE | L | Notify, handoff, SSRF, allow-list. **Milestone M1** (upload plan -> analyze -> gate -> approve -> notify). |
| 14 | 4 | **16.10** Credentials, redaction, secret references | BE | M | Builds on 12.3. |
| 15 | 4 | **16.11** Audit trail | BE + FE | M | Export and UI. |
| 16 | 5 | **12.5 (expanded)** SBOM and checksums | CI | M | Before the runner ships. |
| 17 | 5 | **12.6 (expanded)** Signing and provenance | CI | M | Before the runner ships. |
| 18 | 5 | **16.12** Runner agent, enrollment, protocol | BE + CLI + FE | XL | Outbound runner and Runners tab. |
| 19 | 5 | **16.13** Command catalog and collect steps | BE (runner) | L | Terraform/OpenTofu, Ansible, kubectl, Helm, Git. |
| 20 | 5 | **16.14** Evidence provenance and report linkage | BE + FE | M | Evidence Law for automation-originated reports. |
| 21 | 5 | **16.15** Webhook intake and CLI | BE | M | **Milestone M2** (runner-collected pre-flight). |
| 22 | 6 | **16.16** AI Workflow Composer | BE + FE | XL | Draft, Explain, Review. |
| 23 | 6 | **13.1** Docs information architecture | Docs | S | So Infra Automation docs have a home. |
| 24 | 6 | **12.7 (expanded)** Backup, restore, upgrade, retention docs | Docs | M | Includes new tables and artifacts. |
| 25 | 6 | **12.8 (expanded)** Air-gapped guide | Docs | M | Runner, package mirrors, local AI. |
| 26 | 6 | **16.17** Templates, docs, integration recipes | Docs + BE/FE small | M | Template picker, docs tree. |
| 27 | 6 | **16.18** Verification gate and benchmarks | QA | L | **Release v1.4.0** (Phase A; flag default off). |
| 28 | 6 | **13.2-13.8** Remaining docs stories (with additions) | Docs | M | Additions listed in 17.3. |
| 29 | 7 | **16.19** Infra map and IaC unit detection | BE + FE | L | Phase B starts. |
| 30 | 7 | **16.20** Package inventory and package evidence | BE + FE | XL | Parsers, ledger, signals, allow-list. |
| 31 | 7 | **16.21** Orchestration graph and stage plan | BE + FE | XL | Deterministic edges and waves. |
| 32 | 7 | **16.22** Stage execution and promotion | BE + FE | L | `orchestrate` expansion, per-stage approvals. |
| 33 | 7 | **16.23** AI Infra Mapper | BE + FE | M | |
| 34 | 7 | **16.24** AI Orchestration Planner | BE + FE | L | |
| 35 | 7 | **16.25** Run Diagnostician and failure signatures | BE + FE | M | |
| 36 | 7 | **16.26** Schedules, drift detection, event triggers | BE + FE | L | Cron ADR. |
| 37 | 7 | **16.27** Agent/MCP surface | BE | M | |
| 38 | 7 | **16.28** Scale, locks, change windows, observability | BE + FE | L | |
| 39 | 7 | **16.29** More handoff adapters and Git sync | BE + FE | M | |
| 40 | 7 | **16.30** AI evaluation and hardening gate | QA | L | **Release v1.5.0.** |
| - | 8 | **16.31-16.33** Tier 2, mTLS, isolation profiles | Gated | - | Only after an accepted RFC. |
| parallel | - | **Epic 14** (14.1-14.5, adjusted) | Governance | - | Low coupling; run alongside Wave 6 onward. |

**Milestones:** M1 after 16.9 (end-to-end without a runner). M2 after 16.15 (runner-collected pre-flight). M3 at v1.4.0 (AI Composer, docs, verification). M4 after 16.22 (orchestrated estate). M5 at v1.5.0 (AI Mapper, Planner, Diagnostician, evaluation).

### 17.3 Changes to existing stories

| Story / Epic | Change | Reason |
|--------------|--------|--------|
| **12.2** | Close-out checklist only: provider capability metadata reachable from services; no scope change. | Composer prerequisite. |
| **12.3** | **Expanded acceptance criteria** (below). | New credential classes. |
| **12.4** | Add `infra_automation/` and `frontend/src/features/infra-automation/` to CodeQL scope; add a CI gate that fails on `eval`, `exec`, `shell=True`, or template-engine imports under `infra_automation/`. | Enforces "no code evaluation" (IAU-WF-04). |
| **12.5** | SBOM and checksums include the runner entry point and reference Dockerfile. Any published runner image must not bundle third-party IaC binaries with restrictive licenses. | Runner is distributed software. |
| **12.6** | Signing/provenance cover runner distribution; docs show how to verify before enrollment. | Runner trust. |
| **12.7** | Backup/restore/upgrade/retention docs add `infra_automation_*` tables, `data/infra-automation/` artifacts, retention settings, behavior of in-flight runs after restore, and runner re-enrollment. | New persistent state. |
| **12.8** | Air-gapped guide adds: runner in restricted networks, package allow-list and mirrors, local-only AI with Ollama and its limitations, and no registry lookups. | Restricted-network operation. |
| **13.1** | Add `docs/infra-automation/` (Section 15.2) to the IA. | |
| **13.2** | First-analysis guide links to "Automate this review". | |
| **13.3** | API and schema references add infra-automation endpoints, workflow/infra-map/IR schemas, and the report `automation` block. | |
| **13.4** | CLI and agent references add `infra-automation` and `runner` commands, `compose`, and (Phase B) agent tools. | |
| **13.5** | Connector guides add runners and the optional package-registry connector. | |
| **13.6** | Workflow integration guides add GitHub dispatch, ITSM webhook, Slack, and Kestra/Argo/Jenkins recipes. | |
| **13.7** | Docs CI validates every workflow in `examples/infra-automation/` with the real validator and checks JSON Schema drift. | |
| **13.8** | Release/upgrade notes for v1.4.0 (flag default off) and v1.5.0. | |
| **14.1 / 14.3 / 14.4 / 14.5** | Checklist, maintainer areas (add Infra Automation), health metrics, and the application package mention the subsystem and its governance (tiers, RFC). | |
| **Epic 4** | Package risk patterns added to the public library (16.20). | |
| **Epic 6** | Infra Automation corpus and AI evaluation added (16.18, 16.30). | |
| **Epic 9 (Skills)** | Skills may carry an `infra-automation` tag; Composer and Planner load them by trust level. Skills remain non-executable. | |
| **Epic 10** | AI-agent docs add Infra Automation boundaries; interface extended in 16.27. | |
| **Epic 11** | Floors reuse adapter field names; docs map floors to adapter modes. | |
| **Epic 15** | Add `docs/design/infra-automation-ux.md`; Dashboard budget unchanged; report Audit tab gains a provenance chip (16.14). | |

**Expanded acceptance criteria for Story 12.3**

- **Given** runner enrollment tokens, runner tokens, webhook trigger tokens, HMAC secrets, GitHub dispatch tokens, outbound webhook URLs that embed secrets, and AI-provider usage for Infra Automation **When** they are configured, used, logged, rendered, or exported **Then** they are held only as hashed values or environment-backed references and never appear in the database in clear text, logs, prompts, reports, audit events, or stored AI summaries.
- **Given** the redaction corpus **When** tests run **Then** it covers cloud keys, GitHub tokens, Kubernetes tokens, bearer headers, URLs with credentials, SSH/PEM keys, JWTs, and Terraform `sensitive` values, with zero leaks.
- **Given** the credential helpers **When** this story is done **Then** a reusable `SecretRefResolver` (server, environment-backed) and a token-hashing utility (random 32-byte tokens, SHA-256 digest, constant-time comparison) exist for Stories 16.9, 16.12, and 16.15 to reuse.

### 17.4 Phase A - story playbook (target v1.4.0)

Format for each story: **Backend**, **Frontend**, **Tests**, **Docs**, **Acceptance criteria**. Where a story has no frontend work, that is stated.

#### Story 16.0: Course Correction and Planning Artifacts

As a maintainer, I want the new scope recorded in the planning artifacts before code is written, so that the feature extends DeployWhisper without contradicting its advisory-first identity.

- **Backend / code:** none.
- **Do:** run `bmad-correct-course`; write the RFC (Story 0.4 process) covering Tiers 0/1/2, autonomy levels, hard rules (Section 4.4), and decisions D1-D10; amend PRD 4.4 wording (read-only collection and user-approved handoff; execution needs a further RFC); add ADRs (Section 17.10); add Epic 16 to `epics.md`; update the traceability matrix (Story 0.3); add the Infra Automation area to `MAINTAINERS.md` and CODEOWNERS; run `bmad-check-implementation-readiness` and `bmad-sprint-planning`.
- **Docs:** README roadmap line; `ROADMAP.md`.

**Acceptance Criteria:**
**Given** this PRD is proposed **When** the RFC is accepted **Then** PRD 4.4, `epics.md`, `architecture.md`, and `sprint-status.yaml` reflect Epic 16 **And** Tier 2 is explicitly marked out of scope until a further RFC.
**Given** readiness validation runs **When** it completes **Then** no unresolved planning gaps remain for Stories 16.1-16.18.

#### Story 16.1: Workflow Schema, Validator, and Guardrail Floors

As a platform engineer, I want a strict, versioned workflow format with a validator, so that mistakes and unsafe definitions are caught before anything runs.

- **Backend:**
  - `infra_automation/schema/workflow.py`: Pydantic models with a discriminated union on step `type`; export JSON Schema to `schemas/infra-automation/workflow.v1.schema.json` through a script, with a test that fails if the checked-in file is stale.
  - `infra_automation/registry.py`: closed step registry (param model, tier, `runs_on`, idempotency default).
  - `infra_automation/templating.py`: substitution-only resolver (allowed roots `inputs`, `steps`, `run`, `project`; dotted paths only; no calls or operators).
  - `infra_automation/validator/`: one module per rule group returning `Issue(code, path, message, doc_url)`; DAG check (Kahn), ancestor computation for GRD-1, secret-pattern detection reusing the existing redaction patterns, template reference resolution.
  - `infra_automation/validator/floors.py`: GRD-1..GRD-10 evaluated against a `PolicyContext` (workspace tier, identity mode, allow-lists).
  - Load YAML with `yaml.safe_load` only; reject anchors/aliases and cap input size (suggested 256 KB) to prevent expansion attacks.
- **Frontend:** none.
- **Tests:** table-driven `unittest` over `tests/infra_automation/fixtures/workflows/{valid,invalid}/*.yml`; template resolver property tests; a grep-style test that fails on `eval`, `exec`, `shell=True`, or template-engine imports in `infra_automation/`.
- **Docs:** `reference/workflow-schema.md`, `concepts/guardrail-floors.md` (first drafts).

**Acceptance Criteria:**
**Given** a workflow YAML **When** validation runs **Then** every rule in Section 10.6 is enforced with field-level errors and documentation links **And** the JSON Schema file matches the models.
**Given** a definition with an unknown step type, an inline secret-like value, or a handoff without an approval ancestor **When** validation runs **Then** it fails with an actionable message.

#### Story 16.2: Persistence, Feature Flag, Settings, and Audit Table

As a platform admin, I want durable, project-scoped storage and a safe default-off switch, so that state survives restarts and the feature is opt-in.

- **Backend:**
  - Alembic migration for the Phase A tables in Section 11.5 (additive; indexes on `project_id`, `state`, `lease_expires_at`).
  - `models/infra_automation.py` and `models/repositories/infra_automation_*.py`; every repository method requires explicit scope arguments and fails fast without them; published revisions and audit events expose no update/delete.
  - `config.py`: `DEPLOYWHISPER_INFRA_AUTOMATION_ENABLED` (default false); DB-stored non-secret settings via the same pattern as provider settings (Story 12.2); FastAPI dependency `require_infra_automation_enabled` for all routes.
  - Audit sink: `AuditRepository.append(...)` (events wired progressively; completed in 16.11).
- **Frontend:** Settings page gains an **Infra Automation** section with the enable toggle and read-only defaults; consumes `GET/PUT /api/v1/infra-automation/settings`.
- **Tests:** migration up/down on SQLite (and PostgreSQL where a lane exists); repository scope tests; flag-off returns a bounded "disabled" response.
- **Docs:** `getting-started/enable-infra-automation.md`.

**Acceptance Criteria:**
**Given** the migration runs on a copy of the current database **When** it completes **Then** existing data is untouched and the new tables exist with project scope columns.
**Given** the flag is off **When** any Infra Automation route is called **Then** it returns a documented disabled response and the engine does not start.

#### Story 16.3: Workflow Service and API

As a platform engineer, I want to save drafts, validate, publish revisions, and restore earlier versions, so that live automation is never changed by unfinished work.

- **Backend:** `services/infra_automation_service.py` (create/update draft, validate, publish into a new immutable revision, restore as new draft, archive); `api/routes/infra_automation.py` and `api/schemas/infra_automation.py` for the workflow endpoints in Section 11.6; RBAC through the Story 1.5 role helpers (Maintainer or Project Admin may save/publish; Reviewer/Viewer read); publish runs the full validator including floors and the outbound allow-list; audit events for create/edit/publish/archive.
- **Frontend:** none (types regenerated through the existing OpenAPI step so Story 16.4 can consume them).
- **Tests:** API contract tests, role matrix, revision immutability, publish-blocking floors.
- **Docs:** `reference/api.md` (workflow section).

**Acceptance Criteria:**
**Given** a draft revision exists **When** any trigger fires **Then** only the last published revision runs.
**Given** a user without Maintainer or Project Admin rights **When** they save or publish **Then** the request is denied with a bounded error and an audit event.

#### Story 16.4: Frontend - Nav Entry, Routes, and Workflow Editor

As a user, I want Infra Automation in the left menu and an editor that validates as I type, so that I can create workflows without the CLI.

- **Frontend:**
  - Add the **Infra Automation** item to the sidebar navigation (find the component that renders Dashboard, Skills, Incidents, History, Settings), after Incidents and before History, with the `Workflow` icon and a badge slot (hidden until Story 16.8).
  - Register routes `/infra-automation`, `/infra-automation/workflows/:key` in React Router; lazy-load the feature chunk; add SPA fallback coverage in tests.
  - `frontend/src/features/infra-automation/`: `OverviewPage` (header, KPI row placeholder, **Workflows** tab only for now), `WorkflowEditorPage`, `components/ValidationPanel`, `components/DigestChip`, `components/RevisionDrawer`, hooks `useWorkflows`, `useWorkflow`, `useValidateWorkflow` (debounced mutation), `usePublishWorkflow`.
  - Disabled state: enablement panel with link to docs; empty state with "New workflow".
  - YAML editor: `<textarea>` with monospaced styling by default; CodeMirror 6 only if D6 is approved by an ADR.
  - New primitives added to `src/components/ui/` and to `/dev/components` with Vitest snapshots.
- **Backend:** none beyond 16.3.
- **Tests:** Vitest for components and hooks; Playwright `infra-automation-workflows.spec.ts` against the composed app (create draft, see validation errors, fix, publish); axe and keyboard smoke for the new routes.
- **Docs:** `design/infra-automation-ux.md` (first draft).

**Acceptance Criteria:**
**Given** the SPA loads **When** the sidebar renders **Then** Infra Automation appears after Incidents and before History using the existing nav component **And** the Dashboard is unchanged.
**Given** I edit YAML **When** validation errors exist **Then** they appear by line with documentation links, and **Publish** is disabled until errors clear **And** drafts are labeled "Never executed".

#### Story 16.5: Engine, State Machine, and Server-Side Steps

As a platform engineer, I want runs to execute reliably inside the existing process, so that no new infrastructure is required and no state is lost on restart.

- **Backend:**
  - `infra_automation/engine/`: `state.py` (enums and legal-transition table), `scheduler.py` (ready-step selection), `executor.py` (dispatch by `runs_on`), `leases.py` (engine leader lease and step leases), `loop.py` (asyncio task started from the FastAPI lifespan when the flag is on and the lease is held).
  - Persist-before-side-effect: each transition commits before dispatch; idempotency key per step.
  - `infra_automation/steps/analyze.py`: builds the bundle from artifact inputs, calls the shared orchestrator (`services/analysis_service.py`) with project/workspace scope, sets `trigger_ref = infra-automation:<run_id>`, returns `report_id`, `recommendation`, `severity`, `score`, `evidence_law_status`. **No scoring logic here.**
  - `infra_automation/steps/gate.py`: reads report fields; returns `stop | needs_approval | proceed`.
  - `artifact` input type: multipart upload stored under `data/infra-automation/<run_id>/` with sha256, passed through existing intake (classification, sensitive-file blocking).
  - Crash-test hook: a test-only injector that raises after chosen transitions.
- **Frontend:** none.
- **Tests:** transition-table tests (only legal transitions), fake-clock engine tests, fault injection after every transition with restart recovery, parallel-branch tests, retry/backoff/timeouts, `analyze` integration test using a synthetic plan JSON.
- **Docs:** `concepts/workflows.md`, `concepts/gates.md`.

**Acceptance Criteria:**
**Given** a published workflow with `analyze` and `gate` **When** a run starts **Then** transitions are persisted before side effects, ready steps execute (parallel branches allowed), and the run ends in an explicit terminal state.
**Given** the process is killed at any point **When** it restarts **Then** in-flight runs resume or fail explicitly with no duplicated non-idempotent side effects.
**Given** an `analyze` step **When** it completes **Then** the persisted report is an ordinary report with no duplicated scoring logic and Evidence Law enforced.

#### Story 16.6: Runs API, Runs List, and Run Detail

As a reviewer, I want to follow a run step by step, so that I understand what happened and why.

- **Backend:** endpoints to start (with multipart for `artifact` inputs), list (filters: workflow, state, trigger, date), get detail, cancel; redacted log retrieval; `GET /stats/summary` (KPIs and 7-day sparkline buckets); polling-friendly `ETag` or `updated_at` fields. No websockets in the baseline.
- **Frontend:**
  - **Runs** tab (default) with the five-row table pattern ("View all"), state chips, verdict chip and score from the linked report, ENV column.
  - KPI cards (Workflows, Runs 7-day, Awaiting approval, Median run time) reusing the KPI card with sparklines.
  - **Run workflow** dialog generated from workflow inputs (reuse the Dashboard upload component for `artifact` inputs).
  - `RunDetailPage`: sticky header, `StepTimeline`, redacted log drawer, **Linked briefing** mini-card (reuse report summary components), **Artifacts** list with `DigestChip`; TanStack Query polling with `refetchInterval` while non-terminal.
  - `aria-live` announcements for state changes.
- **Tests:** API contract tests; Playwright e2e (upload sample plan -> run -> open linked briefing); axe; Vitest for timeline states.
- **Docs:** `getting-started/first-workflow-uploaded-plan.md`.

**Acceptance Criteria:**
**Given** a run exists **When** I open it **Then** I see the step timeline, redacted logs, artifacts with sha256, and the linked briefing **And** state changes are announced to assistive technology.
**Given** a user without access to the project **When** they request the run **Then** the response does not reveal whether it exists.

#### Story 16.7: Approvals and Identity Modes (Backend)

As an SRE approver, I want to approve a handoff knowing which evidence I am approving, so that my decision is informed and defensible.

- **Backend:**
  - `infra_automation/steps/approval.py` and `services/infra_automation_approval_service.py`: request (record `pinned_report_id`, `pinned_digests`), decide (single-use, idempotent), expire (engine tick sweeper), invalidate on pin mismatch.
  - Principal types `human | automation | agent` on the auth dependency (add `principal_type` if absent); the decision endpoint accepts `human` only.
  - Identity modes: `single_operator` (decision stored as acknowledgement; separation of duties unavailable) and `multi_user` (enforces `separation_of_duties`, role assignment, `min_approvals`).
  - Threshold rules (GRD-8): reason required for `no_go`, `severity >= high`, `insufficient_context`; typed confirmation required for high/critical.
  - `GET /approvals` inbox and a cheap count endpoint for the sidebar badge.
- **Frontend:** none.
- **Tests:** principal x decision matrix; expiry never approves; pin invalidation; replay and double-submit; separation of duties.
- **Docs:** `concepts/approvals-and-evidence-pinning.md`.

**Acceptance Criteria:**
**Given** an `approval` step **When** it is reached **Then** the run pauses durably and the approval records `report_id` and artifact digests.
**Given** pinned evidence changes, the plan exceeds its TTL, or the approval expires **When** a decision is attempted **Then** it is invalid or flagged stale, and expiry ends the run as `expired` without approving.
**Given** an agent or automation token **When** it calls the decision endpoint **Then** it is denied and audited.

#### Story 16.8: Frontend - Approvals Inbox and Approval Briefing

As an approver, I want a focused screen with the evidence and the exact handoff target, so that I can decide quickly and safely.

- **Frontend:**
  - **Approvals** tab and `/infra-automation/approvals`; sidebar badge from the count endpoint (poll about every 30 s).
  - `ApprovalBriefingCard` reusing the Latest-Briefing pieces (score ring, Evidence Law chip, top findings, blast radius/rollback tiles); sections for pinned evidence (report id, sha256), plan age, AI-involvement indicator, handoff target, context TODOs.
  - Decision form: required reason; typed confirmation for high/critical or `no_go`; disabled states for invalid/expired evidence with explanation; single-operator banner.
  - Right-hand dark **Approval briefing** card on the Overview.
  - Full keyboard flow; focus trap and restore in the decision dialog.
- **Backend:** none beyond 16.7.
- **Tests:** Vitest for decision-form states; Playwright e2e approve and reject; axe and keyboard-only decision test.
- **Docs:** screenshots for `getting-started` pages.

**Acceptance Criteria:**
**Given** a pending approval **When** I open it **Then** I see verdict, score, Evidence Law status, top findings, blast radius, rollback, context TODOs, pinned digests, plan age, and the handoff target **And** a written reason is required.
**Given** pinned evidence changed or the approval expired **When** I open it **Then** approval is disabled with an explanation.

#### Story 16.9: Handoff and Outbound Controls

As a platform engineer, I want notifications and handoff steps that are safe by construction, so that Infra Automation cannot become an SSRF or exfiltration path.

- **Backend:**
  - `infra_automation/net/outbound.py`: allow-listed HTTP client (resolve DNS, block loopback/link-local/metadata/private ranges as configured, pin the resolved IP to prevent DNS rebinding, no cross-host redirects, timeouts, response-size caps).
  - Steps: `notify.slack_webhook`, `notify.github_pr_comment` (reuse `integrations/github`), `handoff.webhook` (optional HMAC), `handoff.github_dispatch` (GitHub workflow dispatch with an environment-backed token reference).
  - Settings: allowed hosts, token references (via the 12.3 `SecretRefResolver`).
  - Publish-time and run-time allow-list checks.
- **Frontend:** Settings -> Infra Automation -> **Outbound hosts** editor with validation; the approval card shows the exact handoff target (repo, workflow, ref or URL host).
- **Tests:** SSRF corpus (loopback, link-local, metadata, IPv6, decimal/octal IP forms, DNS rebinding simulation, redirect to internal host); HMAC tests; mocked GitHub dispatch.
- **Docs:** `guides/github-actions-handoff.md`, `guides/slack-notifications.md`, `guides/itsm-webhook-intake-and-callback.md` (outbound part).

**Acceptance Criteria:**
**Given** a `notify.*` or `handoff.*` target outside the allow-list **When** the workflow is published or run **Then** it is rejected and audited.
**Given** Example B (Section 10.2) **When** a user uploads a plan **Then** the run reaches approval, and after approval sends the notification (**Milestone M1**).

#### Story 16.10: Credentials, Redaction, and Secret References

As a security-conscious operator, I want secrets handled by reference and redacted everywhere, so that Infra Automation cannot become a credential leak path.

- **Backend:** route every persisted log, output, artifact summary, audit event, and AI summary through the shared redaction utility; implement `SecretRefResolver` for server steps (environment-backed) and a runner-local resolver in 16.12; validator rejects inline secrets; add the redaction corpus under `tests/infra_automation/fixtures/redaction/`.
- **Frontend:** a clear "redacted" indicator in log and output views; no secret values ever returned to the SPA.
- **Tests:** corpus must produce zero leaks across logs, outputs, audit, prompts, and exports.
- **Docs:** `security/secret-handling.md`.

**Acceptance Criteria:**
**Given** logs, outputs, artifacts, and audit events **When** persisted or rendered **Then** the corpus yields zero known secret patterns **And** workflows can reference but not contain secrets.
**Given** Story 12.3's expanded criteria **When** this story completes **Then** every new credential class is covered by the same controls.

#### Story 16.11: Audit Trail

As a security reviewer, I want an append-only audit of activity, so that I can reconstruct who did what and why.

- **Backend:** complete event coverage per IAU-AUD-01 including denied actions and AI interactions; filtered query and JSON export endpoints; event digests in export.
- **Frontend:** **Audit** tab on run detail and a project-level audit view with filters (actor, event type, target, date) and JSON export.
- **Tests:** repository exposes no update/delete; content scans for secrets and raw artifacts; project scoping.
- **Docs:** `reference/audit-events.md`.

**Acceptance Criteria:**
**Given** a security-relevant action or a denied attempt **When** it occurs **Then** an event with actor, role, surface, scope, target, timestamp, and reason is stored without secrets.
**Given** an export request **When** it runs **Then** results are project-scoped, filterable, and exportable as JSON.

#### Story 16.12: Runner Agent, Enrollment, and Protocol

As a platform admin, I want to enroll a runner inside my network, so that collection runs where my tools and credentials live.

- **Backend / CLI:**
  - `infra_automation/runner/client.py` (retry with backoff and jitter; shared Pydantic protocol models with the server), `deploywhisper runner enroll | start | status`.
  - Server endpoints in Section 11.4; task-queue claim in a single transaction (`UPDATE ... WHERE state='queued' ... RETURNING`, or select-then-update inside one transaction on SQLite); lease expiry sweeper in the engine tick; tag matching (all-of by default); fail-fast when no runner matches unless `fallback: wait` with `max_wait`.
  - Tokens: random 32 bytes, stored as SHA-256 digest plus a short prefix, constant-time compare, expiring, project-scoped, revocable, shown once (use the 12.3 helper).
  - Protocol version negotiation.
- **Frontend:** **Runners** tab: table (name, tags, projects, version, status, last seen, current task), **Add runner** dialog showing the one-time enrollment command, **Rotate token**, **Revoke**; status is "online" when last seen is within twice the heartbeat interval.
- **Tests:** protocol tests with an in-process fake runner; lease expiry and re-queue only for idempotent steps; token lifecycle; version mismatch.
- **Docs:** `getting-started/install-a-runner-{docker,kubernetes,systemd}.md`, `concepts/runners.md`, `security/runner-hardening.md`, reference Dockerfile where the **operator installs their own tools** (no bundled Terraform).

**Acceptance Criteria:**
**Given** a one-time enrollment token **When** `deploywhisper runner enroll` runs **Then** a project-scoped runner token is issued once, stored hashed, expiring, and revocable.
**Given** a started runner **When** a matching task is queued **Then** it claims outbound over HTTPS, sends heartbeats, and the server re-queues lost tasks only for idempotent steps.
**Given** no runner matches a step's tags **When** the step is scheduled **Then** it fails fast with a message naming the required tags.

#### Story 16.13: Command Catalog and Collection Steps

As a platform engineer, I want safe, read-only collection steps for OpenTofu/Terraform, Ansible, Kubernetes, Helm, and Git, so that artifacts are produced consistently.

- **Backend (runner side):**
  - `catalog.py` loads built-in YAML entries (Section 11.4 format) and validates parameters locally; Phase B adds an operator-owned allow-list file.
  - `executor.py` runs fixed argv lists with `subprocess` (no shell), a per-task temporary working directory, filtered environment (`env_allow`), timeouts, and stdout/stderr size caps; streams logs through redaction; captures artifacts with sha256.
  - Repository access: the runner config maps path roots to local checkouts and uses a temporary Git worktree at the requested ref, never mutating the operator's primary checkout.
  - Terraform plan JSON: redact values marked sensitive; never return state files.
  - Entries: `iac.plan_json`, `ansible.check_diff`, `kubectl.diff`, `helm.template`, `git.diff`.
- **Frontend:** step timeline shows runner name and tags; no new screens.
- **Tests:** catalog schema tests; executor tests using fixture scripts that stand in for real binaries (so CI needs no Terraform); redaction and cap tests; timeout and cancellation.
- **Docs:** `reference/runner-command-catalog.md`, `guides/terraform-preflight.md`, `guides/ansible-check-mode-audit.md`, `guides/kubernetes-diff-check.md`, `guides/helm-and-kustomize.md`.

**Acceptance Criteria:**
**Given** the built-in catalog **When** a `collect.*` task arrives **Then** only fixed argv templates with locally validated parameters run, inside a per-task working directory with an environment allow-list, timeout, and output caps.
**Given** an unknown `command_id` or invalid parameters **When** the runner receives them **Then** it refuses and reports a structured error.
**Given** plan output with sensitive values or state content **When** collection completes **Then** sensitive values are redacted and state files are never returned.

#### Story 16.14: Evidence Provenance and Report Linkage

As a reviewer, I want collected artifacts to carry verifiable provenance into the report, so that the Evidence Law holds for automation-originated reports.

- **Backend:** intake accepts `provenance` metadata (run, step, runner id, `command_id`, argv digest, exit code, `collected_at`, sha256); evidence extraction sets `source_type = automation_collection`, deterministic only when provenance is complete, else `user_provided`; confidence factors and context TODOs for plan age, check-mode coverage gaps, partial collection; additive `automation` block in the report serializer; bump `report_schema_version` (minor) with schema docs and tests; shared-report views continue to hide internal run details.
- **Frontend:** report screen **Audit** tab shows "Collected by workflow run" with workflow, run id link, runner name, `command_id`, and sha256; History/Dashboard rows show a workflow-origin label (via `trigger_ref`) instead of "manual"; no change to the Dashboard information budget.
- **Tests:** Evidence Law CI fixtures including automation-originated reports; schema contract tests; Vitest snapshot for the provenance chip.
- **Docs:** report schema reference update.

**Acceptance Criteria:**
**Given** collected artifacts enter intake **When** evidence is extracted **Then** provenance is stored and evidence is `deterministic` only when complete.
**Given** a report created by a workflow **When** it is returned **Then** it includes the additive `automation` block and an incremented `report_schema_version`.
**Given** CI fixtures **When** tests run **Then** any high/critical finding without deterministic evidence fails the build.

#### Story 16.15: Webhook Intake and CLI

As a CI and CLI user, I want to trigger and manage runs from external systems and the terminal, so that Infra Automation fits scripted workflows.

- **Backend:** `POST /webhooks/{trigger_key}` with a trigger token header, optional HMAC signature, timestamp tolerance, replay protection, idempotency key, and a baseline rate limit; `cli/infra_automation.py` (`validate` runs offline; `run`, `status`, `approve`, `list` call the API using `DEPLOYWHISPER_API_URL` and a token; `approve` denied for non-human principals).
- **Frontend:** workflow **Triggers** panel: create webhook trigger, show token once, rotate, copy a sample `curl`.
- **Tests:** webhook auth/replay/idempotency matrix; CLI snapshot tests; principal checks.
- **Docs:** `reference/cli.md`, `guides/itsm-webhook-intake-and-callback.md` (inbound part).

**Acceptance Criteria:**
**Given** a webhook request **When** it arrives **Then** token (and optional HMAC), timestamp window, idempotency key, and rate limits are enforced and failures return bounded errors.
**Given** an agent or automation token **When** `infra-automation approve` runs **Then** it is denied.
**Given** a runner and a published Example A workflow **When** a run starts **Then** collection, analysis, gate, approval, and handoff complete (**Milestone M2**).

#### Story 16.16: AI Workflow Composer (Draft, Explain, Review)

As a platform engineer, I want to describe a pre-flight in plain language and get a validated draft, so that I do not hand-write YAML for every case.

- **Backend:**
  - `infra_automation/ai/ir.py` (Pydantic `WorkflowIR`), `context.py` (registry summaries, floors, project info, relevant Skills by trust level through the existing Skill loader, current draft), `composer.py` (call through the `llm/` boundary in structured-output mode; strict parse; validate; repair loop of at most two), `render.py` (deterministic IR -> YAML with stable key order via `yaml.safe_dump`).
  - Prompts in `llm/infra_automation/`; `services/infra_automation_ai_service.py` adds rate limits, size caps, per-user budgets, local-only handling, deterministic fallback, and `infra_automation_ai_runs` audit rows (digests and redacted summary; raw prompts not stored by default).
  - `POST /ai/compose` with modes `draft`, `explain`, `review`; never persists a published revision.
  - Provenance integrity: when a draft is saved with an `ai_run_id`, the server verifies that the run belongs to the caller, passed validation, and that the saved diff matches the proposal digest, then sets `authored_by = ai_assisted`.
  - A deterministic fake provider adapter loaded only in test configuration so Playwright runs without network access.
- **Frontend:** `AssistantPanel` with Draft/Explain/Review, AI-generated chip, validator status, floors checklist, diff viewer (a small internal line-diff utility; add a library only through an ADR), **Apply to draft**, **Discard**, audit link; AI-unavailable and local-only states; `aria-live` announcements.
- **Tests:** golden tests with a fake provider; unsafe-request fixtures (skip approval, inline secret, lower floors, unknown step) must all be rejected; injection fixtures embedded in the user text and draft; offline fallback; no raw prompt persistence; provenance-spoofing tests.
- **Docs:** `concepts/ai-assistance.md`, `ai/capabilities-and-data-sent.md`, `guides/local-ai-with-ollama.md`, `security/ai-safety.md`.

**Acceptance Criteria:**
**Given** a natural-language request **When** the Composer runs **Then** the model returns schema-constrained IR, it is validated against the validator and floors, and the result is rendered deterministically and shown as a diff with rationale, assumptions, and warnings.
**Given** a request to skip approval, embed a secret, add an unknown step, or lower a floor **When** the Composer runs **Then** the output is rejected and never shown as usable.
**Given** AI is disabled, local-only without a local model, or the provider fails **When** a user opens the Assistant **Then** the UI explains why and offers templates, and nothing else in the feature is affected.

#### Story 16.17: Templates, Documentation, and Integration Recipes

As a new user and self-hosted operator, I want ready-made workflows and complete docs, so that I can succeed without writing YAML or asking for help.

- **Backend/Frontend (small):** bundle `examples/infra-automation/` into the image; `GET /templates`; empty-state **template picker** that opens a pre-filled draft.
- **Templates:** (1) review an uploaded plan, (2) Terraform/OpenTofu pre-flight, (3) Ansible check-mode audit, (4) Kubernetes diff check, (5) ITSM request to handoff. Each validates in CI and uses synthetic data only.
- **Docs:** every Phase A page in Section 15.2; comparison page; `guides/integrating-with-kestra-argo-jenkins.md` (Alternative B recipes where external orchestrators call the DeployWhisper API and use the verdict).

**Acceptance Criteria:**
**Given** `examples/infra-automation/` **When** CI runs **Then** all templates pass the real validator.
**Given** the Phase A docs **When** a new user follows them **Then** they can reach Milestone M1 in under 10 minutes and M2 in under 30 minutes.

#### Story 16.18: Verification Gate and Benchmarks

As a maintainer, I want a release gate for Phase A, so that trust claims are measured rather than assumed.

- **Tests:** schema/validator unit tests; engine fault injection; runner protocol tests with the fake runner; authorization matrix (roles x projects x principals); SSRF corpus; redaction corpus; prompt-injection fixtures using step output and AI input; API contract tests; Playwright e2e on the composed app at `http://localhost:8080/` (create workflow -> run -> approve -> handoff to a mock); axe and keyboard smoke on every new route.
- **Benchmarks:** NFR-IAU-03..06 on SQLite (and PostgreSQL where available); Composer baseline on the AI corpus (validity, repair rate, zero-tolerance sets).
- **Release:** CHANGELOG, upgrade notes, flag default off, docs complete; publish results honestly including misses, with linked issues for material gaps.

**Acceptance Criteria:**
**Given** the test plan **When** the full suite runs **Then** all layers pass and zero-tolerance AI metrics are zero.
**Given** the NFR targets **When** benchmarks run **Then** results are published with misses and linked issues, and v1.4.0 is released with Infra Automation disabled by default.

### 17.5 Phase B - story playbook: IaC and package orchestration with AI (target v1.5.0)

Phase B turns single-bundle pre-flights into estate-level orchestration. Build the **deterministic** pieces first (16.19-16.22), then layer AI on top (16.23-16.25) so every AI feature has a deterministic oracle to validate against.

#### Story 16.19: Infra Map and IaC Unit Detection

As a platform engineer, I want the system to discover the IaC units in my repositories and let me confirm them, so that orchestration starts from a trusted inventory.

- **Backend:** `infra_automation/orchestration/detectors/` with one detector per type (Terraform/OpenTofu: directories with `*.tf`, ignoring `.terraform/`; Helm: `Chart.yaml`; Kustomize: `kustomization.yaml`; Ansible: playbooks with `hosts:` and tasks/roles; CloudFormation: `AWSTemplateFormatVersion` or `AWS::` resource types; pipelines: `Jenkinsfile`, `.github/workflows`); each detection records the file evidence that triggered it. A runner command `repo.scan` returns **file-tree metadata and detections, not file contents**. Reuse CODEOWNERS mapping (Story 7.4) for owners. Infra map schema, validator, and CRUD endpoints (`/inventory`).
- **Frontend:** **Inventory -> Units** table and a **Discover** wizard: run scan, review detected units with their evidence, edit layer/owner/runner tags, save the map; a YAML view of `infra-map.yaml`.
- **Tests:** synthetic repository fixtures in `tests/infra_automation/fixtures/repos/` (never real infrastructure); detector precision/recall on those fixtures; ignore-rule tests.
- **Docs:** `concepts/iac-units-and-packages.md`, `reference/infra-map-schema.md`.

**Acceptance Criteria:**
**Given** a repository checkout on a runner **When** Discover runs **Then** each detected unit shows the evidence that identified it and nothing but metadata leaves the runner.
**Given** an incomplete or stale infra map **When** a plan is requested **Then** the limitations appear as context TODOs and the system does not guess.

#### Story 16.20: Package Inventory and Package Evidence

As a reviewer, I want module, provider, chart, role, collection, and image changes surfaced as evidence, so that dependency risk is not hidden in a "small" diff.

- **Backend:**
  - Parsers registered in `parsers/`: `.terraform.lock.hcl` (a small tolerant block parser, no new dependency), module calls from plan JSON `configuration.module_calls`, `Chart.yaml`/`Chart.lock`, Ansible `requirements.yml`, Kubernetes image references (extend the existing parser), Kustomize remote bases.
  - `infra_automation/packages/`: package reference model, **package ledger** (migration), signal engine (unpinned/floating, major bump, hash drift, first-seen, non-allow-listed, pin removed).
  - Evidence items of type package signal (deterministic) feed the existing risk engine; add public risk patterns under `patterns/` and benchmark scenarios; allow-list in the infra map; GRD-5 enforcement; `packages.inspect` step.
  - Optional registry connector deferred (Phase C, off by default).
- **Frontend:** **Inventory -> Packages** table with filters (first-seen, not allow-listed, unpinned); approval card section "Packages" with a required acknowledgement checkbox for first-seen packages; package evidence appears in the existing report evidence inspector (no new report screen).
- **Tests:** parser fixtures per ecosystem; ledger semantics (first seen, version change, hash change without version change); Evidence Law tests on package patterns; false-positive notes in each pattern.
- **Docs:** `guides/package-governance.md`.

**Acceptance Criteria:**
**Given** a lockfile diff with a hash change but unchanged version **When** analysis runs **Then** a deterministic package signal is recorded and severity is decided by the existing risk engine under the Evidence Law.
**Given** a package not in the project ledger or allow-list **When** the approval card renders **Then** it is flagged and acknowledgement is required.
**Given** any AI feature **When** it proposes a package **Then** the proposal is rejected by validation.

#### Story 16.21: Orchestration Graph and Stage Plan (Deterministic)

As a platform engineer, I want a correct order of work across units computed from enforcing edges, so that nothing is verified or handed off before its dependencies.

- **Backend:** `orchestration/graph.py` builds the graph from `declared` edges, `layer_rule`, `remote_state` (parsed from plan JSON configuration expressions where available), and Terragrunt dependencies; `planner.py` computes waves with Kahn's algorithm and **deterministic tie-breaking by `unit_id`**; validity checks (respects all enforcing edges, covers exactly the change set); canonical-JSON plan snapshot and sha256 digest; `/graph` and `/plans` endpoints; limitations surfaced as context TODOs.
- **Frontend:** **Plan view**: waves as ordered rows with rationale and basis chips, open questions and TODOs, plan digest; **Graph** toggle with a hand-rolled layered SVG (no new dependency unless an ADR approves one) and an equivalent accessible table.
- **Tests:** property tests over random DAGs (plan always respects edges and covers the change set); determinism (same input gives the same digest); cycle error messages; large-graph degradation (NFR-IAU-17).
- **Docs:** `concepts/orchestration-graph-and-stage-plans.md`.

**Acceptance Criteria:**
**Given** a change set and the infra map **When** the plan is built **Then** waves respect every enforcing edge, cover exactly the change set, and repeated builds produce an identical digest.
**Given** edges whose basis is not enforcing **When** the plan is built **Then** they are informational and never constrain order.

#### Story 16.22: Stage Execution and Promotion

As an SRE, I want each stage verified and approved in order, and the same change promoted across environments with its own approvals, so that rollouts are controlled.

- **Backend:** `orchestrate` expansion into explicit per-stage steps at run start; the expanded definition and plan snapshot digest stored with the run and validated by the same validator; approvals pin the plan digest; bundle analysis plus per-stage analyses; promotion `dev -> stage -> prod` with a promotion diff (report scores, findings, package versions).
- **Frontend:** run detail groups the timeline by stage; per-stage approval cards; **Promotion diff** view.
- **Tests:** expansion cannot produce an unapproved handoff; digest mismatch invalidates approvals; promotion ordering.
- **Docs:** `guides/promotion-dev-stage-prod.md`.

**Acceptance Criteria:**
**Given** an `orchestrate` block **When** a run starts **Then** the engine expands and validates it, stores the snapshot, and each stage requires its own approval pinned to the plan digest.

#### Story 16.23: AI Infra Mapper

As a platform engineer, I want AI to help label and group detected units, so that onboarding a large repository is fast without letting AI invent infrastructure.

- **Backend:** `ai/mapper.py` + `InfraMapIR`; input is detector output only (no file contents); validator requires every proposed unit to exist in detector output; proposals include layers, names, runner tags, and owners from CODEOWNERS; corpus tests; audit rows.
- **Frontend:** **Suggest with AI** in the Discover wizard shows a diff against the deterministic draft with Accept/Edit/Discard per unit.
- **Tests:** mapper corpus (unit precision/recall); invented-unit rejection; injection fixtures in file names and CODEOWNERS text.

**Acceptance Criteria:**
**Given** detector output **When** the Mapper runs **Then** proposed units are a subset of detected units and every item is labeled `ai_suggested` until a human accepts it.

#### Story 16.24: AI Orchestration Planner

As an SRE, I want AI to explain a stage plan and suggest missing dependencies, so that hidden ordering risks are surfaced without AI controlling the order.

- **Backend:** `ai/planner.py` + `StagePlanIR`; validation uses the **deterministic planner as an oracle**: the proposal must respect all enforcing edges and cover exactly the change set; `ai_inferred` edges are returned as suggestions with reasons and can never constrain order until accepted (acceptance writes a `declared` edge to the infra map draft); Skills loaded by trust level; audit rows.
- **Frontend:** Plan view **Suggest with AI** panel: suggested edges list with **Accept** and **Dismiss**, rationale per wave, open questions; AI chip; nothing changes until accepted and saved.
- **Tests:** planner corpus with known enforcing edges (**zero order violations, zero coverage errors**); hallucinated-unit and hallucinated-package rejection; injection fixtures.

**Acceptance Criteria:**
**Given** a change set **When** the Planner runs **Then** any proposal that violates an enforcing edge, omits or adds a unit, or adds a package is rejected, and accepted AI-inferred edges become `declared` only after a human action.

#### Story 16.25: Run Diagnostician and Failure Signatures

As an operator, I want a plain-language explanation and safe next steps when a run fails, so that I recover quickly without guessing.

- **Backend:** `diagnostics/signatures.yaml` (id, match on redacted log patterns and exit codes, category, explanation, next steps, docs link) covering common cases (state lock held, expired or missing credentials, backend init failure, provider version mismatch, quota exceeded, kube context missing, unreachable Ansible host, timeout); classifier runs first; optional AI explanation over the redacted bounded excerpt and the signature id, labeled AI-generated; never produces executable commands; auto-run off by default.
- **Frontend:** run detail **Diagnose** panel: signature match first, then the AI explanation, then docs links.
- **Tests:** signature fixtures; unsafe-suggestion corpus (**zero**); redaction of excerpts before any model call.
- **Docs:** `reference/failure-signatures.md` and a contribution guide for new signatures.

**Acceptance Criteria:**
**Given** a failed step **When** Diagnose is requested **Then** the rule-based signature appears first and any AI text is labeled, bounded, redacted, and free of executable commands.

#### Story 16.26: Schedules, Drift Detection, and Event Triggers

As a platform engineer, I want read-only drift checks and event-driven pre-flights, so that problems are found before someone asks.

- **Backend:** schedule trigger in the engine tick using stdlib `zoneinfo` and either a minimal in-repo 5-field cron parser or an ADR-approved cron library; missed-run policy documented; drift templates (`plan -detailed-exitcode`, Ansible check mode) producing a drift summary run with notification and no handoff; `analysis.completed` internal hook; GitHub PR events through the existing integration.
- **Frontend:** Triggers panel adds schedule with a next-five-runs preview and timezone; a **Drift** filter on the Runs table.
- **Tests:** schedule determinism around DST; missed-run behavior; event filter tests; confirm event-started runs cannot skip approvals.

**Acceptance Criteria:**
**Given** a schedule trigger **When** it fires **Then** the run is read-only up to approval, labeled with its trigger, and cannot hand off without an approval.

#### Story 16.27: Agent and MCP Surface

As an AI-agent operator, I want agents to request pre-flights and read results but never approve or publish, so that humans remain accountable.

- **Backend:** extend the Epic 10 agent interface with `list_workflows`, `request_run` (only workflows marked `agent_callable`), `get_run_status`, `get_report`; origin and session tagging on runs; bounded outputs; project scope; rate limits; prompt-injection tests extended.
- **Frontend:** **Agent-callable** toggle on the workflow (Project Admin only); origin chip on the Runs table.
- **Tests:** authorization matrix proves agents cannot approve, publish, edit floors, or read inaccessible projects.

**Acceptance Criteria:**
**Given** an agent token **When** it requests a run of a non-agent-callable workflow, approves, or publishes **Then** the request is denied and audited.

#### Story 16.28: Scale, Locks, Change Windows, and Observability

As a platform admin, I want safe concurrency and visibility, so that shared installs stay reliable.

- **Backend:** PostgreSQL claim with `FOR UPDATE SKIP LOCKED`; per-workflow concurrency and project quotas; target locks keyed `<unit_id>:<workspace>` with TTL and audited admin break; change windows and freezes; metrics for runs, step durations, queue depth, runner health, approval wait, and AI calls; benchmarks for NFR-IAU-04/05.
- **Frontend:** lock and window state in plan and run views with explicit conflict messages; lock-break action requires a reason; settings for windows and quotas.
- **Tests:** concurrent claim tests on PostgreSQL; lock contention; window enforcement; metrics contain no secrets.

**Acceptance Criteria:**
**Given** two runs targeting the same unit and workspace **When** the second starts **Then** it reports the lock holder and does not proceed to handoff until the lock is released or broken with an audited reason.

#### Story 16.29: More Handoff Adapters and Git Sync

As a platform engineer, I want Jenkins, GitLab, and ITSM callbacks plus Git-managed workflow definitions, so that Infra Automation fits more delivery systems.

- **Backend:** `handoff.jenkins`, `handoff.gitlab_pipeline`, `itsm.callback` (all through the outbound client and approval-ancestor rule); read-only Git import of workflows and infra maps; promotion of workflow definitions between workspaces with a diff.
- **Frontend:** **Import from Git** wizard; workflow promotion diff.
- **Tests:** SSRF corpus applied to every adapter; import validation; approval-ancestor enforcement.

**Acceptance Criteria:**
**Given** an imported workflow **When** it is saved **Then** it arrives as a draft and must pass validation and floors before publish.

#### Story 16.30: AI Evaluation and Hardening Gate

As a maintainer, I want a release gate for the AI and orchestration features, so that safety claims are measured and published honestly.

- **Tests/Benchmarks:** build out `benchmarks/corpus/v1/infra-automation/` (Section 8.9); reuse the Epic 6 runner; publish a report with misses, false positives, and unsupported scenarios; add all zero-tolerance metrics as release blockers; docs `ai/evaluation-results.md`.
- **Release:** v1.5.0 with CHANGELOG and upgrade notes.

**Acceptance Criteria:**
**Given** the corpus **When** the gate runs **Then** unsafe-acceptance, injection-success, order-violation, coverage-error, and unsafe-suggestion rates are zero, and any regression blocks release **And** non-zero-target metrics are published with a baseline.

### 17.6 Phase C - gated stories (do not start without an accepted RFC)

| Story | Title | Key acceptance points |
|-------|-------|-----------------------|
| 16.31 | Tier 2 `execute.*` capability | Instance flag default off; per-project allow; runner tag `exec` plus runner-side allow-list; published revision approved by a different Project Admin; Evidence Law satisfied at run time; fresh plan required; approval at run time; no unattended triggers; break-glass with reason; rollback guidance linked; full audit. |
| 16.32 | Runner mTLS and signed task envelopes | Mutual TLS; envelope signature verification on the runner; certificate rotation docs. |
| 16.33 | Runner isolation profiles and optional registry connector | Reference container, Kubernetes Job, and systemd-sandbox profiles; hardening checklist; conformance tests; optional opt-in registry/MCP lookup connector producing labeled external evidence. |

### 17.7 Definition of Done (every story)

- `unittest`, `ruff check`, and `ruff format --check` pass; `bash scripts/ci-local.sh` passes.
- Frontend: `ui:typecheck`, `ui:test`, `ui:build` pass; for UI stories, compose-based `test:ui-review` passes against `http://localhost:8080/`.
- Migrations are additive, tested on SQLite and PostgreSQL where a lane exists, and noted in upgrade notes.
- Evidence Law fixtures pass; no scoring or severity logic outside the analysis core; no template-engine or `eval`/`exec`/`shell=True` use under `infra_automation/`.
- No new dependency without an approved ADR; no hosted dependency; no raw artifacts sent externally by default; no secrets in code, fixtures, logs, prompts, or audit.
- Docs, release notes, and CHANGELOG updated; CODEOWNERS and `MAINTAINERS.md` reflect the area.
- `bmad-code-review` completed; `sprint-status.yaml` and verification notes updated.

### 17.8 Milestone demo scripts

| Milestone | Demo |
|-----------|------|
| **M1** (after 16.9) | Enable the feature; open **Infra Automation**; create the "review an uploaded plan" workflow; run it with a synthetic plan JSON; see the linked briefing; approve with a reason; see the Slack mock notification; open the audit trail. |
| **M2** (after 16.15) | Enroll a runner; run Example A on a sample stack; observe collect, analyze, gate, approval pinned to the plan digest; change the plan and watch approval invalidate; hand off to a mock dispatch. |
| **M3** (v1.4.0) | Ask the Assistant for a pre-flight; review the diff and validator status; try prompts that attempt to skip approval or embed a secret and see them rejected; publish after review. |
| **M4** (after 16.22) | Discover units in a synthetic repo; confirm the map; run an estate pre-flight across three units and one package change; approve each stage; promote to the next environment. |
| **M5** (v1.5.0) | Use the AI Mapper and Planner; accept one suggested edge; diagnose a failed run; show the evaluation report including misses. |

### 17.9 Requirement coverage map (additive to `epics.md`)

| Requirement family | Primary stories |
|--------------------|-----------------|
| `IAU-WF-*` | 16.1, 16.3, 16.4, 16.17, 16.22, 16.29 |
| `IAU-TRG-*` | 16.15, 16.26 |
| `IAU-RUN-*` | 16.2, 16.5, 16.6, 16.28 |
| `IAU-RNR-*` | 16.12, 16.13, 16.32 |
| `IAU-STP-*` | 16.5, 16.9, 16.13, 16.20, 16.29 |
| `IAU-APR-*` | 16.7, 16.8, 16.22 |
| `IAU-AEV-*` | 16.14, 16.10 |
| `IAU-ORC-*` | 16.19, 16.21, 16.22, 16.28 |
| `IAU-PKG-*` | 16.20, 16.33 |
| `IAU-AI-*` | 16.16, 16.23, 16.24, 16.25, 16.27, 16.30 |
| `IAU-GRD-*` | 16.1, 16.7, 16.9 |
| `IAU-AUD-*` | 16.2, 16.11 |
| `IAU-API-*` | 16.3, 16.6, 16.15, 16.27 |
| `IAU-ADM-*` | 16.2, 16.9, 16.12, 16.19 |
| `UX-DR11..22` | 16.4, 16.6, 16.8, 16.14, 16.16, 16.21 |
| `DOC-28..34` | 16.17, 16.20, 16.25, 16.30 and Epic 13 additions |
| `NFR-IAU-*` | 16.18, 16.28, 16.30 |

### 17.10 ADRs to add to `architecture.md` (Story 16.0)

| ADR | Decision |
|-----|----------|
| ADR-15 | Infra Automation is an additive subsystem; one shared analysis core remains authoritative for findings and severity. |
| ADR-16 | Capability tiers 0/1/2 and autonomy levels L0-L3; Tier 2 and L3 require a further RFC. |
| ADR-17 | AI emits schema-constrained IR; deterministic validators, guardrail floors, and renderers are authoritative; AI never approves, publishes, executes, or edits floors. |
| ADR-18 | Runners are outbound-only agents with a runner-side command catalog and local secret resolution; the server never holds cloud credentials. |
| ADR-19 | The workflow engine is a DB-backed state machine inside the FastAPI process; workers and PostgreSQL claiming are scale paths. |
| ADR-20 | Package governance uses local evidence and an admin allow-list by default; registry lookups are opt-in external evidence. |

---

## 18. Risks and Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R1 | **Posture drift** toward a deployment tool, weakening the "advisory safety layer" identity. | Medium | High | Tiers and hard rules; Story 16.0 RFC; Tier 2 gated; copy review (UX-DR16). |
| R2 | **Runner compromise or misuse** exposes production credentials. | Medium | High | Outbound-only runners; runner-side catalog; local secret resolution; scoped expiring tokens; ephemeral-credential guidance; hardening docs; mTLS later. |
| R3 | **Identity gap**: approvals imply controls that cannot be enforced without multi-user authn. | High | High | Decision D4; single-operator "acknowledgement" mode, visibly labeled; prioritize a minimal identity story. |
| R4 | **Credential leakage** in logs, artifacts, prompts, or audit. | Medium | High | Reference-only secrets; redaction at runner and server; corpus tests; Story 12.3 expanded. |
| R5 | **Engine bugs** (lost approvals, duplicate handoffs). | Medium | High | Persist-before-side-effect; idempotency; fault injection; small closed step set. |
| R6 | **SQLite contention** under concurrent runs. | Medium | Medium | Short transactions; modest tick; documented limits; PostgreSQL claiming. |
| R7 | **Scope creep** toward a general orchestrator or an IaC authoring tool. | High | Medium | Non-goals; closed registry; no plugin catalog; AI does not author IaC. |
| R8 | **Plan/check-mode misleads** (check-mode gaps, plan-apply drift). | Medium | Medium | Confidence factors, plan-age warnings, honest docs; no "safe" claims. |
| R9 | **Prompt injection** through repo files, logs, tickets, or registry text. | High | High | Untrusted-data handling; structured IR; deterministic validation and rendering; no model tool use; zero-tolerance corpus. |
| R10 | **Hallucinated steps, units, or packages** reach users. | High | High | Registry and detector-set membership checks; allow-list; first-seen acknowledgement; validation before display. |
| R11 | **Automation bias**: approvers trust AI-assisted drafts too much. | Medium | High | Evidence-first approval card; AI-involvement indicator; four-eyes for AI-assisted prod revisions; AI never claims safety. |
| R12 | **Local model quality** too low for Composer/Planner. | Medium | Medium | Constrained IR and repair loop; deterministic fallback; evaluation results published; clear UI state. |
| R13 | **"AI magic" erodes trust** (conflicts with AGENTS.md). | Medium | High | Deterministic oracles for every AI feature; AI optional; labels everywhere; evaluation gate. |
| R14 | **Licensing**: bundling third-party IaC binaries in a published runner image. | Medium | Medium | Do not bundle; reference Dockerfiles; document OpenTofu; verify current license terms. |
| R15 | **Maintainer load** for a large new area. | Medium | Medium | Phase it; new CODEOWNERS area; community-friendly templates, signatures, and catalog entries. |
| R16 | **UI budget bloat** on the Dashboard. | Low | Medium | Own page and information budget; Dashboard unchanged. |

---

## 19. Open Questions

1. **Identity:** Will a minimal multi-user mechanism (local users or OIDC) land before Phase A ships, or does Phase A launch in single-operator mode? (D4)
2. **Handoff scope:** Are GitHub `workflow_dispatch` and a generic webhook enough for v1.4.0, or is Jenkins required earlier?
3. **Editor dependency:** Approve CodeMirror 6 (new frontend dependency) or ship a `<textarea>` in Phase A? (D6)
4. **Notifications:** Slack only in Phase A, or also email (needs an SMTP configuration surface)?
5. **Retention defaults:** Are 90 days (runs) and 30 days (artifacts) acceptable for your users' compliance needs?
6. **Naming:** Keep "Infra Automation", or prefer a name that emphasizes the advisory posture?
7. **Tier 2 appetite:** Is execution an eventual goal, or should docs state it is out of scope long term?
8. **Existing epics status:** Confirm Epics 5, 10, and 11 are complete so Infra Automation can reuse GitHub integration, the agent interface, and the policy adapter contract. (A2)
9. **AI scope for v1.4.0:** Is the Composer alone enough for Phase A, or must the Diagnostician also ship earlier (its deterministic signature half is cheap to pull forward)?
10. **Terraform vs OpenTofu:** Should the runner catalog default to OpenTofu and treat Terraform as operator-provided?
11. **CODEOWNERS and ownership:** Is CODEOWNERS data available in the repositories users will map, so the Mapper can derive owners deterministically?

---

## Appendix A - Reference Material

Public sources reviewed for the analysis (accessed during preparation of this document):

- Kestra Infrastructure Automation: https://kestra.io/infra-automation
- Kestra 2.0 overview (Copilot, flows as MCP tools, agent guardrails): https://kestra.io/two-zero
- Kestra worker groups: https://kestra.io/docs/enterprise/scalability/worker-group
- Kestra approval processes: https://kestra.io/docs/use-cases/approval-processes
- HashiCorp, Terraform Stacks explained: https://hashicorp.com/blog/terraform-stacks-explained
- GeekWire, Pulumi Neo announcement: https://www.geekwire.com/2025/seattle-startup-pulumi-bets-big-on-ai-with-neo-an-agent-that-automates-cloud-infrastructure-tasks/
- Spacelift, Guardrails for AI-generated infrastructure: https://spacelift.io/blog/guardrails-for-ai-generated-infrastructure
- TFiR interview on Spacelift Intelligence and Intent: https://tfir.io/spacelift-intelligence-intent-ai-infrastructure-governance/
- Qovery, AI agent infrastructure governance: https://www.qovery.com/blog/ai-agent-infrastructure-governance-audit-policy-budget-guardrails
- Qovery, Policy guardrails for AI agents: https://www.qovery.com/blog/policy-guardrails-ai-agents-infrastructure-automation-platforms
- HashiCorp Terraform MCP server reference: https://developer.hashicorp.com/terraform/mcp-server/v0.5.x/reference
- Endor Labs, Hallucinated packages: https://www.endorlabs.com/learn/hallucinated-packages-how-ai-invents-dependencies-attackers-exploit
- Independent orchestrator comparison: https://guptadeepak.com/tools/top-6-workflow-orchestration-platforms-2026/

DeployWhisper sources reviewed:

- Repository: https://github.com/deploywhisper/deploywhisper (README, `_bmad-output/planning-artifacts/prd.md`, `architecture.md`, `epics.md`)
- Product site: https://deploywhisper.dev/
- Public snapshot of `AGENTS.md` (dated May 2026, may predate the React cutover): https://tomevault.io/tome/deploywhisper/deploywhisper

Vendor statistics (for example, AI-caused incident prevalence) are survey results reported by the vendor and are treated as directional only.

## Appendix B - Suggested File Locations in the Repository

| Artifact | Path |
|----------|------|
| This PRD addendum | `_bmad-output/planning-artifacts/prd-infra-automation.md` |
| Epic 16 stories | Append to `_bmad-output/planning-artifacts/epics.md` after Epic 15 |
| ADRs | Append to `architecture.md` Section 20 (Section 17.10 of this document) |
| RFC | `RFC/` directory (Story 0.4 process) |
| UX notes | `docs/design/infra-automation-ux.md`; note in `docs/ui-migration-plan.md` |
| Workflow and infra-map schemas | `schemas/infra-automation/` |
| AI and orchestration corpus | `benchmarks/corpus/v1/infra-automation/` |
| Examples | `examples/infra-automation/` |

## Appendix C - Glossary

| Term | Meaning |
|------|---------|
| Capability tier | Tier 0 observe, Tier 1 handoff, Tier 2 execute; what Infra Automation may do. |
| Autonomy level | L0 suggest, L1 assisted, L2 supervised, L3 unattended handoff (not in v1). |
| Evidence pinning | Binding an approval to a specific report, artifact digests, and plan digest so it is invalid if any change. |
| Runner | Outbound agent that executes read-only collection tasks in the user's infrastructure. |
| Command catalog | Runner-side allow-list of fixed commands and parameter schemas. |
| Gate | Workflow-level routing based on report fields; never alters the report. |
| Handoff | Triggering the user's own delivery system after approval. |
| IR (intermediate representation) | Schema-constrained structured data produced by AI and rendered deterministically. |
| Guardrail floor | Minimum control enforced in code that AI and workflow content cannot lower. |
| Unit | An orchestrated IaC item: stack, release, playbook, manifests, overlay. |
| Package | A versioned dependency consumed by infrastructure code: provider, module, chart, role, collection, image. |
| Package ledger | Per-project record of packages previously seen, enabling first-seen and drift detection. |
| Infra map | Human-reviewed file describing units, layers, dependencies, owners, and package allow-lists. |
| Stage plan | Ordered waves of units derived from enforcing edges and validated against them. |
| Edge basis | Why a dependency edge exists; determines whether it can enforce order. |
| Single-operator mode | Deployment without multi-user identity; approvals recorded as acknowledgements. |
