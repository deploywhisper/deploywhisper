<p align="center">
  <img src="docs/assets/wordmark-stacked-light-bg.svg" alt="DeployWhisper" width="80"/>
  <br/>
  <strong style="font-size: 2em;">DeployWhisper</strong>
  <br/>
  <em>AI-Powered Pre-Deployment Risk Intelligence Platform for infrastructure changes</em>
  <br/><br/>
  <a href="#quick-start">Quick Start</a> · <a href="#features">Features</a> · <a href="#architecture">Architecture</a> · <a href="#ai-skills">AI Skills</a> · <a href="#docs">Docs</a>
</p>

---

## What is DeployWhisper?

DeployWhisper analyzes your infrastructure-as-code changes across **Terraform, Kubernetes, Ansible, Jenkins, and CloudFormation** — and generates a plain-English risk narrative, blast radius map, and automated rollback plan **before you deploy**.

It uses large language models enriched with **AI Skills** (deep, tool-specific domain knowledge) to catch risks that generic AI tools miss — like Terraform state drift patterns, Kubernetes readiness probe gaps, or Ansible idempotency violations.

```
Upload IaC files → AI analyzes changes → Get risk score + narrative + rollback plan
```

### Complete Project Directory Structure

```text
ai-deploy-whisper/
├── README.md
├── pyproject.toml
├── requirements.txt
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── app.py
├── api_server.py
├── cli.py
├── config.py
├── logging_config.py
├── .github/
│   └── workflows/
│       └── ci.yml
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── api/
│   ├── __init__.py
│   ├── routes/
│   │   ├── analyses.py
│   │   ├── incidents.py
│   │   ├── health.py
│   │   └── settings.py
│   ├── dependencies.py
│   ├── errors.py
│   └── schemas.py
├── services/
│   ├── __init__.py
│   ├── analysis_service.py
│   ├── intake_service.py
│   ├── report_service.py
│   ├── incident_service.py
│   ├── topology_service.py
│   └── settings_service.py
├── parsers/
│   ├── __init__.py
│   ├── base.py
│   ├── registry.py
│   ├── terraform_parser.py
│   ├── kubernetes_parser.py
│   ├── ansible_parser.py
│   ├── jenkins_parser.py
│   └── cloudformation_parser.py
├── analysis/
│   ├── __init__.py
│   ├── risk_scorer.py
│   ├── blast_radius.py
│   ├── env_classifier.py
│   ├── incident_matcher.py
│   └── rollback_planner.py
├── llm/
│   ├── __init__.py
│   ├── narrator.py
│   ├── providers.py
│   ├── prompts.py
│   └── skill_context.py
├── skills/
│   ├── terraform.md
│   ├── kubernetes.md
│   ├── ansible.md
│   ├── jenkins.md
│   ├── cloudformation.md
│   ├── git.md
│   ├── docker.md
│   └── custom/
├── models/
│   ├── __init__.py
│   ├── database.py
│   ├── tables.py
│   ├── repositories/
│   │   ├── analysis_reports.py
│   │   ├── incident_records.py
│   │   └── settings.py
│   └── types.py
├── ui/
│   ├── __init__.py
│   ├── routes/
│   │   ├── dashboard.py
│   │   ├── history.py
│   │   ├── settings.py
│   │   └── incidents.py
│   ├── components/
│   │   ├── upload_panel.py
│   │   ├── risk_summary.py
│   │   ├── change_table.py
│   │   ├── blast_radius_graph.py
│   │   ├── rollback_plan.py
│   │   └── progress_tracker.py
│   ├── state/
│   │   └── session_state.py
│   └── formatters/
│       ├── narrative.py
│       └── risk_labels.py
├── cli/
│   ├── __init__.py
│   └── analyze.py
├── samples/
│   ├── safe_deploy/
│   ├── medium_risk/
│   └── critical_risk/
├── data/
│   ├── topology/
│   │   └── service_topology.json
│   └── incidents/
├── tests/
│   ├── test_parsers/
│   ├── test_analysis/
│   ├── test_llm/
│   ├── test_api/
│   ├── test_ui/
│   ├── test_services/
│   ├── test_cli/
│   └── fixtures/
└── docs/
    └── assets/
```

## Current Status

This repository is currently a **planning workspace with an implemented foundation scaffold**, not a completed feature-complete product.

What exists today:
- Product requirements document
- Architecture decision document
- UX design specification
- Epics and stories breakdown
- Implementation readiness assessment
- Story `1.1` foundation scaffold with a working shared runtime shell and health endpoint

These artifacts were created through BMAD workflows and live under [`_bmad-output/planning-artifacts/`](/Users/psaho01/ai-deploy-whisper/_bmad-output/planning-artifacts).

Core planning artifacts:
- [PRD](/Users/psaho01/ai-deploy-whisper/_bmad-output/planning-artifacts/prd.md)
- [Architecture](/Users/psaho01/ai-deploy-whisper/_bmad-output/planning-artifacts/architecture.md)
- [UX Specification](/Users/psaho01/ai-deploy-whisper/_bmad-output/planning-artifacts/ux-design-specification.md)
- [Epics and Stories](/Users/psaho01/ai-deploy-whisper/_bmad-output/planning-artifacts/epics.md)
- [Implementation Readiness Report](/Users/psaho01/ai-deploy-whisper/_bmad-output/planning-artifacts/implementation-readiness-report-2026-04-16.md)

## Product Summary

