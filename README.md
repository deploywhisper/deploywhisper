<p align="center">
  <img src="docs/assets/logo.png" alt="DeployWhisper" width="80"/>
  <br/>
  <strong style="font-size: 2em;">DeployWhisper</strong>
  <br/>
  <em>AI-Powered Pre-Deployment Risk Intelligence Platform</em>
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

**Built entirely in Python. No JavaScript. No React. No npm.**

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/your-org/ai-deploy-whisper.git
cd ai-deploy-whisper

# Install dependencies
pip install -r requirements.txt

# Set your LLM API key (pick one)
export ANTHROPIC_API_KEY="sk-ant-..."       # For Claude
# OR
export OPENAI_API_KEY="sk-..."              # For OpenAI
# OR use Ollama locally (no key needed)

# Launch the dashboard
streamlit run app.py
```

Open `http://localhost:8501` — click **"Load demo report"** to see a sample analysis instantly.

**Time from clone to first analysis: under 5 minutes.**

---

## Features

### Multi-Tool IaC Analysis
| Tool | Input Format | What It Catches |
|------|-------------|----------------|
| **Terraform** | `terraform plan -json` | SG 0.0.0.0/0 exposure, IAM wildcards, RDS without deletion protection, state-breaking changes |
| **Kubernetes** | YAML manifests | Missing readiness probes, privileged containers, resource limit gaps, RBAC escalation |
| **Ansible** | Playbook YAML | Non-idempotent shell tasks, production inventory targeting, dangerous module usage |
| **Jenkins** | Jenkinsfile | Removed approval gates, credential exposure, missing rollback hooks |
| **CloudFormation** | Template YAML/JSON | Resource replacements, missing DeletionPolicy, cross-stack dependency risks |

### AI-Powered Risk Narrative
Not just a diff viewer — DeployWhisper generates a **human-readable story** explaining:
- What changed and why it matters
- How changes interact across tools
- Which downstream services are affected (blast radius)
- A clear **GO / CAUTION / NO-GO** recommendation
- Step-by-step rollback plan with time estimates

### AI Skills Knowledge Base
Each tool has a dedicated **AI Skill** — a curated knowledge module injected into the LLM context:
- **Terraform Skill**: Provider-specific risks, state operations, lifecycle rule pitfalls
- **Kubernetes Skill**: Workload safety, rolling update risks, network policy gaps
- **Ansible Skill**: Module danger classification, idempotency violations, inventory targeting
- **Jenkins Skill**: Approval gate analysis, credential exposure, agent security
- **CloudFormation Skill**: Replacement detection, deletion policies, drift patterns
- **Git Skill**: Commit context, sensitive file detection, branch risk signals
- **Docker Skill**: Dockerfile risks, image provenance, compose file security

Skills are **customizable** — drop a markdown file in `skills/custom/` to add your team's domain knowledge.

### Bring Your Own LLM
| Provider | Models | API Key Required |
|----------|--------|-----------------|
| Anthropic Claude | claude-sonnet-4-20250514, claude-opus-4-20250115 | Yes |
| OpenAI | gpt-4o, gpt-4-turbo | Yes |
| Ollama (Local) | llama3, mistral, codellama | **No** (fully air-gapped) |
| Groq | llama-3.3-70b, mixtral-8x7b | Yes |
| Azure OpenAI | Any deployment | Yes |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  PARSER LAYER                                               │
│  Terraform · Kubernetes · Ansible · Jenkins · CloudFormation │
│                    ↓ UnifiedChange JSON                     │
├─────────────────────────────────────────────────────────────┤
│  ANALYSIS ENGINE                                            │
│  Blast Radius · Risk Scorer · Incident Matcher · Env Detect │
│                    ↓ Enriched Context                       │
├─────────────────────────────────────────────────────────────┤
│  AI SKILLS ENGINE                                           │
│  Loads tool-specific knowledge → injects into LLM prompt    │
├─────────────────────────────────────────────────────────────┤
│  LLM LAYER (LiteLLM)                                       │
│  Claude · OpenAI · Ollama · Groq · Azure                    │
│                    ↓ Structured Risk Report                 │
├─────────────────────────────────────────────────────────────┤
│  OUTPUT LAYER                                               │
│  Streamlit Dashboard · CLI · REST API · Slack Bot           │
└─────────────────────────────────────────────────────────────┘
```

**Full architecture diagram**: See `docs/DeployWhisper_Architecture.docx`, Section 1.2

---

## Project Structure

```
ai-deploy-whisper/
├── app.py                      # Streamlit dashboard entry point
├── server.py                   # FastAPI entry point (API/CLI mode)
├── config.py                   # Settings and LLM configuration
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
│
├── parsers/                    # IaC file parsers
│   ├── base.py                 # UnifiedChange Pydantic model
│   ├── registry.py             # Auto-detect parser from file type
│   ├── terraform_parser.py
│   ├── kubernetes_parser.py
│   ├── ansible_parser.py
│   ├── jenkins_parser.py
│   └── cloudformation_parser.py
│
├── skills/                     # AI Skills knowledge base
│   ├── loader.py               # Skill discovery + prompt injection
│   ├── terraform.md
│   ├── kubernetes.md
│   ├── ansible.md
│   ├── jenkins.md
│   ├── cloudformation.md
│   ├── git.md
│   ├── docker.md
│   └── custom/                 # Team-specific skill overrides
│
├── analysis/                   # Risk intelligence engine
│   ├── blast_radius.py         # NetworkX dependency graph + BFS
│   ├── risk_scorer.py          # Weighted heuristic scoring
│   ├── incident_matcher.py     # Embedding similarity search
│   └── env_classifier.py       # Prod/staging/dev detection
│
├── llm/                        # LLM abstraction layer
│   ├── narrator.py             # LiteLLM + skill-enhanced prompts
│   ├── prompts.py              # System prompts + output schemas
│   └── providers.py            # Provider config + validation
│
├── models/                     # Data layer
│   ├── database.py             # SQLAlchemy engine + session
│   ├── schemas.py              # Pydantic API schemas
│   └── tables.py               # ORM models
│
├── ui/                         # Streamlit frontend
│   ├── components/             # Reusable UI components
│   ├── pages/                  # Multi-page app routes
│   └── styles/theme.py         # Custom theming
│
├── samples/                    # Demo scenarios
│   ├── safe_deploy/
│   ├── medium_risk/
│   └── critical_risk/
│
├── tests/
│   ├── test_parsers/
│   ├── test_skills/
│   ├── test_analysis/
│   └── test_integration/
│
└── docs/
    ├── DeployWhisper_PRD.docx
    └── DeployWhisper_Architecture.docx