DeployWhisper is intended to replace fragmented manual deploy review with one deploy briefing that includes:
- Unified multi-tool change analysis
- Explainable risk score and deploy recommendation
- Plain-English narrative of what changed and why it matters
- Blast radius view of downstream impact
- Rollback guidance and recovery complexity
- Historical incident similarity matching
- Audit trail and history review

The product is advisory-only in v1. It supports human judgment; it does not block deployments.

## LLM API Key Handling

DeployWhisper is designed to keep LLM API keys in process memory and environment variables, not in the application database.

Why:
- container restarts should recover secrets from the runtime environment, not from app-managed persistence
- storing an encrypted secret in the same app database is weaker unless the decryption key lives outside the app and outside that database
- the project requirement explicitly forbids persisting API keys to local DB tables, logs, or generated reports

Current code behavior:
- provider/model/base URL can be persisted in `app_settings`
- provider API keys are resolved from environment variables at runtime
- the app intentionally deletes any DB key entries instead of saving them

Relevant code:
- [config.py](/Users/psaho01/ai-deploy-whisper/config.py:17)
- [services/settings_service.py](/Users/psaho01/ai-deploy-whisper/services/settings_service.py:100)
- [models/tables.py](/Users/psaho01/ai-deploy-whisper/models/tables.py:55)
- [PRD requirement](/Users/psaho01/ai-deploy-whisper/_bmad-output/planning-artifacts/prd.md:430)

Recommended runtime pattern:
- local dev: `.env`
- Docker Compose: `env_file: .env` or host-exported environment variables
- production: orchestrator secrets or an external secret manager

Supported environment variables:
- `LLM_PROVIDER`
- `LLM_MODEL`
- `LLM_API_BASE`
- `LLM_API_KEY` as a generic fallback
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY` or `GOOGLE_API_KEY`
- `OPENROUTER_API_KEY`
- `GROQ_API_KEY`
- `XAI_API_KEY`

### Docker Compose

The repo now passes through provider keys from your host or `.env` file into the container. Define them in `.env` next to `docker-compose.yml` or export them in your shell before starting Compose.

Example `.env` for OpenAI:

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4.1-mini
LLM_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=your-real-key
```

Start the stack:

```bash
docker compose up --build
```

Example `.env` for Ollama:

```env
LLM_PROVIDER=ollama
LLM_MODEL=ollama/llama3
LLM_API_BASE=http://host.docker.internal:11434
```

No API key is required for local Ollama mode.

### Dockerfile

Do not bake API keys into the `Dockerfile` with `ENV` instructions.
Pass them at runtime through Compose, `docker run -e ...`, Kubernetes secrets, or your platform's secret manager.

## Why It Exists

Existing tools mostly review one artifact at a time:
- linters catch single-tool rule violations
- plan viewers show raw infrastructure diffs
- policy engines enforce only pre-written rules
- generic LLM prompts lack system context and auditability

DeployWhisper’s core thesis is that real deployment risk is a **context problem**, not a single-file problem. The value comes from combining:
- multi-tool parsing
- tool-specific AI Skills
- blast radius analysis
- incident memory
- one decision-ready briefing

## Target Users

- Platform engineers running day-to-day pre-deploy review
- SRE / DevOps leads making go/no-go decisions
- Junior engineers learning from plain-English explanations
- Engineering managers reviewing trends and audit history
- Platform admins managing topology, incident records, and AI Skills
- Technical users integrating analysis into CLI/API/CI workflows

## Planned Technical Foundation

The current architecture source of truth is the BMAD architecture document, not older exploratory drafts.

Planned v1 stack:
- **UI runtime:** NiceGUI
- **API runtime:** FastAPI
- **Persistence:** SQLite + SQLAlchemy + Alembic
- **Contracts and validation:** Pydantic
- **LLM abstraction:** LiteLLM
- **Graph analysis:** NetworkX
- **Artifact parsing:** Python-native parsers for Terraform, Kubernetes, Ansible, Jenkins, and CloudFormation

Key architectural constraints:
- pure Python, no JavaScript build tooling
- single-container application runtime
- local-first raw IaC handling
- structured-summary-only LLM boundary
- fully offline Ollama mode supported

## UX Direction

The UX source of truth is the generated UX specification. The high-level UX direction is:
- desktop-first, internal operational tool
- verdict-first review experience
- calm, high-signal briefing rather than dashboard sprawl
- dark-mode-first visual system
- parser coverage and uncertainty made explicit
- summary first, evidence below

Supporting UX assets:
- [UX spec](/Users/psaho01/ai-deploy-whisper/_bmad-output/planning-artifacts/ux-design-specification.md)
- [Design directions HTML](/Users/psaho01/ai-deploy-whisper/_bmad-output/planning-artifacts/ux-design-directions.html)

## Repository Intent

This repo currently serves as:
- a BMAD planning workspace
- a technical source of truth for implementation
- a handoff package for story execution

It does **not** yet contain the full application described by the planning artifacts, but it now includes the first implemented foundation story and a runnable shared runtime scaffold.

## Related Source Documents

The original source documents used during planning are still present in the repository root:
- [DeployWhisper_PRD.docx](/Users/psaho01/ai-deploy-whisper/DeployWhisper_PRD.docx)
- [DeployWhisper_Architecture.docx](/Users/psaho01/ai-deploy-whisper/DeployWhisper_Architecture.docx)

These are useful for provenance, but the BMAD-generated markdown artifacts should now be treated as the current planning baseline.

## Recommended Next Step

The planning set is now marked ready for implementation. The next practical BMAD step is story execution:
- `bmad-create-story`
- or `bmad-dev-story`

If implementation changes the design or architecture materially, update the planning artifacts rather than letting code and docs drift apart.