```

---

## Running Modes

| Mode | Command | Use Case |
|------|---------|----------|
| **Dashboard** | `streamlit run app.py` | Interactive web UI |
| **API Server** | `uvicorn server:app --port 8000` | REST API for CI/CD, Slack bots |
| **CLI** | `python -m deploywhisper analyze plan.json` | Terminal / headless analysis |
| **Docker** | `docker compose up -d` | Containerized deployment |

---

## Configuration

Copy `.env.example` to `.env` and set your preferred LLM provider:

```bash
# LLM Provider (claude / openai / ollama / groq / azure)
LLM_PROVIDER=claude
LLM_MODEL=claude-sonnet-4-20250514
LLM_API_KEY=sk-ant-your-key-here

# For Ollama (no key needed)
# LLM_PROVIDER=ollama
# LLM_MODEL=ollama/llama3
# LLM_API_BASE=http://localhost:11434
```

Or configure interactively via the **Settings** page in the dashboard.

---

## Security

- **API keys** are stored only in environment variables or session memory — never written to disk or logs
- **Raw IaC content** is parsed locally — only structured summaries (resource names, action types) are sent to the LLM
- **Sensitive files** (.env, private keys, kubeconfig) are auto-detected by the Git skill and blocked from LLM transmission
- **Air-gap mode**: Use Ollama for fully offline operation where zero data leaves your machine
- **Log sanitization**: Application logs never contain API keys, file content, or LLM responses

---

## Custom AI Skills

Add your team's domain knowledge without writing any Python:

```bash
# Create a custom skill for your internal Terraform modules
cat > skills/custom/terraform.md << 'EOF'
---
skill: terraform
version: 1.0
triggers: [.tf, .tfvars]
token_budget: 500
---

## Internal module patterns
- Module `corp-vpc` v2.x requires NAT gateway — flag if nat_enabled = false
- Module `corp-rds` always sets multi_az in prod — flag if single-AZ detected
- Tag `team` is mandatory on all resources — flag if missing

## Naming conventions
- Production resources must match pattern: prod-{region}-{service}
- Security groups must have description field populated
EOF
```

Custom skills **override** built-in skills with the same name, so your team-specific patterns take precedence.

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | **Streamlit** | Pure Python, zero JS, built-in charts/tables/uploads |
| Backend API | **FastAPI** | Async, auto OpenAPI docs, Pydantic integration |
| LLM Abstraction | **LiteLLM** | Single `completion()` call for 100+ providers |
| AI Skills | **Markdown files** | Human-readable, version-controlled, customizable |
| Database | **SQLite + SQLAlchemy** | Zero setup, file-based persistence |
| Visualization | **Plotly + streamlit-agraph** | Interactive gauges, charts, and network graphs |
| Graph Engine | **NetworkX** | Blast radius dependency traversal |

---

## Documentation

| Document | Description |
|----------|-------------|
| `docs/DeployWhisper_PRD.docx` | Product Requirements Document — functional requirements, user stories, success metrics, release plan |
| `docs/DeployWhisper_Architecture.docx` | Technical Architecture — complete tech stack, system design, AI Skills engine, data flow, database schema, deployment guide |

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-parser`)
3. Add tests in `tests/`
4. Run the test suite: `pytest`
5. Run the linter: `ruff check .`
6. Submit a pull request

To add a new IaC parser, see `docs/DeployWhisper_Architecture.docx`, Section 9.1.
To add a new AI skill, see `skills/custom/` and the Custom AI Skills section above.

---

## License

MIT License. See `LICENSE` for details.

---

<p align="center">
  Built with Python · Powered by AI Skills · Made for DevOps teams who ship safely
</p>
